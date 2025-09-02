import time
import asyncio
import uuid
import os
from typing import Awaitable, Any, Callable
from astrbot.core.platform import (
    Platform,
    AstrBotMessage,
    MessageMember,
    MessageType,
    PlatformMetadata,
)
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.message.components import Plain, Image, Record  # noqa: F403
from astrbot import logger
from .webchat_queue_mgr import webchat_queue_mgr, WebChatQueueMgr
from .webchat_event import WebChatMessageEvent
from astrbot.core.platform.astr_message_event import MessageSesion
from ...register import register_platform_adapter
from astrbot.core.utils.astrbot_path import get_astrbot_data_path


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
                    f"Error processing message from conversation {conversation_id}: {e}"
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
        self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue
    ) -> None:
        super().__init__(event_queue)

        self.config = platform_config
        self.settings = platform_settings
        self.unique_session = platform_settings["unique_session"]
        self.imgs_dir = os.path.join(get_astrbot_data_path(), "webchat", "imgs")
        os.makedirs(self.imgs_dir, exist_ok=True)

        self.metadata = PlatformMetadata(
            name="webchat", description="webchat", id=self.config.get("id", "")
        )

    async def send_by_session(
        self, session: MessageSesion, message_chain: MessageChain
    ):
        await WebChatMessageEvent._send(message_chain, session.session_id)
        await super().send_by_session(session, message_chain)

    async def convert_message(self, data: tuple) -> AstrBotMessage:
        username, cid, payload = data

        abm = AstrBotMessage()
        abm.self_id = "webchat"
        abm.tag = "webchat"
        abm.sender = MessageMember(username, username)

        abm.type = MessageType.FRIEND_MESSAGE

        abm.session_id = f"webchat!{username}!{cid}"

        abm.message_id = str(uuid.uuid4())
        abm.message = []

        if payload["message"]:
            abm.message.append(Plain(payload["message"]))
        if payload["image_url"]:
            if isinstance(payload["image_url"], list):
                for img in payload["image_url"]:
                    abm.message.append(
                        Image.fromFileSystem(os.path.join(self.imgs_dir, img))
                    )
            else:
                abm.message.append(
                    Image.fromFileSystem(
                        os.path.join(self.imgs_dir, payload["image_url"])
                    )
                )
        if payload["audio_url"]:
            if isinstance(payload["audio_url"], list):
                for audio in payload["audio_url"]:
                    path = os.path.join(self.imgs_dir, audio)
                    abm.message.append(Record(file=path, path=path))
            else:
                path = os.path.join(self.imgs_dir, payload["audio_url"])
                abm.message.append(Record(file=path, path=path))

        logger.debug(f"WebChatAdapter: {abm.message}")

        message_str = payload["message"]
        abm.timestamp = int(time.time())
        abm.message_str = message_str
        abm.raw_message = data
        return abm

    def run(self) -> Awaitable[Any]:
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

        self.commit_event(message_event)

    async def terminate(self):
        # Do nothing
        pass
