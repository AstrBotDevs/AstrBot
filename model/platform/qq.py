from nakuru.entities.components import Plain, At, Image, Node
from util import general_utils as gu
from util.cmd_config import CmdConfig
import asyncio
from nakuru import (
    CQHTTP,
    GuildMessage
)
import time



class QQ:
    def __init__(self, is_start: bool, cc: CmdConfig = None, gocq_loop = None) -> None:
        self.is_start = is_start
        self.gocq_loop = gocq_loop
        self.cc = cc

    def run_bot(self, gocq):
        self.client: CQHTTP = gocq
        self.client.run()

    def get_msg_loop(self):
        return self.gocq_loop

    async def send_qq_msg(self, 
                          source, 
                          res, 
                          image_mode: bool = False):
        if not self.is_start:
            raise Exception("管理员未启动GOCQ平台")
        """
         res可以是一个数组, 也就是gocq的消息链。
         插件开发者请使用send方法, 可以不用直接调用这个方法。
        """
        gu.log("回复GOCQ消息: "+str(res), level=gu.LEVEL_INFO, tag="GOCQ", max_len=40)

        if isinstance(source, int):
            source = {
                "type": "GroupMessage",
                "group_id": source
            }
            
        if isinstance(res, str):
            res_str = res
            res = []
            if source.type == "GroupMessage":
                res.append(At(qq=source.user_id))
            if image_mode:
                res.append(Plain(text="好的，我根据你的需要为你生成了一张图片😊"))
                res.append(Image.fromURL(url=res))
            else:
                res.append(Plain(text=res_str))

        # 回复消息链
        if isinstance(res, list) and len(res) > 0:
            if source.type == "GuildMessage":
                await self.client.sendGuildChannelMessage(source.guild_id, source.channel_id, res)
                return
            elif source.type == "FriendMessage":
                await self.client.sendFriendMessage(source.user_id, res)
                return
            elif source.type == "GroupMessage":
                # 过长时forward发送
                plain_text_len = 0
                image_num = 0
                for i in res:
                    if isinstance(i, Plain):
                        plain_text_len += len(i.text)
                    elif isinstance(i, Image):
                        image_num += 1
                if plain_text_len > self.cc.get('qq_forward_threshold', 200) or image_num > 1:
                    # 删除At
                    _t = ""
                    for i in res:
                        if isinstance(i, Plain):
                            _t += i.text
                    node = Node(res)
                    node.content = _t
                    node.uin = source.self_id
                    print(source)
                    node.name = f"To {source.sender.nickname}:"
                    node.time = int(time.time())
                    # print(node)
                    nodes = [node]
                    await self.client.sendGroupForwardMessage(source.group_id, nodes)
                    return
                await self.client.sendGroupMessage(source.group_id, res)
                return

    def send(self, 
            to,
            res,
            ):
        '''
        提供给插件的发送QQ消息接口, 不用在外部await。
        参数说明：第一个参数可以是消息对象，也可以是QQ群号。第二个参数是消息内容（消息内容可以是消息链列表，也可以是纯文字信息）。
        '''
        try:
            asyncio.run_coroutine_threadsafe(self.send_qq_msg(to, res), self.gocq_loop).result()
        except BaseException as e:
            raise e
        
    def send_guild(self, 
            message_obj,
            res,
            ):
        '''
        提供给插件的发送GOCQ QQ频道消息接口, 不用在外部await。
        参数说明：第一个参数必须是消息对象, 第二个参数是消息内容（消息内容可以是消息链列表，也可以是纯文字信息）。
        '''
        try:
            asyncio.run_coroutine_threadsafe(self.send_qq_msg(message_obj, res), self.gocq_loop).result()
        except BaseException as e:
            raise e

    def create_text_image(title: str, text: str, max_width=30, font_size=20):
        '''
        文本转图片。
        title: 标题
        text: 文本内容
        max_width: 文本宽度最大值（默认30）
        font_size: 字体大小（默认20）

        返回：文件路径
        '''
        try:
            img = gu.word2img(title, text, max_width, font_size)
            p = gu.save_temp_img(img)
            return p
        except Exception as e:
            raise e
