from typing import cast

from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.dashboard.fastapi_compat import (
    Response as CompatResponse,
)
from astrbot.dashboard.fastapi_compat import (
    make_response,
    request,
    send_file,
    websocket,
)
from astrbot.dashboard.services.chat_service import (
    ChatService,
    ChatServiceError,
    extract_web_search_refs,
)
from astrbot.dashboard.services.open_api_service import (
    OpenApiService,
    OpenApiServiceError,
    OpenApiWebSocketChatBridge,
)

from .route import Response, Route, RouteContext


class OpenApiRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        db: BaseDatabase,
        core_lifecycle: AstrBotCoreLifecycle,
        chat_service: ChatService,
        *,
        register_routes: bool = True,
    ) -> None:
        super().__init__(context)
        self.core_lifecycle = core_lifecycle
        self.chat_service = chat_service
        self.service = OpenApiService(db, core_lifecycle)

        self.routes = {
            "/v1/chat": ("POST", self.chat_send),
            "/v1/chat/sessions": ("GET", self.get_chat_sessions),
            "/v1/configs": ("GET", self.get_chat_configs),
            "/v1/file": [
                ("POST", self.openapi_upload_file),
                ("GET", self.openapi_get_file),
            ],
            "/v1/im/message": ("POST", self.send_message),
            "/v1/im/bots": ("GET", self.get_bots),
        }
        if register_routes:
            self.register_routes()
            self.app.websocket("/api/v1/chat/ws")(self.chat_ws)

    @staticmethod
    def _ok(data=None):
        return Response().ok(data=data).__dict__

    @staticmethod
    def _error(message: str):
        return Response().error(message).__dict__

    @staticmethod
    async def _json_body() -> dict:
        data = await request.get_json()
        return data if isinstance(data, dict) else {}

    async def _run(self, operation):
        try:
            result = operation() if callable(operation) else operation
            while hasattr(result, "__await__"):
                result = await result
            return self._ok(result)
        except (OpenApiServiceError, ChatServiceError) as exc:
            return self._error(str(exc))

    async def _run_json(self, operation):
        async def invoke():
            data = await self._json_body()
            return operation(data)

        return await self._run(invoke)

    def _get_chat_config_list(self) -> list[dict]:
        return self.service.get_chat_config_list()

    async def chat_send(self):
        post_data = await request.get_json(silent=True) or {}
        try:
            (
                effective_username,
                session_id,
                config_id,
            ) = await self.service.prepare_chat_send(
                post_data,
                self._get_chat_config_list(),
            )
        except OpenApiServiceError as exc:
            return self._error(str(exc))

        config_err = await self.service.update_session_config_route(
            username=effective_username,
            session_id=session_id,
            config_id=config_id,
        )
        if config_err:
            return self._error(config_err)

        return await self._chat_response(effective_username, post_data)

    async def _chat_response(self, username: str, post_data: dict):
        try:
            stream = await self.chat_service.build_chat_stream(username, post_data)
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
        response.timeout = None
        return response

    @staticmethod
    def _extract_ws_api_key() -> str | None:
        if key := websocket.args.get("api_key"):
            return key.strip()
        if key := websocket.args.get("key"):
            return key.strip()
        if key := websocket.headers.get("X-API-Key"):
            return key.strip()

        auth_header = websocket.headers.get("Authorization", "").strip()
        if auth_header.startswith("Bearer "):
            return auth_header.removeprefix("Bearer ").strip()
        if auth_header.startswith("ApiKey "):
            return auth_header.removeprefix("ApiKey ").strip()
        return None

    async def _insert_webchat_user_message(
        self,
        session_id: str,
        effective_username: str,
        message_parts: list,
    ) -> None:
        await self.service.insert_webchat_user_message(
            session_id=session_id,
            effective_username=effective_username,
            message_parts=message_parts,
        )

    def _build_chat_ws_bridge(self) -> OpenApiWebSocketChatBridge:
        return OpenApiWebSocketChatBridge(
            build_user_message_parts=self.chat_service.build_user_message_parts,
            create_attachment_from_file=self.chat_service.create_attachment_from_file,
            extract_web_search_refs=extract_web_search_refs,
            insert_user_message=self._insert_webchat_user_message,
            save_bot_message=self.chat_service.save_bot_message,
        )

    async def chat_ws(self) -> None:
        await self.service.run_chat_websocket(
            raw_api_key=self._extract_ws_api_key(),
            receive_json=websocket.receive_json,
            send_json=websocket.send_json,
            close=websocket.close,
            conf_list=self._get_chat_config_list(),
            chat_bridge=self._build_chat_ws_bridge(),
        )

    async def openapi_upload_file(self):
        return await self._run(
            self.chat_service.save_uploaded_file_from_legacy_files(await request.files)
        )

    async def openapi_get_file(self):
        try:
            (
                file_path,
                mimetype,
            ) = await self.chat_service.resolve_attachment_file_from_legacy_query(
                request.args.get("attachment_id")
            )
            return await send_file(file_path, mimetype=mimetype)
        except ChatServiceError as exc:
            return self._error(str(exc))
        except (FileNotFoundError, OSError):
            return self._error("File access error")

    async def get_chat_sessions(self):
        return await self._run(
            self.service.get_chat_sessions_from_legacy_query(
                username=request.args.get("username"),
                page=request.args.get("page", 1),
                page_size=request.args.get("page_size", 20),
                platform_id=request.args.get("platform_id"),
            )
        )

    async def get_chat_configs(self):
        return self._ok({"configs": self._get_chat_config_list()})

    async def send_message(self):
        return await self._run_json(self.service.send_message)

    async def get_bots(self):
        return await self._run(self.service.get_bots)
