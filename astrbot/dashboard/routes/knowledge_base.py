"""知识库管理 API 路由"""

from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.dashboard.fastapi_compat import request
from astrbot.dashboard.services.knowledge_base_service import (
    KnowledgeBaseService,
    KnowledgeBaseServiceError,
)

from .route import Response, Route, RouteContext


class KnowledgeBaseRoute(Route):
    """知识库管理路由"""

    def __init__(
        self,
        context: RouteContext,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.service = KnowledgeBaseService(core_lifecycle)

        self.routes = {
            "/kb/list": ("GET", self.list_kbs),
            "/kb/create": ("POST", self.create_kb),
            "/kb/get": ("GET", self.get_kb),
            "/kb/update": ("POST", self.update_kb),
            "/kb/delete": ("POST", self.delete_kb),
            "/kb/stats": ("GET", self.get_kb_stats),
            "/kb/document/list": ("GET", self.list_documents),
            "/kb/document/upload": ("POST", self.upload_document),
            "/kb/document/import": ("POST", self.import_documents),
            "/kb/document/upload/url": ("POST", self.upload_document_from_url),
            "/kb/document/upload/progress": ("GET", self.get_upload_progress),
            "/kb/document/get": ("GET", self.get_document),
            "/kb/document/delete": ("POST", self.delete_document),
            "/kb/chunk/list": ("GET", self.list_chunks),
            "/kb/chunk/delete": ("POST", self.delete_chunk),
            "/kb/retrieve": ("POST", self.retrieve),
        }
        self.register_routes()

    @staticmethod
    def _ok(data: dict | list | None = None, message: str | None = None) -> dict:
        return Response().ok(data, message).__dict__

    @staticmethod
    def _error(message: str) -> dict:
        return Response().error(message).__dict__

    @staticmethod
    async def _json_body() -> dict:
        data = await request.get_json()
        return data if isinstance(data, dict) else {}

    async def _run(self, operation, *, prefix: str):
        try:
            result = operation() if callable(operation) else operation
            while hasattr(result, "__await__"):
                result = await result
            if isinstance(result, tuple):
                data, message = result
                return self._ok(data, message)
            return self._ok(result)
        except (KnowledgeBaseServiceError, ValueError) as exc:
            return self._error(str(exc))
        except Exception as exc:
            logger.error("%s: %s", prefix, exc, exc_info=True)
            return self._error(f"{prefix}: {exc!s}")

    async def _run_json(self, operation, *, prefix: str):
        async def invoke():
            data = await self._json_body()
            return operation(data)

        return await self._run(invoke, prefix=prefix)

    async def list_kbs(self):
        return await self._run(
            self.service.list_kbs_from_legacy_query(
                page=request.args.get("page", 1),
                page_size=request.args.get("page_size", 20),
            ),
            prefix="获取知识库列表失败",
        )

    async def create_kb(self):
        return await self._run_json(self.service.create_kb, prefix="创建知识库失败")

    async def get_kb(self):
        return await self._run(
            self.service.get_kb_from_legacy_query(request.args.get("kb_id")),
            prefix="获取知识库详情失败",
        )

    async def update_kb(self):
        return await self._run_json(self.service.update_kb, prefix="更新知识库失败")

    async def delete_kb(self):
        return await self._run_json(self.service.delete_kb, prefix="删除知识库失败")

    async def get_kb_stats(self):
        return await self._run(
            self.service.get_kb_stats_from_legacy_query(request.args.get("kb_id")),
            prefix="获取知识库统计失败",
        )

    async def list_documents(self):
        return await self._run(
            self.service.list_documents_from_legacy_query(
                kb_id=request.args.get("kb_id"),
                page=request.args.get("page", 1),
                page_size=request.args.get("page_size", 100),
            ),
            prefix="获取文档列表失败",
        )

    async def upload_document(self):
        async def _operation():
            form_data = await request.form
            files = await request.files
            return await self.service.upload_document(
                content_type=request.content_type,
                form_data=form_data,
                files=files,
            )

        return await self._run(_operation, prefix="上传文档失败")

    async def import_documents(self):
        return await self._run_json(
            self.service.import_documents,
            prefix="导入文档失败",
        )

    async def get_upload_progress(self):
        return await self._run(
            lambda: self.service.get_upload_progress_from_legacy_query(
                request.args.get("task_id")
            ),
            prefix="获取上传进度失败",
        )

    async def get_document(self):
        return await self._run(
            self.service.get_document_from_legacy_query(
                kb_id=request.args.get("kb_id"),
                doc_id=request.args.get("doc_id"),
            ),
            prefix="获取文档详情失败",
        )

    async def delete_document(self):
        return await self._run_json(
            self.service.delete_document,
            prefix="删除文档失败",
        )

    async def delete_chunk(self):
        return await self._run_json(
            self.service.delete_chunk,
            prefix="删除文本块失败",
        )

    async def list_chunks(self):
        return await self._run(
            self.service.list_chunks_from_legacy_query(
                kb_id=request.args.get("kb_id"),
                doc_id=request.args.get("doc_id"),
                page=request.args.get("page", 1),
                page_size=request.args.get("page_size", 100),
            ),
            prefix="获取块列表失败",
        )

    async def retrieve(self):
        return await self._run_json(self.service.retrieve, prefix="检索失败")

    async def upload_document_from_url(self):
        return await self._run_json(
            self.service.upload_document_from_url,
            prefix="从URL上传文档失败",
        )


__all__ = ["KnowledgeBaseRoute"]
