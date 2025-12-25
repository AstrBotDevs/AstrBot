from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase

from ...services.chat import ChatService
from ..route import Route, RouteContext


class V1ChatRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        core_lifecycle: AstrBotCoreLifecycle,
        db: BaseDatabase,
    ):
        super().__init__(context)
        self.chat_service = ChatService(core_lifecycle, db)
        self.routes = {
            "/v1/chat": [("POST", self.chat_service.chat, "v1_chat_send")],
            "/v1/chat/sessions": [
                ("GET", self.chat_service.get_sessions, "v1_chat_sessions")
            ],
            "/v1/chat/session": [
                ("POST", self.chat_service.new_session, "v1_chat_new_session")
            ],
            "/v1/chat/session/<session_id>": [
                ("GET", self.chat_service.get_session, "v1_chat_get_session"),
                ("DELETE", self.chat_service.delete_session, "v1_chat_delete_session"),
                (
                    "PUT",
                    self.chat_service.update_session_display_name,
                    "v1_chat_update_session_display_name",
                ),
            ],
            "/v1/chat/attachment": [
                ("POST", self.chat_service.post_file, "v1_chat_post_file")
            ],
            "/v1/chat/attachment/<attachment_id>": [
                ("GET", self.chat_service.get_attachment, "v1_chat_get_attachment")
            ],
        }
        self.register_routes()
