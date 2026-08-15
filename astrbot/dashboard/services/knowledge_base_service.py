import asyncio
import shutil
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import aiofiles
from starlette.datastructures import UploadFile

from astrbot import logger
from astrbot.core.exceptions import KnowledgeBaseUploadError
from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
from astrbot.core.provider.provider import EmbeddingProvider, RerankProvider
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.error_redaction import safe_error
from astrbot.core.utils.task_utils import create_tracked_task
from astrbot.dashboard.schemas import KnowledgeBaseRequest
from astrbot.dashboard.upload_utils import save_upload_to_path
from astrbot.dashboard.utils import generate_tsne_visualization


class KnowledgeBaseServiceError(Exception):
    pass


_BACKGROUND_TASK_ERROR = "Knowledge base task failed"
_DOCUMENT_UPLOAD_ERROR = "Document upload failed"
_KB_INITIALIZATION_ERROR = "Knowledge base initialization failed"


class KnowledgeBaseService:
    def __init__(self, knowledge_base_manager: KnowledgeBaseManager) -> None:
        self.knowledge_base_manager = knowledge_base_manager
        self.upload_progress: dict[str, dict[str, Any]] = {}
        self.upload_tasks: dict[str, dict[str, Any]] = {}
        self._background_tasks: set[asyncio.Task] = set()

    @staticmethod
    def _payload(data: object) -> dict[str, Any]:
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _canonical_kb_payload(data: object) -> dict[str, Any]:
        """Normalize knowledge base create/update payloads.

        Uses KnowledgeBaseRequest to handle the legacy ``name`` →
        ``kb_name`` migration while preserving operational fields
        like ``kb_id``.
        """
        raw = KnowledgeBaseService._payload(data)
        canonical = KnowledgeBaseRequest(**raw).canonical_payload()
        raw.update(canonical)
        return raw

    def get_kb_manager(self):
        return self.knowledge_base_manager

    def _get_background_tasks(self) -> set[asyncio.Task]:
        task_set = getattr(self, "_background_tasks", None)
        if task_set is None:
            task_set = set()
            self._background_tasks = task_set
        return task_set

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
        if task_id not in self.upload_progress:
            return
        progress = self.upload_progress[task_id]
        if status is not None:
            progress["status"] = status
        if file_index is not None:
            progress["file_index"] = file_index
        if file_name is not None:
            progress["file_name"] = file_name
        if stage is not None:
            progress["stage"] = stage
        if current is not None:
            progress["current"] = current
        if total is not None:
            progress["total"] = total

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
        if isinstance(error, KnowledgeBaseUploadError):
            message = error.user_message.strip()
            if message:
                return (
                    message
                    if message.startswith(file_name)
                    else f"{file_name}: {message}"
                )
        message = _DOCUMENT_UPLOAD_ERROR
        return f"{file_name}: {message}"

    @staticmethod
    def _cleanup_upload_staging_dir(staging_dir: Path) -> None:
        """Remove a knowledge base upload staging directory.

        Args:
            staging_dir: Task-specific temporary directory to remove.
        """
        try:
            shutil.rmtree(staging_dir)
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.warning(
                "Failed to clean knowledge base upload staging directory %s: %s",
                staging_dir,
                safe_error("", exc),
            )

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
                    logger.error(
                        "上传文档 %s 失败: %s",
                        file_info["file_name"],
                        safe_error("", exc),
                    )
                    failed_docs.append(
                        {
                            "file_name": file_info["file_name"],
                            "error": self.format_failed_doc_error(
                                file_info["file_name"], exc
                            ),
                        },
                    )
                finally:
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
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "后台上传任务 %s 失败: %s",
                task_id,
                safe_error("", exc),
            )
            self.set_task_result(task_id, "failed", error=_BACKGROUND_TASK_ERROR)
        finally:
            self._cleanup_upload_staging_dir(staging_dir)

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
                    logger.error(
                        "导入文档 %s 失败: %s",
                        file_name,
                        safe_error("", exc),
                    )
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
            logger.error(
                "后台导入任务 %s 失败: %s",
                task_id,
                safe_error("", exc),
            )
            self.set_task_result(task_id, "failed", error=_BACKGROUND_TASK_ERROR)

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

        kb_list = []
        for kb in paged_kbs:
            kb_dict = kb.model_dump()
            kb_helper = await kb_manager.get_kb(kb.kb_id)
            if kb_helper and kb_helper.init_error:
                kb_dict["init_error"] = _KB_INITIALIZATION_ERROR
            kb_list.append(kb_dict)

        return {"items": kb_list, "page": page, "page_size": page_size, "total": total}

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
            logger.error("知识库嵌入模型验证失败: %s", safe_error("", exc))
            raise KnowledgeBaseServiceError("测试嵌入模型失败") from exc

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
                logger.error("知识库重排序模型验证失败: %s", safe_error("", exc))
                raise KnowledgeBaseServiceError("测试重排序模型失败") from exc

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
        if not kb_id:
            raise KnowledgeBaseServiceError("缺少参数 kb_id")
        kb_helper = await self.get_kb_manager().get_kb(kb_id)
        if not kb_helper:
            raise KnowledgeBaseServiceError("知识库不存在")
        return kb_helper.kb.model_dump()

    async def update_kb(self, data: object) -> tuple[dict[str, Any], str]:
        payload = self._canonical_kb_payload(data)
        kb_id = payload.get("kb_id")
        if not kb_id:
            raise KnowledgeBaseServiceError("缺少参数 kb_id")

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

        current_kb = await self.get_kb_manager().get_kb(kb_id)
        if not current_kb:
            raise KnowledgeBaseServiceError("知识库不存在")
        current = current_kb.kb
        kb_helper = await self.get_kb_manager().update_kb(
            kb_id=kb_id,
            kb_name=provided_updates.get("kb_name", current.kb_name),
            description=provided_updates.get("description", current.description),
            emoji=provided_updates.get("emoji", current.emoji),
            embedding_provider_id=provided_updates.get(
                "embedding_provider_id",
                current.embedding_provider_id,
            ),
            rerank_provider_id=provided_updates.get(
                "rerank_provider_id",
                current.rerank_provider_id,
            ),
            chunk_size=provided_updates.get("chunk_size", current.chunk_size),
            chunk_overlap=provided_updates.get(
                "chunk_overlap",
                current.chunk_overlap,
            ),
            top_k_dense=provided_updates.get("top_k_dense", current.top_k_dense),
            top_k_sparse=provided_updates.get("top_k_sparse", current.top_k_sparse),
            top_m_final=provided_updates.get("top_m_final", current.top_m_final),
        )
        if not kb_helper:
            raise KnowledgeBaseServiceError("知识库不存在")
        return kb_helper.kb.model_dump(), "更新知识库成功"

    async def delete_kb(self, data: object) -> tuple[None, str]:
        payload = self._payload(data)
        kb_id = payload.get("kb_id")
        if not kb_id:
            raise KnowledgeBaseServiceError("缺少参数 kb_id")
        success = await self.get_kb_manager().delete_kb(kb_id)
        if not success:
            raise KnowledgeBaseServiceError("知识库不存在")
        return None, "删除知识库成功"

    async def get_kb_stats(self, kb_id: str | None) -> dict[str, Any]:
        if not kb_id:
            raise KnowledgeBaseServiceError("缺少参数 kb_id")
        kb_helper = await self.get_kb_manager().get_kb(kb_id)
        if not kb_helper:
            raise KnowledgeBaseServiceError("知识库不存在")
        kb = kb_helper.kb
        return {
            "kb_id": kb.kb_id,
            "kb_name": kb.kb_name,
            "doc_count": kb.doc_count,
            "chunk_count": kb.chunk_count,
            "created_at": kb.created_at.isoformat(),
            "updated_at": kb.updated_at.isoformat(),
        }

    async def list_documents(
        self,
        *,
        kb_id: str | None,
        page: int,
        page_size: int,
        search: str | None = None,
    ) -> dict[str, Any]:
        if not kb_id:
            raise KnowledgeBaseServiceError("缺少参数 kb_id")
        kb_helper = await self.get_kb_manager().get_kb(kb_id)
        if not kb_helper:
            raise KnowledgeBaseServiceError("知识库不存在")

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

    async def upload_document(
        self,
        *,
        content_type: str | None,
        form_data,
        files: Sequence[UploadFile],
    ) -> dict[str, Any]:
        if content_type and "multipart/form-data" not in content_type:
            raise KnowledgeBaseServiceError("Content-Type 须为 multipart/form-data")

        kb_id = form_data.get("kb_id")
        chunk_size = int(form_data.get("chunk_size", 512))
        chunk_overlap = int(form_data.get("chunk_overlap", 50))
        batch_size = int(form_data.get("batch_size", 32))
        tasks_limit = int(form_data.get("tasks_limit", 3))
        max_retries = int(form_data.get("max_retries", 3))
        if not kb_id:
            raise KnowledgeBaseServiceError("缺少参数 kb_id")

        if not files:
            raise KnowledgeBaseServiceError("缺少文件")

        task_id = str(uuid.uuid4())
        temp_root = Path(get_astrbot_temp_path())
        temp_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        staging_dir = temp_root / f"kb_upload_{task_id}"
        staging_dir.mkdir(mode=0o700)
        files_to_upload = []
        try:
            for file in files:
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
                await save_upload_to_path(file, temp_file_path)
        except Exception:
            self._cleanup_upload_staging_dir(staging_dir)
            raise

        try:
            kb_helper = await self.get_kb_manager().get_kb(kb_id)
            if not kb_helper:
                raise KnowledgeBaseServiceError("知识库不存在")
        except Exception:
            self._cleanup_upload_staging_dir(staging_dir)
            raise

        try:
            self.init_task(task_id, status="pending")
            create_tracked_task(
                self._get_background_tasks(),
                self.background_upload_task(
                    task_id=task_id,
                    kb_helper=kb_helper,
                    files_to_upload=files_to_upload,
                    staging_dir=staging_dir,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                    batch_size=batch_size,
                    tasks_limit=tasks_limit,
                    max_retries=max_retries,
                ),
                name=f"kb-upload:{task_id}",
            )
        except Exception:
            self._cleanup_upload_staging_dir(staging_dir)
            raise
        return {
            "task_id": task_id,
            "file_count": len(files_to_upload),
            "message": "task created, processing in background",
        }

    @staticmethod
    def validate_import_request(data: dict[str, Any]):
        kb_id = data.get("kb_id")
        if not kb_id:
            raise KnowledgeBaseServiceError("缺少参数 kb_id")

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

        kb_helper = await self.get_kb_manager().get_kb(kb_id)
        if not kb_helper:
            raise KnowledgeBaseServiceError("知识库不存在")

        task_id = str(uuid.uuid4())
        self.init_task(task_id, status="pending")
        create_tracked_task(
            self._get_background_tasks(),
            self.background_import_task(
                task_id=task_id,
                kb_helper=kb_helper,
                documents=documents,
                batch_size=batch_size,
                tasks_limit=tasks_limit,
                max_retries=max_retries,
            ),
            name=f"kb-import:{task_id}",
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

        task_info = self.upload_tasks[task_id]
        status = task_info["status"]
        response_data = {
            "task_id": task_id,
            "status": status,
        }
        if status == "processing" and task_id in self.upload_progress:
            response_data["progress"] = self.upload_progress[task_id]
        if status == "completed":
            response_data["result"] = task_info["result"]
        if status == "failed":
            response_data["error"] = task_info["error"]
        return response_data

    async def get_document(
        self,
        *,
        kb_id: str | None,
        doc_id: str | None,
    ) -> dict[str, Any]:
        if not kb_id:
            raise KnowledgeBaseServiceError("缺少参数 kb_id")
        if not doc_id:
            raise KnowledgeBaseServiceError("缺少参数 doc_id")
        kb_helper = await self.get_kb_manager().get_kb(kb_id)
        if not kb_helper:
            raise KnowledgeBaseServiceError("知识库不存在")
        doc = await kb_helper.get_document(doc_id)
        if not doc:
            raise KnowledgeBaseServiceError("文档不存在")
        return doc.model_dump()

    async def delete_document(self, data: object) -> tuple[None, str]:
        payload = self._payload(data)
        kb_id = payload.get("kb_id")
        doc_id = payload.get("doc_id")
        if not kb_id:
            raise KnowledgeBaseServiceError("缺少参数 kb_id")
        if not doc_id:
            raise KnowledgeBaseServiceError("缺少参数 doc_id")
        kb_helper = await self.get_kb_manager().get_kb(kb_id)
        if not kb_helper:
            raise KnowledgeBaseServiceError("知识库不存在")
        await kb_helper.delete_document(doc_id)
        return None, "删除文档成功"

    async def delete_chunk(self, data: object) -> tuple[None, str]:
        payload = self._payload(data)
        kb_id = payload.get("kb_id")
        chunk_id = payload.get("chunk_id")
        doc_id = payload.get("doc_id")
        if not kb_id:
            raise KnowledgeBaseServiceError("缺少参数 kb_id")
        if not chunk_id:
            raise KnowledgeBaseServiceError("缺少参数 chunk_id")
        if not doc_id:
            raise KnowledgeBaseServiceError("缺少参数 doc_id")
        kb_helper = await self.get_kb_manager().get_kb(kb_id)
        if not kb_helper:
            raise KnowledgeBaseServiceError("知识库不存在")
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
        if not kb_id:
            raise KnowledgeBaseServiceError("缺少参数 kb_id")
        if not doc_id:
            raise KnowledgeBaseServiceError("缺少参数 doc_id")
        kb_helper = await self.get_kb_manager().get_kb(kb_id)
        if not kb_helper:
            raise KnowledgeBaseServiceError("知识库不存在")

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

    async def retrieve(self, data: object) -> dict[str, Any]:
        payload = self._payload(data)
        query = payload.get("query")
        kb_names = payload.get("kb_names")
        debug = payload.get("debug", False)

        if not query:
            raise KnowledgeBaseServiceError("缺少参数 query")
        kb_manager = self.get_kb_manager()
        if not kb_names or not isinstance(kb_names, list):
            raise KnowledgeBaseServiceError("缺少参数 kb_names 或格式错误")

        top_k = payload.get("top_k", 5)
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
                logger.error("生成 t-SNE 可视化失败: %s", safe_error("", exc))
                response_data["visualization_error"] = "Visualization generation failed"

        return response_data

    async def upload_document_from_url(self, data: object) -> dict[str, Any]:
        payload = self._payload(data)
        kb_id = payload.get("kb_id")
        if not kb_id:
            raise KnowledgeBaseServiceError("缺少参数 kb_id")
        url = payload.get("url")
        if not url:
            raise KnowledgeBaseServiceError("缺少参数 url")

        kb_helper = await self.get_kb_manager().get_kb(kb_id)
        if not kb_helper:
            raise KnowledgeBaseServiceError("知识库不存在")

        task_id = str(uuid.uuid4())
        self.init_task(task_id, status="pending")
        create_tracked_task(
            self._get_background_tasks(),
            self.background_upload_from_url_task(
                task_id=task_id,
                kb_helper=kb_helper,
                url=url,
                chunk_size=payload.get("chunk_size", 512),
                chunk_overlap=payload.get("chunk_overlap", 50),
                batch_size=payload.get("batch_size", 32),
                tasks_limit=payload.get("tasks_limit", 3),
                max_retries=payload.get("max_retries", 3),
                enable_cleaning=payload.get("enable_cleaning", False),
                cleaning_provider_id=payload.get("cleaning_provider_id"),
            ),
            name=f"kb-upload-url:{task_id}",
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
            logger.error(
                "后台上传URL任务 %s 失败: %s",
                task_id,
                safe_error("", exc),
            )
            self.set_task_result(task_id, "failed", error=_BACKGROUND_TASK_ERROR)


__all__ = ["KnowledgeBaseService", "KnowledgeBaseServiceError"]
