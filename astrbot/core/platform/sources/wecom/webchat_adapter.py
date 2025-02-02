import time
import asyncio
import uuid
import os
from typing import Awaitable, Any
from astrbot.api.platform import Platform, AstrBotMessage, MessageMember, MessageType, PlatformMetadata
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain, Image, Record  # noqa: F403
from astrbot.api import logger
from astrbot.core import web_chat_queue, web_chat_back_queue
from .webchat_event import WebChatMessageEvent
from astrbot.core.platform.astr_message_event import MessageSesion
from ...register import register_platform_adapter


@register_platform_adapter("wecom", "wecom")
class WecomAdapter(Platform):
    def __init__(self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue) -> None:
        super().__init__(event_queue)
        
        self.config = platform_config
        self.settings = platform_settings
        self.unique_session = platform_settings['unique_session']

        self.metadata = PlatformMetadata(
            "wecom",
            "wecom",
        )
        
    async def send_by_session(self, session: MessageSesion, message_chain: MessageChain):

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
        
        if payload['message']:
            abm.message.append(Plain(payload['message']))
        if payload['image_url']:
            if isinstance(payload['image_url'], list):
                for img in payload['image_url']:
                    abm.message.append(Image.fromFileSystem(os.path.join(self.imgs_dir, img)))
            else:
                abm.message.append(Image.fromFileSystem(os.path.join(self.imgs_dir, payload['image_url'])))
        if payload['audio_url']:
            if isinstance(payload['audio_url'], list):
                for audio in payload['audio_url']:
                    path = os.path.join(self.imgs_dir, audio)
                    abm.message.append(Record(file=path, path=path))
            else:
                path = os.path.join(self.imgs_dir, payload['audio_url'])
                abm.message.append(Record(file=path, path=path))
            
        logger.debug(f"WebChatAdapter: {abm.message}")
        
        message_str = payload['message']
        abm.timestamp = int(time.time())
        abm.message_str = message_str
        abm.raw_message = data
        return abm
    
    def run(self) -> Awaitable[Any]:
        pass
    
    def meta(self) -> PlatformMetadata:
        return self.metadata

    async def handle_msg(self, message: AstrBotMessage):
        
        message_event = WebChatMessageEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id
        )
        
        self.commit_event(message_event)