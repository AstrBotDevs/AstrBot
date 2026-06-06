"""知识库管理 API 路由"""

import asyncio
import os
import traceback
import uuid
from typing import Any

import aiofiles
from quart import request

from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.knowledge_base.capabilities import (
    ALLOWED_UPLOAD_EXTENSIONS,
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_PAGE_SIZE,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_DOCUMENT_PAGE_SIZE,
    DEFAULT_INDEX_TYPE,
    DEFAULT_KB_PAGE_SIZE,
    DEFAULT_TOP_K_DENSE,
    DEFAULT_TOP_K_SPARSE,
    DEFAULT_TOP_M_FINAL,
    DEFAULT_UPLOAD_BATCH_SIZE,
    DEFAULT_UPLOAD_MAX_RETRIES,
    DEFAULT_UPLOAD_TASKS_LIMIT,
    DOCUMENT_FILTER_SOURCE_TYPES,
    DOCUMENT_FILTER_STATUSES,
    MAX_BATCH_DELETE_DOCUMENTS,
    MAX_BATCH_REBUILD_DOCUMENTS,
    MAX_RETRIEVE_TOP_K,
    MAX_UPLOAD_FILE_SIZE,
    MAX_UPLOAD_FILES,
    get_knowledge_base_capabilities,
)
from astrbot.core.provider.provider import EmbeddingProvider, RerankProvider
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from ..utils import generate_tsne_visualization
from .route import Response, Route, RouteContext


class KnowledgeBaseRoute(Route):
    """知识库管理路由

    提供知识库、文档、检索、会话配置等 API 接口
    """

    def __init__(
        self,
        context: RouteContext,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.core_lifecycle = core_lifecycle
        self.kb_manager = None  # 延迟初始化
        self.kb_db = None
        self.session_config_db = None  # 会话配置数据库
        self.retrieval_manager = None
        self.upload_progress = {}  # 存储上传进度 {task_id: {status, file_index, file_total, stage, current, total}}
        self.upload_tasks = {}  # 存储后台上传任务 {task_id: {"status", "result", "error"}}

        # 注册路由
        self.routes = {
            # 知识库管理
            "/kb/capabilities": ("GET", self.get_capabilities),
            "/kb/list": ("GET", self.list_kbs),
            "/kb/create": ("POST", self.create_kb),
            "/kb/get": ("GET", self.get_kb),
            "/kb/update": ("POST", self.update_kb),
            "/kb/delete": ("POST", self.delete_kb),
            "/kb/stats": ("GET", self.get_kb_stats),
            "/kb/consistency/check": ("GET", self.check_kb_consistency),
            "/kb/consistency/repair": ("POST", self.repair_kb_consistency),
            "/kb/rebuild": ("POST", self.rebuild_kb),
            # 文档管理
            "/kb/document/list": ("GET", self.list_documents),
            "/kb/document/upload": ("POST", self.upload_document),
            "/kb/document/import": ("POST", self.import_documents),
            "/kb/document/upload/url": ("POST", self.upload_document_from_url),
            "/kb/document/upload/progress": ("GET", self.get_upload_progress),
            "/kb/document/get": ("GET", self.get_document),
            "/kb/document/rebuild": ("POST", self.rebuild_document),
            "/kb/document/batch-rebuild": ("POST", self.batch_rebuild_documents),
            "/kb/document/delete": ("POST", self.delete_document),
            "/kb/document/batch-delete": ("POST", self.batch_delete_documents),
            "/kb/task/get": ("GET", self.get_task),
            "/kb/task/list": ("GET", self.list_tasks),
            # # 块管理
            "/kb/chunk/list": ("GET", self.list_chunks),
            "/kb/chunk/context": ("GET", self.get_chunk_context),
            "/kb/chunk/delete": ("POST", self.delete_chunk),
            # # 多媒体管理
            # "/kb/media/list": ("GET", self.list_media),
            # "/kb/media/delete": ("POST", self.delete_media),
            # 检索
            "/kb/retrieve": ("POST", self.retrieve),
        }
        self.register_routes()

    def _get_kb_manager(self):
        return self.core_lifecycle.kb_manager

    def _get_kb_db(self):
        if not hasattr(self, "core_lifecycle"):
            return None
        kb_manager = self._get_kb_manager()
        return getattr(kb_manager, "kb_db", None)

    @staticmethod
    def _get_positive_query_int(name: str, default: int) -> int:
        value = request.args.get(name, default, type=int)
        return max(value if value is not None else default, 1)

    async def get_capabilities(self):
        """Return knowledge base capabilities, defaults, and limits."""
        return Response().ok(get_knowledge_base_capabilities()).__dict__

    async def _create_persistent_task(
        self,
        *,
        task_id: str,
        kb_id: str | None,
        task_type: str,
        status: str,
        progress: dict | None = None,
    ) -> None:
        kb_db = self._get_kb_db()
        if not kb_db or not kb_id:
            return
        try:
            await kb_db.create_ingestion_task(
                task_id=task_id,
                kb_id=kb_id,
                task_type=task_type,
                status=status,
                progress_stage=(progress or {}).get("stage"),
                progress_current=(progress or {}).get("current", 0),
                progress_total=(progress or {}).get("total", 100),
                progress=progress,
            )
        except Exception as e:
            logger.warning(f"创建知识库持久任务记录失败 {task_id}: {e}")

    async def _update_persistent_task(self, task_id: str, **updates) -> None:
        kb_db = self._get_kb_db()
        if not kb_db:
            return
        try:
            await kb_db.update_ingestion_task(task_id, **updates)
        except Exception as e:
            logger.warning(f"更新知识库持久任务记录失败 {task_id}: {e}")

    async def _get_persistent_task(self, task_id: str) -> dict | None:
        kb_db = self._get_kb_db()
        if not kb_db:
            return None
        try:
            return await kb_db.get_ingestion_task(task_id)
        except Exception as e:
            logger.warning(f"读取知识库持久任务记录失败 {task_id}: {e}")
            return None

    def _get_persistent_progress_updates(self, task_id: str) -> dict:
        progress = self.upload_progress.get(task_id)
        if not progress:
            return {}
        return {
            "progress_stage": progress.get("stage"),
            "progress_current": progress.get("current", 0),
            "progress_total": progress.get("total", 100),
            "progress": progress,
        }

    def _init_task(self, task_id: str, status: str = "pending") -> None:
        self.upload_tasks[task_id] = {
            "status": status,
            "result": None,
            "error": None,
        }

    def _set_task_result(
        self, task_id: str, status: str, result: Any = None, error: str | None = None
    ) -> None:
        self.upload_tasks[task_id] = {
            "status": status,
            "result": result,
            "error": error,
        }
        if task_id in self.upload_progress:
            self.upload_progress[task_id]["status"] = status

    def _cleanup_task(self, task_id: str) -> None:
        """清理已完成/失败的任务，释放内存。幂等操作。"""
        self.upload_tasks.pop(task_id, None)
        self.upload_progress.pop(task_id, None)

    async def _schedule_delayed_cleanup(
        self, task_id: str, delay_seconds: int = 300
    ) -> None:
        """延迟清理任务，作为客户端不轮询时的兜底机制。"""
        try:
            await asyncio.sleep(delay_seconds)
        except asyncio.CancelledError:
            return
        self._cleanup_task(task_id)

    def _update_progress(
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
        p = self.upload_progress[task_id]
        if status is not None:
            p["status"] = status
        if file_index is not None:
            p["file_index"] = file_index
        if file_name is not None:
            p["file_name"] = file_name
        if stage is not None:
            p["stage"] = stage
        if current is not None:
            p["current"] = current
        if total is not None:
            p["total"] = total

    async def _persist_progress(self, task_id: str) -> None:
        progress = self.upload_progress.get(task_id)
        if not progress:
            return
        await self._update_persistent_task(
            task_id,
            status=progress.get("status"),
            **self._get_persistent_progress_updates(task_id),
        )

    def _make_progress_callback(self, task_id: str, file_idx: int, file_name: str):
        async def _callback(stage: str, current: int, total: int) -> None:
            self._update_progress(
                task_id,
                status="processing",
                file_index=file_idx,
                file_name=file_name,
                stage=stage,
                current=current,
                total=total,
            )
            await self._persist_progress(task_id)

        return _callback

    @staticmethod
    def _format_failed_doc_error(file_name: str, error: Exception) -> str:
        message = str(error).strip() or "上传失败：发生未知错误。"
        if message.startswith(f"{file_name}:"):
            return message
        return f"{file_name}: {message}"

    @staticmethod
    def _build_batch_failure_error(failed_docs: list[dict]) -> str | None:
        if not failed_docs:
            return None
        if len(failed_docs) == 1:
            return failed_docs[0].get("error") or "上传失败：发生未知错误。"
        return f"所有文档上传失败，共 {len(failed_docs)} 个失败。"

    @staticmethod
    def _format_size_limit(size_bytes: int) -> str:
        size_mb = size_bytes / (1024 * 1024)
        if size_mb.is_integer():
            return f"{int(size_mb)}MB"
        return f"{size_mb:.2f}MB"

    @staticmethod
    def _coerce_optional_int(value: Any, field_name: str) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError) as e:
            raise ValueError(f"{field_name} 必须是整数") from e

    @staticmethod
    def _coerce_optional_bool(value: Any, field_name: str) -> bool:
        if isinstance(value, bool):
            return value
        if value in (None, ""):
            return False
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "on"}:
                return True
            if lowered in {"false", "0", "no", "off"}:
                return False
        raise ValueError(f"{field_name} 必须是布尔值")

    @staticmethod
    def _validate_chunk_options(
        *,
        chunk_size: int | None,
        chunk_overlap: int | None,
    ) -> None:
        if chunk_size is not None and chunk_size <= 0:
            raise ValueError("chunk_size 必须大于 0")
        if chunk_overlap is not None and chunk_overlap < 0:
            raise ValueError("chunk_overlap 不能为负数")
        if (
            chunk_size is not None
            and chunk_overlap is not None
            and chunk_overlap >= chunk_size
        ):
            raise ValueError("chunk_overlap 必须小于 chunk_size")

    @staticmethod
    def _validate_positive_int(value: int | None, field_name: str) -> None:
        if value is not None and value <= 0:
            raise ValueError(f"{field_name} 必须大于 0")

    @classmethod
    def _validate_kb_options(
        cls,
        *,
        chunk_size: int | None,
        chunk_overlap: int | None,
        top_k_dense: int | None,
        top_k_sparse: int | None,
        top_m_final: int | None,
        index_type: str | None,
    ) -> None:
        cls._validate_chunk_options(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        cls._validate_positive_int(top_k_dense, "top_k_dense")
        cls._validate_positive_int(top_k_sparse, "top_k_sparse")
        cls._validate_positive_int(top_m_final, "top_m_final")
        if index_type is not None and index_type not in {"flat", "hnsw"}:
            raise ValueError("index_type 必须是 flat 或 hnsw")

    @classmethod
    def _validate_upload_options(
        cls,
        *,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int,
        tasks_limit: int,
        max_retries: int,
    ) -> None:
        cls._validate_chunk_options(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        cls._validate_positive_int(batch_size, "batch_size")
        cls._validate_positive_int(tasks_limit, "tasks_limit")
        if max_retries < 0:
            raise ValueError("max_retries 不能为负数")

    @staticmethod
    def _validate_upload_file(file_name: str, file_size: int) -> None:
        file_type = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
        if file_type not in ALLOWED_UPLOAD_EXTENSIONS:
            raise ValueError(f"不支持的文件类型: {file_name}")
        if file_size > MAX_UPLOAD_FILE_SIZE:
            limit = KnowledgeBaseRoute._format_size_limit(MAX_UPLOAD_FILE_SIZE)
            raise ValueError(f"文件超过 {limit} 限制: {file_name}")

    async def _background_upload_task(
        self,
        task_id: str,
        kb_helper,
        files_to_upload: list,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int,
        tasks_limit: int,
        max_retries: int,
    ) -> None:
        """后台上传任务"""
        try:
            # 初始化任务状态
            self._init_task(task_id, status="processing")
            self.upload_progress[task_id] = {
                "status": "processing",
                "file_index": 0,
                "file_total": len(files_to_upload),
                "stage": "waiting",
                "current": 0,
                "total": 100,
            }
            await self._persist_progress(task_id)

            uploaded_docs = []
            failed_docs = []

            for file_idx, file_info in enumerate(files_to_upload):
                try:
                    # 更新整体进度
                    self._update_progress(
                        task_id,
                        status="processing",
                        file_index=file_idx,
                        file_name=file_info["file_name"],
                        stage="parsing",
                        current=0,
                        total=100,
                    )
                    await self._persist_progress(task_id)

                    # 创建进度回调函数
                    progress_callback = self._make_progress_callback(
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
                except Exception as e:
                    logger.error(f"上传文档 {file_info['file_name']} 失败: {e}")
                    failed_docs.append(
                        {
                            "file_name": file_info["file_name"],
                            "error": self._format_failed_doc_error(
                                file_info["file_name"], e
                            ),
                        },
                    )

            # 更新任务完成状态
            result = {
                "task_id": task_id,
                "uploaded": uploaded_docs,
                "failed": failed_docs,
                "total": len(files_to_upload),
                "success_count": len(uploaded_docs),
                "failed_count": len(failed_docs),
            }

            task_status = "completed" if uploaded_docs else "failed"
            task_error = self._build_batch_failure_error(failed_docs)
            self._set_task_result(
                task_id,
                task_status,
                result=result,
                error=task_error,
            )
            await self._update_persistent_task(
                task_id,
                status=task_status,
                result=result,
                error=task_error,
                **self._get_persistent_progress_updates(task_id),
            )

        except Exception as e:
            logger.error(f"后台上传任务 {task_id} 失败: {e}")
            logger.error(traceback.format_exc())
            self._set_task_result(task_id, "failed", error=str(e))
            await self._update_persistent_task(
                task_id,
                status="failed",
                error=str(e),
                **self._get_persistent_progress_updates(task_id),
            )
        finally:
            # 兜底清理：防止客户端不轮询 get_upload_progress 导致内存泄漏
            asyncio.create_task(self._schedule_delayed_cleanup(task_id))

    async def _background_import_task(
        self,
        task_id: str,
        kb_helper,
        documents: list,
        batch_size: int,
        tasks_limit: int,
        max_retries: int,
    ) -> None:
        """后台导入预切片文档任务"""
        try:
            # 初始化任务状态
            self._init_task(task_id, status="processing")
            self.upload_progress[task_id] = {
                "status": "processing",
                "file_index": 0,
                "file_total": len(documents),
                "stage": "waiting",
                "current": 0,
                "total": 100,
            }
            await self._persist_progress(task_id)

            uploaded_docs = []
            failed_docs = []

            for file_idx, doc_info in enumerate(documents):
                file_name = doc_info.get("file_name", f"imported_doc_{file_idx}")
                chunks = doc_info.get("chunks", [])

                try:
                    # 更新整体进度
                    self._update_progress(
                        task_id,
                        status="processing",
                        file_index=file_idx,
                        file_name=file_name,
                        stage="importing",
                        current=0,
                        total=100,
                    )
                    await self._persist_progress(task_id)

                    # 创建进度回调函数
                    progress_callback = self._make_progress_callback(
                        task_id, file_idx, file_name
                    )

                    # 调用 upload_document，传入 pre_chunked_text
                    doc = await kb_helper.upload_document(
                        file_name=file_name,
                        file_content=None,  # 预切片模式下不需要原始内容
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
                        source_type="import",
                        source_uri=file_name,
                    )

                    uploaded_docs.append(doc.model_dump())
                except Exception as e:
                    logger.error(f"导入文档 {file_name} 失败: {e}")
                    failed_docs.append(
                        {
                            "file_name": file_name,
                            "error": self._format_failed_doc_error(file_name, e),
                        },
                    )

            # 更新任务完成状态
            result = {
                "task_id": task_id,
                "uploaded": uploaded_docs,
                "failed": failed_docs,
                "total": len(documents),
                "success_count": len(uploaded_docs),
                "failed_count": len(failed_docs),
            }

            task_status = "completed" if uploaded_docs else "failed"
            task_error = self._build_batch_failure_error(failed_docs)
            self._set_task_result(
                task_id,
                task_status,
                result=result,
                error=task_error,
            )
            await self._update_persistent_task(
                task_id,
                status=task_status,
                result=result,
                error=task_error,
                **self._get_persistent_progress_updates(task_id),
            )

        except Exception as e:
            logger.error(f"后台导入任务 {task_id} 失败: {e}")
            logger.error(traceback.format_exc())
            self._set_task_result(task_id, "failed", error=str(e))
            await self._update_persistent_task(
                task_id,
                status="failed",
                error=str(e),
                **self._get_persistent_progress_updates(task_id),
            )
        finally:
            asyncio.create_task(self._schedule_delayed_cleanup(task_id))

    async def _background_rebuild_document_task(
        self,
        task_id: str,
        kb_helper,
        doc_id: str,
        chunk_size: int | None,
        chunk_overlap: int | None,
        batch_size: int,
        tasks_limit: int,
        max_retries: int,
    ) -> None:
        """Run a single document rebuild in the background."""
        try:
            self._init_task(task_id, status="processing")
            self.upload_progress[task_id] = {
                "status": "processing",
                "file_index": 0,
                "file_total": 1,
                "file_name": doc_id,
                "stage": "rebuilding",
                "current": 0,
                "total": 100,
            }
            await self._persist_progress(task_id)

            progress_callback = self._make_progress_callback(task_id, 0, doc_id)
            doc = await kb_helper.rebuild_document(
                doc_id,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                batch_size=batch_size,
                tasks_limit=tasks_limit,
                max_retries=max_retries,
                progress_callback=progress_callback,
            )

            result = {
                "task_id": task_id,
                "rebuilt": [doc.model_dump()],
                "failed": [],
                "total": 1,
                "success_count": 1,
                "failed_count": 0,
            }
            self._update_progress(
                task_id,
                status="completed",
                file_index=0,
                file_name=doc_id,
                stage="completed",
                current=100,
                total=100,
            )
            self._set_task_result(task_id, "completed", result=result)
            await self._update_persistent_task(
                task_id,
                status="completed",
                result=result,
                error=None,
                **self._get_persistent_progress_updates(task_id),
            )

        except Exception as e:
            logger.error(f"后台重建文档任务 {task_id} 失败: {e}")
            logger.error(traceback.format_exc())
            self._set_task_result(task_id, "failed", error=str(e))
            await self._update_persistent_task(
                task_id,
                status="failed",
                error=str(e),
                **self._get_persistent_progress_updates(task_id),
            )
        finally:
            asyncio.create_task(self._schedule_delayed_cleanup(task_id))

    async def _background_rebuild_kb_task(
        self,
        task_id: str,
        kb_helper,
        chunk_size: int | None,
        chunk_overlap: int | None,
        batch_size: int,
        tasks_limit: int,
        max_retries: int,
    ) -> None:
        """Run a full knowledge base rebuild in the background."""
        kb_name = getattr(getattr(kb_helper, "kb", None), "kb_name", "knowledge base")
        try:
            self._init_task(task_id, status="processing")
            self.upload_progress[task_id] = {
                "status": "processing",
                "file_index": 0,
                "file_total": 1,
                "file_name": kb_name,
                "stage": "rebuilding",
                "current": 0,
                "total": 100,
            }
            await self._persist_progress(task_id)

            progress_callback = self._make_progress_callback(
                task_id,
                0,
                kb_name,
            )
            result = await kb_helper.rebuild_all_documents(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                batch_size=batch_size,
                tasks_limit=tasks_limit,
                max_retries=max_retries,
                progress_callback=progress_callback,
            )
            result = {
                "task_id": task_id,
                **result,
            }
            completed_total = max(int(result.get("total") or 0), 1)
            self._update_progress(
                task_id,
                status="completed",
                file_index=0,
                file_name=kb_name,
                stage="completed",
                current=completed_total,
                total=completed_total,
            )
            self._set_task_result(task_id, "completed", result=result)
            await self._update_persistent_task(
                task_id,
                status="completed",
                result=result,
                error=None,
                **self._get_persistent_progress_updates(task_id),
            )

        except Exception as e:
            logger.error(f"后台重建知识库任务 {task_id} 失败: {e}")
            logger.error(traceback.format_exc())
            self._set_task_result(task_id, "failed", error=str(e))
            await self._update_persistent_task(
                task_id,
                status="failed",
                error=str(e),
                **self._get_persistent_progress_updates(task_id),
            )
        finally:
            asyncio.create_task(self._schedule_delayed_cleanup(task_id))

    async def _background_rebuild_documents_task(
        self,
        task_id: str,
        kb_helper,
        doc_ids: list[str],
        chunk_size: int | None,
        chunk_overlap: int | None,
        batch_size: int,
        tasks_limit: int,
        max_retries: int,
    ) -> None:
        """Run selected document rebuilds in the background."""
        total = max(len(doc_ids), 1)
        task_name = f"{len(doc_ids)} selected documents"
        try:
            self._init_task(task_id, status="processing")
            self.upload_progress[task_id] = {
                "status": "processing",
                "file_index": 0,
                "file_total": total,
                "file_name": task_name,
                "stage": "rebuilding",
                "current": 0,
                "total": total,
            }
            await self._persist_progress(task_id)

            progress_callback = self._make_progress_callback(
                task_id,
                0,
                task_name,
            )
            result = await kb_helper.rebuild_documents(
                doc_ids,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                batch_size=batch_size,
                tasks_limit=tasks_limit,
                max_retries=max_retries,
                progress_callback=progress_callback,
            )
            result = {
                "task_id": task_id,
                **result,
            }
            completed_total = max(int(result.get("total") or 0), 1)
            self._update_progress(
                task_id,
                status="completed",
                file_index=0,
                file_name=task_name,
                stage="completed",
                current=completed_total,
                total=completed_total,
            )
            self._set_task_result(task_id, "completed", result=result)
            await self._update_persistent_task(
                task_id,
                status="completed",
                result=result,
                error=None,
                **self._get_persistent_progress_updates(task_id),
            )

        except Exception as e:
            logger.error(f"后台批量重建文档任务 {task_id} 失败: {e}")
            logger.error(traceback.format_exc())
            self._set_task_result(task_id, "failed", error=str(e))
            await self._update_persistent_task(
                task_id,
                status="failed",
                error=str(e),
                **self._get_persistent_progress_updates(task_id),
            )
        finally:
            asyncio.create_task(self._schedule_delayed_cleanup(task_id))

    async def list_kbs(self):
        """获取知识库列表

        Query 参数:
        - page: 页码 (默认 1)
        - page_size: 每页数量
        - refresh_stats: 是否刷新统计信息 (默认 false，首次加载时可设为 true)
        """
        try:
            kb_manager = self._get_kb_manager()
            page = self._get_positive_query_int("page", 1)
            page_size = self._get_positive_query_int(
                "page_size",
                DEFAULT_KB_PAGE_SIZE,
            )
            refresh_stats = request.args.get("refresh_stats") == "true"
            kb_db = self._get_kb_db()

            kbs = await kb_manager.list_kbs()
            total = len(kbs)
            start = (page - 1) * page_size
            paged_kbs = kbs[start : start + page_size]

            # 转换为字典列表
            kb_list = []
            for kb in paged_kbs:
                kb_dict = kb.model_dump()
                if refresh_stats and kb_db and hasattr(kb_db, "get_kb_stats"):
                    stats = await kb_db.get_kb_stats(kb.kb_id)
                    if stats:
                        kb_dict.update(stats)
                # include init_error from KBHelper if present
                kb_helper = await kb_manager.get_kb(kb.kb_id)
                if kb_helper and kb_helper.init_error:
                    kb_dict["init_error"] = kb_helper.init_error
                kb_list.append(kb_dict)

            return (
                Response()
                .ok(
                    {
                        "items": kb_list,
                        "page": page,
                        "page_size": page_size,
                        "total": total,
                    },
                )
                .__dict__
            )
        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"获取知识库列表失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"获取知识库列表失败: {e!s}").__dict__

    async def create_kb(self):
        """创建知识库

        Body:
        - kb_name: 知识库名称 (必填)
        - description: 描述 (可选)
        - emoji: 图标 (可选)
        - embedding_provider_id: 嵌入模型提供商ID (可选)
        - rerank_provider_id: 重排序模型提供商ID (可选)
        - chunk_size: 分块大小 (可选, 默认512)
        - chunk_overlap: 块重叠大小 (可选, 默认50)
        - top_k_dense: 密集检索数量 (可选, 默认50)
        - top_k_sparse: 稀疏检索数量 (可选, 默认50)
        - top_m_final: 最终返回数量 (可选, 默认5)
        """
        try:
            kb_manager = self._get_kb_manager()
            data = await request.json
            kb_name = data.get("kb_name")
            if not kb_name:
                return Response().error("知识库名称不能为空").__dict__

            description = data.get("description")
            emoji = data.get("emoji")
            embedding_provider_id = data.get("embedding_provider_id")
            rerank_provider_id = data.get("rerank_provider_id")
            chunk_size = self._coerce_optional_int(data.get("chunk_size"), "chunk_size")
            chunk_overlap = self._coerce_optional_int(
                data.get("chunk_overlap"),
                "chunk_overlap",
            )
            top_k_dense = self._coerce_optional_int(
                data.get("top_k_dense"),
                "top_k_dense",
            )
            top_k_sparse = self._coerce_optional_int(
                data.get("top_k_sparse"),
                "top_k_sparse",
            )
            top_m_final = self._coerce_optional_int(
                data.get("top_m_final"),
                "top_m_final",
            )
            index_type = data.get("index_type")
            self._validate_kb_options(
                chunk_size=chunk_size if chunk_size is not None else DEFAULT_CHUNK_SIZE,
                chunk_overlap=chunk_overlap
                if chunk_overlap is not None
                else DEFAULT_CHUNK_OVERLAP,
                top_k_dense=top_k_dense
                if top_k_dense is not None
                else DEFAULT_TOP_K_DENSE,
                top_k_sparse=top_k_sparse
                if top_k_sparse is not None
                else DEFAULT_TOP_K_SPARSE,
                top_m_final=top_m_final
                if top_m_final is not None
                else DEFAULT_TOP_M_FINAL,
                index_type=index_type if index_type is not None else DEFAULT_INDEX_TYPE,
            )

            # pre-check embedding dim
            if not embedding_provider_id:
                return Response().error("缺少参数 embedding_provider_id").__dict__
            prv = await kb_manager.provider_manager.get_provider_by_id(
                embedding_provider_id,
            )  # type: ignore
            if not prv or not isinstance(prv, EmbeddingProvider):
                return (
                    Response().error(f"嵌入模型不存在或类型错误({type(prv)})").__dict__
                )
            try:
                vec = await prv.get_embedding("astrbot")
                if len(vec) != prv.get_dim():
                    raise ValueError(
                        f"嵌入向量维度不匹配，实际是 {len(vec)}，然而配置是 {prv.get_dim()}",
                    )
            except Exception as e:
                return Response().error(f"测试嵌入模型失败: {e!s}").__dict__
            # pre-check rerank
            if rerank_provider_id:
                rerank_prv: RerankProvider = (
                    await kb_manager.provider_manager.get_provider_by_id(
                        rerank_provider_id,
                    )
                )  # type: ignore
                if not rerank_prv:
                    return Response().error("重排序模型不存在").__dict__
                # 检查重排序模型可用性
                try:
                    res = await rerank_prv.rerank(
                        query="astrbot",
                        documents=["astrbot knowledge base"],
                    )
                    if not res:
                        raise ValueError("重排序模型返回结果异常")
                except Exception as e:
                    return (
                        Response()
                        .error(f"测试重排序模型失败: {e!s}，请检查平台日志输出。")
                        .__dict__
                    )

            kb_helper = await kb_manager.create_kb(
                kb_name=kb_name,
                description=description,
                emoji=emoji,
                embedding_provider_id=embedding_provider_id,
                rerank_provider_id=rerank_provider_id,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                top_k_dense=top_k_dense,
                top_k_sparse=top_k_sparse,
                top_m_final=top_m_final,
                index_type=index_type,
            )
            kb = kb_helper.kb

            return Response().ok(kb.model_dump(), "创建知识库成功").__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"创建知识库失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"创建知识库失败: {e!s}").__dict__

    async def get_kb(self):
        """获取知识库详情

        Query 参数:
        - kb_id: 知识库 ID (必填)
        """
        try:
            kb_manager = self._get_kb_manager()
            kb_id = request.args.get("kb_id")
            if not kb_id:
                return Response().error("缺少参数 kb_id").__dict__

            kb_helper = await kb_manager.get_kb(kb_id)
            if not kb_helper:
                return Response().error("知识库不存在").__dict__
            kb = kb_helper.kb

            return Response().ok(kb.model_dump()).__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"获取知识库详情失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"获取知识库详情失败: {e!s}").__dict__

    async def update_kb(self):
        """更新知识库

        Body:
        - kb_id: 知识库 ID (必填)
        - kb_name: 新的知识库名称 (可选)
        - description: 新的描述 (可选)
        - emoji: 新的图标 (可选)
        - embedding_provider_id: 新的嵌入模型提供商ID (可选)
        - rerank_provider_id: 新的重排序模型提供商ID (可选)
        - chunk_size: 分块大小 (可选)
        - chunk_overlap: 块重叠大小 (可选)
        - top_k_dense: 密集检索数量 (可选)
        - top_k_sparse: 稀疏检索数量 (可选)
        - top_m_final: 最终返回数量 (可选)
        """
        try:
            kb_manager = self._get_kb_manager()
            data = await request.json

            kb_id = data.get("kb_id")
            if not kb_id:
                return Response().error("缺少参数 kb_id").__dict__

            update_fields = [
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
                "index_type",
            ]
            if not any(field in data for field in update_fields):
                return Response().error("至少需要提供一个更新字段").__dict__

            kb_name = data.get("kb_name")
            description = data.get("description")
            emoji = data.get("emoji")
            embedding_provider_id = data.get("embedding_provider_id")
            rerank_provider_provided = "rerank_provider_id" in data
            rerank_provider_id = (
                data.get("rerank_provider_id") if rerank_provider_provided else None
            )
            chunk_size = self._coerce_optional_int(data.get("chunk_size"), "chunk_size")
            chunk_overlap = self._coerce_optional_int(
                data.get("chunk_overlap"),
                "chunk_overlap",
            )
            top_k_dense = self._coerce_optional_int(
                data.get("top_k_dense"),
                "top_k_dense",
            )
            top_k_sparse = self._coerce_optional_int(
                data.get("top_k_sparse"),
                "top_k_sparse",
            )
            top_m_final = self._coerce_optional_int(
                data.get("top_m_final"),
                "top_m_final",
            )
            index_type = data.get("index_type")
            kb_helper = await kb_manager.get_kb(kb_id)
            if not kb_helper:
                return Response().error("知识库不存在").__dict__
            current_kb = kb_helper.kb
            self._validate_kb_options(
                chunk_size=chunk_size
                if chunk_size is not None
                else current_kb.chunk_size,
                chunk_overlap=chunk_overlap
                if chunk_overlap is not None
                else current_kb.chunk_overlap,
                top_k_dense=top_k_dense
                if top_k_dense is not None
                else current_kb.top_k_dense,
                top_k_sparse=top_k_sparse
                if top_k_sparse is not None
                else current_kb.top_k_sparse,
                top_m_final=top_m_final
                if top_m_final is not None
                else current_kb.top_m_final,
                index_type=index_type
                if index_type is not None
                else current_kb.index_type,
            )

            kb_helper = await kb_manager.update_kb(
                kb_id=kb_id,
                kb_name=kb_name,
                description=description,
                emoji=emoji,
                embedding_provider_id=embedding_provider_id,
                **(
                    {"rerank_provider_id": rerank_provider_id}
                    if rerank_provider_provided
                    else {}
                ),
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                top_k_dense=top_k_dense,
                top_k_sparse=top_k_sparse,
                top_m_final=top_m_final,
                index_type=index_type,
            )

            if not kb_helper:
                return Response().error("知识库不存在").__dict__

            kb = kb_helper.kb
            return Response().ok(kb.model_dump(), "更新知识库成功").__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"更新知识库失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"更新知识库失败: {e!s}").__dict__

    async def delete_kb(self):
        """删除知识库

        Body:
        - kb_id: 知识库 ID (必填)
        """
        try:
            kb_manager = self._get_kb_manager()
            data = await request.json

            kb_id = data.get("kb_id")
            if not kb_id:
                return Response().error("缺少参数 kb_id").__dict__

            success = await kb_manager.delete_kb(kb_id)
            if not success:
                return Response().error("知识库不存在").__dict__

            return Response().ok(message="删除知识库成功").__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"删除知识库失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"删除知识库失败: {e!s}").__dict__

    async def get_kb_stats(self):
        """获取知识库统计信息

        Query 参数:
        - kb_id: 知识库 ID (必填)
        """
        try:
            kb_manager = self._get_kb_manager()
            kb_id = request.args.get("kb_id")
            if not kb_id:
                return Response().error("缺少参数 kb_id").__dict__

            kb_helper = await kb_manager.get_kb(kb_id)
            if not kb_helper:
                return Response().error("知识库不存在").__dict__
            kb = kb_helper.kb
            kb_db = self._get_kb_db()
            if kb_db and hasattr(kb_db, "get_kb_stats"):
                stats = await kb_db.get_kb_stats(kb_id)
                if stats is not None:
                    return Response().ok(stats).__dict__

            stats = {
                "kb_id": kb.kb_id,
                "kb_name": kb.kb_name,
                "doc_count": kb.doc_count,
                "chunk_count": kb.chunk_count,
                "document_count": kb.doc_count,
                "ready_document_count": kb.doc_count,
                "failed_document_count": 0,
                "pending_document_count": 0,
                "processing_document_count": 0,
                "indexed_chunk_count": kb.chunk_count,
                "document_chunk_count": kb.chunk_count,
                "media_count": 0,
                "source_file_count": 0,
                "storage_bytes": 0,
                "status_counts": {"ready": kb.doc_count},
                "created_at": kb.created_at.isoformat(),
                "updated_at": kb.updated_at.isoformat(),
            }

            return Response().ok(stats).__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"获取知识库统计失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"获取知识库统计失败: {e!s}").__dict__

    async def check_kb_consistency(self):
        """Check consistency across metadata, source files, and indexed chunks."""
        try:
            kb_manager = self._get_kb_manager()
            kb_id = request.args.get("kb_id")
            if not kb_id:
                return Response().error("缺少参数 kb_id").__dict__

            kb_helper = await kb_manager.get_kb(kb_id)
            if not kb_helper:
                return Response().error("知识库不存在").__dict__

            report = await kb_helper.check_consistency()
            return Response().ok(report).__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"检查知识库一致性失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"检查知识库一致性失败: {e!s}").__dict__

    async def repair_kb_consistency(self):
        """Repair low-risk consistency issues for a knowledge base."""
        try:
            kb_manager = self._get_kb_manager()
            data = await request.json

            kb_id = data.get("kb_id")
            if not kb_id:
                return Response().error("缺少参数 kb_id").__dict__

            repair_types = data.get("repair_types")
            if repair_types is not None and not isinstance(repair_types, list):
                return Response().error("repair_types 格式错误").__dict__

            kb_helper = await kb_manager.get_kb(kb_id)
            if not kb_helper:
                return Response().error("知识库不存在").__dict__

            report = await kb_helper.repair_consistency(repair_types=repair_types)
            return Response().ok(report).__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"修复知识库一致性失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"修复知识库一致性失败: {e!s}").__dict__

    # ===== 文档管理 API =====

    async def list_documents(self):
        """获取文档列表

        Query 参数:
        - kb_id: 知识库 ID (必填)
        - page: 页码 (默认 1)
        - page_size: 每页数量
        """
        try:
            kb_manager = self._get_kb_manager()
            kb_id = request.args.get("kb_id")
            if not kb_id:
                return Response().error("缺少参数 kb_id").__dict__
            kb_helper = await kb_manager.get_kb(kb_id)
            if not kb_helper:
                return Response().error("知识库不存在").__dict__

            page = self._get_positive_query_int("page", 1)
            page_size = self._get_positive_query_int(
                "page_size",
                DEFAULT_DOCUMENT_PAGE_SIZE,
            )
            search = (request.args.get("search") or "").strip() or None
            status = (request.args.get("status") or "").strip() or None
            source_type = (request.args.get("source_type") or "").strip() or None
            if status and status not in DOCUMENT_FILTER_STATUSES:
                return Response().error("status 参数无效").__dict__
            if source_type and source_type not in DOCUMENT_FILTER_SOURCE_TYPES:
                return Response().error("source_type 参数无效").__dict__

            offset = (page - 1) * page_size
            limit = page_size

            doc_list = await kb_helper.list_documents(
                offset=offset,
                limit=limit,
                search=search,
                status=status,
                source_type=source_type,
            )
            total = await kb_helper.count_documents(
                search=search,
                status=status,
                source_type=source_type,
            )
            document_count = total
            if search is not None or status is not None or source_type is not None:
                document_count = await kb_helper.count_documents()

            doc_list = [doc.model_dump() for doc in doc_list]

            return (
                Response()
                .ok(
                    {
                        "items": doc_list,
                        "page": page,
                        "page_size": page_size,
                        "total": total,
                        "filtered_total": total,
                        "document_count": document_count,
                    },
                )
                .__dict__
            )

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"获取文档列表失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"获取文档列表失败: {e!s}").__dict__

    async def upload_document(self):
        """上传文档

        支持两种方式:
        1. multipart/form-data 文件上传（支持多文件，最多10个）
        2. JSON 格式 base64 编码上传（支持多文件，最多10个）

        Form Data (multipart/form-data):
        - kb_id: 知识库 ID (必填)
        - file: 文件对象 (必填，可多个，字段名为 file, file1, file2, ... 或 files[])

        JSON Body (application/json):
        - kb_id: 知识库 ID (必填)
        - files: 文件数组 (必填)
          - file_name: 文件名 (必填)
          - file_content: base64 编码的文件内容 (必填)

        返回:
        - task_id: 任务ID，用于查询上传进度和结果
        """
        try:
            kb_manager = self._get_kb_manager()

            # 检查 Content-Type
            content_type = request.content_type
            kb_id = None
            chunk_size = None
            chunk_overlap = None
            batch_size = None
            tasks_limit = None
            max_retries = None
            files_to_upload = []  # 存储待上传的文件信息列表

            if content_type and "multipart/form-data" not in content_type:
                return (
                    Response().error("Content-Type 须为 multipart/form-data").__dict__
                )
            form_data = await request.form
            files = await request.files

            kb_id = form_data.get("kb_id")
            chunk_size = self._coerce_optional_int(
                form_data.get("chunk_size"),
                "chunk_size",
            )
            chunk_overlap = self._coerce_optional_int(
                form_data.get("chunk_overlap"),
                "chunk_overlap",
            )
            batch_size = self._coerce_optional_int(
                form_data.get("batch_size"),
                "batch_size",
            )
            tasks_limit = self._coerce_optional_int(
                form_data.get("tasks_limit"),
                "tasks_limit",
            )
            max_retries = self._coerce_optional_int(
                form_data.get("max_retries"),
                "max_retries",
            )
            chunk_size = chunk_size if chunk_size is not None else DEFAULT_CHUNK_SIZE
            chunk_overlap = (
                chunk_overlap if chunk_overlap is not None else DEFAULT_CHUNK_OVERLAP
            )
            batch_size = (
                batch_size if batch_size is not None else DEFAULT_UPLOAD_BATCH_SIZE
            )
            tasks_limit = (
                tasks_limit if tasks_limit is not None else DEFAULT_UPLOAD_TASKS_LIMIT
            )
            max_retries = (
                max_retries if max_retries is not None else DEFAULT_UPLOAD_MAX_RETRIES
            )
            self._validate_upload_options(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                batch_size=batch_size,
                tasks_limit=tasks_limit,
                max_retries=max_retries,
            )
            if not kb_id:
                return Response().error("缺少参数 kb_id").__dict__

            # 收集所有文件
            file_list = []
            # 支持 file, file1, file2, ... 或 files[] 格式
            for key in files.keys():
                if key == "file" or key.startswith("file") or key == "files[]":
                    file_items = files.getlist(key)
                    file_list.extend(file_items)

            if not file_list:
                return Response().error("缺少文件").__dict__

            # 限制文件数量
            if len(file_list) > MAX_UPLOAD_FILES:
                return (
                    Response().error(f"最多只能上传{MAX_UPLOAD_FILES}个文件").__dict__
                )

            # 处理每个文件
            for file in file_list:
                file_name = file.filename

                # 保存到临时文件
                temp_file_path = os.path.join(
                    get_astrbot_temp_path(),
                    f"kb_upload_{uuid.uuid4()}_{file_name}",
                )
                await file.save(temp_file_path)

                try:
                    # 异步读取文件内容
                    async with aiofiles.open(temp_file_path, "rb") as f:
                        file_content = await f.read()

                    # 提取文件类型
                    file_type = (
                        file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
                    )
                    self._validate_upload_file(file_name, len(file_content))

                    files_to_upload.append(
                        {
                            "file_name": file_name,
                            "file_content": file_content,
                            "file_type": file_type,
                        },
                    )
                finally:
                    # 清理临时文件
                    if os.path.exists(temp_file_path):
                        os.remove(temp_file_path)

            # 获取知识库
            kb_helper = await kb_manager.get_kb(kb_id)
            if not kb_helper:
                return Response().error("知识库不存在").__dict__

            # 生成任务ID
            task_id = str(uuid.uuid4())

            # 初始化任务状态
            self._init_task(task_id, status="pending")
            await self._create_persistent_task(
                task_id=task_id,
                kb_id=kb_id,
                task_type="upload",
                status="pending",
                progress={
                    "status": "pending",
                    "file_index": 0,
                    "file_total": len(files_to_upload),
                    "stage": "waiting",
                    "current": 0,
                    "total": 100,
                },
            )

            # 启动后台任务
            asyncio.create_task(
                self._background_upload_task(
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

            return (
                Response()
                .ok(
                    {
                        "task_id": task_id,
                        "file_count": len(files_to_upload),
                        "message": "task created, processing in background",
                    },
                )
                .__dict__
            )

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"上传文档失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"上传文档失败: {e!s}").__dict__

    def _validate_import_request(self, data: dict):
        kb_id = data.get("kb_id")
        if not kb_id:
            raise ValueError("缺少参数 kb_id")

        documents = data.get("documents")
        if not documents or not isinstance(documents, list):
            raise ValueError("缺少参数 documents 或格式错误")

        for doc in documents:
            if "file_name" not in doc or "chunks" not in doc:
                raise ValueError("文档格式错误，必须包含 file_name 和 chunks")
            if not isinstance(doc["chunks"], list):
                raise ValueError("chunks 必须是列表")
            if not all(
                isinstance(chunk, str) and chunk.strip() for chunk in doc["chunks"]
            ):
                raise ValueError("chunks 必须是非空字符串列表")

        batch_size = self._coerce_optional_int(data.get("batch_size"), "batch_size")
        tasks_limit = self._coerce_optional_int(data.get("tasks_limit"), "tasks_limit")
        max_retries = self._coerce_optional_int(data.get("max_retries"), "max_retries")
        batch_size = batch_size if batch_size is not None else DEFAULT_UPLOAD_BATCH_SIZE
        tasks_limit = (
            tasks_limit if tasks_limit is not None else DEFAULT_UPLOAD_TASKS_LIMIT
        )
        max_retries = (
            max_retries if max_retries is not None else DEFAULT_UPLOAD_MAX_RETRIES
        )
        self._validate_positive_int(batch_size, "batch_size")
        self._validate_positive_int(tasks_limit, "tasks_limit")
        if max_retries < 0:
            raise ValueError("max_retries 不能为负数")
        return kb_id, documents, batch_size, tasks_limit, max_retries

    async def import_documents(self):
        """导入预切片文档

        Body:
        - kb_id: 知识库 ID (必填)
        - documents: 文档列表 (必填)
            - file_name: 文件名 (必填)
            - chunks: 切片列表 (必填, list[str])
            - file_type: 文件类型 (可选, 默认从文件名推断或为 txt)
        - batch_size: 批处理大小 (可选, 默认32)
        - tasks_limit: 并发任务限制 (可选, 默认3)
        - max_retries: 最大重试次数 (可选, 默认3)
        """
        try:
            kb_manager = self._get_kb_manager()
            data = await request.json

            kb_id, documents, batch_size, tasks_limit, max_retries = (
                self._validate_import_request(data)
            )

            # 获取知识库
            kb_helper = await kb_manager.get_kb(kb_id)
            if not kb_helper:
                return Response().error("知识库不存在").__dict__

            # 生成任务ID
            task_id = str(uuid.uuid4())

            # 初始化任务状态
            self._init_task(task_id, status="pending")
            await self._create_persistent_task(
                task_id=task_id,
                kb_id=kb_id,
                task_type="import",
                status="pending",
                progress={
                    "status": "pending",
                    "file_index": 0,
                    "file_total": len(documents),
                    "stage": "waiting",
                    "current": 0,
                    "total": 100,
                },
            )

            # 启动后台任务
            asyncio.create_task(
                self._background_import_task(
                    task_id=task_id,
                    kb_helper=kb_helper,
                    documents=documents,
                    batch_size=batch_size,
                    tasks_limit=tasks_limit,
                    max_retries=max_retries,
                ),
            )

            return (
                Response()
                .ok(
                    {
                        "task_id": task_id,
                        "doc_count": len(documents),
                        "message": "import task created, processing in background",
                    },
                )
                .__dict__
            )

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"导入文档失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"导入文档失败: {e!s}").__dict__

    async def get_upload_progress(self):
        """获取上传进度和结果

        Query 参数:
        - task_id: 任务 ID (必填)

        返回状态:
        - pending: 任务待处理
        - processing: 任务处理中
        - completed: 任务完成
        - failed: 任务失败
        """
        try:
            task_id = request.args.get("task_id")
            if not task_id:
                return Response().error("缺少参数 task_id").__dict__

            # 检查任务是否存在
            if task_id not in self.upload_tasks:
                persistent_task = await self._get_persistent_task(task_id)
                if persistent_task is None:
                    return Response().error("找不到该任务").__dict__
                response_data = {
                    "task_id": task_id,
                    "status": persistent_task["status"],
                    "progress_stage": persistent_task.get("progress_stage"),
                    "progress_current": persistent_task.get("progress_current", 0),
                    "progress_total": persistent_task.get("progress_total", 100),
                }
                if persistent_task.get("progress") is not None:
                    response_data["progress"] = persistent_task["progress"]
                if persistent_task["status"] in ("completed", "failed"):
                    response_data["result"] = persistent_task.get("result")
                if persistent_task["status"] == "failed":
                    response_data["error"] = persistent_task.get("error")
                return Response().ok(response_data).__dict__

            task_info = self.upload_tasks[task_id]
            status = task_info["status"]

            # 构建返回数据
            response_data = {
                "task_id": task_id,
                "status": status,
            }

            # 如果任务正在处理，返回进度信息
            if status == "processing" and task_id in self.upload_progress:
                response_data["progress"] = self.upload_progress[task_id]

            # 如果任务完成，返回结果
            if status in ("completed", "failed"):
                response_data["result"] = task_info["result"]

            # 如果任务失败，返回错误信息
            if status == "failed":
                response_data["error"] = task_info["error"]

            # 清理已完成/失败的任务，释放内存
            if status in ("completed", "failed"):
                self._cleanup_task(task_id)

            return Response().ok(response_data).__dict__

        except Exception as e:
            logger.error(f"获取上传进度失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"获取上传进度失败: {e!s}").__dict__

    async def get_task(self):
        """获取知识库持久任务详情"""
        try:
            task_id = request.args.get("task_id")
            if not task_id:
                return Response().error("缺少参数 task_id").__dict__

            task = await self._get_persistent_task(task_id)
            if not task:
                return Response().error("任务不存在").__dict__
            return Response().ok(task).__dict__

        except Exception as e:
            logger.error(f"获取知识库任务失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"获取知识库任务失败: {e!s}").__dict__

    async def list_tasks(self):
        """列出知识库持久任务"""
        try:
            kb_db = self._get_kb_db()
            if not kb_db:
                return Response().error("知识库数据库未初始化").__dict__

            page = self._get_positive_query_int("page", 1)
            page_size = self._get_positive_query_int(
                "page_size",
                DEFAULT_DOCUMENT_PAGE_SIZE,
            )
            kb_id = (request.args.get("kb_id") or "").strip() or None
            status = (request.args.get("status") or "").strip() or None
            task_type = (request.args.get("task_type") or "").strip() or None

            tasks = await kb_db.list_ingestion_tasks(
                kb_id=kb_id,
                status=status,
                task_type=task_type,
                offset=(page - 1) * page_size,
                limit=page_size,
            )
            total = await kb_db.count_ingestion_tasks(
                kb_id=kb_id,
                status=status,
                task_type=task_type,
            )
            return (
                Response()
                .ok(
                    {
                        "items": tasks,
                        "total": total,
                        "page": page,
                        "page_size": page_size,
                    },
                )
                .__dict__
            )

        except Exception as e:
            logger.error(f"获取知识库任务列表失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"获取知识库任务列表失败: {e!s}").__dict__

    async def get_document(self):
        """获取文档详情

        Query 参数:
        - doc_id: 文档 ID (必填)
        """
        try:
            kb_manager = self._get_kb_manager()
            kb_id = request.args.get("kb_id")
            if not kb_id:
                return Response().error("缺少参数 kb_id").__dict__
            doc_id = request.args.get("doc_id")
            if not doc_id:
                return Response().error("缺少参数 doc_id").__dict__
            kb_helper = await kb_manager.get_kb(kb_id)
            if not kb_helper:
                return Response().error("知识库不存在").__dict__

            doc = await kb_helper.get_document(doc_id)
            if not doc:
                return Response().error("文档不存在").__dict__

            return Response().ok(doc.model_dump()).__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"获取文档详情失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"获取文档详情失败: {e!s}").__dict__

    async def delete_document(self):
        """删除文档

        Body:
        - kb_id: 知识库 ID (必填)
        - doc_id: 文档 ID (必填)
        """
        try:
            kb_manager = self._get_kb_manager()
            data = await request.json

            kb_id = data.get("kb_id")
            if not kb_id:
                return Response().error("缺少参数 kb_id").__dict__
            doc_id = data.get("doc_id")
            if not doc_id:
                return Response().error("缺少参数 doc_id").__dict__

            kb_helper = await kb_manager.get_kb(kb_id)
            if not kb_helper:
                return Response().error("知识库不存在").__dict__

            await kb_helper.delete_document(doc_id)
            return Response().ok(message="删除文档成功").__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"删除文档失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"删除文档失败: {e!s}").__dict__

    async def rebuild_document(self):
        """重建单个文档"""
        try:
            kb_manager = self._get_kb_manager()
            data = await request.json

            kb_id = data.get("kb_id")
            if not kb_id:
                return Response().error("缺少参数 kb_id").__dict__
            doc_id = data.get("doc_id")
            if not doc_id:
                return Response().error("缺少参数 doc_id").__dict__

            chunk_size = self._coerce_optional_int(data.get("chunk_size"), "chunk_size")
            chunk_overlap = self._coerce_optional_int(
                data.get("chunk_overlap"),
                "chunk_overlap",
            )
            batch_size = self._coerce_optional_int(data.get("batch_size"), "batch_size")
            tasks_limit = self._coerce_optional_int(
                data.get("tasks_limit"),
                "tasks_limit",
            )
            max_retries = self._coerce_optional_int(
                data.get("max_retries"),
                "max_retries",
            )
            effective_chunk_size = (
                chunk_size if chunk_size is not None else DEFAULT_CHUNK_SIZE
            )
            effective_chunk_overlap = (
                chunk_overlap if chunk_overlap is not None else DEFAULT_CHUNK_OVERLAP
            )
            effective_batch_size = (
                batch_size if batch_size is not None else DEFAULT_UPLOAD_BATCH_SIZE
            )
            effective_tasks_limit = (
                tasks_limit if tasks_limit is not None else DEFAULT_UPLOAD_TASKS_LIMIT
            )
            effective_max_retries = (
                max_retries if max_retries is not None else DEFAULT_UPLOAD_MAX_RETRIES
            )
            self._validate_upload_options(
                chunk_size=effective_chunk_size,
                chunk_overlap=effective_chunk_overlap,
                batch_size=effective_batch_size,
                tasks_limit=effective_tasks_limit,
                max_retries=effective_max_retries,
            )
            background = self._coerce_optional_bool(
                data.get("background"),
                "background",
            )

            kb_helper = await kb_manager.get_kb(kb_id)
            if not kb_helper:
                return Response().error("知识库不存在").__dict__

            if background:
                task_id = str(uuid.uuid4())
                self._init_task(task_id, status="pending")
                await self._create_persistent_task(
                    task_id=task_id,
                    kb_id=kb_id,
                    task_type="document_rebuild",
                    status="pending",
                    progress={
                        "status": "pending",
                        "file_index": 0,
                        "file_total": 1,
                        "file_name": doc_id,
                        "stage": "waiting",
                        "current": 0,
                        "total": 100,
                    },
                )
                asyncio.create_task(
                    self._background_rebuild_document_task(
                        task_id=task_id,
                        kb_helper=kb_helper,
                        doc_id=doc_id,
                        chunk_size=chunk_size,
                        chunk_overlap=chunk_overlap,
                        batch_size=effective_batch_size,
                        tasks_limit=effective_tasks_limit,
                        max_retries=effective_max_retries,
                    ),
                )
                return (
                    Response()
                    .ok(
                        {
                            "task_id": task_id,
                            "doc_id": doc_id,
                            "message": (
                                "document rebuild task created, "
                                "processing in background"
                            ),
                        },
                    )
                    .__dict__
                )

            doc = await kb_helper.rebuild_document(
                doc_id,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                batch_size=effective_batch_size,
                tasks_limit=effective_tasks_limit,
                max_retries=effective_max_retries,
            )
            return Response().ok(doc.model_dump(), "重建文档成功").__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"重建文档失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"重建文档失败: {e!s}").__dict__

    async def rebuild_kb(self):
        """重建整个知识库"""
        try:
            kb_manager = self._get_kb_manager()
            data = await request.json

            kb_id = data.get("kb_id")
            if not kb_id:
                return Response().error("缺少参数 kb_id").__dict__

            chunk_size = self._coerce_optional_int(data.get("chunk_size"), "chunk_size")
            chunk_overlap = self._coerce_optional_int(
                data.get("chunk_overlap"),
                "chunk_overlap",
            )
            batch_size = self._coerce_optional_int(data.get("batch_size"), "batch_size")
            tasks_limit = self._coerce_optional_int(
                data.get("tasks_limit"),
                "tasks_limit",
            )
            max_retries = self._coerce_optional_int(
                data.get("max_retries"),
                "max_retries",
            )
            effective_chunk_size = (
                chunk_size if chunk_size is not None else DEFAULT_CHUNK_SIZE
            )
            effective_chunk_overlap = (
                chunk_overlap if chunk_overlap is not None else DEFAULT_CHUNK_OVERLAP
            )
            effective_batch_size = (
                batch_size if batch_size is not None else DEFAULT_UPLOAD_BATCH_SIZE
            )
            effective_tasks_limit = (
                tasks_limit if tasks_limit is not None else DEFAULT_UPLOAD_TASKS_LIMIT
            )
            effective_max_retries = (
                max_retries if max_retries is not None else DEFAULT_UPLOAD_MAX_RETRIES
            )
            self._validate_upload_options(
                chunk_size=effective_chunk_size,
                chunk_overlap=effective_chunk_overlap,
                batch_size=effective_batch_size,
                tasks_limit=effective_tasks_limit,
                max_retries=effective_max_retries,
            )
            background = self._coerce_optional_bool(
                data.get("background"),
                "background",
            )

            kb_helper = await kb_manager.get_kb(kb_id)
            if not kb_helper:
                return Response().error("知识库不存在").__dict__

            if background:
                kb_name = getattr(
                    getattr(kb_helper, "kb", None),
                    "kb_name",
                    "knowledge base",
                )
                task_id = str(uuid.uuid4())
                self._init_task(task_id, status="pending")
                await self._create_persistent_task(
                    task_id=task_id,
                    kb_id=kb_id,
                    task_type="kb_rebuild",
                    status="pending",
                    progress={
                        "status": "pending",
                        "file_index": 0,
                        "file_total": 1,
                        "file_name": kb_name,
                        "stage": "waiting",
                        "current": 0,
                        "total": 100,
                    },
                )
                asyncio.create_task(
                    self._background_rebuild_kb_task(
                        task_id=task_id,
                        kb_helper=kb_helper,
                        chunk_size=chunk_size,
                        chunk_overlap=chunk_overlap,
                        batch_size=effective_batch_size,
                        tasks_limit=effective_tasks_limit,
                        max_retries=effective_max_retries,
                    ),
                )
                return (
                    Response()
                    .ok(
                        {
                            "task_id": task_id,
                            "kb_id": kb_id,
                            "message": (
                                "knowledge base rebuild task created, "
                                "processing in background"
                            ),
                        },
                    )
                    .__dict__
                )

            result = await kb_helper.rebuild_all_documents(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                batch_size=effective_batch_size,
                tasks_limit=effective_tasks_limit,
                max_retries=effective_max_retries,
            )
            return Response().ok(result, "重建知识库完成").__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"重建知识库失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"重建知识库失败: {e!s}").__dict__

    async def batch_rebuild_documents(self):
        """Start a background task to rebuild selected documents.

        Body:
        - kb_id: knowledge base ID (required)
        - doc_ids: document ID list (required)
        """
        try:
            kb_manager = self._get_kb_manager()
            data = await request.json

            kb_id = data.get("kb_id")
            if not kb_id:
                return Response().error("缺少参数 kb_id").__dict__
            doc_ids = data.get("doc_ids")
            if not doc_ids or not isinstance(doc_ids, list):
                return Response().error("缺少参数 doc_ids 或格式错误").__dict__
            normalized_doc_ids = list(
                dict.fromkeys(
                    doc_id.strip()
                    for doc_id in doc_ids
                    if isinstance(doc_id, str) and doc_id.strip()
                )
            )
            if not normalized_doc_ids:
                return Response().error("缺少参数 doc_ids 或格式错误").__dict__
            if len(normalized_doc_ids) > MAX_BATCH_REBUILD_DOCUMENTS:
                return (
                    Response()
                    .error(f"最多只能批量重建 {MAX_BATCH_REBUILD_DOCUMENTS} 个文档")
                    .__dict__
                )

            chunk_size = self._coerce_optional_int(data.get("chunk_size"), "chunk_size")
            chunk_overlap = self._coerce_optional_int(
                data.get("chunk_overlap"),
                "chunk_overlap",
            )
            batch_size = self._coerce_optional_int(data.get("batch_size"), "batch_size")
            tasks_limit = self._coerce_optional_int(
                data.get("tasks_limit"),
                "tasks_limit",
            )
            max_retries = self._coerce_optional_int(
                data.get("max_retries"),
                "max_retries",
            )
            effective_chunk_size = (
                chunk_size if chunk_size is not None else DEFAULT_CHUNK_SIZE
            )
            effective_chunk_overlap = (
                chunk_overlap if chunk_overlap is not None else DEFAULT_CHUNK_OVERLAP
            )
            effective_batch_size = (
                batch_size if batch_size is not None else DEFAULT_UPLOAD_BATCH_SIZE
            )
            effective_tasks_limit = (
                tasks_limit if tasks_limit is not None else DEFAULT_UPLOAD_TASKS_LIMIT
            )
            effective_max_retries = (
                max_retries if max_retries is not None else DEFAULT_UPLOAD_MAX_RETRIES
            )
            self._validate_upload_options(
                chunk_size=effective_chunk_size,
                chunk_overlap=effective_chunk_overlap,
                batch_size=effective_batch_size,
                tasks_limit=effective_tasks_limit,
                max_retries=effective_max_retries,
            )

            kb_helper = await kb_manager.get_kb(kb_id)
            if not kb_helper:
                return Response().error("知识库不存在").__dict__

            task_id = str(uuid.uuid4())
            self._init_task(task_id, status="pending")
            await self._create_persistent_task(
                task_id=task_id,
                kb_id=kb_id,
                task_type="document_batch_rebuild",
                status="pending",
                progress={
                    "status": "pending",
                    "file_index": 0,
                    "file_total": len(normalized_doc_ids),
                    "file_name": f"{len(normalized_doc_ids)} selected documents",
                    "stage": "waiting",
                    "current": 0,
                    "total": len(normalized_doc_ids),
                },
            )
            asyncio.create_task(
                self._background_rebuild_documents_task(
                    task_id=task_id,
                    kb_helper=kb_helper,
                    doc_ids=normalized_doc_ids,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                    batch_size=effective_batch_size,
                    tasks_limit=effective_tasks_limit,
                    max_retries=effective_max_retries,
                ),
            )
            return (
                Response()
                .ok(
                    {
                        "task_id": task_id,
                        "doc_ids": normalized_doc_ids,
                        "message": (
                            "document batch rebuild task created, "
                            "processing in background"
                        ),
                    },
                )
                .__dict__
            )

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"批量重建文档失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"批量重建文档失败: {e!s}").__dict__

    async def batch_delete_documents(self):
        """批量删除文档

        Body:
        - kb_id: 知识库 ID (必填)
        - doc_ids: 文档 ID 列表 (必填, 最多 100 个)
        """
        try:
            kb_manager = self._get_kb_manager()
            data = await request.json

            kb_id = data.get("kb_id")
            if not kb_id:
                return Response().error("缺少参数 kb_id").__dict__
            doc_ids = data.get("doc_ids")
            if not doc_ids or not isinstance(doc_ids, list):
                return Response().error("缺少参数 doc_ids 或格式错误").__dict__
            if len(doc_ids) > MAX_BATCH_DELETE_DOCUMENTS:
                return (
                    Response()
                    .error(f"最多只能批量删除 {MAX_BATCH_DELETE_DOCUMENTS} 个文档")
                    .__dict__
                )

            kb_helper = await kb_manager.get_kb(kb_id)
            if not kb_helper:
                return Response().error("知识库不存在").__dict__

            results = await kb_helper.delete_documents(doc_ids)

            success_count = sum(1 for v in results.values() if v)
            failed_count = len(doc_ids) - success_count

            return (
                Response()
                .ok(
                    {
                        "results": results,
                        "total": len(doc_ids),
                        "success_count": success_count,
                        "failed_count": failed_count,
                    },
                    "批量删除完成",
                )
                .__dict__
            )

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"批量删除文档失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"批量删除文档失败: {e!s}").__dict__

    async def delete_chunk(self):
        """删除文本块

        Body:
        - kb_id: 知识库 ID (必填)
        - chunk_id: 块 ID (必填)
        """
        try:
            kb_manager = self._get_kb_manager()
            data = await request.json

            kb_id = data.get("kb_id")
            if not kb_id:
                return Response().error("缺少参数 kb_id").__dict__
            chunk_id = data.get("chunk_id")
            if not chunk_id:
                return Response().error("缺少参数 chunk_id").__dict__
            doc_id = data.get("doc_id")
            if not doc_id:
                return Response().error("缺少参数 doc_id").__dict__

            kb_helper = await kb_manager.get_kb(kb_id)
            if not kb_helper:
                return Response().error("知识库不存在").__dict__

            await kb_helper.delete_chunk(chunk_id, doc_id)
            return Response().ok(message="删除文本块成功").__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"删除文本块失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"删除文本块失败: {e!s}").__dict__

    async def list_chunks(self):
        """获取块列表

        Query 参数:
        - kb_id: 知识库 ID (必填)
        - page: 页码 (默认 1)
        - page_size: 每页数量
        """
        try:
            kb_manager = self._get_kb_manager()
            kb_id = request.args.get("kb_id")
            doc_id = request.args.get("doc_id")
            page = self._get_positive_query_int("page", 1)
            page_size = self._get_positive_query_int(
                "page_size",
                DEFAULT_CHUNK_PAGE_SIZE,
            )
            search = (request.args.get("search") or "").strip() or None
            if not kb_id:
                return Response().error("缺少参数 kb_id").__dict__
            if not doc_id:
                return Response().error("缺少参数 doc_id").__dict__
            kb_helper = await kb_manager.get_kb(kb_id)
            offset = (page - 1) * page_size
            limit = page_size
            if not kb_helper:
                return Response().error("知识库不存在").__dict__
            chunk_list, total = await kb_helper.search_chunks_by_doc_id(
                doc_id=doc_id,
                search=search,
                offset=offset,
                limit=limit,
            )
            document_chunk_count = total
            if search is not None:
                document_chunk_count = await kb_helper.get_chunk_count_by_doc_id(doc_id)
            return (
                Response()
                .ok(
                    data={
                        "items": chunk_list,
                        "page": page,
                        "page_size": page_size,
                        "total": total,
                        "filtered_total": total,
                        "document_chunk_count": document_chunk_count,
                    },
                )
                .__dict__
            )
        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"获取块列表失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"获取块列表失败: {e!s}").__dict__

    async def get_chunk_context(self):
        """获取文本块和相邻上下文块

        Query 参数:
        - kb_id: 知识库 ID (必填)
        - doc_id: 文档 ID (必填)
        - chunk_id: 文本块 ID (必填)
        """
        try:
            kb_manager = self._get_kb_manager()
            kb_id = request.args.get("kb_id")
            doc_id = request.args.get("doc_id")
            chunk_id = request.args.get("chunk_id")
            if not kb_id:
                return Response().error("缺少参数 kb_id").__dict__
            if not doc_id:
                return Response().error("缺少参数 doc_id").__dict__
            if not chunk_id:
                return Response().error("缺少参数 chunk_id").__dict__

            kb_helper = await kb_manager.get_kb(kb_id)
            if not kb_helper:
                return Response().error("知识库不存在").__dict__
            context = await kb_helper.get_chunk_context(
                chunk_id=chunk_id,
                doc_id=doc_id,
            )
            return Response().ok(data=context).__dict__
        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"获取文本块上下文失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"获取文本块上下文失败: {e!s}").__dict__

    # ===== 检索 API =====

    async def retrieve(self):
        """检索知识库

        Body:
        - query: 查询文本 (必填)
        - kb_ids: 知识库 ID 列表 (必填)
        - top_k: 返回结果数量 (可选, 默认 5)
        - debug: 是否启用调试模式，返回 t-SNE 可视化图片 (可选, 默认 False)
        """
        try:
            kb_manager = self._get_kb_manager()
            data = await request.json

            query = data.get("query")
            kb_ids = data.get("kb_ids")
            kb_names = data.get("kb_names")
            debug = self._coerce_optional_bool(data.get("debug", False), "debug")
            trace = self._coerce_optional_bool(data.get("trace", False), "trace")

            if not query:
                return Response().error("缺少参数 query").__dict__
            if kb_ids is not None and not isinstance(kb_ids, list):
                return Response().error("参数 kb_ids 格式错误").__dict__
            if kb_names is not None and not isinstance(kb_names, list):
                return Response().error("参数 kb_names 格式错误").__dict__
            if not kb_ids and not kb_names:
                return Response().error("缺少参数 kb_ids 或 kb_names").__dict__

            top_k = self._coerce_optional_int(
                data.get("top_k", DEFAULT_TOP_M_FINAL),
                "top_k",
            )
            top_k = top_k if top_k is not None else DEFAULT_TOP_M_FINAL
            self._validate_positive_int(top_k, "top_k")
            if top_k > MAX_RETRIEVE_TOP_K:
                return Response().error(f"top_k 不能大于 {MAX_RETRIEVE_TOP_K}").__dict__

            results = await kb_manager.retrieve(
                query=query,
                kb_names=kb_names,
                kb_ids=kb_ids,
                top_m_final=top_k,
                include_trace=trace or debug,
            )
            result_list = []
            if results:
                result_list = results["results"]

            response_data = {
                "results": result_list,
                "total": len(result_list),
                "query": query,
            }
            if results and "trace" in results:
                response_data["trace"] = results["trace"]

            # Debug 模式：生成 t-SNE 可视化
            if debug:
                try:
                    visualization_kb_names = kb_names
                    if not visualization_kb_names and kb_ids:
                        visualization_kb_names = []
                        for kb_id in kb_ids:
                            if kb_helper := await kb_manager.get_kb(kb_id):
                                visualization_kb_names.append(kb_helper.kb.kb_name)
                    img_base64 = await generate_tsne_visualization(
                        query,
                        visualization_kb_names or [],
                        kb_manager,
                    )
                    if img_base64:
                        response_data["visualization"] = img_base64
                except Exception as e:
                    logger.error(f"生成 t-SNE 可视化失败: {e}")
                    logger.error(traceback.format_exc())
                    response_data["visualization_error"] = str(e)

            return Response().ok(response_data).__dict__

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"检索失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"检索失败: {e!s}").__dict__

    async def upload_document_from_url(self):
        """从 URL 上传文档

        Body:
        - kb_id: 知识库 ID (必填)
        - url: 要提取内容的网页 URL (必填)
        - chunk_size: 分块大小 (可选, 默认512)
        - chunk_overlap: 块重叠大小 (可选, 默认50)
        - batch_size: 批处理大小 (可选, 默认32)
        - tasks_limit: 并发任务限制 (可选, 默认3)
        - max_retries: 最大重试次数 (可选, 默认3)

        返回:
        - task_id: 任务ID，用于查询上传进度和结果
        """
        try:
            kb_manager = self._get_kb_manager()
            data = await request.json

            kb_id = data.get("kb_id")
            if not kb_id:
                return Response().error("缺少参数 kb_id").__dict__

            url = data.get("url")
            if not url:
                return Response().error("缺少参数 url").__dict__

            chunk_size = self._coerce_optional_int(data.get("chunk_size"), "chunk_size")
            chunk_overlap = self._coerce_optional_int(
                data.get("chunk_overlap"),
                "chunk_overlap",
            )
            batch_size = self._coerce_optional_int(data.get("batch_size"), "batch_size")
            tasks_limit = self._coerce_optional_int(
                data.get("tasks_limit"),
                "tasks_limit",
            )
            max_retries = self._coerce_optional_int(
                data.get("max_retries"),
                "max_retries",
            )
            chunk_size = chunk_size if chunk_size is not None else DEFAULT_CHUNK_SIZE
            chunk_overlap = (
                chunk_overlap if chunk_overlap is not None else DEFAULT_CHUNK_OVERLAP
            )
            batch_size = (
                batch_size if batch_size is not None else DEFAULT_UPLOAD_BATCH_SIZE
            )
            tasks_limit = (
                tasks_limit if tasks_limit is not None else DEFAULT_UPLOAD_TASKS_LIMIT
            )
            max_retries = (
                max_retries if max_retries is not None else DEFAULT_UPLOAD_MAX_RETRIES
            )
            self._validate_upload_options(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                batch_size=batch_size,
                tasks_limit=tasks_limit,
                max_retries=max_retries,
            )
            enable_cleaning = data.get("enable_cleaning", False)
            cleaning_provider_id = data.get("cleaning_provider_id")

            # 获取知识库
            kb_helper = await kb_manager.get_kb(kb_id)
            if not kb_helper:
                return Response().error("知识库不存在").__dict__

            # 生成任务ID
            task_id = str(uuid.uuid4())

            # 初始化任务状态
            self._init_task(task_id, status="pending")
            await self._create_persistent_task(
                task_id=task_id,
                kb_id=kb_id,
                task_type="url",
                status="pending",
                progress={
                    "status": "pending",
                    "file_index": 0,
                    "file_total": 1,
                    "file_name": f"URL: {url}",
                    "stage": "waiting",
                    "current": 0,
                    "total": 100,
                },
            )

            # 启动后台任务
            asyncio.create_task(
                self._background_upload_from_url_task(
                    task_id=task_id,
                    kb_helper=kb_helper,
                    url=url,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                    batch_size=batch_size,
                    tasks_limit=tasks_limit,
                    max_retries=max_retries,
                    enable_cleaning=enable_cleaning,
                    cleaning_provider_id=cleaning_provider_id,
                ),
            )

            return (
                Response()
                .ok(
                    {
                        "task_id": task_id,
                        "url": url,
                        "message": "URL upload task created, processing in background",
                    },
                )
                .__dict__
            )

        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"从URL上传文档失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"从URL上传文档失败: {e!s}").__dict__

    async def _background_upload_from_url_task(
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
        """后台上传URL任务"""
        try:
            # 初始化任务状态
            self._init_task(task_id, status="processing")
            self.upload_progress[task_id] = {
                "status": "processing",
                "file_index": 0,
                "file_total": 1,
                "file_name": f"URL: {url}",
                "stage": "extracting",
                "current": 0,
                "total": 100,
            }
            await self._persist_progress(task_id)

            # 创建进度回调函数
            progress_callback = self._make_progress_callback(task_id, 0, f"URL: {url}")

            # 上传文档
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

            # 更新任务完成状态
            result = {
                "task_id": task_id,
                "uploaded": [doc.model_dump()],
                "failed": [],
                "total": 1,
                "success_count": 1,
                "failed_count": 0,
            }

            self._set_task_result(task_id, "completed", result=result)
            await self._update_persistent_task(
                task_id,
                status="completed",
                result=result,
                error=None,
                **self._get_persistent_progress_updates(task_id),
            )

        except Exception as e:
            logger.error(f"后台上传URL任务 {task_id} 失败: {e}")
            logger.error(traceback.format_exc())
            self._set_task_result(task_id, "failed", error=str(e))
            await self._update_persistent_task(
                task_id,
                status="failed",
                error=str(e),
                **self._get_persistent_progress_updates(task_id),
            )
        finally:
            asyncio.create_task(self._schedule_delayed_cleanup(task_id))
