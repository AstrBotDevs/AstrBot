import io
import botpy
from PIL import Image as PILImage
from botpy.message import Message, DirectMessage
import re
import asyncio
import requests
from util import general_utils as gu

from botpy.types.message import Reference
from botpy import Client
import time
from ._platfrom import Platform
from ._nakuru_translation_layer import(
    NakuruGuildMessage, 
    gocq_compatible_receive, 
    gocq_compatible_send
) 
from typing import Union

# QQ 机器人官方框架
class botClient(Client):
    def set_platform(self, platform: 'QQOfficial'):
        self.platform = platform

    # 收到频道消息
    async def on_at_message_create(self, message: Message):
        # 转换层
        nakuru_guild_message = gocq_compatible_receive(message)
        self.platform.new_sub_thread(self.platform.handle_msg, (nakuru_guild_message, True))

    # 收到私聊消息
    async def on_direct_message_create(self, message: DirectMessage):
        # 转换层
        nakuru_guild_message = gocq_compatible_receive(message)
        self.platform.new_sub_thread(self.platform.handle_msg, (nakuru_guild_message, False))

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

    async def handle_msg(self, message: NakuruGuildMessage, is_group: bool):
        _t = "/私聊" if not is_group else ""
        self.logger.log(f"{message.sender.nickname}({message.sender.tiny_id}{_t}) -> {self.parse_message_outline(message)}", tag="QQ_OFFICIAL")
        # 解析出 session_id
        if self.unique_session or not is_group:
            session_id = message.sender.user_id
        else:
            session_id = message.channel_id

        # 解析出 role
        sender_id = str(message.sender.tiny_id)
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

        self.reply_msg(is_group, message, message_result.result_message)
        if message_result.callback is not None:
            message_result.callback()

        # 如果是等待回复的消息
        if session_id in self.waiting and self.waiting[session_id] == '':
            self.waiting[session_id] = message

    def reply_msg(self, 
                is_group: bool,
                message: NakuruGuildMessage, 
                res: Union[str, list]):
        '''
        回复频道消息
        '''
        self.logger.log(f"{message.sender.nickname}({message.sender.tiny_id}) <- {self.parse_message_outline(res)}", tag="QQ_OFFICIAL")

        plain_text = ''
        image_path = ''
        msg_ref = None

        if isinstance(res, list):
            plain_text, image_path = gocq_compatible_send(res)
        elif isinstance(res, str):
            plain_text = res
            
        if self.cfg['qq_pic_mode']:
            # 文本转图片，并且加上原来的图片
            if plain_text != '' or image_path != '':
                if image_path is not None and image_path != '':
                    if image_path.startswith("http"):
                        plain_text += "\n\n" + "![](" + image_path + ")"
                    else:
                        plain_text += "\n\n" + "![](file:///" + image_path + ")"
                image_path = gu.create_markdown_image("".join(plain_text))
                plain_text = ""

        else:
            if image_path is not None and image_path != '':
                msg_ref = None
                if image_path.startswith("http"):
                    pic_res = requests.get(image_path, stream = True)
                    if pic_res.status_code == 200:
                        image = PILImage.open(io.BytesIO(pic_res.content))
                        image_path = gu.save_temp_img(image)

        if message.raw_message is not None and image_path == '': # file_image与message_reference不能同时传入
            msg_ref = Reference(message_id=message.raw_message.id, ignore_get_message_error=False)
        
        # 到这里，我们得到了 plain_text，image_path，msg_ref
        data = {
            'content': plain_text,
            'msg_id': message.message_id,
            'message_reference': msg_ref
        }
        if is_group:
            data['channel_id'] = str(message.channel_id)
        else:
            data['guild_id'] = str(message.guild_id)
        if image_path != '':
            data['file_image'] = image_path

        try:
            # await self._send_wrapper(**data)
            self._send_wrapper(**data)
        except BaseException as e:
            print(e)
            # 分割过长的消息
            if "msg over length" in str(e):
                split_res = []
                split_res.append(plain_text[:len(plain_text)//2])      
                split_res.append(plain_text[len(plain_text)//2:])
                for i in split_res:
                    data['content'] = i
                    # await self._send_wrapper(**data)
                    self._send_wrapper(**data)
            else:
                # 发送qq信息
                try:
                    # 防止被qq频道过滤消息
                    plain_text = plain_text.replace(".", " . ")
                    # await self._send_wrapper(**data)
                    self._send_wrapper(**data)

                except BaseException as e:
                    try:
                        data['content'] = str.join(" ", plain_text)
                        # await self._send_wrapper(**data)
                        self._send_wrapper(**data)
                    except BaseException as e:
                        plain_text = re.sub(r'(https|http)?:\/\/(\w|\.|\/|\?|\=|\&|\%)*\b', '[被隐藏的链接]', str(e), flags=re.MULTILINE)
                        plain_text = plain_text.replace(".", "·")
                        data['content'] = plain_text
                        # await self._send_wrapper(**data)
                        self._send_wrapper(**data)
 
    def _send_wrapper(self, **kwargs):
        if 'channel_id' in kwargs:
            asyncio.run_coroutine_threadsafe(self.client.api.post_message(**kwargs), self.loop).result()
        else:
            asyncio.run_coroutine_threadsafe(self.client.api.post_dms(**kwargs), self.loop).result()


    def send_msg(self, channel_id: int, message_chain: list, message_id: int = None):
        '''
        推送消息, 如果有 message_id，那么就是回复消息。非异步。
        '''
        _n = NakuruGuildMessage()
        _n.channel_id = channel_id
        _n.message_id = message_id
        # await self.reply_msg(_n, message_chain)
        self.reply_msg(_n, message_chain)

    def send(self, message_obj, message_chain: list):
        '''
        发送信息。内容同 reply_msg。非异步。
        '''
        # await self.reply_msg(message_obj, message_chain)
        self.reply_msg(message_obj, message_chain)

    def wait_for_message(self, channel_id: int) -> NakuruGuildMessage:
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
            time.sleep(1)
