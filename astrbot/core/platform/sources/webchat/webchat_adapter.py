from astrbot.core.lang import t
import asyncio
import os
import time
import uuid
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

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
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from ...register import register_platform_adapter
from .message_parts_helper import (
    message_chain_to_storage_message_parts,
    parse_webchat_message_parts,
)
from .webchat_event import WebChatMessageEvent
from .webchat_queue_mgr import WebChatQueueMgr, webchat_queue_mgr


def _extract_conversation_id(session_id: str) -> str:
    """Extract raw webchat conversation id from event/session id."""
    if session_id.startswith("webchat!"):
        parts = session_id.split("!", 2)
        if len(parts) == 3:
            return parts[2]
    return session_id


class QueueListener:
    def __init__(
        self,
        webchat_queue_mgr: WebChatQueueMgr,
        callback: Callable,
        stop_event: asyncio.Event,
    ) -> None:
        self.webchat_queue_mgr = webchat_queue_mgr
        self.callback = callback
        self.stop_event = stop_event

    async def run(self) -> None:
        """Register callback and keep adapter task alive."""
        self.webchat_queue_mgr.set_listener(self.callback)
        try:
            await self.stop_event.wait()
        finally:
            await self.webchat_queue_mgr.clear_listener()


@register_platform_adapter("webchat", "webchat")
class WebChatAdapter(Platform):
    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)

        self.settings = platform_settings
        self.imgs_dir = os.path.join(get_astrbot_data_path(), "webchat", "imgs")
        self.attachments_dir = Path(get_astrbot_data_path()) / "attachments"
        os.makedirs(self.imgs_dir, exist_ok=True)
        self.attachments_dir.mkdir(parents=True, exist_ok=True)

        self.metadata = PlatformMetadata(
            name="webchat",
            description="webchat",
            id="webchat",
            support_proactive_message=True,
        )
        self._shutdown_event = asyncio.Event()
        self._webchat_queue_mgr = webchat_queue_mgr

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        conversation_id = _extract_conversation_id(session.session_id)
        active_request_ids = self._webchat_queue_mgr.list_back_request_ids(
            conversation_id
        )
        subscription_request_ids = [
            req_id for req_id in active_request_ids if req_id.startswith("ws_sub_")
        ]
        target_request_ids = subscription_request_ids or active_request_ids

        if target_request_ids:
            for request_id in target_request_ids:
                await WebChatMessageEvent._send(
                    request_id,
                    message_chain,
                    session.session_id,
                )
        else:
            message_id = f"active_{uuid.uuid4()!s}"
            await WebChatMessageEvent._send(
                message_id,
                message_chain,
                session.session_id,
            )

        should_persist = (
            bool(subscription_request_ids)
            or not active_request_ids
            or all(req_id.startswith("active_") for req_id in active_request_ids)
        )
        if should_persist:
            try:
                await self._save_proactive_message(conversation_id, message_chain)
            except Exception as e:
                logger.error(
                    t("msg-7177ecf8", e=e),
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
            platform_id="webchat",
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
        """解析消息段列表，返回消息组件列表和纯文本列表

        Args:
            message_parts: 消息段列表
            depth: 当前递归深度
            max_depth: 最大递归深度（用于处理 reply）

        Returns:
            tuple[list, list[str]]: (消息组件列表, 纯文本列表)
        """

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
        abm.self_id = "webchat"
        abm.sender = MessageMember(username, username)

        abm.type = MessageType.FRIEND_MESSAGE

        abm.session_id = f"webchat!{username}!{cid}"

        abm.message_id = payload.get("message_id")

        # 处理消息段列表
        message_parts = payload.get("message", [])
        abm.message, message_str_parts = await self._parse_message_parts(message_parts)

        logger.debug(t("msg-9406158c", res=abm.message))

        abm.timestamp = int(time.time())
        abm.message_str = "".join(message_str_parts)
        abm.raw_message = data
        return abm

    def run(self) -> Coroutine[Any, Any, None]:
        async def callback(data: tuple) -> None:
            abm = await self.convert_message(data)
            await self.handle_msg(abm)

        bot = QueueListener(self._webchat_queue_mgr, callback, self._shutdown_event)
        return bot.run()

    def meta(self) -> PlatformMetadata:
        return self.metadata

    async def handle_msg(self, message: AstrBotMessage) -> None:
        message_event = WebChatMessageEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
        )

        _, _, payload = message.raw_message  # type: ignore
        message_event.set_extra("selected_provider", payload.get("selected_provider"))
        message_event.set_extra("selected_model", payload.get("selected_model"))
        message_event.set_extra(
            "enable_streaming", payload.get("enable_streaming", True)
        )
        message_event.set_extra("action_type", payload.get("action_type"))

        self.commit_event(message_event)

    async def terminate(self) -> None:
        self._shutdown_event.set()
