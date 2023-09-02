import io
import botpy
from PIL import Image as PILImage
from botpy.message import Message, DirectMessage
import re
import asyncio
import requests
from cores.qqbot.personality import personalities
from util import general_utils as gu
from nakuru.entities.components import Plain, At, Image

class NakuruGuildMember():
    tiny_id: int
    user_id: int
    title: str
    nickname: str
    role: int
    icon_url: str

class NakuruGuildMessage():
    type: str = "GuildMessage"
    self_id: int
    self_tiny_id: int
    sub_type: str
    message_id: str
    guild_id: int
    channel_id: int
    user_id: int
    message: list
    sender: NakuruGuildMember
    raw_message: Message

    def __str__(self) -> str:
        return str(self.__dict__)

class QQChan():

    def run_bot(self, botclient, appid, token):
        intents = botpy.Intents(public_guild_messages=True, direct_message=True) 
        self.client = botclient
        self.client.run(appid=appid, token=token)

    # gocq-频道SDK兼容层（发）
    def gocq_compatible_send(self, gocq_message_chain: list):
        plain_text = ""
        image_path = None # only one img supported
        for i in gocq_message_chain:
            if isinstance(i, Plain):
                plain_text += i.text
            elif isinstance(i, Image) and image_path == None:
                image_path = i.file
        return plain_text, image_path
    
    # gocq-频道SDK兼容层（收）
    def gocq_compatible_receive(self, message: Message) -> NakuruGuildMessage:
        ngm = NakuruGuildMessage()
        ngm.self_id = message.mentions[0].id
        ngm.self_tiny_id = message.mentions[0].id
        ngm.sub_type = "normal"
        ngm.message_id = message.id
        ngm.guild_id = int(message.channel_id)
        ngm.channel_id = int(message.channel_id)
        ngm.user_id = int(message.author.id)
        msg = []
        plain_content = message.content.replace("<@!"+str(ngm.self_id)+">", "").strip()
        msg.append(Plain(plain_content))
        if message.attachments:
            for i in message.attachments:
                if i.content_type.startswith("image"):
                    url = i.url
                    if not url.startswith("http"):
                        url = "https://"+url
                    img = Image.fromURL(url)
                    msg.append(img)
        ngm.message = msg
        ngm.sender = NakuruGuildMember()
        ngm.sender.tiny_id = int(message.author.id)
        ngm.sender.user_id = int(message.author.id)
        ngm.sender.title = ""
        ngm.sender.nickname = message.author.username
        ngm.sender.role = 0
        ngm.sender.icon_url = message.author.avatar
        ngm.raw_message = message
        return ngm



    def send_qq_msg(self, message: NakuruGuildMessage, res, msg_ref = None):
        gu.log("回复QQ频道消息: "+str(res), level=gu.LEVEL_INFO, tag="QQ频道", max_len=500)

        plain_text = ""
        image_path = None
        if isinstance(res, list):
            # 兼容gocq
            plain_text, image_path = self.gocq_compatible_send(res)
        elif isinstance(res, str):
            plain_text = res

        print(plain_text, image_path)

        try:
            reply_res = asyncio.run_coroutine_threadsafe(message.raw_message.reply(content=str(plain_text), message_reference = msg_ref, file_image=image_path), self.client.loop)
            reply_res.result()
        except BaseException as e:
            # 分割过长的消息
            if "msg over length" in str(e):
                split_res = []
                split_res.append(plain_text[:len(plain_text)//2])      
                split_res.append(plain_text[len(plain_text)//2:])
                for i in split_res:
                    reply_res = asyncio.run_coroutine_threadsafe(message.raw_message.reply(content=str(i), message_reference = msg_ref, file_image=image_path), self.client.loop)
                    reply_res.result()
            else:
                # 发送qq信息
                try:
                    # 防止被qq频道过滤消息
                    plain_text = plain_text.replace(".", " . ")
                    reply_res = asyncio.run_coroutine_threadsafe(message.raw_message.reply(content=str(plain_text), message_reference = msg_ref, file_image=image_path), self.client.loop)
                    # 发送信息
                except BaseException as e:
                    print("QQ频道API错误: \n"+str(e))
                    try:
                        reply_res = asyncio.run_coroutine_threadsafe(message.raw_message.reply(content=str(str.join(" ", plain_text)), message_reference = msg_ref, file_image=image_path), self.client.loop)
                    except BaseException as e:
                        plain_text = re.sub(r'(https|http)?:\/\/(\w|\.|\/|\?|\=|\&|\%)*\b', '[被隐藏的链接]', str(e), flags=re.MULTILINE)
                        plain_text = plain_text.replace(".", "·")
                        asyncio.run_coroutine_threadsafe(message.raw_message.reply(content=plain_text), self.client.loop).result()
                        # send(message, f"QQ频道API错误：{str(e)}\n下面是格式化后的回答：\n{f_res}")