from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.platform.message_session import MessageSesion
from astrbot.core.platform.sources.webchat.message_parts_helper import (
    build_message_chain_from_payload,
    strip_message_parts_path_fields,
    webchat_message_parts_have_content,
)
from astrbot.core.platform.sources.webchat.webchat_queue_mgr import webchat_queue_mgr
from astrbot.core.utils.datetime_utils import to_utc_isoformat
from astrbot.dashboard.services.api_key_service import ApiKeyService
from astrbot.dashboard.services.auth_service import ALL_OPEN_API_SCOPES
from astrbot.dashboard.services.chat_service import (
    BotMessageAccumulator,
    collect_plain_text_from_message_parts,
)

SendJson = Callable[[dict], Awaitable[None]]
ReceiveJson = Callable[[], Awaitable[Any]]
CloseWebSocket = Callable[[int, str], Awaitable[None]]


class OpenApiServiceError(Exception):
    pass


@dataclass
class OpenApiWebSocketChatBridge:
    build_user_message_parts: Callable[[object], Awaitable[list]]
    create_attachment_from_file: Callable[[str, str], Awaitable[Any]]
    extract_web_search_refs: Callable[[str, list], dict]
    insert_user_message: Callable[[str, str, list], Awaitable[None]]
    save_bot_message: Callable[[str, list, dict, dict], Awaitable[Any]]


class OpenApiService:
    def __init__(
        self,
        db: BaseDatabase,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        self.db = db
        self.core_lifecycle = core_lifecycle
        self.platform_manager = core_lifecycle.platform_manager
        self.platform_history_mgr = getattr(
            core_lifecycle,
            "platform_message_history_manager",
            None,
        )

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
        conf_list = self.core_lifecycle.astrbot_config_mgr.get_conf_list()

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

        raw_session_id = post_data.get("session_id", post_data.get("conversation_id"))
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
            if session.creator != username:
                return "session_id belongs to another username"
            return None

        try:
            await self.db.create_platform_session(
                creator=username,
                platform_id="webchat",
                session_id=session_id,
                is_group=0,
            )
        except Exception as exc:
            existing = await self.db.get_platform_session_by_id(session_id)
            if existing and existing.creator == username:
                return None
            logger.error("Failed to create chat session %s: %s", session_id, exc)
            return f"Failed to create session: {exc}"

        return None

    async def authenticate_api_key(
        self, raw_key: str | None
    ) -> tuple[bool, str | None]:
        if not raw_key:
            return False, "Missing API key"

        key_hash = ApiKeyService.hash_key(raw_key)
        api_key = await self.db.get_active_api_key_by_hash(key_hash)
        if not api_key:
            return False, "Invalid API key"

        if isinstance(api_key.scopes, list):
            scopes = api_key.scopes
        else:
            scopes = list(ALL_OPEN_API_SCOPES)

        if "*" not in scopes and "chat" not in scopes:
            return False, "Insufficient API key scope"

        await self.db.touch_api_key(api_key.key_id)
        return True, None

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
        authed, auth_err = await self.authenticate_api_key(raw_api_key)
        if not authed:
            message = auth_err or "Unauthorized"
            await self.send_chat_ws_error(send_json, message, "UNAUTHORIZED")
            await close(1008, message)
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
                )
        except Exception as exc:
            logger.debug("Open API WS connection closed: %s", exc)

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
                await self.core_lifecycle.umop_config_router.delete_route(umo)
            else:
                await self.core_lifecycle.umop_config_router.update_route(
                    umo, config_id
                )
        except Exception as exc:
            logger.error(
                "Failed to update chat config route for %s with %s: %s",
                umo,
                config_id,
                exc,
                exc_info=True,
            )
            return f"Failed to update chat config route: {exc}"
        return None

    async def insert_webchat_user_message(
        self,
        *,
        session_id: str,
        effective_username: str,
        message_parts: list,
    ) -> None:
        if self.platform_history_mgr is None:
            raise OpenApiServiceError("Platform message history manager is unavailable")
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

        back_queue = webchat_queue_mgr.get_or_create_back_queue(message_id, session_id)
        try:
            chat_queue = webchat_queue_mgr.get_or_create_queue(session_id)
            await chat_queue.put(
                (
                    effective_username,
                    session_id,
                    {
                        "message": message_parts,
                        "selected_provider": selected_provider,
                        "selected_model": selected_model,
                        "enable_streaming": enable_streaming,
                        "message_id": message_id,
                    },
                )
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

            message_accumulator = BotMessageAccumulator()
            agent_stats = {}
            refs = {}
            while True:
                try:
                    result = await asyncio.wait_for(back_queue.get(), timeout=1)
                except asyncio.TimeoutError:
                    continue

                if not result:
                    continue

                if "message_id" in result and result["message_id"] != message_id:
                    logger.warning("openapi ws stream message_id mismatch")
                    continue

                result_text = result.get("data", "")
                msg_type = result.get("type")
                streaming = result.get("streaming", False)
                chain_type = result.get("chain_type")

                if chain_type == "agent_stats":
                    try:
                        stats_info = {
                            "type": "agent_stats",
                            "data": json.loads(result_text),
                        }
                        await send_json(stats_info)
                        agent_stats = stats_info["data"]
                    except Exception:
                        pass
                    continue

                await send_json(result)

                if msg_type == "plain":
                    message_accumulator.add_plain(
                        result_text,
                        chain_type=chain_type,
                        streaming=streaming,
                    )
                elif msg_type in {"image", "record", "file", "video"}:
                    filename = str(result_text).replace(f"[{msg_type.upper()}]", "")
                    part = await chat_bridge.create_attachment_from_file(
                        filename,
                        msg_type,
                    )
                    message_accumulator.add_attachment(part)

                should_save = False
                if msg_type == "end":
                    should_save = bool(
                        message_accumulator.has_content() or refs or agent_stats
                    )
                elif (streaming and msg_type == "complete") or not streaming:
                    if chain_type not in ("tool_call", "tool_call_result"):
                        should_save = True

                if should_save:
                    message_parts_to_save = message_accumulator.build_message_parts(
                        include_pending_tool_calls=True
                    )
                    plain_text = collect_plain_text_from_message_parts(
                        message_parts_to_save
                    )
                    try:
                        refs = chat_bridge.extract_web_search_refs(
                            plain_text,
                            message_parts_to_save,
                        )
                    except Exception as exc:
                        logger.exception(
                            f"Open API WS failed to extract web search refs: {exc}",
                            exc_info=True,
                        )

                    saved_record = await chat_bridge.save_bot_message(
                        session_id,
                        message_parts_to_save,
                        agent_stats,
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
                    message_accumulator = BotMessageAccumulator()
                    agent_stats = {}
                    refs = {}
                if msg_type == "end":
                    break
        except Exception as exc:
            logger.exception(f"Open API WS chat failed: {exc}", exc_info=True)
            await send_error(f"Failed to process message: {exc}", "PROCESSING_ERROR")
        finally:
            webchat_queue_mgr.remove_back_queue(message_id)

    async def get_chat_sessions(
        self,
        *,
        username: str,
        page_raw,
        page_size_raw,
        platform_id: str | None,
    ) -> dict:
        try:
            page = int(page_raw)
            page_size = int(page_size_raw)
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
                    "is_group": session.is_group,
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

    async def get_chat_sessions_from_dashboard_query(
        self,
        *,
        username: str | None,
        page,
        page_size,
        platform_id: str | None,
    ) -> dict:
        resolved_username, username_err = self.resolve_open_username(username)
        if username_err:
            raise OpenApiServiceError(username_err)
        if not resolved_username:
            raise OpenApiServiceError("Invalid username")

        return await self.get_chat_sessions(
            username=resolved_username,
            page_raw=page,
            page_size_raw=page_size,
            platform_id=platform_id,
        )

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
            session = MessageSesion.from_str(str(umo))
        except Exception as exc:
            raise OpenApiServiceError(f"Invalid umo: {exc}") from exc

        platform_id = session.platform_name
        platform_inst = next(
            (
                inst
                for inst in self.platform_manager.platform_insts
                if inst.meta().id == platform_id
            ),
            None,
        )
        if not platform_inst:
            raise OpenApiServiceError(
                f"Bot not found or not running for platform: {platform_id}"
            )

        try:
            message_chain = await self.build_message_chain_from_payload(message_payload)
            await platform_inst.send_by_session(session, message_chain)
        except OpenApiServiceError:
            raise
        except ValueError as exc:
            raise OpenApiServiceError(str(exc)) from exc
        except Exception as exc:
            logger.error(f"Open API send_message failed: {exc}", exc_info=True)
            raise OpenApiServiceError(f"Failed to send message: {exc}") from exc

    def get_bots(self) -> dict:
        bot_ids = []
        for platform in self.core_lifecycle.astrbot_config.get("platform", []):
            platform_id = platform.get("id") if isinstance(platform, dict) else None
            if (
                isinstance(platform_id, str)
                and platform_id
                and platform_id not in bot_ids
            ):
                bot_ids.append(platform_id)
        return {"bot_ids": bot_ids}
