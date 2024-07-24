import botpy
import re
import time
import traceback
import asyncio
import botpy.message
import botpy.types
import botpy.types.message

from botpy.types.message import Reference, Media
from botpy import Client
from util.io import save_temp_img
from . import Platform
from type.astrbot_message import *
from type.message_event import *
from typing import Union, List, Dict
from nakuru.entities.components import *
from SparkleLogging.utils.core import LogManager
from logging import Logger
from astrbot.message.handler import MessageHandler

logger: Logger = LogManager.GetLogger(log_name='astrbot')

# QQ 机器人官方框架
class botClient(Client):
    def set_platform(self, platform: 'QQOfficial'):
        self.platform = platform
        
    # 收到群消息
    async def on_group_at_message_create(self, message: botpy.message.GroupMessage):
        abm = self.platform._parse_from_qqofficial(message, MessageType.GROUP_MESSAGE)
        await self.platform.handle_msg(abm)

    # 收到频道消息
    async def on_at_message_create(self, message: botpy.message.Message):
        # 转换层
        abm = self.platform._parse_from_qqofficial(message, MessageType.GUILD_MESSAGE)
        await self.platform.handle_msg(abm)

    # 收到私聊消息
    async def on_direct_message_create(self, message: botpy.message.DirectMessage):
        # 转换层
        abm = self.platform._parse_from_qqofficial(message, MessageType.FRIEND_MESSAGE)
        await self.platform.handle_msg(abm)


class QQOfficial(Platform):

    def __init__(self, context: Context, message_handler: MessageHandler) -> None:
        super().__init__()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        self.message_handler = message_handler
        self.waiting: dict = {}
        self.context = context
        
        self.appid = context.base_config['qqbot']['appid']
        self.token = context.base_config['qqbot']['token']
        self.secret = context.base_config['qqbot_secret']
        self.unique_session = context.unique_session
        qq_group = context.base_config['qqofficial_enable_group_message']
        

        if qq_group:
            self.intents = botpy.Intents(
                public_messages=True,
                public_guild_messages=True,
                direct_message=context.base_config['direct_message_mode']
            )
        else:
            self.intents = botpy.Intents(
                public_guild_messages=True,
                direct_message=context.base_config['direct_message_mode']
            )
        self.client = botClient(
            intents=self.intents,
            bot_log=False
        )

        self.client.set_platform(self)
        
    def _parse_to_qqofficial(self, message: List[BaseMessageComponent]):
        plain_text = ""
        image_path = None  # only one img supported
        for i in message:
            if isinstance(i, Plain):
                plain_text += i.text
            elif isinstance(i, Image) and not image_path:
                if i.path:
                    image_path = i.path
                elif i.file and i.file.startswith("base64://"):
                    img_data = base64.b64decode(i.file[9:])
                    image_path = save_temp_img(img_data)
                else:
                    image_path = save_temp_img(i.file)
        return plain_text, image_path

    def _parse_from_qqofficial(self, message: Union[botpy.message.Message, botpy.message.GroupMessage],
                                  message_type: MessageType):
        abm = AstrBotMessage()
        abm.type = message_type
        abm.timestamp = int(time.time())
        abm.raw_message = message
        abm.message_id = message.id
        abm.tag = "qqchan"
        msg: List[BaseMessageComponent] = []

        if message_type == MessageType.GROUP_MESSAGE:
            abm.sender = MessageMember(
                message.author.member_openid,
                ""
            )
            abm.message_str = message.content.strip()
            abm.self_id = "unknown_selfid"

            msg.append(Plain(abm.message_str))
            if message.attachments:
                for i in message.attachments:
                    if i.content_type.startswith("image"):
                        url = i.url
                        if not url.startswith("http"):
                            url = "https://"+url
                        img = Image.fromURL(url)
                        msg.append(img)
            abm.message = msg

        elif message_type == MessageType.GUILD_MESSAGE or message_type == MessageType.FRIEND_MESSAGE:
            # 目前对于 FRIEND_MESSAGE 只处理频道私聊
            try:
                abm.self_id = str(message.mentions[0].id)
            except:
                abm.self_id = ""

            plain_content = message.content.replace(
                "<@!"+str(abm.self_id)+">", "").strip()
            msg.append(Plain(plain_content))
            if message.attachments:
                for i in message.attachments:
                    if i.content_type.startswith("image"):
                        url = i.url
                        if not url.startswith("http"):
                            url = "https://"+url
                        img = Image.fromURL(url)
                        msg.append(img)
            abm.message = msg
            abm.message_str = plain_content
            abm.sender = MessageMember(
                str(message.author.id),
                str(message.author.username)
            )
        else:
            raise ValueError(f"Unknown message type: {message_type}")
        return abm

    def run(self):
        try:
            return self.client.start(
                appid=self.appid,
                secret=self.secret
            )
        except BaseException as e:
            # 早期的 qq-botpy 版本使用 token 登录。
            logger.error(traceback.format_exc())
            self.client = botClient(
                intents=self.intents,
                bot_log=False
            )
            self.client.set_platform(self)
            return self.client.start(
                appid=self.appid,
                token=self.token
            )

    async def handle_msg(self, message: AstrBotMessage):
        assert isinstance(message.raw_message, (botpy.message.Message,
                          botpy.message.GroupMessage, botpy.message.DirectMessage))
        is_group = message.type != MessageType.FRIEND_MESSAGE

        _t = "/私聊" if not is_group else ""
        logger.info(
            f"{message.sender.nickname}({message.sender.user_id}{_t}) -> {self.parse_message_outline(message)}")

        # 解析出 session_id
        if self.unique_session or not is_group:
            session_id = message.sender.user_id
        else:
            if message.type == MessageType.GUILD_MESSAGE:
                session_id = message.raw_message.channel_id
            elif message.type == MessageType.GROUP_MESSAGE:
                session_id = str(message.raw_message.group_openid)
            else:
                session_id = str(message.raw_message.author.id)
        message.session_id = session_id

        # 解析出 role
        sender_id = message.sender.user_id
        if sender_id == self.context.config_helper.get('admin_qqchan', None) or \
                sender_id in self.context.config_helper.get('other_admins', None):
            role = 'admin'
        else:
            role = 'member'
            
        # construct astrbot message event
        ame = AstrMessageEvent.from_astrbot_message(message, self.context, "qqchan", session_id, role)
        
        message_result = await self.message_handler.handle(ame)
        if not message_result:
            return

        await self.reply_msg(message, message_result.result_message)
        if message_result.callback:
            message_result.callback()

        # 如果是等待回复的消息
        if session_id in self.waiting and self.waiting[session_id] == '':
            self.waiting[session_id] = message

    async def reply_msg(self,
                        message: AstrBotMessage,
                        result_message: List[BaseMessageComponent]):
        '''
        回复频道消息
        '''
        source = message.raw_message
        assert isinstance(source, (botpy.message.Message,
                          botpy.message.GroupMessage, botpy.message.DirectMessage))
        logger.info(
            f"{message.sender.nickname}({message.sender.user_id}) <- {self.parse_message_outline(result_message)}")

        plain_text = ''
        image_path = ''
        msg_ref = None
        rendered_images = []
        
        if self.context.config_helper.get("qq_pic_mode", False) and isinstance(result_message, list):
            rendered_images = await self.convert_to_t2i_chain(result_message)
        
        if isinstance(result_message, list):
            plain_text, image_path = self._parse_to_qqofficial(result_message)
        else:
            plain_text = result_message

        if source and not image_path:  # file_image与message_reference不能同时传入
            msg_ref = Reference(message_id=source.id,
                                ignore_get_message_error=False)

        # 到这里，我们得到了 plain_text，image_path，msg_ref
        data = {
            'content': plain_text,
            'msg_id': message.message_id,
            'message_reference': msg_ref
        }
        
        if message.type == MessageType.GROUP_MESSAGE:
            data['group_openid'] = str(source.group_openid)
        elif message.type == MessageType.GUILD_MESSAGE:
            data['channel_id'] = source.channel_id
        elif message.type == MessageType.FRIEND_MESSAGE:
            data['guild_id'] = source.guild_id
        if image_path:
            data['file_image'] = image_path
        if rendered_images:
            # 文转图
            _data = data.copy()
            _data['content'] = ''
            _data['file_image'] = rendered_images[0].file
            _data['message_reference'] = None
            
            try:
                await self._reply(**_data)
                return
            except BaseException as e:
                logger.warn(traceback.format_exc())
                logger.warn(f"以文本转图片的形式回复消息时发生错误: {e}，将尝试默认方式。")

        try:
            await self._reply(**data)
        except BaseException as e:
            logger.error(traceback.format_exc())
            # 分割过长的消息
            if "msg over length" in str(e):
                split_res = []
                split_res.append(plain_text[:len(plain_text)//2])
                split_res.append(plain_text[len(plain_text)//2:])
                for i in split_res:
                    data['content'] = i
                    await self._reply(**data)
            else:
                try:
                    # 防止被qq频道过滤消息
                    plain_text = plain_text.replace(".", " . ")
                    await self._reply(**data)
                except BaseException as e:
                    try:
                        data['content'] = str.join(" ", plain_text)
                        await self._reply(**data)
                    except BaseException as e:
                        plain_text = re.sub(
                            r'(https|http)?:\/\/(\w|\.|\/|\?|\=|\&|\%)*\b', '[被隐藏的链接]', str(e), flags=re.MULTILINE)
                        plain_text = plain_text.replace(".", "·")
                        data['content'] = plain_text
                        await self._reply(**data)

    async def _reply(self, **kwargs):
        if 'group_openid' in kwargs:
            # QQ群组消息
            # qq群组消息需要自行上传，暂时不处理
            if 'file_image' in kwargs:
                file_image_path = kwargs['file_image'].replace("file:///", "")
                if file_image_path:
                    
                    if file_image_path.startswith("http"):
                        image_url = file_image_path
                    else:
                        logger.debug(f"上传图片: {file_image_path}")
                        image_url = await self.context.image_uploader.upload_image(file_image_path)
                        logger.debug(f"上传成功: {image_url}")
                    media = await self.client.api.post_group_file(kwargs['group_openid'], 1, image_url)
                    del kwargs['file_image']
                    kwargs['media'] = media
                    kwargs['msg_type'] = 7 # 富媒体
            await self.client.api.post_group_message(**kwargs)
        elif 'channel_id' in kwargs:
            # 频道消息
            if 'file_image' in kwargs:
                kwargs['file_image'] = kwargs['file_image'].replace("file:///", "")
            await self.client.api.post_message(**kwargs)
        else:
            # 频道私聊消息
            if 'file_image' in kwargs:
                kwargs['file_image'] = kwargs['file_image'].replace("file:///", "")
            await self.client.api.post_dms(**kwargs)

    async def send_msg(self, target: Dict[str, str], result_message: Union[List[BaseMessageComponent], str]):
        '''
        以主动的方式给用户、群或者频道发送一条消息。
        
        `target` 接收一个 dict 类型的值引用。
        
        - 如果目标是 QQ 群，请添加 key `group_openid`。
        - 如果目标是 频道消息，请添加 key `channel_id`。
        - 如果目标是 频道私聊，请添加 key `guild_id`。
        '''
        if isinstance(result_message, list):
            plain_text, image_path = self._parse_to_qqofficial(result_message)
        else:
            plain_text = result_message

        payload = {
            'content': plain_text,
            'file_image': image_path,
            **target
        }
        await self._reply(**payload)

    def wait_for_message(self, channel_id: int) -> AstrBotMessage:
        '''
        等待指定 channel_id 的下一条信息，超时 300s 后抛出异常
        '''
        self.waiting[channel_id] = ''
        cnt = 0
        while True:
            if channel_id in self.waiting and self.waiting[channel_id] != '':
                # 去掉
                ret = self.waiting[channel_id]
                del self.waiting[channel_id]
                return ret
            cnt += 1
            if cnt > 300:
                raise Exception("等待消息超时。")
            time.sleep(1)()
