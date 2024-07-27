import time
import asyncio
import traceback
import logging
from aiocqhttp import CQHttp, Event
from aiocqhttp.exceptions import ActionFailed
from . import Platform
from type.astrbot_message import *
from type.message_event import *
from type.command import *
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
        self.bot = CQHttp(use_ws_reverse=True, import_name='aiocqhttp')
        @self.bot.on_message('group')
        async def group(event: Event):
            abm = self.convert_message(event)
            if abm:
                await self.handle_msg(abm)
            # return {'reply': event.message}
        
        @self.bot.on_message('private')
        async def private(event: Event):
            abm = self.convert_message(event)
            if abm:
                await self.handle_msg(abm)
            # return {'reply': event.message}
        
        bot = self.bot.run_task(host=self.host, port=int(self.port), shutdown_trigger=self.shutdown_trigger_placeholder)
        
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        logging.getLogger('aiocqhttp').setLevel(logging.ERROR)
        
        return bot
    
    async def shutdown_trigger_placeholder(self):
        while True:
            await asyncio.sleep(1)
    
    def pre_check(self, message: AstrBotMessage) -> bool:
        # if message chain contains Plain components or At components which points to self_id, return True
        if message.type == MessageType.FRIEND_MESSAGE:
            return True
        for comp in message.message:
            if isinstance(comp, At) and str(comp.qq) == message.self_id:
                return True
        # check nicks
        if self.check_nick(message.message_str):
            return True
        return False
        
    async def handle_msg(self, message: AstrBotMessage):
        logger.info(
            f"{message.sender.nickname}/{message.sender.user_id} -> {self.parse_message_outline(message)}")
        
        if not self.pre_check(message):
            return
        
        # 解析 role
        sender_id = str(message.sender.user_id)
        if sender_id == self.context.config_helper.get('admin_qq', '') or \
                sender_id in self.context.config_helper.get('other_admins', []):
            role = 'admin'
        else:
            role = 'member'
            
        # construct astrbot message event
        ame = AstrMessageEvent.from_astrbot_message(message, self.context, "aiocqhttp", message.session_id, role)
        
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
        """
        回复用户唤醒机器人的消息。（被动回复）
        """
        logger.info(
            f"{message.sender.user_id} <- {self.parse_message_outline(message)}")
        
        res = result_message
        
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
        
        await self._reply(message, res)
            
    async def _reply(self, message: Union[AstrBotMessage, Dict], message_chain: List[BaseMessageComponent]):
        if isinstance(message_chain, str): 
            message_chain = [Plain(text=message_chain), ]
            
        ret = []
        image_idx = []
        for idx, segment in enumerate(message_chain):
            d = segment.toDict()
            if isinstance(segment, Plain):
                d['type'] = 'text'
            if isinstance(segment, Image):
                image_idx.append(idx)
            ret.append(d)
        try:
            if isinstance(message, AstrBotMessage):
                await self.bot.send(message.raw_message, ret)
            if isinstance(message, dict):
                if 'group_id' in message:
                    await self.bot.send_group_msg(group_id=message['group_id'], message=ret)
                elif 'user_id' in message:
                    await self.bot.send_private_msg(user_id=message['user_id'], message=ret)
                else:
                    raise Exception("aiocqhttp: 无法识别的消息来源。仅支持 group_id 和 user_id。")
        except ActionFailed as e:
            logger.error(traceback.format_exc())
            logger.error(f"回复消息失败: {e}")
            if e.retcode == 1200:
                # ENOENT
                if not image_idx:
                    raise e
                logger.info("检测到失败原因为文件未找到，猜测用户的协议端与 AstrBot 位于不同的文件系统上。尝试采用上传图片的方式发图。")
                for idx in image_idx:
                    if ret[idx]['data']['file'].startswith('file://'):
                        logger.info(f"正在上传图片: {ret[idx]['data']['path']}")
                        image_url = await self.context.image_uploader.upload_image(ret[idx]['data']['path'])
                        logger.info(f"上传成功。")
                        ret[idx]['data']['file'] = image_url
                        ret[idx]['data']['path'] = image_url
                await self.bot.send(message.raw_message, ret)
                
    async def send_msg(self, target: Dict[str, int], result_message: CommandResult):
        '''
        以主动的方式给QQ用户、QQ群发送一条消息。
        
        `target` 接收一个 dict 类型的值引用。
        
        - 要发给 QQ 下的某个用户，请添加 key `user_id`，值为 int 类型的 qq 号；
        - 要发给某个群聊，请添加 key `group_id`，值为 int 类型的 qq 群号；
        
        '''
        
        await self._reply(target, result_message.message_chain)