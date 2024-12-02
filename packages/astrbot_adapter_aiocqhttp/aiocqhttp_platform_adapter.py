import time
import asyncio
import traceback
import logging
from typing import Awaitable, Any
from aiocqhttp import CQHttp, Event
from astrbot.api import Platform
from astrbot.api import MessageChain, MessageEventResult, AstrBotMessage, MessageMember, MessageType, PlatformMetadata
from .aiocqhttp_message_event import *
from astrbot.api.message_components import *
from astrbot.api import logger
from .aiocqhttp_message_event import AiocqhttpMessageEvent
from astrbot.core.config.astrbot_config import PlatformConfig, AiocqhttpPlatformConfig, PlatformSettings
from astrbot.core.platform.astr_message_event import MessageSesion

class AiocqhttpAdapter(Platform):
    def __init__(self, platform_config: AiocqhttpPlatformConfig, platform_settings: PlatformSettings, event_queue: asyncio.Queue) -> None:
        super().__init__(event_queue)
        
        self.config = platform_config
        self.settings = platform_settings
        self.unique_session = platform_settings.unique_session
        self.host = platform_config.ws_reverse_host
        self.port = platform_config.ws_reverse_port
        
        self.metadata = PlatformMetadata(
            "aiocqhttp",
            "适用于 OneBot 标准的消息平台适配器，支持反向 WebSockets。",
        )
        
    async def send_by_session(self, session: MessageSesion, message_chain: MessageChain):
        ret = await AiocqhttpMessageEvent._parse_onebot_json(message_chain)
        match session.message_type.value:
            case MessageType.GROUP_MESSAGE.value:
                if "_" in session.session_id:
                    # 独立会话
                    _, group_id = session.session_id.split("_")
                    await self.bot.send_group_msg(group_id=group_id, message=ret)
                else:
                    await self.bot.send_group_msg(group_id=session.session_id, message=ret)
            case MessageType.FRIEND_MESSAGE.value:
                await self.bot.send_private_msg(user_id=session.session_id, message=ret)
        await super().send_by_session(session, message_chain)
        
    def convert_message(self, event: Event) -> AstrBotMessage:
        abm = AstrBotMessage()
        abm.self_id = str(event.self_id)
        abm.tag = "aiocqhttp"
        
        abm.sender = MessageMember(str(event.sender['user_id']), event.sender['nickname'])        

        if event['message_type'] == 'group':
            abm.type = MessageType.GROUP_MESSAGE
        elif event['message_type'] == 'private':
            abm.type = MessageType.FRIEND_MESSAGE
        
        if self.unique_session:
            abm.session_id = abm.sender.user_id + "_" + str(event.group_id) # 也保留群组 id
        else:
            abm.session_id = str(event.group_id) if abm.type == MessageType.GROUP_MESSAGE else abm.sender.user_id
        
        abm.message_id = str(event.message_id)
        abm.message = []
        
        message_str = ""
        if not isinstance(event.message, list):
            err = f"aiocqhttp: 无法识别的消息类型: {str(event.message)}，此条消息将被忽略。如果您在使用 go-cqhttp，请将其配置文件中的 message.post-format 更改为 array。"
            logger.critical(err)
            try:
                self.bot.send(event, err)
            except BaseException as e:
                logger.error(f"回复消息失败: {e}")
            return
        for m in event.message:
            t = m['type']
            a = None
            if t == 'at':
                a = At(**m['data'])
                abm.message.append(a)
            if t == 'text':
                a = Plain(text=m['data']['text'])
                message_str += m['data']['text'].strip()
                abm.message.append(a)
            if t == 'image':
                file = m['data']['file'] if 'file' in m['data'] else None
                url = m['data']['url'] if 'url' in m['data'] else None
                a = Image(file=file, url=url)
                abm.message.append(a)
        abm.timestamp = int(time.time())
        abm.message_str = message_str
        abm.raw_message = event
        return abm

    def handle_whitelist(self, event: Event) -> bool:
        match event['message_type']:
            case "group":
                if self.config.qq_group_id_whitelist and str(event.group_id) in self.config.qq_group_id_whitelist:
                    return True
            case "private":
                if self.config.qq_id_whitelist and str(event.sender['user_id']) in self.config.qq_id_whitelist:
                    return True
        return False
    
    def run(self) -> Awaitable[Any]:
        if not self.host or not self.port:
            return
        self.bot = CQHttp(use_ws_reverse=True, import_name='aiocqhttp', api_timeout_sec=180)
        @self.bot.on_message('group')
        async def group(event: Event):
            if not self.handle_whitelist(event):
                logger.debug(f"一个群消息({event.group_id})事件由于不在白名单而被过滤。")
                return
            abm = self.convert_message(event)
            if abm:
                await self.handle_msg(abm)
        
        @self.bot.on_message('private')
        async def private(event: Event):
            if not self.handle_whitelist(event):
                logger.debug(f"一个私聊消息({event.sender['nickname']}/{event.sender['user_id']})事件由于不在白名单而被过滤。")
                return
            abm = self.convert_message(event)
            if abm:
                await self.handle_msg(abm)
        
        bot = self.bot.run_task(host=self.host, port=int(self.port), shutdown_trigger=self.shutdown_trigger_placeholder)
        
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        logging.getLogger('aiocqhttp').setLevel(logging.ERROR)
        
        return bot
    
    def meta(self) -> PlatformMetadata:
        return self.metadata
    
    async def shutdown_trigger_placeholder(self):
        while not self._event_queue.closed:
            await asyncio.sleep(1)
        logger.info("aiocqhttp 适配器已关闭。")

    async def handle_msg(self, message: AstrBotMessage):
        
        message_event = AiocqhttpMessageEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            bot=self.bot
        )
        
        self.commit_event(message_event)