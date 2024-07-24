import time
import traceback
import logging
from aiocqhttp import CQHttp, Event
from . import Platform
from type.astrbot_message import *
from type.message_event import *
from typing import Union, List, Dict
from nakuru.entities.components import *
from SparkleLogging.utils.core import LogManager
from logging import Logger
from astrbot.message.handler import MessageHandler

logger: Logger = LogManager.GetLogger(log_name='astrbot')

class AIOCQHTTP(Platform):
    def __init__(self, context: Context, message_handler: MessageHandler) -> None:
        self.message_handler = message_handler
        self.waiting = {}
        self.context = context
        self.unique_session = self.context.unique_session
        self.announcement = self.context.base_config.get("announcement", "欢迎新人！")
        self.host = self.context.base_config['aiocqhttp']['ws_reverse_host']
        self.port = self.context.base_config['aiocqhttp']['ws_reverse_port']

        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)   
        
    def compat_onebot2astrbotmsg(self, event: Event) -> AstrBotMessage:
        
        abm = AstrBotMessage()
        abm.self_id = str(event.self_id)
        abm.tag = "aiocqhttp"
        
        abm.sender = MessageMember(str(event.sender['user_id']), event.sender['nickname'])        

        if event['message_type'] == 'group':
            abm.type = MessageType.GROUP_MESSAGE
        elif event['message_type'] == 'private':
            abm.type = MessageType.FRIEND_MESSAGE
        
        if self.unique_session:
            abm.session_id = abm.sender.user_id
        else:
            abm.session_id = str(event.group_id) if abm.type == MessageType.GROUP_MESSAGE else abm.sender.user_id
        
        abm.message_id = str(event.message_id)
        abm.message = []
        
        message_str = ""
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
                a = Image(file=m['data']['file'])
                abm.message.append(a)
        abm.timestamp = int(time.time())
        abm.message_str = message_str
        abm.raw_message = event
        return abm
            
    def run_aiocqhttp(self):
        if not self.host or not self.port:
            return
        self.bot = CQHttp(use_ws_reverse=True)
        
        @self.bot.on_message('group')
        async def group(event: Event):
            abm = self.compat_onebot2astrbotmsg(event)
            if abm:
                await self.handle_msg(event, abm)
            return {'reply': event.message}
        
        @self.bot.on_message('private')
        async def private(event: Event):
            abm = self.compat_onebot2astrbotmsg(event)
            if abm:
                await self.handle_msg(event, abm)
            return {'reply': event.message}
        
        return self.bot.run_task(host=self.host, port=int(self.port))
        
    async def handle_msg(self, message: AstrBotMessage):
        logger.info(
            f"{message.sender.nickname}/{message.sender.user_id} -> {self.parse_message_outline(message)}")
        
        # 解析 role
        sender_id = str(message.sender.user_id)
        if sender_id == self.context.config_helper.get('admin_qq', '') or \
                sender_id in self.context.config_helper.get('other_admins', []):
            role = 'admin'
        else:
            role = 'member'
            
        # construct astrbot message event
        ame = AstrMessageEvent().from_astrbot_message(message, self.context, "gocq", message.session_id, role)
        
        # transfer control to message handler
        message_result = await self.message_handler.handle(ame)
        if not message_result: return
        
        await self.reply_msg(message, message_result.result_message)
        if message_result.callback:
            message_result.callback()

        # 如果是等待回复的消息
        if message.session_id in self.waiting and self.waiting[message.session_id] == '':
            self.waiting[message.session_id] = message

    
    async def reply_msg(self,
                        message: AstrBotMessage,
                        result_message: list):
        await super().reply_msg()
        """
        回复用户唤醒机器人的消息。（被动回复）
        """
        logger.info(
            f"{message.sender.user_id} <- {self.parse_message_outline(message)}")
        
        if isinstance(res, str):
            res = [Plain(text=res), ]
            
        # if image mode, put all Plain texts into a new picture.
        if self.context.config_helper.get("qq_pic_mode", False) and isinstance(res, list):
            rendered_images = await self.convert_to_t2i_chain(res)
            if rendered_images:
                try:
                    await self._reply(message, rendered_images)
                    return
                except BaseException as e:
                    logger.warn(traceback.format_exc())
                    logger.warn(f"以文本转图片的形式回复消息时发生错误: {e}，将尝试默认方式。")
            
    async def _reply(self, message: AstrBotMessage, message_chain: List[BaseMessageComponent]):
        if isinstance(message_chain, str): 
            message_chain = [Plain(text=message_chain), ]
        
        await self.bot.send(message.raw_message, message_chain)