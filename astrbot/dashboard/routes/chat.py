from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase

from ..services.chat import ChatService
from .route import Route, RouteContext


class ChatRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        db: BaseDatabase,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.chat_service = ChatService(core_lifecycle, db)
        self.routes = {
            "/chat/send": ("POST", self.chat_service.chat),
            "/chat/new_session": ("GET", self.chat_service.new_session),
            "/chat/sessions": ("GET", self.chat_service.get_sessions),
            "/chat/get_session": ("GET", self.chat_service.get_session),
            "/chat/delete_session": ("GET", self.chat_service.delete_session),
            "/chat/update_session_display_name": (
                "POST",
                self.chat_service.update_session_display_name,
            ),
            "/chat/get_file": ("GET", self.chat_service.get_file),
            "/chat/get_attachment": ("GET", self.chat_service.get_attachment),
            "/chat/post_file": ("POST", self.chat_service.post_file),
        }
        self.register_routes()
