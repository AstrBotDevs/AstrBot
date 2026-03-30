import asyncio
import os
import time
from collections.abc import Callable, Coroutine
from typing import Any, cast

from astrbot import logger
from astrbot.core import db_helper
from astrbot.core.db.po import PlatformMessageHistory
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.platform.register import register_platform_adapter
from astrbot.core.platform.sources.webchat.message_parts_helper import (
    message_chain_to_storage_message_parts,
    parse_webchat_message_parts,
)
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .tui_event import TUIMessageEvent
from .tui_queue_mgr import TUIQueueMgr, tui_queue_mgr


def _extract_conversation_id(session_id: str) -> str:
    """Extract raw TUI conversation id from event/session id."""
    if session_id.startswith("tui!"):
        parts = session_id.split("!", 2)
        if len(parts) == 3:
            return parts[2]
    return session_id


class QueueListener:
    def __init__(
        self,
        tui_queue_mgr: TUIQueueMgr,
        callback: Callable,
        stop_event: asyncio.Event,
    ) -> None:
        self.tui_queue_mgr = tui_queue_mgr
        self.callback = callback
        self.stop_event = stop_event

    async def run(self) -> None:
        """Register callback and keep adapter task alive."""
        self.tui_queue_mgr.set_listener(self.callback)
        try:
            await self.stop_event.wait()
        finally:
            await self.tui_queue_mgr.clear_listener()


@register_platform_adapter("tui", "tui")
class TUIAdapter(Platform):
    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)

        self.settings = platform_settings
        self.imgs_dir = os.path.join(get_astrbot_data_path(), "tui", "imgs")
        self.attachments_dir = os.path.join(get_astrbot_data_path(), "attachments")
        os.makedirs(self.imgs_dir, exist_ok=True)
        os.makedirs(self.attachments_dir, exist_ok=True)

        self.metadata = PlatformMetadata(
            name="tui",
            description="tui",
            id="tui",
            support_proactive_message=True,
        )
        self._shutdown_event = asyncio.Event()
        self._tui_queue_mgr = tui_queue_mgr

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        conversation_id = _extract_conversation_id(session.session_id)
        active_request_ids = self._tui_queue_mgr.list_back_request_ids(conversation_id)
        stream_request_ids = [
            req_id for req_id in active_request_ids if not req_id.startswith("ws_sub_")
        ]
        target_request_ids = stream_request_ids or active_request_ids

        if not target_request_ids:
            try:
                await self._save_proactive_message(conversation_id, message_chain)
            except Exception as e:
                logger.error(
                    f"[TUIAdapter] Failed to save proactive message: {e}",
                    exc_info=True,
                )
            await super().send_by_session(session, message_chain)
            return

        for request_id in target_request_ids:
            await TUIMessageEvent._send(
                request_id,
                message_chain,
                session.session_id,
                streaming=True,
                emit_complete=True,
            )

        if not stream_request_ids:
            try:
                await self._save_proactive_message(conversation_id, message_chain)
            except Exception as e:
                logger.error(
                    f"[TUIAdapter] Failed to save proactive message: {e}",
                    exc_info=True,
                )

        await super().send_by_session(session, message_chain)

    async def _save_proactive_message(
        self,
        conversation_id: str,
        message_chain: MessageChain,
    ) -> None:
        message_parts = await message_chain_to_storage_message_parts(
            message_chain,
            insert_attachment=db_helper.insert_attachment,
            attachments_dir=self.attachments_dir,
        )
        if not message_parts:
            return

        await db_helper.insert_platform_message_history(
            platform_id="tui",
            user_id=conversation_id,
            content={"type": "bot", "message": message_parts},
            sender_id="bot",
            sender_name="bot",
        )

    async def _get_message_history(
        self, message_id: int
    ) -> PlatformMessageHistory | None:
        return await db_helper.get_platform_message_history_by_id(message_id)

    async def _parse_message_parts(
        self,
        message_parts: list,
        depth: int = 0,
        max_depth: int = 1,
    ) -> tuple[list, list[str]]:
        """Parse message parts list, return message components and plain text lists."""

        async def get_reply_parts(
            message_id: Any,
        ) -> tuple[list[dict], str | None, str | None] | None:
            history = await self._get_message_history(message_id)
            if not history or not history.content:
                return None

            reply_parts = history.content.get("message", [])
            if not isinstance(reply_parts, list):
                return None

            return reply_parts, history.sender_id, history.sender_name

        components, text_parts, _ = await parse_webchat_message_parts(
            message_parts,
            strict=False,
            include_empty_plain=True,
            verify_media_path_exists=False,
            reply_history_getter=get_reply_parts,
            current_depth=depth,
            max_reply_depth=max_depth,
            cast_reply_id_to_str=False,
        )
        return components, text_parts

    async def convert_message(self, data: tuple) -> AstrBotMessage:
        username, cid, payload = data

        abm = AstrBotMessage()
        abm.self_id = "tui"
        abm.sender = MessageMember(username, username)

        abm.type = MessageType.FRIEND_MESSAGE

        abm.session_id = f"tui!{username}!{cid}"

        abm.message_id = payload.get("message_id")

        message_parts = payload.get("message", [])
        abm.message, message_str_parts = await self._parse_message_parts(message_parts)

        logger.debug(f"TUIAdapter: {abm.message}")

        abm.timestamp = int(time.time())
        abm.message_str = "".join(message_str_parts)
        abm.raw_message = data
        return abm

    def run(self) -> Coroutine[Any, Any, None]:
        async def callback(data: tuple) -> None:
            abm = await self.convert_message(data)
            await self.handle_msg(abm)

        bot = QueueListener(self._tui_queue_mgr, callback, self._shutdown_event)
        return bot.run()

    def meta(self) -> PlatformMetadata:
        return self.metadata

    async def handle_msg(self, message: AstrBotMessage) -> None:
        message_event = TUIMessageEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
        )

        _, _, payload = cast(tuple[Any, Any, dict[str, Any]], message.raw_message)
        message_event.set_extra("selected_provider", payload.get("selected_provider"))
        message_event.set_extra("selected_model", payload.get("selected_model"))
        message_event.set_extra(
            "enable_streaming", payload.get("enable_streaming", True)
        )
        message_event.set_extra("action_type", payload.get("action_type"))

        self.commit_event(message_event)

    async def terminate(self) -> None:
        self._shutdown_event.set()
