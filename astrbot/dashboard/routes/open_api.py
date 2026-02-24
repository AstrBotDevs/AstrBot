from uuid import uuid4

from quart import g, request

from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.platform.message_session import MessageSesion
from astrbot.core.platform.sources.webchat.message_parts_helper import (
    build_message_chain_from_payload,
)

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
                    "created_at": session.created_at.astimezone().isoformat(),
                    "updated_at": session.updated_at.astimezone().isoformat(),
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
