import asyncio
import hashlib
import json
from uuid import uuid4

from quart import g, request, websocket

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

from .api_key import ALL_OPEN_API_SCOPES
from .chat import ChatRoute
from .route import Response, Route, RouteContext


class OpenApiRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        db: BaseDatabase,
        core_lifecycle: AstrBotCoreLifecycle,
        chat_route: ChatRoute,
    ) -> None:
        super().__init__(context)
        self.db = db
        self.core_lifecycle = core_lifecycle
        self.platform_manager = core_lifecycle.platform_manager
        self.chat_route = chat_route

        self.routes = {
            "/v1/chat": ("POST", self.chat_send),
            "/v1/chat/sessions": ("GET", self.get_chat_sessions),
            "/v1/configs": ("GET", self.get_chat_configs),
            "/v1/file": ("POST", self.upload_file),
            "/v1/im/message": ("POST", self.send_message),
            "/v1/im/bots": ("GET", self.get_bots),
        }
        self.register_routes()
        self.app.websocket("/api/v1/chat/ws")(self.chat_ws)

    @staticmethod
    def _resolve_open_username(
        raw_username: str | None,
    ) -> tuple[str | None, str | None]:
        if raw_username is None:
            return None, "Missing key: username"
        username = str(raw_username).strip()
        if not username:
            return None, "username is empty"
        return username, None

    def _get_chat_config_list(self) -> list[dict]:
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

    def _resolve_chat_config_id(self, post_data: dict) -> tuple[str | None, str | None]:
        raw_config_id = post_data.get("config_id")
        raw_config_name = post_data.get("config_name")
        config_id = str(raw_config_id).strip() if raw_config_id is not None else ""
        config_name = (
            str(raw_config_name).strip() if raw_config_name is not None else ""
        )

        if not config_id and not config_name:
            return None, None

        conf_list = self._get_chat_config_list()
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

    async def _ensure_chat_session(
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
        except Exception as e:
            # Handle rare race when same session_id is created concurrently.
            existing = await self.db.get_platform_session_by_id(session_id)
            if existing and existing.creator == username:
                return None
            logger.error("Failed to create chat session %s: %s", session_id, e)
            return f"Failed to create session: {e}"

        return None

    async def chat_send(self):
        post_data = await request.get_json(silent=True) or {}
        effective_username, username_err = self._resolve_open_username(
            post_data.get("username")
        )
        if username_err:
            return Response().error(username_err).__dict__
        if not effective_username:
            return Response().error("Invalid username").__dict__

        raw_session_id = post_data.get("session_id", post_data.get("conversation_id"))
        session_id = str(raw_session_id).strip() if raw_session_id is not None else ""
        if not session_id:
            session_id = str(uuid4())
            post_data["session_id"] = session_id
        ensure_session_err = await self._ensure_chat_session(
            effective_username,
            session_id,
        )
        if ensure_session_err:
            return Response().error(ensure_session_err).__dict__

        config_id, resolve_err = self._resolve_chat_config_id(post_data)
        if resolve_err:
            return Response().error(resolve_err).__dict__

        original_username = g.get("username", "guest")
        g.username = effective_username
        if config_id:
            umo = f"webchat:FriendMessage:webchat!{effective_username}!{session_id}"
            try:
                if config_id == "default":
                    await self.core_lifecycle.umop_config_router.delete_route(umo)
                else:
                    await self.core_lifecycle.umop_config_router.update_route(
                        umo, config_id
                    )
            except Exception as e:
                logger.error(
                    "Failed to update chat config route for %s with %s: %s",
                    umo,
                    config_id,
                    e,
                    exc_info=True,
                )
                return (
                    Response()
                    .error(f"Failed to update chat config route: {e}")
                    .__dict__
                )
        try:
            return await self.chat_route.chat(post_data=post_data)
        finally:
            g.username = original_username

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

    async def _authenticate_chat_ws_api_key(self) -> tuple[bool, str | None]:
        raw_key = self._extract_ws_api_key()
        if not raw_key:
            return False, "Missing API key"

        key_hash = hashlib.pbkdf2_hmac(
            "sha256",
            raw_key.encode("utf-8"),
            b"astrbot_api_key",
            100_000,
        ).hex()
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

    async def _send_chat_ws_error(self, message: str, code: str) -> None:
        await websocket.send_json(
            {
                "type": "error",
                "code": code,
                "data": message,
            }
        )

    async def _update_session_config_route(
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
        except Exception as e:
            logger.error(
                "Failed to update chat config route for %s with %s: %s",
                umo,
                config_id,
                e,
                exc_info=True,
            )
            return f"Failed to update chat config route: {e}"
        return None

    async def _handle_chat_ws_send(self, post_data: dict) -> None:
        effective_username, username_err = self._resolve_open_username(
            post_data.get("username")
        )
        if username_err or not effective_username:
            await self._send_chat_ws_error(
                username_err or "Invalid username", "BAD_USER"
            )
            return

        message = post_data.get("message")
        if message is None:
            await self._send_chat_ws_error("Missing key: message", "INVALID_MESSAGE")
            return

        raw_session_id = post_data.get("session_id", post_data.get("conversation_id"))
        session_id = str(raw_session_id).strip() if raw_session_id is not None else ""
        if not session_id:
            session_id = str(uuid4())

        ensure_session_err = await self._ensure_chat_session(
            effective_username,
            session_id,
        )
        if ensure_session_err:
            await self._send_chat_ws_error(ensure_session_err, "SESSION_ERROR")
            return

        config_id, resolve_err = self._resolve_chat_config_id(post_data)
        if resolve_err:
            await self._send_chat_ws_error(resolve_err, "CONFIG_ERROR")
            return

        config_err = await self._update_session_config_route(
            username=effective_username,
            session_id=session_id,
            config_id=config_id,
        )
        if config_err:
            await self._send_chat_ws_error(config_err, "CONFIG_ERROR")
            return

        message_parts = await self.chat_route._build_user_message_parts(message)
        if not webchat_message_parts_have_content(message_parts):
            await self._send_chat_ws_error(
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
            await self.chat_route.platform_history_mgr.insert(
                platform_id="webchat",
                user_id=session_id,
                content={"type": "user", "message": message_parts_for_storage},
                sender_id=effective_username,
                sender_name=effective_username,
            )

            await websocket.send_json(
                {
                    "type": "session_id",
                    "data": None,
                    "session_id": session_id,
                    "message_id": message_id,
                }
            )

            accumulated_parts = []
            accumulated_text = ""
            accumulated_reasoning = ""
            tool_calls = {}
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
                        await websocket.send_json(stats_info)
                        agent_stats = stats_info["data"]
                    except Exception:
                        pass
                    continue

                await websocket.send_json(result)

                if msg_type == "plain":
                    if chain_type == "tool_call":
                        tool_call = json.loads(result_text)
                        tool_calls[tool_call.get("id")] = tool_call
                        if accumulated_text:
                            accumulated_parts.append(
                                {"type": "plain", "text": accumulated_text}
                            )
                            accumulated_text = ""
                    elif chain_type == "tool_call_result":
                        tcr = json.loads(result_text)
                        tc_id = tcr.get("id")
                        if tc_id in tool_calls:
                            tool_calls[tc_id]["result"] = tcr.get("result")
                            tool_calls[tc_id]["finished_ts"] = tcr.get("ts")
                            accumulated_parts.append(
                                {"type": "tool_call", "tool_calls": [tool_calls[tc_id]]}
                            )
                            tool_calls.pop(tc_id, None)
                    elif chain_type == "reasoning":
                        accumulated_reasoning += result_text
                    elif streaming:
                        accumulated_text += result_text
                    else:
                        accumulated_text = result_text
                elif msg_type == "image":
                    filename = str(result_text).replace("[IMAGE]", "")
                    part = await self.chat_route._create_attachment_from_file(
                        filename, "image"
                    )
                    if part:
                        accumulated_parts.append(part)
                elif msg_type == "record":
                    filename = str(result_text).replace("[RECORD]", "")
                    part = await self.chat_route._create_attachment_from_file(
                        filename, "record"
                    )
                    if part:
                        accumulated_parts.append(part)
                elif msg_type == "file":
                    filename = str(result_text).replace("[FILE]", "")
                    part = await self.chat_route._create_attachment_from_file(
                        filename, "file"
                    )
                    if part:
                        accumulated_parts.append(part)
                elif msg_type == "video":
                    filename = str(result_text).replace("[VIDEO]", "")
                    part = await self.chat_route._create_attachment_from_file(
                        filename, "video"
                    )
                    if part:
                        accumulated_parts.append(part)

                if msg_type == "end":
                    break
                if (streaming and msg_type == "complete") or not streaming:
                    if chain_type in ("tool_call", "tool_call_result"):
                        continue
                    try:
                        refs = self.chat_route._extract_web_search_refs(
                            accumulated_text,
                            accumulated_parts,
                        )
                    except Exception as e:
                        logger.exception(
                            f"Open API WS failed to extract web search refs: {e}",
                            exc_info=True,
                        )

                    saved_record = await self.chat_route._save_bot_message(
                        session_id,
                        accumulated_text,
                        accumulated_parts,
                        accumulated_reasoning,
                        agent_stats,
                        refs,
                    )
                    if saved_record:
                        await websocket.send_json(
                            {
                                "type": "message_saved",
                                "data": {
                                    "id": saved_record.id,
                                    "created_at": saved_record.created_at.replace(tzinfo=timezone.utc).isoformat(),
                                },
                                "session_id": session_id,
                            }
                        )
                    accumulated_parts = []
                    accumulated_text = ""
                    accumulated_reasoning = ""
                    agent_stats = {}
                    refs = {}
        except Exception as e:
            logger.exception(f"Open API WS chat failed: {e}", exc_info=True)
            await self._send_chat_ws_error(
                f"Failed to process message: {e}", "PROCESSING_ERROR"
            )
        finally:
            webchat_queue_mgr.remove_back_queue(message_id)

    async def chat_ws(self) -> None:
        authed, auth_err = await self._authenticate_chat_ws_api_key()
        if not authed:
            await self._send_chat_ws_error(auth_err or "Unauthorized", "UNAUTHORIZED")
            await websocket.close(1008, auth_err or "Unauthorized")
            return

        try:
            while True:
                message = await websocket.receive_json()
                if not isinstance(message, dict):
                    await self._send_chat_ws_error(
                        "message must be an object",
                        "INVALID_MESSAGE",
                    )
                    continue

                msg_type = message.get("t", "send")
                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue
                if msg_type != "send":
                    await self._send_chat_ws_error(
                        f"Unsupported message type: {msg_type}",
                        "INVALID_MESSAGE",
                    )
                    continue

                await self._handle_chat_ws_send(message)
        except Exception as e:
            logger.debug("Open API WS connection closed: %s", e)

    async def upload_file(self):
        return await self.chat_route.post_file()

    async def get_chat_sessions(self):
        username, username_err = self._resolve_open_username(
            request.args.get("username")
        )
        if username_err:
            return Response().error(username_err).__dict__

        assert username is not None  # for type checker

        try:
            page = int(request.args.get("page", 1))
            page_size = int(request.args.get("page_size", 20))
        except ValueError:
            return Response().error("page and page_size must be integers").__dict__

        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 1
        if page_size > 100:
            page_size = 100

        platform_id = request.args.get("platform_id")

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
                    "created_at": session.created_at.replace(tzinfo=timezone.utc).isoformat(),
                    "updated_at": session.updated_at.replace(tzinfo=timezone.utc).isoformat(),
                }
            )

        return (
            Response()
            .ok(
                data={
                    "sessions": sessions_data,
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                }
            )
            .__dict__
        )

    async def get_chat_configs(self):
        conf_list = self._get_chat_config_list()
        return Response().ok(data={"configs": conf_list}).__dict__

    async def _build_message_chain_from_payload(
        self,
        message_payload: str | list,
    ):
        return await build_message_chain_from_payload(
            message_payload,
            get_attachment_by_id=self.db.get_attachment_by_id,
            strict=True,
        )

    async def send_message(self):
        post_data = await request.json or {}
        message_payload = post_data.get("message", {})
        umo = post_data.get("umo")

        if message_payload is None:
            return Response().error("Missing key: message").__dict__
        if not umo:
            return Response().error("Missing key: umo").__dict__

        try:
            session = MessageSesion.from_str(str(umo))
        except Exception as e:
            return Response().error(f"Invalid umo: {e}").__dict__

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
            return (
                Response()
                .error(f"Bot not found or not running for platform: {platform_id}")
                .__dict__
            )

        try:
            message_chain = await self._build_message_chain_from_payload(
                message_payload
            )
            await platform_inst.send_by_session(session, message_chain)
            return Response().ok().__dict__
        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"Open API send_message failed: {e}", exc_info=True)
            return Response().error(f"Failed to send message: {e}").__dict__

    async def get_bots(self):
        bot_ids = []
        for platform in self.core_lifecycle.astrbot_config.get("platform", []):
            platform_id = platform.get("id") if isinstance(platform, dict) else None
            if (
                isinstance(platform_id, str)
                and platform_id
                and platform_id not in bot_ids
            ):
                bot_ids.append(platform_id)
        return Response().ok(data={"bot_ids": bot_ids}).__dict__
