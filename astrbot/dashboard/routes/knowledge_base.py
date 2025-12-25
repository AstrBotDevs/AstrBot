"""知识库管理 API 路由"""

from astrbot.core.core_lifecycle import AstrBotCoreLifecycle

from ..services.knowledge_base import KnowledgeBaseService
from .route import Route, RouteContext


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
        self.kb_service = KnowledgeBaseService(core_lifecycle)

        # 注册路由
        self.routes = {
            # 知识库管理
            "/kb/list": ("GET", self.kb_service.list_kbs),
            "/kb/create": ("POST", self.kb_service.create_kb),
            "/kb/get": ("GET", self.kb_service.get_kb),
            "/kb/update": ("POST", self.kb_service.update_kb),
            "/kb/delete": ("POST", self.kb_service.delete_kb),
            "/kb/stats": ("GET", self.kb_service.get_kb_stats),
            # 文档管理
            "/kb/document/list": ("GET", self.kb_service.list_documents),
            "/kb/document/upload": ("POST", self.kb_service.upload_document),
            "/kb/document/import": ("POST", self.kb_service.import_documents),
            "/kb/document/upload/url": (
                "POST",
                self.kb_service.upload_document_from_url,
            ),
            "/kb/document/upload/progress": (
                "GET",
                self.kb_service.get_upload_progress,
            ),
            "/kb/document/get": ("GET", self.kb_service.get_document),
            "/kb/document/delete": ("POST", self.kb_service.delete_document),
            # # 块管理
            "/kb/chunk/list": ("GET", self.kb_service.list_chunks),
            "/kb/chunk/delete": ("POST", self.kb_service.delete_chunk),
            # 检索
            "/kb/retrieve": ("POST", self.kb_service.retrieve),
        }
        self.register_routes()
