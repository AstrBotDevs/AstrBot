from __future__ import annotations

import asyncio
import shutil
import traceback
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiofiles

from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.provider.provider import EmbeddingProvider, RerankProvider
from astrbot.core.utils.astrbot_path import get_astrbot_system_tmp_path
from astrbot.dashboard.schemas import KnowledgeBaseRequest
from astrbot.dashboard.services.task_progress import (
    task_progress_response,
    update_task_progress,
)
from astrbot.dashboard.utils import generate_tsne_visualization
from astrbot.dashboard.validation import (
    integer_field,
    is_json_object,
    is_string_list,
    string_field,
)

if TYPE_CHECKING:
    from astrbot.core.knowledge_base.kb_helper import KBHelper
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
    from astrbot.core.knowledge_base.models import KnowledgeBase


class KnowledgeBaseServiceError(Exception):
    pass


async def _require_kb(
    kb_manager: KnowledgeBaseManager,
    kb_id: str,
    *,
    error_type: type[Exception] = KnowledgeBaseServiceError,
) -> KBHelper:
    """Resolve an existing knowledge base with the adapter's error contract."""
    kb_helper = await kb_manager.get_kb(kb_id)
    if not kb_helper:
        raise error_type("知识库不存在")
    return kb_helper


async def _serialize_kb(
    kb_manager: KnowledgeBaseManager, kb: KnowledgeBase
) -> dict[str, Any]:
    """Include initialization failures in a knowledge base list item."""
    kb_dict = kb.model_dump()
    kb_helper = await kb_manager.get_kb(kb.kb_id)
    if kb_helper and kb_helper.init_error:
        kb_dict["init_error"] = kb_helper.init_error
    return kb_dict


def _upload_options(form_data: Mapping[str, Any]) -> dict[str, int]:
    """Parse multipart embedding options in their established validation order."""
    defaults = {
        "chunk_size": 512,
        "chunk_overlap": 50,
        "batch_size": 32,
        "tasks_limit": 3,
        "max_retries": 3,
    }
    return {key: int(form_data.get(key, default)) for key, default in defaults.items()}


def _update_upload_progress(
    progress_by_task: dict[str, dict[str, Any]],
    task_id: str,
    *,
    status: str | None = None,
    file_index: int | None = None,
    file_name: str | None = None,
    stage: str | None = None,
    current: int | None = None,
    total: int | None = None,
) -> None:
    """Apply shared job progress and knowledge base file metadata together."""
    if task_id not in progress_by_task:
        return
    update_task_progress(progress_by_task, task_id, status=status)
    progress = progress_by_task[task_id]
    if file_index is not None:
        progress["file_index"] = file_index
    if file_name is not None:
        progress["file_name"] = file_name
    update_task_progress(
        progress_by_task,
        task_id,
        stage=stage,
        current=current,
        total=total,
    )


class KnowledgeBaseService:
    def __init__(self, core_lifecycle: AstrBotCoreLifecycle) -> None:
        self.core_lifecycle = core_lifecycle
        self.upload_progress: dict[str, dict[str, Any]] = {}
        self.upload_tasks: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _payload(data: object) -> dict[str, object]:
        return data if is_json_object(data) else {}

    @staticmethod
    def _canonical_kb_payload(data: object) -> dict[str, Any]:
        """Normalize knowledge base create/update payloads.

        Uses KnowledgeBaseRequest to handle the legacy ``name`` →
        ``kb_name`` migration while preserving operational fields
        like ``kb_id``.
        """
        raw = KnowledgeBaseService._payload(data)
        canonical = KnowledgeBaseRequest.model_validate(raw).canonical_payload()
        raw.update(canonical)
        return raw

    def get_kb_manager(self):
        return self.core_lifecycle.kb_manager

    @staticmethod
    def _required_identifier(value: object, field: str) -> str:
        """Validate service identifiers without changing their error messages."""
        if not isinstance(value, str) or not value:
            raise KnowledgeBaseServiceError(f"缺少参数 {field}")
        return value

    async def _prepare_upload_task(self, kb_id: str) -> tuple[str, KBHelper]:
        """Resolve the target before registering a pending background task."""
        kb_helper = await _require_kb(self.get_kb_manager(), kb_id)
        task_id = str(uuid.uuid4())
        self.init_task(task_id, status="pending")
        return task_id, kb_helper

    def init_task(self, task_id: str, status: str = "pending") -> None:
        self.upload_tasks[task_id] = {
            "status": status,
            "result": None,
            "error": None,
        }

    def set_task_result(
        self,
        task_id: str,
        status: str,
        result: Any = None,
        error: str | None = None,
    ) -> None:
        self.upload_tasks[task_id] = {
            "status": status,
            "result": result,
            "error": error,
        }
        if task_id in self.upload_progress:
            self.upload_progress[task_id]["status"] = status

    def update_progress(
        self,
        task_id: str,
        *,
        status: str | None = None,
        file_index: int | None = None,
        file_name: str | None = None,
        stage: str | None = None,
        current: int | None = None,
        total: int | None = None,
    ) -> None:
        _update_upload_progress(
            self.upload_progress,
            task_id,
            status=status,
            file_index=file_index,
            file_name=file_name,
            stage=stage,
            current=current,
            total=total,
        )

    def make_progress_callback(self, task_id: str, file_idx: int, file_name: str):
        async def _callback(stage: str, current: int, total: int) -> None:
            self.update_progress(
                task_id,
                status="processing",
                file_index=file_idx,
                file_name=file_name,
                stage=stage,
                current=current,
                total=total,
            )

        return _callback

    @staticmethod
    def format_failed_doc_error(file_name: str, error: Exception) -> str:
        message = str(error).strip() or "上传失败：发生未知错误。"
        if message.startswith(file_name):
            return message
        return f"{file_name}: {message}"

    @staticmethod
    def _cleanup_staging_dir(staging_dir: Path) -> None:
        """Remove a knowledge base upload staging directory.

        Args:
            staging_dir: Task-specific system temporary directory to remove.
        """
        try:
            shutil.rmtree(staging_dir)
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.warning(f"Failed to clean upload staging directory: {exc}")

    async def background_upload_task(
        self,
        task_id: str,
        kb_helper,
        files_to_upload: list[dict[str, Any]],
        staging_dir: Path,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int,
        tasks_limit: int,
        max_retries: int,
    ) -> None:
        """Process staged knowledge base files one at a time.

        Args:
            task_id: Identifier used to report upload progress and results.
            kb_helper: Knowledge base helper that parses and stores documents.
            files_to_upload: Metadata and temporary paths for staged files.
            staging_dir: Task-specific system temporary directory.
            chunk_size: Maximum size of each generated document chunk.
            chunk_overlap: Number of overlapping characters between chunks.
            batch_size: Number of chunks sent in each embedding batch.
            tasks_limit: Maximum number of concurrent embedding tasks.
            max_retries: Maximum retries for embedding operations.
        """
        try:
            self.init_task(task_id, status="processing")
            self.upload_progress[task_id] = {
                "status": "processing",
                "file_index": 0,
                "file_total": len(files_to_upload),
                "stage": "waiting",
                "current": 0,
                "total": 100,
            }

            uploaded_docs = []
            failed_docs = []

            for file_idx, file_info in enumerate(files_to_upload):
                file_content = None
                try:
                    temp_file_path = Path(file_info["temp_file_path"])
                    async with aiofiles.open(temp_file_path, "rb") as file_obj:
                        file_content = await file_obj.read()
                    self.update_progress(
                        task_id,
                        status="processing",
                        file_index=file_idx,
                        file_name=file_info["file_name"],
                        stage="parsing",
                        current=0,
                        total=100,
                    )
                    progress_callback = self.make_progress_callback(
                        task_id, file_idx, file_info["file_name"]
                    )
                    doc = await kb_helper.upload_document(
                        file_name=file_info["file_name"],
                        file_content=file_content,
                        file_type=file_info["file_type"],
                        chunk_size=chunk_size,
                        chunk_overlap=chunk_overlap,
                        batch_size=batch_size,
                        tasks_limit=tasks_limit,
                        max_retries=max_retries,
                        progress_callback=progress_callback,
                    )
                    uploaded_docs.append(doc.model_dump())
                except Exception as exc:
                    logger.error(f"上传文档 {file_info['file_name']} 失败: {exc}")
                    failed_docs.append(
                        {
                            "file_name": file_info["file_name"],
                            "error": self.format_failed_doc_error(
                                file_info["file_name"], exc
                            ),
                        },
                    )
                finally:
                    # Release the current file before reading the next one.
                    file_content = None
                    Path(file_info["temp_file_path"]).unlink(missing_ok=True)

            self.set_task_result(
                task_id,
                "completed",
                result={
                    "task_id": task_id,
                    "uploaded": uploaded_docs,
                    "failed": failed_docs,
                    "total": len(files_to_upload),
                    "success_count": len(uploaded_docs),
                    "failed_count": len(failed_docs),
                },
            )
        except Exception as exc:
            logger.error(f"后台上传任务 {task_id} 失败: {exc}")
            logger.error(traceback.format_exc())
            self.set_task_result(task_id, "failed", error=str(exc))
        finally:
            self._cleanup_staging_dir(staging_dir)

    async def background_import_task(
        self,
        task_id: str,
        kb_helper,
        documents: list[dict[str, Any]],
        batch_size: int,
        tasks_limit: int,
        max_retries: int,
    ) -> None:
        try:
            self.init_task(task_id, status="processing")
            self.upload_progress[task_id] = {
                "status": "processing",
                "file_index": 0,
                "file_total": len(documents),
                "stage": "waiting",
                "current": 0,
                "total": 100,
            }

            uploaded_docs = []
            failed_docs = []

            for file_idx, doc_info in enumerate(documents):
                file_name = doc_info.get("file_name", f"imported_doc_{file_idx}")
                chunks = doc_info.get("chunks", [])

                try:
                    self.update_progress(
                        task_id,
                        status="processing",
                        file_index=file_idx,
                        file_name=file_name,
                        stage="importing",
                        current=0,
                        total=100,
                    )
                    progress_callback = self.make_progress_callback(
                        task_id, file_idx, file_name
                    )
                    doc = await kb_helper.upload_document(
                        file_name=file_name,
                        file_content=None,
                        file_type=doc_info.get("file_type")
                        or (
                            file_name.rsplit(".", 1)[-1].lower()
                            if "." in file_name
                            else "txt"
                        ),
                        batch_size=batch_size,
                        tasks_limit=tasks_limit,
                        max_retries=max_retries,
                        progress_callback=progress_callback,
                        pre_chunked_text=chunks,
                    )
                    uploaded_docs.append(doc.model_dump())
                except Exception as exc:
                    logger.error(f"导入文档 {file_name} 失败: {exc}")
                    failed_docs.append(
                        {
                            "file_name": file_name,
                            "error": self.format_failed_doc_error(file_name, exc),
                        },
                    )

            self.set_task_result(
                task_id,
                "completed",
                result={
                    "task_id": task_id,
                    "uploaded": uploaded_docs,
                    "failed": failed_docs,
                    "total": len(documents),
                    "success_count": len(uploaded_docs),
                    "failed_count": len(failed_docs),
                },
            )
        except Exception as exc:
            logger.error(f"后台导入任务 {task_id} 失败: {exc}")
            logger.error(traceback.format_exc())
            self.set_task_result(task_id, "failed", error=str(exc))

    async def list_kbs(self, *, page: int, page_size: int) -> dict[str, Any]:
        kb_manager = self.get_kb_manager()
        kbs = await kb_manager.list_kbs()
        total = len(kbs)

        # Clamp page and page_size to at least 1 before calculating offsets/slices.
        page = max(page, 1)
        page_size = max(page_size, 1)
        start = (page - 1) * page_size
        end = start + page_size
        paged_kbs = kbs[start:end]

        kb_list = [await _serialize_kb(kb_manager, kb) for kb in paged_kbs]

        return {"items": kb_list, "page": page, "page_size": page_size, "total": total}

    async def list_kbs_from_dashboard_query(self, *, page, page_size) -> dict[str, Any]:
        return await self.list_kbs(
            page=self._to_int(page, 1),
            page_size=self._to_int(page_size, 20),
        )

    async def create_kb(self, data: object) -> tuple[dict[str, Any], str]:
        kb_manager = self.get_kb_manager()
        payload = self._canonical_kb_payload(data)
        kb_name = payload.get("kb_name")
        if not kb_name:
            raise KnowledgeBaseServiceError("知识库名称不能为空")

        embedding_provider_id = payload.get("embedding_provider_id")
        rerank_provider_id = payload.get("rerank_provider_id")

        if not embedding_provider_id:
            raise KnowledgeBaseServiceError("缺少参数 embedding_provider_id")
        provider = await kb_manager.provider_manager.get_provider_by_id(
            embedding_provider_id,
        )
        if not provider or not isinstance(provider, EmbeddingProvider):
            raise KnowledgeBaseServiceError(
                f"嵌入模型不存在或类型错误({type(provider)})"
            )
        try:
            vec = await provider.get_embedding("astrbot")
            if len(vec) != provider.get_dim():
                raise ValueError(
                    f"嵌入向量维度不匹配，实际是 {len(vec)}，然而配置是 {provider.get_dim()}",
                )
        except Exception as exc:
            raise KnowledgeBaseServiceError(f"测试嵌入模型失败: {exc!s}") from exc

        if rerank_provider_id:
            rerank_provider = await kb_manager.provider_manager.get_provider_by_id(
                rerank_provider_id,
            )
            if not isinstance(rerank_provider, RerankProvider):
                raise KnowledgeBaseServiceError("重排序模型不存在")
            try:
                result = await rerank_provider.rerank(
                    query="astrbot",
                    documents=["astrbot knowledge base"],
                )
                if not result:
                    raise ValueError("重排序模型返回结果异常")
            except Exception as exc:
                raise KnowledgeBaseServiceError(
                    f"测试重排序模型失败: {exc!s}，请检查平台日志输出。"
                ) from exc

        kb_helper = await kb_manager.create_kb(
            kb_name=kb_name,
            description=payload.get("description"),
            emoji=payload.get("emoji"),
            embedding_provider_id=embedding_provider_id,
            rerank_provider_id=rerank_provider_id,
            chunk_size=payload.get("chunk_size"),
            chunk_overlap=payload.get("chunk_overlap"),
            top_k_dense=payload.get("top_k_dense"),
            top_k_sparse=payload.get("top_k_sparse"),
            top_m_final=payload.get("top_m_final"),
        )
        return kb_helper.kb.model_dump(), "创建知识库成功"

    async def get_kb(self, kb_id: str | None) -> dict[str, Any]:
        kb_id = self._required_identifier(kb_id, "kb_id")
        kb_helper = await _require_kb(self.get_kb_manager(), kb_id)
        return kb_helper.kb.model_dump()

    async def get_kb_from_dashboard_query(self, kb_id: str | None) -> dict[str, Any]:
        return await self.get_kb(kb_id)

    async def update_kb(self, data: object) -> tuple[dict[str, Any], str]:
        payload = self._canonical_kb_payload(data)
        kb_id = payload.get("kb_id")
        kb_id = self._required_identifier(kb_id, "kb_id")

        update_keys = [
            "kb_name",
            "description",
            "emoji",
            "embedding_provider_id",
            "rerank_provider_id",
            "chunk_size",
            "chunk_overlap",
            "top_k_dense",
            "top_k_sparse",
            "top_m_final",
        ]
        provided_updates = {key: payload[key] for key in update_keys if key in payload}
        if not provided_updates:
            raise KnowledgeBaseServiceError("至少需要提供一个更新字段")

        current_kb = await _require_kb(self.get_kb_manager(), kb_id)
        current = current_kb.kb
        update_data = {key: getattr(current, key, None) for key in update_keys}
        update_data.update(provided_updates)

        kb_name = string_field(update_data, "kb_name")
        update_data.pop("kb_name", None)
        kb_helper = await self.get_kb_manager().update_kb(
            kb_id=kb_id,
            kb_name=current.kb_name if kb_name is None else kb_name,
            **update_data,
        )
        if not kb_helper:
            raise KnowledgeBaseServiceError("知识库不存在")
        return kb_helper.kb.model_dump(), "更新知识库成功"

    async def delete_kb(self, data: object) -> tuple[None, str]:
        payload = self._payload(data)
        kb_id = payload.get("kb_id")
        kb_id = self._required_identifier(kb_id, "kb_id")
        success = await self.get_kb_manager().delete_kb(kb_id)
        if not success:
            raise KnowledgeBaseServiceError("知识库不存在")
        return None, "删除知识库成功"

    async def get_kb_stats(self, kb_id: str | None) -> dict[str, Any]:
        kb_id = self._required_identifier(kb_id, "kb_id")
        kb_helper = await _require_kb(self.get_kb_manager(), kb_id)
        kb = kb_helper.kb
        return {
            "kb_id": kb.kb_id,
            "kb_name": kb.kb_name,
            "doc_count": kb.doc_count,
            "chunk_count": kb.chunk_count,
            "created_at": kb.created_at.isoformat(),
            "updated_at": kb.updated_at.isoformat(),
        }

    async def get_kb_stats_from_dashboard_query(
        self,
        kb_id: str | None,
    ) -> dict[str, Any]:
        return await self.get_kb_stats(kb_id)

    async def list_documents(
        self,
        *,
        kb_id: str | None,
        page: int,
        page_size: int,
        search: str | None = None,
    ) -> dict[str, Any]:
        kb_id = self._required_identifier(kb_id, "kb_id")
        kb_helper = await _require_kb(self.get_kb_manager(), kb_id)

        if search is not None:
            search = search.strip()
            if not search:
                search = None

        page = max(page, 1)
        page_size = max(page_size, 1)
        offset = (page - 1) * page_size
        doc_list = await kb_helper.list_documents(
            offset=offset,
            limit=page_size,
            search=search,
        )
        total = await kb_helper.count_documents(search=search)
        return {
            "items": [doc.model_dump() for doc in doc_list],
            "page": page,
            "page_size": page_size,
            "total": total,
        }

    async def list_documents_from_dashboard_query(
        self,
        *,
        kb_id: str | None,
        page,
        page_size,
        search: str | None = None,
    ) -> dict[str, Any]:
        return await self.list_documents(
            kb_id=kb_id,
            page=self._to_int(page, 1),
            page_size=self._to_int(page_size, 100),
            search=search,
        )

    async def upload_document(
        self,
        *,
        content_type: str | None,
        form_data,
        files,
    ) -> dict[str, Any]:
        if content_type and "multipart/form-data" not in content_type:
            raise KnowledgeBaseServiceError("Content-Type 须为 multipart/form-data")

        kb_id = form_data.get("kb_id")
        upload_options = _upload_options(form_data)
        kb_id = self._required_identifier(kb_id, "kb_id")

        file_list = []
        for key in files.keys():
            if key == "file" or key.startswith("file") or key == "files[]":
                file_list.extend(files.getlist(key))
        if not file_list:
            raise KnowledgeBaseServiceError("缺少文件")

        task_id = str(uuid.uuid4())
        system_temp_root = Path(get_astrbot_system_tmp_path())
        system_temp_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        staging_dir = system_temp_root / f"kb_upload_{task_id}"
        staging_dir.mkdir(mode=0o700)
        files_to_upload = []
        try:
            for file in file_list:
                file_name = Path(
                    str(file.filename or "document").replace("\\", "/")
                ).name
                if file_name in {"", ".", ".."}:
                    file_name = "document"
                temp_file_path = staging_dir / f"{uuid.uuid4()}_{file_name}"
                file_type = (
                    file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
                )
                files_to_upload.append(
                    {
                        "file_name": file_name,
                        "temp_file_path": temp_file_path,
                        "file_type": file_type,
                    },
                )
                await file.save(temp_file_path)
        except Exception:
            self._cleanup_staging_dir(staging_dir)
            raise

        try:
            kb_helper = await _require_kb(self.get_kb_manager(), kb_id)
        except Exception:
            self._cleanup_staging_dir(staging_dir)
            raise

        try:
            self.init_task(task_id, status="pending")
            asyncio.create_task(
                self.background_upload_task(
                    task_id=task_id,
                    kb_helper=kb_helper,
                    files_to_upload=files_to_upload,
                    staging_dir=staging_dir,
                    **upload_options,
                ),
            )
        except Exception:
            self._cleanup_staging_dir(staging_dir)
            raise
        return {
            "task_id": task_id,
            "file_count": len(files_to_upload),
            "message": "task created, processing in background",
        }

    @staticmethod
    def validate_import_request(data: dict[str, Any]):
        kb_id = data.get("kb_id")
        kb_id = KnowledgeBaseService._required_identifier(kb_id, "kb_id")

        documents = data.get("documents")
        if not documents or not isinstance(documents, list):
            raise KnowledgeBaseServiceError("缺少参数 documents 或格式错误")

        for doc in documents:
            if (
                not isinstance(doc, dict)
                or "file_name" not in doc
                or "chunks" not in doc
            ):
                raise KnowledgeBaseServiceError(
                    "文档格式错误，必须包含 file_name 和 chunks"
                )
            if not isinstance(doc["chunks"], list):
                raise KnowledgeBaseServiceError("chunks 必须是列表")
            if not all(
                isinstance(chunk, str) and chunk.strip() for chunk in doc["chunks"]
            ):
                raise KnowledgeBaseServiceError("chunks 必须是非空字符串列表")

        return (
            kb_id,
            documents,
            data.get("batch_size", 32),
            data.get("tasks_limit", 3),
            data.get("max_retries", 3),
        )

    async def import_documents(self, data: object) -> dict[str, Any]:
        payload = self._payload(data)
        kb_id, documents, batch_size, tasks_limit, max_retries = (
            self.validate_import_request(payload)
        )

        task_id, kb_helper = await self._prepare_upload_task(kb_id)
        asyncio.create_task(
            self.background_import_task(
                task_id=task_id,
                kb_helper=kb_helper,
                documents=documents,
                batch_size=batch_size,
                tasks_limit=tasks_limit,
                max_retries=max_retries,
            ),
        )
        return {
            "task_id": task_id,
            "doc_count": len(documents),
            "message": "import task created, processing in background",
        }

    def get_upload_progress(self, task_id: str | None) -> dict[str, Any]:
        if not task_id:
            raise KnowledgeBaseServiceError("缺少参数 task_id")
        if task_id not in self.upload_tasks:
            raise KnowledgeBaseServiceError("找不到该任务")

        return task_progress_response(
            task_id, self.upload_tasks[task_id], self.upload_progress
        )

    def get_upload_progress_from_dashboard_query(
        self,
        task_id: str | None,
    ) -> dict[str, Any]:
        return self.get_upload_progress(task_id)

    async def get_document(
        self,
        *,
        kb_id: str | None,
        doc_id: str | None,
    ) -> dict[str, Any]:
        kb_id = self._required_identifier(kb_id, "kb_id")
        doc_id = self._required_identifier(doc_id, "doc_id")
        kb_helper = await _require_kb(self.get_kb_manager(), kb_id)
        doc = await kb_helper.get_document(doc_id)
        if not doc:
            raise KnowledgeBaseServiceError("文档不存在")
        return doc.model_dump()

    async def get_document_from_dashboard_query(
        self,
        *,
        kb_id: str | None,
        doc_id: str | None,
    ) -> dict[str, Any]:
        return await self.get_document(kb_id=kb_id, doc_id=doc_id)

    async def delete_document(self, data: object) -> tuple[None, str]:
        payload = self._payload(data)
        kb_id = payload.get("kb_id")
        doc_id = payload.get("doc_id")
        kb_id = self._required_identifier(kb_id, "kb_id")
        doc_id = self._required_identifier(doc_id, "doc_id")
        kb_helper = await _require_kb(self.get_kb_manager(), kb_id)
        await kb_helper.delete_document(doc_id)
        return None, "删除文档成功"

    async def delete_chunk(self, data: object) -> tuple[None, str]:
        payload = self._payload(data)
        kb_id = payload.get("kb_id")
        chunk_id = payload.get("chunk_id")
        doc_id = payload.get("doc_id")
        kb_id = self._required_identifier(kb_id, "kb_id")
        chunk_id = self._required_identifier(chunk_id, "chunk_id")
        doc_id = self._required_identifier(doc_id, "doc_id")
        kb_helper = await _require_kb(self.get_kb_manager(), kb_id)
        await kb_helper.delete_chunk(chunk_id, doc_id)
        return None, "删除文本块成功"

    async def list_chunks(
        self,
        *,
        kb_id: str | None,
        doc_id: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        kb_id = self._required_identifier(kb_id, "kb_id")
        doc_id = self._required_identifier(doc_id, "doc_id")
        kb_helper = await _require_kb(self.get_kb_manager(), kb_id)

        offset = (page - 1) * page_size
        return {
            "items": await kb_helper.get_chunks_by_doc_id(
                doc_id=doc_id,
                offset=offset,
                limit=page_size,
            ),
            "page": page,
            "page_size": page_size,
            "total": await kb_helper.get_chunk_count_by_doc_id(doc_id),
        }

    async def list_chunks_from_dashboard_query(
        self,
        *,
        kb_id: str | None,
        doc_id: str | None,
        page,
        page_size,
    ) -> dict[str, Any]:
        return await self.list_chunks(
            kb_id=kb_id,
            doc_id=doc_id,
            page=self._to_int(page, 1),
            page_size=self._to_int(page_size, 100),
        )

    async def retrieve(self, data: object) -> dict[str, Any]:
        payload = self._payload(data)
        query = payload.get("query")
        kb_names = payload.get("kb_names")
        debug = payload.get("debug", False)

        if not isinstance(query, str) or not query:
            raise KnowledgeBaseServiceError("缺少参数 query")
        kb_manager = self.get_kb_manager()
        if not kb_names or not is_string_list(kb_names):
            raise KnowledgeBaseServiceError("缺少参数 kb_names 或格式错误")

        top_k = integer_field(payload, "top_k", 5, error_type=KnowledgeBaseServiceError)
        results = await kb_manager.retrieve(
            query=query,
            kb_names=kb_names,
            top_m_final=top_k,
        )
        result_list = results["results"] if results else []
        response_data = {
            "results": result_list,
            "total": len(result_list),
            "query": query,
        }

        if debug:
            try:
                img_base64 = await generate_tsne_visualization(
                    query,
                    kb_names,
                    kb_manager,
                )
                if img_base64:
                    response_data["visualization"] = img_base64
            except Exception as exc:
                logger.error(f"生成 t-SNE 可视化失败: {exc}")
                logger.error(traceback.format_exc())
                response_data["visualization_error"] = str(exc)

        return response_data

    async def upload_document_from_url(self, data: object) -> dict[str, Any]:
        payload = self._payload(data)
        kb_id = payload.get("kb_id")
        kb_id = self._required_identifier(kb_id, "kb_id")
        url = payload.get("url")
        url = self._required_identifier(url, "url")

        task_id, kb_helper = await self._prepare_upload_task(kb_id)
        asyncio.create_task(
            self.background_upload_from_url_task(
                task_id=task_id,
                kb_helper=kb_helper,
                url=url,
                chunk_size=integer_field(payload, "chunk_size", 512),
                chunk_overlap=integer_field(payload, "chunk_overlap", 50),
                batch_size=integer_field(payload, "batch_size", 32),
                tasks_limit=integer_field(payload, "tasks_limit", 3),
                max_retries=integer_field(payload, "max_retries", 3),
                enable_cleaning=bool(payload.get("enable_cleaning", False)),
                cleaning_provider_id=string_field(payload, "cleaning_provider_id"),
            ),
        )
        return {
            "task_id": task_id,
            "url": url,
            "message": "URL upload task created, processing in background",
        }

    async def background_upload_from_url_task(
        self,
        task_id: str,
        kb_helper,
        url: str,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int,
        tasks_limit: int,
        max_retries: int,
        enable_cleaning: bool,
        cleaning_provider_id: str | None,
    ) -> None:
        try:
            self.init_task(task_id, status="processing")
            self.upload_progress[task_id] = {
                "status": "processing",
                "file_index": 0,
                "file_total": 1,
                "file_name": f"URL: {url}",
                "stage": "extracting",
                "current": 0,
                "total": 100,
            }
            progress_callback = self.make_progress_callback(task_id, 0, f"URL: {url}")
            doc = await kb_helper.upload_from_url(
                url=url,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                batch_size=batch_size,
                tasks_limit=tasks_limit,
                max_retries=max_retries,
                progress_callback=progress_callback,
                enable_cleaning=enable_cleaning,
                cleaning_provider_id=cleaning_provider_id,
            )
            self.set_task_result(
                task_id,
                "completed",
                result={
                    "task_id": task_id,
                    "uploaded": [doc.model_dump()],
                    "failed": [],
                    "total": 1,
                    "success_count": 1,
                    "failed_count": 0,
                },
            )
        except Exception as exc:
            logger.error(f"后台上传URL任务 {task_id} 失败: {exc}")
            logger.error(traceback.format_exc())
            self.set_task_result(task_id, "failed", error=str(exc))

    @staticmethod
    def _to_int(value, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default


__all__ = ["KnowledgeBaseService", "KnowledgeBaseServiceError"]
