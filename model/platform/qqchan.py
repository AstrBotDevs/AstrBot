import io
import botpy
from PIL import Image
from botpy.message import Message, DirectMessage
import re
import asyncio
import requests
from cores.qqbot.personality import personalities
from util import general_utils as gu

class QQChan():

    def run_bot(self, botclient, appid, token):
        intents = botpy.Intents(public_guild_messages=True, direct_message=True) 
        self.client = botclient
        self.client.run(appid=appid, token=token)

    def send_qq_msg(self, message, res, image_mode=False, msg_ref = None):
        gu.log("回复QQ频道消息: "+str(res), level=gu.LEVEL_INFO, tag="QQ频道", max_len=30)

        if not image_mode:
            try:
                if msg_ref is not None:
                    reply_res = asyncio.run_coroutine_threadsafe(message.reply(content=str(res), message_reference = msg_ref), self.client.loop)
                else:
                    reply_res = asyncio.run_coroutine_threadsafe(message.reply(content=str(res)), self.client.loop)
                reply_res.result()
            except BaseException as e:
                # 分割过长的消息
                if "msg over length" in str(e):
                    split_res = []
                    split_res.append(res[:len(res)//2])      
                    split_res.append(res[len(res)//2:])
                    for i in split_res:
                        if msg_ref is not None:
                            reply_res = asyncio.run_coroutine_threadsafe(message.reply(content=i, message_reference = msg_ref), self.client.loop)
                        else:
                            reply_res = asyncio.run_coroutine_threadsafe(message.reply(content=i), self.client.loop)
                        reply_res.result()
                else:
                    # 发送qq信息
                    try:
                        # 防止被qq频道过滤消息
                        res = res.replace(".", " . ")
                        asyncio.run_coroutine_threadsafe(message.reply(content=res), self.client.loop).result()
                        # 发送信息
                    except BaseException as e:
                        print("QQ频道API错误: \n"+str(e))
                        res = str.join(" ", res)
                        try:
                            asyncio.run_coroutine_threadsafe(message.reply(content=res), self.client.loop).result()
                        except BaseException as e:
                            # 如果还是不行则报出错误
                            res = re.sub(r'(https|http)?:\/\/(\w|\.|\/|\?|\=|\&|\%)*\b', '[被隐藏的链接]', str(e), flags=re.MULTILINE)
                            res = res.replace(".", "·")
                            asyncio.run_coroutine_threadsafe(message.reply(content=res), self.client.loop).result()
                            # send(message, f"QQ频道API错误：{str(e)}\n下面是格式化后的回答：\n{f_res}")
        else:
            pic_res = requests.get(str(res), stream=True)
            if pic_res.status_code == 200:
                # 将二进制数据转换成图片对象
                image = Image.open(io.BytesIO(pic_res.content))
                # 保存图片到本地
                image.save('tmp_image.jpg')
            asyncio.run_coroutine_threadsafe(message.reply(file_image='tmp_image.jpg', content=""), self.client.loop)