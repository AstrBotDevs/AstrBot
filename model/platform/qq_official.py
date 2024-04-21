import io
import botpy
from PIL import Image as PILImage
import botpy.message
import re
import asyncio
import aiohttp
from util import general_utils as gu

from botpy.types.message import Reference
from botpy import Client
import time
from ._platfrom import Platform
from ._message_parse import (
    qq_official_message_parse_rev,
    qq_official_message_parse
)
from cores.astrbot.types import MessageType, AstrBotMessage, MessageMember
from typing import Union, List
from nakuru.entities.components import BaseMessageComponent

# QQ 机器人官方框架


class botClient(Client):
    def set_platform(self, platform: 'QQOfficial'):
        self.platform = platform

    async def on_group_at_message_create(self, message: botpy.message.GroupMessage):
        abm = qq_official_message_parse_rev(message, MessageType.GROUP_MESSAGE)
        await self.platform.handle_msg(abm)

    # 收到频道消息
    async def on_at_message_create(self, message: botpy.message.Message):
        # 转换层
        abm = qq_official_message_parse_rev(message, MessageType.GUILD_MESSAGE)
        await self.platform.handle_msg(abm)

    # 收到私聊消息
    async def on_direct_message_create(self, message: botpy.message.DirectMessage):
        # 转换层
        abm = qq_official_message_parse_rev(
            message, MessageType.FRIEND_MESSAGE)
        await self.platform.handle_msg(abm)


class QQOfficial(Platform):

    def __init__(self, cfg: dict, message_handler: callable, global_object) -> None:
        super().__init__(message_handler)

        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        self.waiting: dict = {}

        self.cfg = cfg
        self.appid = cfg['qqbot']['appid']
        self.token = cfg['qqbot']['token']
        self.secret = cfg['qqbot_secret']
        self.unique_session = cfg['uniqueSessionMode']
        self.logger: gu.Logger = global_object.logger
        qq_group = cfg['qqofficial_enable_group_message']

        if qq_group:
            self.intents = botpy.Intents(
                public_messages=True,
                public_guild_messages=True,
                direct_message=cfg['direct_message_mode']
            )
        else:
            self.intents = botpy.Intents(
                public_guild_messages=True,
                direct_message=cfg['direct_message_mode']
            )
        self.client = botClient(
            intents=self.intents,
            bot_log=False
        )

        self.client.set_platform(self)

    def run(self):
        try:
            self.loop.run_until_complete(self.client.run(
                appid=self.appid,
                secret=self.secret
            ))
        except BaseException as e:
            print(e)
            self.client = botClient(
                intents=self.intents,
                bot_log=False
            )
            self.client.set_platform(self)
            self.client.run(
                appid=self.appid,
                token=self.token
            )

    async def handle_msg(self, message: AstrBotMessage):
        assert isinstance(message.raw_message, (botpy.message.Message,
                          botpy.message.GroupMessage, botpy.message.DirectMessage))
        is_group = message.type != MessageType.FRIEND_MESSAGE

        _t = "/私聊" if not is_group else ""
        self.logger.log(
            f"{message.sender.nickname}({message.sender.user_id}{_t}) -> {self.parse_message_outline(message)}", tag="QQ_OFFICIAL")

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
        if sender_id == self.cfg['admin_qqchan'] or \
                sender_id in self.cfg['other_admins']:
            role = 'admin'
        else:
            role = 'member'

        message_result = await self.message_handler(
            message=message,
            session_id=session_id,
            role=role,
            platform='qqchan'
        )

        if message_result is None:
            return

        await self.reply_msg(message, message_result.result_message)
        if message_result.callback is not None:
            message_result.callback()

        # 如果是等待回复的消息
        if session_id in self.waiting and self.waiting[session_id] == '':
            self.waiting[session_id] = message

    async def reply_msg(self,
                        message: Union[botpy.message.Message, botpy.message.GroupMessage, botpy.message.DirectMessage, AstrBotMessage],
                        res: Union[str, list]):
        '''
        回复频道消息
        '''
        if isinstance(message, AstrBotMessage):
            source = message.raw_message
        else:
            source = message
        assert isinstance(source, (botpy.message.Message,
                          botpy.message.GroupMessage, botpy.message.DirectMessage))
        self.logger.log(
            f"{message.sender.nickname}({message.sender.user_id}) <- {self.parse_message_outline(res)}", tag="QQ_OFFICIAL")

        plain_text = ''
        image_path = ''
        msg_ref = None

        if isinstance(res, list):
            plain_text, image_path = qq_official_message_parse(res)
        elif isinstance(res, str):
            plain_text = res

        if self.cfg['qq_pic_mode']:
            # 文本转图片，并且加上原来的图片
            if plain_text != '' or image_path != '':
                if image_path is not None and image_path != '':
                    if image_path.startswith("http"):
                        plain_text += "\n\n" + "![](" + image_path + ")"
                    else:
                        plain_text += "\n\n" + \
                            "![](file:///" + image_path + ")"
                image_path = gu.create_markdown_image("".join(plain_text))
                plain_text = ""

        else:
            if image_path is not None and image_path != '':
                msg_ref = None
                if image_path.startswith("http"):
                    async with aiohttp.ClientSession() as session:
                        async with session.get(image_path) as response:
                            if response.status == 200:
                                image = PILImage.open(io.BytesIO(await response.read()))
                                image_path = gu.save_temp_img(image)

        if source is not None and image_path == '':  # file_image与message_reference不能同时传入
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
            # 目前只处理频道私聊
            data['guild_id'] = source.guild_id
        else:
            raise ValueError(f"未知的消息类型: {message.type}")
        if image_path != '':
            data['file_image'] = image_path

        try:
            await self._send_wrapper(**data)
        except BaseException as e:
            print(e)
            # 分割过长的消息
            if "msg over length" in str(e):
                split_res = []
                split_res.append(plain_text[:len(plain_text)//2])
                split_res.append(plain_text[len(plain_text)//2:])
                for i in split_res:
                    data['content'] = i
                    await self._send_wrapper(**data)
            else:
                # 发送qq信息
                try:
                    # 防止被qq频道过滤消息
                    plain_text = plain_text.replace(".", " . ")
                    await self._send_wrapper(**data)

                except BaseException as e:
                    try:
                        data['content'] = str.join(" ", plain_text)
                        await self._send_wrapper(**data)
                    except BaseException as e:
                        plain_text = re.sub(
                            r'(https|http)?:\/\/(\w|\.|\/|\?|\=|\&|\%)*\b', '[被隐藏的链接]', str(e), flags=re.MULTILINE)
                        plain_text = plain_text.replace(".", "·")
                        data['content'] = plain_text
                        await self._send_wrapper(**data)

    async def _send_wrapper(self, **kwargs):
        if 'group_openid' in kwargs:
            # QQ群组消息
            media = None
            # qq群组消息需要自行上传，暂时不处理
            # if 'file_image' in kwargs:
            #     file_image_path = kwargs['file_image']
            #     if file_image_path != "":
            #         media = await self.upload_img(file_image_path, kwargs['group_openid'])
            #         del kwargs['file_image']
            #     if media is not None:
            #         kwargs['msg_type'] = 7 # 富媒体
            await self.client.api.post_group_message(media=media, **kwargs)
        elif 'channel_id' in kwargs:
            # 频道消息
            if 'file_image' in kwargs:
                kwargs['file_image'] = kwargs['file_image'].replace(
                    "file://", "")
            await self.client.api.post_message(**kwargs)
        else:
            # 频道私聊消息
            if 'file_image' in kwargs:
                kwargs['file_image'] = kwargs['file_image'].replace(
                    "file://", "")
            await self.client.api.post_dms(**kwargs)

    async def send_msg(self,
                       message_obj: Union[botpy.message.Message, botpy.message.GroupMessage, botpy.message.DirectMessage, AstrBotMessage],
                       message_chain: List[BaseMessageComponent],
                       ):
        '''
        发送消息。目前只支持被动回复消息（即拥有一个 botpy Message 类型的 message_obj 传入）
        '''
        await self.reply_msg(message_obj, message_chain)

    async def send(self,
                   message_obj: Union[botpy.message.Message, botpy.message.GroupMessage, botpy.message.DirectMessage, AstrBotMessage],
                   message_chain: List[BaseMessageComponent],
                   ):
        '''
        发送消息。目前只支持被动回复消息（即拥有一个 botpy Message 类型的 message_obj 传入）
        '''
        await self.reply_msg(message_obj, message_chain)

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
