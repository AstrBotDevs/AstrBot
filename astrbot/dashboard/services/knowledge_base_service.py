from __future__ import annotations

import asyncio
import traceback
import uuid
from pathlib import Path
from typing import Any

import aiofiles

from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.provider.provider import EmbeddingProvider, RerankProvider
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.dashboard.utils import generate_tsne_visualization


class KnowledgeBaseServiceError(Exception):
    pass


class KnowledgeBaseService:
    def __init__(self, core_lifecycle: AstrBotCoreLifecycle) -> None:
        self.core_lifecycle = core_lifecycle
        self.upload_progress: dict[str, dict[str, Any]] = {}
        self.upload_tasks: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _payload(data: object) -> dict[str, Any]:
        return data if isinstance(data, dict) else {}

    def get_kb_manager(self):
        return self.core_lifecycle.kb_manager

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
        message = str(error).strip() or "上传失败：发生未知错误。"
        if message.startswith(file_name):
            return message
        return f"{file_name}: {message}"

    async def background_upload_task(
        self,
        task_id: str,
        kb_helper,
        files_to_upload: list[dict[str, Any]],
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
                try:
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
                        file_content=file_info["file_content"],
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

        kb_list = []
        for kb in kbs:
            kb_dict = kb.model_dump()
            kb_helper = await kb_manager.get_kb(kb.kb_id)
            if kb_helper and kb_helper.init_error:
                kb_dict["init_error"] = kb_helper.init_error
            kb_list.append(kb_dict)

        return {"items": kb_list, "page": page, "page_size": page_size}

    async def list_kbs_from_dashboard_query(self, *, page, page_size) -> dict[str, Any]:
        return await self.list_kbs(
            page=self._to_int(page, 1),
            page_size=self._to_int(page_size, 20),
        )

    async def create_kb(self, data: object) -> tuple[dict[str, Any], str]:
        kb_manager = self.get_kb_manager()
        payload = self._payload(data)
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
        if not kb_id:
            raise KnowledgeBaseServiceError("缺少参数 kb_id")
        kb_helper = await self.get_kb_manager().get_kb(kb_id)
        if not kb_helper:
            raise KnowledgeBaseServiceError("知识库不存在")
        return kb_helper.kb.model_dump()

    async def get_kb_from_dashboard_query(self, kb_id: str | None) -> dict[str, Any]:
        return await self.get_kb(kb_id)

    async def update_kb(self, data: object) -> tuple[dict[str, Any], str]:
        payload = self._payload(data)
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
        if all(payload.get(key) is None for key in update_keys):
            raise KnowledgeBaseServiceError("至少需要提供一个更新字段")

        current_kb = await self.get_kb_manager().get_kb(kb_id)
        kb_name = payload.get("kb_name")
        if kb_name is None:
            if not current_kb:
                raise KnowledgeBaseServiceError("知识库不存在")
            kb_name = current_kb.kb.kb_name

        kb_helper = await self.get_kb_manager().update_kb(
            kb_id=kb_id,
            kb_name=kb_name,
            description=payload.get("description"),
            emoji=payload.get("emoji"),
            embedding_provider_id=payload.get("embedding_provider_id"),
            rerank_provider_id=payload.get("rerank_provider_id"),
            chunk_size=payload.get("chunk_size"),
            chunk_overlap=payload.get("chunk_overlap"),
            top_k_dense=payload.get("top_k_dense"),
            top_k_sparse=payload.get("top_k_sparse"),
            top_m_final=payload.get("top_m_final"),
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
    ) -> dict[str, Any]:
        if not kb_id:
            raise KnowledgeBaseServiceError("缺少参数 kb_id")
        kb_helper = await self.get_kb_manager().get_kb(kb_id)
        if not kb_helper:
            raise KnowledgeBaseServiceError("知识库不存在")

        offset = (page - 1) * page_size
        doc_list = await kb_helper.list_documents(offset=offset, limit=page_size)
        return {
            "items": [doc.model_dump() for doc in doc_list],
            "page": page,
            "page_size": page_size,
        }

    async def list_documents_from_dashboard_query(
        self,
        *,
        kb_id: str | None,
        page,
        page_size,
    ) -> dict[str, Any]:
        return await self.list_documents(
            kb_id=kb_id,
            page=self._to_int(page, 1),
            page_size=self._to_int(page_size, 100),
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
        chunk_size = int(form_data.get("chunk_size", 512))
        chunk_overlap = int(form_data.get("chunk_overlap", 50))
        batch_size = int(form_data.get("batch_size", 32))
        tasks_limit = int(form_data.get("tasks_limit", 3))
        max_retries = int(form_data.get("max_retries", 3))
        if not kb_id:
            raise KnowledgeBaseServiceError("缺少参数 kb_id")

        file_list = []
        for key in files.keys():
            if key == "file" or key.startswith("file") or key == "files[]":
                file_list.extend(files.getlist(key))
        if not file_list:
            raise KnowledgeBaseServiceError("缺少文件")
        if len(file_list) > 10:
            raise KnowledgeBaseServiceError("最多只能上传10个文件")

        files_to_upload = []
        for file in file_list:
            file_name = file.filename
            temp_file_path = (
                Path(get_astrbot_temp_path()) / f"kb_upload_{uuid.uuid4()}_{file_name}"
            )
            await file.save(temp_file_path)
            try:
                async with aiofiles.open(temp_file_path, "rb") as file_obj:
                    file_content = await file_obj.read()
                file_type = (
                    file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
                )
                files_to_upload.append(
                    {
                        "file_name": file_name,
                        "file_content": file_content,
                        "file_type": file_type,
                    },
                )
            finally:
                temp_file_path.unlink(missing_ok=True)

        kb_helper = await self.get_kb_manager().get_kb(kb_id)
        if not kb_helper:
            raise KnowledgeBaseServiceError("知识库不存在")

        task_id = str(uuid.uuid4())
        self.init_task(task_id, status="pending")
        asyncio.create_task(
            self.background_upload_task(
                task_id=task_id,
                kb_helper=kb_helper,
                files_to_upload=files_to_upload,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                batch_size=batch_size,
                tasks_limit=tasks_limit,
                max_retries=max_retries,
            ),
        )
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

        if not query:
            raise KnowledgeBaseServiceError("缺少参数 query")
        if not kb_names or not isinstance(kb_names, list):
            raise KnowledgeBaseServiceError("缺少参数 kb_names 或格式错误")

        top_k = payload.get("top_k", 5)
        kb_manager = self.get_kb_manager()
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
        asyncio.create_task(
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
