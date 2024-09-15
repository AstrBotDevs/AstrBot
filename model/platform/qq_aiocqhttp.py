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
from util.cmd_config import PlatformConfig, AiocqhttpPlatformConfig

logger: Logger = LogManager.GetLogger(log_name='astrbot')

class AIOCQHTTP(Platform):
    def __init__(self, context: Context, 
                 message_handler: MessageHandler, 
                 platform_config: PlatformConfig) -> None:
        super().__init__("aiocqhttp", context)
        assert isinstance(platform_config, AiocqhttpPlatformConfig), "aiocqhttp: 无法识别的配置类型。"
        
        self.message_handler = message_handler
        self.waiting = {}
        self.context = context
        self.config = platform_config
        self.unique_session = context.config_helper.platform_settings.unique_session
        self.host = platform_config.ws_reverse_host
        self.port = platform_config.ws_reverse_port
        self.admins = context.config_helper.admins_id
        
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
            
    def run_aiocqhttp(self):
        if not self.host or not self.port:
            return
        self.bot = CQHttp(use_ws_reverse=True, import_name='aiocqhttp', api_timeout_sec=180)
        @self.bot.on_message('group')
        async def group(event: Event):
            abm = self.convert_message(event)
            if abm:
                await self.handle_msg(abm)
        
        @self.bot.on_message('private')
        async def private(event: Event):
            abm = self.convert_message(event)
            if abm:
                await self.handle_msg(abm)
        
        bot = self.bot.run_task(host=self.host, port=int(self.port), shutdown_trigger=self.shutdown_trigger_placeholder)
        
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        logging.getLogger('aiocqhttp').setLevel(logging.ERROR)
        
        return bot
    
    async def shutdown_trigger_placeholder(self):
        while self.context.running:
            await asyncio.sleep(1)
    
    async def pre_check(self, message: AstrBotMessage) -> bool:
        # if message chain contains Plain components or 
        # At components which points to self_id, return True
        if message.type == MessageType.FRIEND_MESSAGE:
            return True, "friend"
        for comp in message.message:
            if isinstance(comp, At) and str(comp.qq) == message.self_id:
                return True, "at"
        # check commands which ignore prefix
        if await self.context.command_manager.check_command_ignore_prefix(message.message_str):
            return True, "command"
        # check nicks
        if self.check_nick(message.message_str):
            return True, "nick"
        return False, "none"
        
    async def handle_msg(self, message: AstrBotMessage):
        logger.info(
            f"{message.sender.nickname}/{message.sender.user_id} -> {self.parse_message_outline(message)}")
        
        ok, reason = await self.pre_check(message)
        if not ok:
            return
        
        # 解析 role
        sender_id = str(message.sender.user_id)
        if sender_id in self.admins:
            role = 'admin'
        else:
            role = 'member'
            
        # parse unified message origin
        unified_msg_origin = None
        assert isinstance(message.raw_message, Event)
        if message.type == MessageType.GROUP_MESSAGE:
            unified_msg_origin = f"aiocqhttp:{message.type.value}:{message.raw_message.group_id}"
        elif message.type == MessageType.FRIEND_MESSAGE:
            unified_msg_origin = f"aiocqhttp:{message.type.value}:{message.sender.user_id}"
        
        logger.debug(f"unified_msg_origin: {unified_msg_origin}")

        # construct astrbot message event
        ame = AstrMessageEvent.from_astrbot_message(message, 
                                                    self.context, 
                                                    "aiocqhttp", 
                                                    message.session_id, 
                                                    role, 
                                                    unified_msg_origin,
                                                    reason == "command") # only_command
        
        # transfer control to message handler
        message_result = await self.message_handler.handle(ame)
        if not message_result: return
        
        await self.reply_msg(message, message_result.result_message, message_result.use_t2i)
        if message_result.callback:
            message_result.callback()

        # 如果是等待回复的消息
        if message.session_id in self.waiting and self.waiting[message.session_id] == '':
            self.waiting[message.session_id] = message
            
        return message_result

    
    async def reply_msg(self,
                        message: AstrBotMessage,
                        result_message: list,
                        use_t2i: bool = None):
        """
        回复用户唤醒机器人的消息。（被动回复）
        """
        res = result_message
        
        if isinstance(res, str):
            res = [Plain(text=res), ]
            
        # if image mode, put all Plain texts into a new picture.
        if (use_t2i or (use_t2i == None and self.context.config_helper.t2i)) and isinstance(result_message, list):
            rendered_images = await self.convert_to_t2i_chain(res)
            if rendered_images:
                try:
                    await self._reply(message, rendered_images)
                    return rendered_images
                except BaseException as e:
                    logger.warn(traceback.format_exc())
                    logger.warn(f"以文本转图片的形式回复消息时发生错误: {e}，将尝试默认方式。")
        
        await self._reply(message, res)
        return res
            
    async def _reply(self, message: Union[AstrBotMessage, Dict], message_chain: List[BaseMessageComponent]):
        await self.record_metrics()
        if isinstance(message_chain, str): 
            message_chain = [Plain(text=message_chain), ]
        
        if isinstance(message, AstrBotMessage):
            logger.info(
                f"{message.sender.user_id} <- {self.parse_message_outline(message)}")
        else:
            logger.info(f"回复消息: {message_chain}")

        ret = []
        image_idx = []
        for idx, segment in enumerate(message_chain):
            d = segment.toDict()
            if isinstance(segment, Plain):
                d['type'] = 'text'
            if isinstance(segment, Image):
                image_idx.append(idx)
            ret.append(d)
        if os.environ.get('TEST_MODE', 'off') == 'on':
            logger.info(f"回复消息: {ret}")
            return
        try:
            await self._reply_wrapper(message, ret)
        except ActionFailed as e:
            if e.retcode == 1200:
                # ENOENT
                if not image_idx:
                    raise e
                logger.warn("回复失败。检测到失败原因为文件未找到，猜测用户的协议端与 AstrBot 位于不同的文件系统上。尝试采用上传图片的方式发图。")
                for idx in image_idx:
                    if ret[idx]['data']['file'].startswith('file://'):
                        logger.info(f"正在上传图片: {ret[idx]['data']['path']}")
                        image_url = await self.context.image_uploader.upload_image(ret[idx]['data']['path'])
                        logger.info(f"上传成功。")
                        ret[idx]['data']['file'] = image_url
                        ret[idx]['data']['path'] = image_url
                await self._reply_wrapper(message, ret)
            else:
                logger.error(traceback.format_exc())
                logger.error(f"回复消息失败: {e}")
                raise e
                    
    async def _reply_wrapper(self, message: Union[AstrBotMessage, Dict], ret: List):
        if isinstance(message, AstrBotMessage):
            await self.bot.send(message.raw_message, ret)
        if isinstance(message, dict):
            if 'group_id' in message:
                await self.bot.send_group_msg(group_id=message['group_id'], message=ret)
            elif 'user_id' in message:
                await self.bot.send_private_msg(user_id=message['user_id'], message=ret)
            else:
                raise Exception("aiocqhttp: 无法识别的消息来源。仅支持 group_id 和 user_id。")

    async def send_msg(self, target: Dict[str, int], result_message: CommandResult):
        '''
        以主动的方式给QQ用户、QQ群发送一条消息。
        
        `target` 接收一个 dict 类型的值引用。
        
        - 要发给 QQ 下的某个用户，请添加 key `user_id`，值为 int 类型的 qq 号；
        - 要发给某个群聊，请添加 key `group_id`，值为 int 类型的 qq 群号；
        
        '''
        
        await self._reply(target, result_message.message_chain)
        
    async def send_msg_new(self, message_type: MessageType, target: str, result_message: CommandResult):
        if message_type == MessageType.GROUP_MESSAGE:
            await self.send_msg({'group_id': int(target)}, result_message)
        elif message_type == MessageType.FRIEND_MESSAGE:
            await self.send_msg({'user_id': int(target)}, result_message)
        else:
            raise Exception("aiocqhttp: 无法识别的消息类型。")