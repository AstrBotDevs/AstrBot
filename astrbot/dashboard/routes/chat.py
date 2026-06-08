from typing import cast

from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.dashboard.fastapi_compat import Response as CompatResponse
from astrbot.dashboard.fastapi_compat import g, make_response, request, send_file
from astrbot.dashboard.services.chat_service import (
    ChatService,
    ChatServiceError,
)

from .route import Response, Route, RouteContext

__all__ = ["ChatRoute"]


class ChatRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        db: BaseDatabase,
        core_lifecycle: AstrBotCoreLifecycle,
        service: ChatService | None = None,
    ) -> None:
        super().__init__(context)
        self.routes = {
            "/chat/send": ("POST", self.chat),
            "/chat/new_session": ("GET", self.new_session),
            "/chat/sessions": ("GET", self.get_sessions),
            "/chat/get_session": ("GET", self.get_session),
            "/chat/stop": ("POST", self.stop_session),
            "/chat/delete_session": ("GET", self.delete_webchat_session),
            "/chat/batch_delete_sessions": ("POST", self.batch_delete_sessions),
            "/chat/update_session_display_name": (
                "POST",
                self.update_session_display_name,
            ),
            "/chat/message/edit": ("POST", self.update_message),
            "/chat/message/regenerate": ("POST", self.regenerate_message),
            "/chat/thread/create": ("POST", self.create_thread),
            "/chat/thread/get": ("GET", self.get_thread),
            "/chat/thread/send": ("POST", self.send_thread_message),
            "/chat/thread/delete": ("POST", self.delete_thread),
            "/chat/get_file": ("GET", self.get_file),
            "/chat/get_attachment": ("GET", self.get_attachment),
            "/chat/post_file": ("POST", self.post_file),
        }
        self.service = service or ChatService(db, core_lifecycle)
        self.register_routes()

    @staticmethod
    def _ok(data=None):
        return Response().ok(data=data).__dict__

    @staticmethod
    def _error(message: str):
        return Response().error(message).__dict__

    @staticmethod
    async def _json_body():
        return await request.get_json()

    async def _run(self, operation):
        try:
            result = operation() if callable(operation) else operation
            while hasattr(result, "__await__"):
                result = await result
            return self._ok(result)
        except ChatServiceError as exc:
            return self._error(str(exc))

    async def _run_json(self, operation):
        async def invoke():
            data = await self._json_body()
            return operation(data)

        return await self._run(invoke)

    async def get_file(self):
        try:
            (
                file_path,
                mimetype,
            ) = await self.service.resolve_webchat_file_from_legacy_query(
                request.args.get("filename")
            )
            if mimetype:
                return await send_file(file_path, mimetype=mimetype)
            return await send_file(file_path)
        except ChatServiceError as exc:
            return self._error(str(exc))
        except (FileNotFoundError, OSError):
            return self._error("File access error")

    async def get_attachment(self):
        """Get attachment file by attachment_id."""
        try:
            (
                file_path,
                mimetype,
            ) = await self.service.resolve_attachment_file_from_legacy_query(
                request.args.get("attachment_id")
            )
            return await send_file(file_path, mimetype=mimetype)
        except ChatServiceError as exc:
            return self._error(str(exc))
        except (FileNotFoundError, OSError):
            return self._error("File access error")

    async def post_file(self):
        """Upload a file and create an attachment record, return attachment_id."""
        return await self._run(
            self.service.save_uploaded_file_from_legacy_files(await request.files)
        )

    async def chat(self, post_data: dict | None = None):
        username = g.get("username", "guest")

        if post_data is None:
            post_data = await request.get_json()
        if post_data is None:
            return self._error("Missing JSON body")

        try:
            stream = await self.service.build_chat_stream(username, post_data)
        except ChatServiceError as exc:
            return self._error(str(exc))
        response = cast(
            CompatResponse,
            await make_response(
                stream,
                {
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "Transfer-Encoding": "chunked",
                    "Connection": "keep-alive",
                },
            ),
        )
        response.timeout = None  # fix SSE auto disconnect issue
        return response

    async def stop_session(self):
        return await self._run_json(
            lambda data: self.service.stop_session_from_legacy_payload(
                g.get("username", "guest"),
                data,
            )
        )

    async def delete_webchat_session(self):
        """Delete a Platform session and all its related data."""
        return await self._run(
            lambda: self.service.delete_webchat_session_from_legacy_query(
                g.get("username", "guest"),
                request.args.get("session_id"),
            )
        )

    async def batch_delete_sessions(self):
        """Batch delete multiple Platform sessions."""
        return await self._run_json(
            lambda data: self.service.batch_delete_sessions_from_legacy_payload(
                g.get("username", "guest"),
                data,
            )
        )

    async def new_session(self):
        return await self._run(
            self.service.new_session_from_legacy_query(
                g.get("username", "guest"),
                request.args.get("platform_id", "webchat"),
            )
        )

    async def get_sessions(self):
        return await self._run(
            self.service.get_sessions_from_legacy_query(
                g.get("username", "guest"),
                request.args.get("platform_id"),
            )
        )

    async def get_session(self):
        return await self._run(
            self.service.get_session_from_legacy_query(
                g.get("username", "guest"),
                request.args.get("session_id"),
            )
        )

    async def create_thread(self):
        return await self._run_json(
            lambda data: self.service.create_thread_from_legacy_payload(
                g.get("username", "guest"),
                data,
            )
        )

    async def get_thread(self):
        return await self._run(
            self.service.get_thread_from_legacy_query(
                g.get("username", "guest"),
                request.args.get("thread_id"),
            )
        )

    async def send_thread_message(self):
        """Send a message inside a WebChat side thread."""
        try:
            return await self.chat(
                await self.service.prepare_thread_chat_payload_from_legacy_payload(
                    g.get("username", "guest"),
                    await self._json_body(),
                )
            )
        except ChatServiceError as exc:
            return self._error(str(exc))

    async def delete_thread(self):
        return await self._run_json(
            lambda data: self.service.delete_thread_from_legacy_payload(
                g.get("username", "guest"),
                data,
            )
        )

    async def update_message(self):
        """Update a persisted WebChat message and its linked LLM turn."""
        return await self._run_json(
            lambda data: self.service.update_message_from_legacy_payload(
                g.get("username", "guest"),
                data,
            )
        )

    async def regenerate_message(self):
        """Regenerate the latest bot message linked to an LLM checkpoint."""
        try:
            return await self.chat(
                await self.service.prepare_regenerate_message_payload_from_legacy_payload(
                    g.get("username", "guest"),
                    await self._json_body(),
                )
            )
        except ChatServiceError as exc:
            return self._error(str(exc))

    async def update_session_display_name(self):
        return await self._run_json(
            lambda data: self.service.update_session_display_name_from_legacy_payload(
                g.get("username", "guest"),
                data,
            )
        )
