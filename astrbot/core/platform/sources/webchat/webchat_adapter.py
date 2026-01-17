import asyncio
import os
import time
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

from astrbot import logger
from astrbot.core import db_helper
from astrbot.core.db.po import PlatformMessageHistory
from astrbot.core.message.components import File, Image, Plain, Record, Reply, Video
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
from .webchat_event import WebChatMessageEvent
from .webchat_queue_mgr import WebChatQueueMgr, webchat_queue_mgr


class QueueListener:
    def __init__(self, webchat_queue_mgr: WebChatQueueMgr, callback: Callable) -> None:
        self.webchat_queue_mgr = webchat_queue_mgr
        self.callback = callback
        self.running_tasks = set()

    async def listen_to_queue(self, conversation_id: str):
        """Listen to a specific conversation queue"""
        queue = self.webchat_queue_mgr.get_or_create_queue(conversation_id)
        while True:
            try:
                data = await queue.get()
                await self.callback(data)
            except Exception as e:
                logger.error(
                    f"Error processing message from conversation {conversation_id}: {e}",
                )
                break

    async def run(self):
        """Monitor for new conversation queues and start listeners"""
        monitored_conversations = set()

        while True:
            # Check for new conversations
            current_conversations = set(self.webchat_queue_mgr.queues.keys())
            new_conversations = current_conversations - monitored_conversations

            # Start listeners for new conversations
            for conversation_id in new_conversations:
                task = asyncio.create_task(self.listen_to_queue(conversation_id))
                self.running_tasks.add(task)
                task.add_done_callback(self.running_tasks.discard)
                monitored_conversations.add(conversation_id)
                logger.debug(f"Started listener for conversation: {conversation_id}")

            # Clean up monitored conversations that no longer exist
            removed_conversations = monitored_conversations - current_conversations
            monitored_conversations -= removed_conversations

            await asyncio.sleep(1)  # Check for new conversations every second


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
        os.makedirs(self.imgs_dir, exist_ok=True)

        self.metadata = PlatformMetadata(
            name="webchat",
            description="webchat",
            id="webchat",
        )

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ):
        message_id = f"active_{str(uuid.uuid4())}"
        await WebChatMessageEvent._send(message_id, message_chain, session.session_id)
        await super().send_by_session(session, message_chain)

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
        components = []
        text_parts = []

        for part in message_parts:
            part_type = part.get("type")
            if part_type == "plain":
                text = part.get("text", "")
                components.append(Plain(text=text))
                text_parts.append(text)
            elif part_type == "reply":
                message_id = part.get("message_id")
                reply_chain = []
                reply_message_str = part.get("selected_text", "")
                sender_id = None
                sender_name = None

                if reply_message_str:
                    reply_chain = [Plain(text=reply_message_str)]

                # recursively get the content of the referenced message, if selected_text is empty
                if not reply_message_str and depth < max_depth and message_id:
                    history = await self._get_message_history(message_id)
                    if history and history.content:
                        reply_parts = history.content.get("message", [])
                        if isinstance(reply_parts, list):
                            (
                                reply_chain,
                                reply_text_parts,
                            ) = await self._parse_message_parts(
                                reply_parts,
                                depth=depth + 1,
                                max_depth=max_depth,
                            )
                            reply_message_str = "".join(reply_text_parts)
                        sender_id = history.sender_id
                        sender_name = history.sender_name

                components.append(
                    Reply(
                        id=message_id,
                        chain=reply_chain,
                        message_str=reply_message_str,
                        sender_id=sender_id,
                        sender_nickname=sender_name,
                    )
                )
            elif part_type == "image":
                path = part.get("path")
                if path:
                    components.append(Image.fromFileSystem(path))
            elif part_type == "record":
                path = part.get("path")
                if path:
                    components.append(Record.fromFileSystem(path))
            elif part_type == "file":
                path = part.get("path")
                if path:
                    filename = part.get("filename") or (
                        os.path.basename(path) if path else "file"
                    )
                    components.append(File(name=filename, file=path))
            elif part_type == "video":
                path = part.get("path")
                if path:
                    components.append(Video.fromFileSystem(path))

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

        logger.debug(f"WebChatAdapter: {abm.message}")

        abm.timestamp = int(time.time())
        abm.message_str = "".join(message_str_parts)
        abm.raw_message = data
        return abm

    def run(self) -> Coroutine[Any, Any, None]:
        async def callback(data: tuple):
            abm = await self.convert_message(data)
            await self.handle_msg(abm)

        bot = QueueListener(webchat_queue_mgr, callback)
        return bot.run()

    def meta(self) -> PlatformMetadata:
        return self.metadata

    async def handle_msg(self, message: AstrBotMessage):
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

        self.commit_event(message_event)

    async def terminate(self):
        # Do nothing
        pass
