import os
import time
import asyncio
import logging
from typing import Awaitable, Any
from aiocqhttp import CQHttp, Event
from astrbot.api.platform import Platform, AstrBotMessage, MessageMember, MessageType, PlatformMetadata
from astrbot.api.event import MessageChain
from .aiocqhttp_message_event import *  # noqa: F403
from astrbot.api.message_components import *  # noqa: F403
from astrbot.api import logger
from .aiocqhttp_message_event import AiocqhttpMessageEvent
from astrbot.core.platform.astr_message_event import MessageSesion
from ...register import register_platform_adapter
from aiocqhttp.exceptions import ActionFailed

@register_platform_adapter("aiocqhttp", "适用于 OneBot 标准的消息平台适配器，支持反向 WebSockets。")
class AiocqhttpAdapter(Platform):
    def __init__(self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue) -> None:
        super().__init__(event_queue)
        
        self.config = platform_config
        self.settings = platform_settings
        self.unique_session = platform_settings['unique_session']
        self.host = platform_config['ws_reverse_host']
        self.port = platform_config['ws_reverse_port']
        
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
        
    async def convert_message(self, event: Event) -> AstrBotMessage:
        abm = AstrBotMessage()
        abm.self_id = str(event.self_id)
        abm.tag = "aiocqhttp"
        
        abm.sender = MessageMember(str(event.sender['user_id']), event.sender['nickname'])        

        if event['message_type'] == 'group':
            abm.type = MessageType.GROUP_MESSAGE
            abm.group_id = str(event.group_id)
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
        logger.debug(f"aiocqhttp: 收到消息: {event.message}")
        for m in event.message:
            t = m['type']
            a = None
            if t == 'text':
                message_str += m['data']['text'].strip()
            elif t == 'file':
                try:
                    # Napcat, LLBot
                    ret = await self.bot.call_action(action="get_file", file_id=event.message[0]['data']['file_id'])
                    if not ret.get('file', None):
                        raise ValueError(f"无法解析文件响应: {ret}")
                    if not os.path.exists(ret['file']):
                        raise FileNotFoundError(f"文件不存在: {ret['file']}。如果您使用 Docker 部署了 AstrBot 或者消息协议端(Napcat等),暂时无法获取用户上传的文件。")
                    
                    m['data'] = {
                        "file": ret['file'],
                        "name": ret['file_name']
                    }
                except ActionFailed as e:
                    logger.error(f"获取文件失败: {e}，此消息段将被忽略。")
                except BaseException as e:
                    logger.error(f"获取文件失败: {e}，此消息段将被忽略。")
                    
            a = ComponentTypes[t](**m['data'])  # noqa: F405
            abm.message.append(a)
        abm.timestamp = int(time.time())
        abm.message_str = message_str
        abm.raw_message = event
        return abm
    
    def run(self) -> Awaitable[Any]:
        if not self.host or not self.port:
            return
        self.bot = CQHttp(use_ws_reverse=True, import_name='aiocqhttp', api_timeout_sec=180)
        @self.bot.on_message('group')
        async def group(event: Event):
            abm = await self.convert_message(event)
            if abm:
                await self.handle_msg(abm)
        
        @self.bot.on_message('private')
        async def private(event: Event):
            abm = await self.convert_message(event)
            if abm:
                await self.handle_msg(abm)
                
        @self.bot.on_websocket_connection
        def on_websocket_connection(_):
            logger.info("aiocqhttp 适配器已连接。")
        
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