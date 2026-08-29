import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from astrbot import logger
from astrbot.core.auth.models import AuthContext, Resource, Subject
from astrbot.core.auth.service import AuthorizationService
from astrbot.core.db.protocols import OpenApiStore
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.utils.datetime_utils import to_utc_isoformat
from astrbot.core.utils.error_redaction import safe_error
from astrbot.core.webchat.message_parts import (
    build_message_chain_from_payload,
    strip_message_parts_path_fields,
    webchat_message_parts_have_content,
)
from astrbot.core.webchat.result_reducer import (
    WebChatResultReducer,
    collect_plain_text_from_message_parts,
    merge_webchat_refs,
    parse_webchat_attachment,
)
from astrbot.core.webchat.run_coordinator import (
    DuplicateWebChatRunError,
    WebChatRunCoordinator,
)
from astrbot.dashboard.responses import INTERNAL_SERVER_ERROR_MESSAGE
from astrbot.dashboard.services.api_key_service import ApiKeyService

if TYPE_CHECKING:
    from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
    from astrbot.core.config.astrbot_config import AstrBotConfig
    from astrbot.core.platform.manager import PlatformManager
    from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager
    from astrbot.core.umop_config_router import UmopConfigRouter

SendJson = Callable[[dict], Awaitable[None]]
ReceiveJson = Callable[[], Awaitable[Any]]
CloseWebSocket = Callable[[int, str], Awaitable[None]]


class OpenApiServiceError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class OpenApiKeyAuthContext:
    """Trusted capability resolved from one API key for a WebSocket run."""

    key_id: str
    scopes: tuple[str, ...]


@dataclass
class OpenApiWebSocketChatBridge:
    build_user_message_parts: Callable[[object], Awaitable[list]]
    create_attachment_from_file: Callable[..., Awaitable[Any]]
    extract_web_search_refs: Callable[[str, list], dict]
    insert_user_message: Callable[[str, str, list], Awaitable[None]]
    save_bot_message: Callable[[str, list, dict, dict], Awaitable[Any]]


class OpenApiService:
    def __init__(
        self,
        db: OpenApiStore,
        *,
        platform_manager: PlatformManager,
        astrbot_config_mgr: AstrBotConfigManager,
        umop_config_router: UmopConfigRouter,
        astrbot_config: AstrBotConfig,
        platform_message_history_manager: PlatformMessageHistoryManager,
        webchat_run_coordinator: WebChatRunCoordinator,
        authorization: AuthorizationService | None = None,
    ) -> None:
        self.db = db
        self.platform_manager = platform_manager
        self.astrbot_config_mgr = astrbot_config_mgr
        self.umop_config_router = umop_config_router
        self.astrbot_config = astrbot_config
        self.webchat_run_coordinator = webchat_run_coordinator
        self.platform_history_mgr = platform_message_history_manager
        self.authorization = authorization

    @staticmethod
    def chat_user_resource(username: str) -> Resource:
        resource_id = hashlib.sha256(str(username).encode("utf-8")).hexdigest()
        return Resource.named("webchat-user", resource_id)

    async def authorize_declared_chat_user(
        self, *, key_id: str, action: str, username: str
    ) -> bool:
        if self.authorization is None:
            return False
        subject = Subject.api_key(key_id)
        decision = await self.authorization.authorize(
            subject,
            action,
            self.chat_user_resource(username),
            AuthContext(subject=subject, source="api_key", authenticated=True),
        )
        return decision.allowed

    @staticmethod
    def resolve_open_username(
        raw_username: str | None,
    ) -> tuple[str | None, str | None]:
        if raw_username is None:
            return None, "Missing key: username"
        username = str(raw_username).strip()
        if not username:
            return None, "username is empty"
        return username, None

    def get_chat_config_list(self) -> list[dict]:
        conf_list = self.astrbot_config_mgr.get_conf_list()

        result = []
        for conf_info in conf_list:
            conf_id = str(conf_info.get("id", "")).strip()
            result.append(
                {
                    "id": conf_id,
                    "name": str(conf_info.get("name", "")).strip(),
                    "path": str(conf_info.get("path", "")).strip(),
                    "is_default": conf_id == "default",
                }
            )
        return result

    @staticmethod
    def resolve_chat_config_id(
        post_data: dict,
        conf_list: list[dict],
    ) -> tuple[str | None, str | None]:
        raw_config_id = post_data.get("config_id")
        raw_config_name = post_data.get("config_name")
        config_id = str(raw_config_id).strip() if raw_config_id is not None else ""
        config_name = (
            str(raw_config_name).strip() if raw_config_name is not None else ""
        )

        if not config_id and not config_name:
            return None, None

        conf_map = {item["id"]: item for item in conf_list}

        if config_id:
            if config_id not in conf_map:
                return None, f"config_id not found: {config_id}"
            return config_id, None

        if not config_name:
            return None, "config_name is empty"

        matched = [item for item in conf_list if item["name"] == config_name]
        if not matched:
            return None, f"config_name not found: {config_name}"
        if len(matched) > 1:
            return (
                None,
                f"config_name is ambiguous, please use config_id: {config_name}",
            )

        return matched[0]["id"], None

    async def prepare_chat_send(
        self,
        post_data: dict,
        conf_list: list[dict],
    ) -> tuple[str, str, str | None]:
        effective_username, username_err = self.resolve_open_username(
            post_data.get("username")
        )
        if username_err:
            raise OpenApiServiceError(username_err)
        if not effective_username:
            raise OpenApiServiceError("Invalid username")
        raw_session_id = post_data.get("session_id")
        session_id = str(raw_session_id).strip() if raw_session_id is not None else ""
        if not session_id:
            session_id = str(uuid4())
            post_data["session_id"] = session_id

        ensure_session_err = await self.ensure_chat_session(
            effective_username,
            session_id,
        )
        if ensure_session_err:
            raise OpenApiServiceError(ensure_session_err)

        config_id, resolve_err = self.resolve_chat_config_id(post_data, conf_list)
        if resolve_err:
            raise OpenApiServiceError(resolve_err)

        return effective_username, session_id, config_id

    async def ensure_chat_session(
        self,
        username: str,
        session_id: str,
    ) -> str | None:
        session = await self.db.get_platform_session_by_id(session_id)
        if session:
            if session.platform_id != "webchat" or session.creator != username:
                return "session_id belongs to another username"
            return None

        try:
            await self.db.create_platform_session(
                creator=username,
                platform_id="webchat",
                session_id=session_id,
            )
        except Exception as exc:
            existing = await self.db.get_platform_session_by_id(session_id)
            if (
                existing
                and existing.platform_id == "webchat"
                and existing.creator == username
            ):
                return None
            logger.error("Failed to create chat session: %s", safe_error("", exc))
            return "Failed to create session"

        return None

    async def authenticate_api_key(
        self, raw_key: str | None
    ) -> tuple[OpenApiKeyAuthContext | None, str | None]:
        if not raw_key:
            return None, "Missing API key"

        key_hash = ApiKeyService.hash_key(raw_key)
        api_key = await self.db.get_active_api_key_by_hash(key_hash)
        if not api_key:
            return None, "Invalid API key"

        if self.authorization is None:
            return None, "Authorization unavailable"
        subject = Subject.api_key(api_key.key_id)
        decision = await self.authorization.authorize(
            subject,
            "session.read",
            Resource.named("webchat", "socket"),
            AuthContext(subject=subject, source="api_key", authenticated=True),
        )
        if not decision.allowed:
            return None, "Insufficient API key scope"

        await self.db.touch_api_key(api_key.key_id)
        return OpenApiKeyAuthContext(api_key.key_id, ()), None

    @staticmethod
    async def send_chat_ws_error(
        send_json: SendJson,
        message: str,
        code: str,
    ) -> None:
        await send_json(
            {
                "type": "error",
                "code": code,
                "data": message,
            }
        )

    async def run_chat_websocket(
        self,
        *,
        raw_api_key: str | None,
        receive_json: ReceiveJson,
        send_json: SendJson,
        close: CloseWebSocket,
        conf_list: list[dict],
        chat_bridge: OpenApiWebSocketChatBridge,
    ) -> None:
        try:
            auth, auth_err = await self.authenticate_api_key(raw_api_key)
        except Exception as exc:
            logger.error("Open API WS authentication failed: %s", safe_error("", exc))
            await self.send_chat_ws_error(
                send_json,
                INTERNAL_SERVER_ERROR_MESSAGE,
                "PROCESSING_ERROR",
            )
            await close(1011, INTERNAL_SERVER_ERROR_MESSAGE)
            return
        if auth is None:
            message = auth_err or "Unauthorized"
            await self.send_chat_ws_error(send_json, message, "UNAUTHORIZED")
            await close(1008, message)
            return

        # Authenticate the socket itself before accepting any caller-declared
        # username/session payload. API-key scope is a capability check, never
        # an implicit dashboard role.
        if self.authorization is None:
            await self.send_chat_ws_error(
                send_json, "Authorization unavailable", "PROCESSING_ERROR"
            )
            await close(1011, "Authorization unavailable")
            return
        principal = Subject.api_key(auth.key_id)
        socket_context = AuthContext(
            subject=principal,
            source="api_key",
            authenticated=True,
            api_scopes=auth.scopes,
            metadata={"transport": "websocket"},
        )
        decision = await self.authorization.authorize(
            principal,
            "session.read",
            Resource.named("webchat", "socket"),
            socket_context,
        )
        if not decision.allowed:
            await self.send_chat_ws_error(
                send_json, "Insufficient API key scope", "FORBIDDEN"
            )
            await close(1008, "Insufficient API key scope")
            return

        async def send_error(message: str, code: str) -> None:
            await self.send_chat_ws_error(send_json, message, code)

        try:
            while True:
                message = await receive_json()
                if not isinstance(message, dict):
                    await send_error(
                        "message must be an object",
                        "INVALID_MESSAGE",
                    )
                    continue

                msg_type = message.get("t", "send")
                if msg_type == "ping":
                    await send_json({"type": "pong"})
                    continue
                if msg_type != "send":
                    await send_error(
                        f"Unsupported message type: {msg_type}",
                        "INVALID_MESSAGE",
                    )
                    continue

                await self.handle_chat_ws_send(
                    post_data=message,
                    conf_list=conf_list,
                    chat_bridge=chat_bridge,
                    send_json=send_json,
                    send_error=send_error,
                    api_key_principal={
                        "key_id": auth.key_id,
                        "scopes": list(auth.scopes),
                    },
                )
        except Exception as exc:
            logger.debug("Open API WS connection closed: %s", safe_error("", exc))

    async def update_session_config_route(
        self,
        *,
        username: str,
        session_id: str,
        config_id: str | None,
    ) -> str | None:
        if not config_id:
            return None

        umo = f"webchat:FriendMessage:webchat!{username}!{session_id}"
        try:
            if config_id == "default":
                await self.umop_config_router.delete_route(umo)
            else:
                await self.umop_config_router.update_route(umo, config_id)
        except Exception as exc:
            logger.error(
                "Failed to update chat config route: %s",
                safe_error("", exc),
            )
            return "Failed to update chat config route"
        return None

    async def insert_webchat_user_message(
        self,
        *,
        session_id: str,
        effective_username: str,
        message_parts: list,
    ) -> None:
        await self.platform_history_mgr.insert(
            platform_id="webchat",
            user_id=session_id,
            content={"type": "user", "message": message_parts},
            sender_id=effective_username,
            sender_name=effective_username,
        )

    @staticmethod
    def get_chat_send_error_code(message: str) -> str:
        if message in ("Missing key: username", "username is empty"):
            return "BAD_USER"
        if message.startswith("config_"):
            return "CONFIG_ERROR"
        if "session" in message:
            return "SESSION_ERROR"
        return "INVALID_MESSAGE"

    async def handle_chat_ws_send(
        self,
        *,
        post_data: dict,
        conf_list: list[dict],
        chat_bridge: OpenApiWebSocketChatBridge,
        send_json: SendJson,
        send_error: Callable[[str, str], Awaitable[None]],
        api_key_principal: dict | None = None,
    ) -> None:
        message = post_data.get("message")
        if message is None:
            await send_error("Missing key: message", "INVALID_MESSAGE")
            return

        try:
            (
                effective_username,
                session_id,
                config_id,
            ) = await self.prepare_chat_send(
                post_data,
                conf_list,
            )
        except OpenApiServiceError as exc:
            message = str(exc)
            await send_error(message, self.get_chat_send_error_code(message))
            return

        if api_key_principal is not None:
            key_id = api_key_principal.get("key_id")
            if not isinstance(
                key_id, str
            ) or not await self.authorize_declared_chat_user(
                key_id=key_id,
                action="session.manage",
                username=effective_username,
            ):
                await send_error("Authorization denied", "FORBIDDEN")
                return

        config_err = await self.update_session_config_route(
            username=effective_username,
            session_id=session_id,
            config_id=config_id,
        )
        if config_err:
            await send_error(config_err, "CONFIG_ERROR")
            return

        message_parts = await chat_bridge.build_user_message_parts(message)
        if not webchat_message_parts_have_content(message_parts):
            await send_error(
                "Message content is empty (reply only is not allowed)",
                "INVALID_MESSAGE",
            )
            return

        message_id = str(post_data.get("message_id") or uuid4())
        selected_provider = post_data.get("selected_provider")
        selected_model = post_data.get("selected_model")
        enable_streaming = post_data.get("enable_streaming", True)

        run = None
        try:
            run = self.webchat_run_coordinator.create_run(
                session_id=session_id,
                username=effective_username,
                request_id=message_id,
                kind="open_api",
            )
            self.webchat_run_coordinator.bind_task(run)
            await self.webchat_run_coordinator.dispatch(
                run,
                {
                    "message": message_parts,
                    "selected_provider": selected_provider,
                    "selected_model": selected_model,
                    "enable_streaming": enable_streaming,
                    "_api_key_principal": api_key_principal,
                },
            )

            message_parts_for_storage = strip_message_parts_path_fields(message_parts)
            await chat_bridge.insert_user_message(
                session_id,
                effective_username,
                message_parts_for_storage,
            )

            await send_json(
                {
                    "type": "session_id",
                    "data": None,
                    "session_id": session_id,
                    "message_id": message_id,
                }
            )

            reducer = WebChatResultReducer()
            while True:
                result = await self.webchat_run_coordinator.next_result(
                    run,
                    wait_seconds=1,
                )

                if not result:
                    continue

                result_text = result.get("data", "")
                msg_type = result.get("type")
                chain_type = result.get("chain_type")

                if chain_type == "agent_stats":
                    if reducer.consume_metadata(result) == "agent_stats":
                        stats_info = {
                            "type": "agent_stats",
                            "data": reducer.agent_stats,
                        }
                        await send_json(stats_info)
                    continue

                if msg_type == "refs":
                    reducer.consume_metadata(result)
                    await send_json(result)
                    continue

                await send_json(result)

                if msg_type == "plain":
                    reducer.accumulate_plain(result)
                elif msg_type in {"image", "record", "file", "video"}:
                    attachment = parse_webchat_attachment(msg_type, result_text)
                    assert attachment is not None
                    filename, attach_type, display_name = attachment
                    part = await chat_bridge.create_attachment_from_file(
                        filename,
                        attach_type,
                        **({"display_name": display_name} if display_name else {}),
                    )
                    reducer.accumulator.add_attachment(part)

                if reducer.should_flush(result):
                    message_parts_to_save = reducer.accumulator.build_message_parts(
                        include_pending_tool_calls=True
                    )
                    plain_text = collect_plain_text_from_message_parts(
                        message_parts_to_save
                    )
                    try:
                        extracted_refs = chat_bridge.extract_web_search_refs(
                            plain_text,
                            message_parts_to_save,
                        )
                        refs = merge_webchat_refs(extracted_refs, reducer.native_refs)
                    except Exception as exc:
                        logger.error(
                            "Open API WS failed to extract web search refs: %s",
                            safe_error("", exc),
                        )

                        refs = reducer.native_refs

                    saved_record = await chat_bridge.save_bot_message(
                        session_id,
                        message_parts_to_save,
                        reducer.agent_stats,
                        refs,
                    )
                    if saved_record:
                        await send_json(
                            {
                                "type": "message_saved",
                                "data": {
                                    "id": saved_record.id,
                                    "created_at": to_utc_isoformat(
                                        saved_record.created_at
                                    ),
                                },
                                "session_id": session_id,
                            }
                        )
                    reducer.reset()
                if msg_type == "end":
                    break
        except DuplicateWebChatRunError:
            await send_error("Duplicate active message_id", "INVALID_MESSAGE")
        except Exception as exc:
            logger.error("Open API WS chat failed: %s", safe_error("", exc))
            await send_error("Failed to process message", "PROCESSING_ERROR")
        finally:
            if run is not None:
                await self.webchat_run_coordinator.close_run(run)

    async def get_chat_sessions(
        self,
        *,
        username: str,
        page,
        page_size,
        platform_id: str | None,
    ) -> dict:
        try:
            page = int(page)
            page_size = int(page_size)
        except ValueError as exc:
            raise OpenApiServiceError("page and page_size must be integers") from exc

        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 1
        if page_size > 100:
            page_size = 100

        (
            paginated_sessions,
            total,
        ) = await self.db.get_platform_sessions_by_creator_paginated(
            creator=username,
            platform_id=platform_id,
            page=page,
            page_size=page_size,
            exclude_project_sessions=True,
        )

        sessions_data = []
        for item in paginated_sessions:
            session = item["session"]
            sessions_data.append(
                {
                    "session_id": session.session_id,
                    "platform_id": session.platform_id,
                    "creator": session.creator,
                    "display_name": session.display_name,
                    "created_at": to_utc_isoformat(session.created_at),
                    "updated_at": to_utc_isoformat(session.updated_at),
                }
            )

        return {
            "sessions": sessions_data,
            "page": page,
            "page_size": page_size,
            "total": total,
        }

    def get_chat_configs(self) -> dict:
        return {"configs": self.get_chat_config_list()}

    async def build_message_chain_from_payload(self, message_payload: str | list):
        return await build_message_chain_from_payload(
            message_payload,
            get_attachment_by_id=self.db.get_attachment_by_id,
            strict=True,
        )

    async def send_message(self, post_data: object) -> None:
        payload = post_data if isinstance(post_data, dict) else {}
        message_payload = payload.get("message", {})
        umo = payload.get("umo")

        if message_payload is None:
            raise OpenApiServiceError("Missing key: message")
        if not umo:
            raise OpenApiServiceError("Missing key: umo")

        try:
            session = MessageSession.from_str(str(umo))
        except Exception as exc:
            logger.error("Open API invalid UMO: %s", safe_error("", exc))
            raise OpenApiServiceError("Invalid umo") from exc

        try:
            message_chain = await self.build_message_chain_from_payload(message_payload)
            result = await self.platform_manager.send_to_session(session, message_chain)
            if not result.success:
                if result.error_message == "platform adapter not found":
                    raise OpenApiServiceError(
                        f"Bot not found or not running for platform: {session.platform_id}"
                    )
                logger.error(
                    "Open API platform send failed: %s",
                    safe_error("", result.error_message or "unknown error"),
                )
                raise OpenApiServiceError(
                    INTERNAL_SERVER_ERROR_MESSAGE,
                    status_code=500,
                )
        except OpenApiServiceError:
            raise
        except ValueError as exc:
            logger.error("Open API message payload rejected: %s", safe_error("", exc))
            raise OpenApiServiceError("Invalid message payload") from exc
        except Exception as exc:
            logger.error("Open API send_message failed: %s", safe_error("", exc))
            raise OpenApiServiceError(
                INTERNAL_SERVER_ERROR_MESSAGE,
                status_code=500,
            ) from exc

    def get_bots(self) -> dict:
        bot_ids = []
        for platform in self.astrbot_config.get("platform", []):
            platform_id = platform.get("id") if isinstance(platform, dict) else None
            if (
                isinstance(platform_id, str)
                and platform_id
                and platform_id not in bot_ids
            ):
                bot_ids.append(platform_id)
        return {"bot_ids": bot_ids}
