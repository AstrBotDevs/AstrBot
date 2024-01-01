from nakuru.entities.components import Plain, At, Image, Node
from util import general_utils as gu
from util.cmd_config import CmdConfig
import asyncio
from nakuru import (
    CQHTTP,
    GuildMessage,
    GroupMessage,
    FriendMessage,
    GroupMemberIncrease,
    Notify
)
from typing import Union
import time

from ._platfrom import Platform


class FakeSource:
    def __init__(self, type, group_id):
        self.type = type
        self.group_id = group_id

    
class QQGOCQ(Platform):
    def __init__(self, cfg: dict, message_handler: callable) -> None:
        super().__init__(message_handler)

        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        self.waiting = {}
        self.gocq_cnt = 0
        self.cc = CmdConfig()
        self.cfg = cfg

        self.nick_qq = cfg['nick_qq']
        nick_qq = self.nick_qq
        if nick_qq == None:
            nick_qq = ("ai","!","！")
        if isinstance(nick_qq, str):
            nick_qq = (nick_qq,)
        if isinstance(nick_qq, list):
            nick_qq = tuple(nick_qq)
        
        self.unique_session = cfg['uniqueSessionMode']
        self.pic_mode = cfg['qq_pic_mode']

        self.client = CQHTTP(
            host=self.cc.get("gocq_host", "127.0.0.1"),
            port=self.cc.get("gocq_websocket_port", 6700),
            http_port=self.cc.get("gocq_http_port", 5700),
        )
        gocq_app = self.client

        self.announcement = self.cc.get("announcement", "欢迎新人！")

        @gocq_app.receiver("GroupMessage")
        async def _(app: CQHTTP, source: GroupMessage):
            if self.cc.get("gocq_react_group", True):
                if isinstance(source.message[0], Plain):
                    # await self.handle_msg(source, True)
                    self.new_sub_thread(self.handle_msg, (source, True))
                elif isinstance(source.message[0], At):
                    if source.message[0].qq == source.self_id:
                        # await self.handle_msg(source, True)
                        self.new_sub_thread(self.handle_msg, (source, True))
                else:
                    return
            
        @gocq_app.receiver("FriendMessage")
        async def _(app: CQHTTP, source: FriendMessage):
            if self.cc.get("gocq_react_friend", True):
                if isinstance(source.message[0], Plain):
                    # await self.handle_msg(source, False)
                    self.new_sub_thread(self.handle_msg, (source, False))
                else:
                    return
            
        @gocq_app.receiver("GroupMemberIncrease")
        async def _(app: CQHTTP, source: GroupMemberIncrease):
            if self.cc.get("gocq_react_group_increase", True):

                await app.sendGroupMessage(source.group_id, [
                    Plain(text = self.announcement)
                ])

        @gocq_app.receiver("Notify")
        async def _(app: CQHTTP, source: Notify):
            print(source)
            if source.sub_type == "poke" and source.target_id == source.self_id:
                # await self.handle_msg(source, False)
                self.new_sub_thread(self.handle_msg, (source, False))

        @gocq_app.receiver("GuildMessage")
        async def _(app: CQHTTP, source: GuildMessage):
            if self.cc.get("gocq_react_guild", True):
                if isinstance(source.message[0], Plain):
                    # await self.handle_msg(source, True)
                    self.new_sub_thread(self.handle_msg, (source, True))
                elif isinstance(source.message[0], At):
                    if source.message[0].qq == source.self_tiny_id:
                        # await self.handle_msg(source, True)
                        self.new_sub_thread(self.handle_msg, (source, True))
                else:
                    return
        
    def run(self):
        self.client.run()
                
    async def handle_msg(self, message: Union[GroupMessage, FriendMessage, GuildMessage, Notify], is_group: bool):
        # 判断是否响应消息
        resp = False
        for i in message.message:
            if isinstance(i, At):
                if message.type == "GuildMessage":
                    if i.qq == message.user_id or i.qq == message.self_tiny_id:
                        resp = True
                if message.type == "FriendMessage":
                    if i.qq == message.self_id:
                        resp = True
                if message.type == "GroupMessage":
                    if i.qq == message.self_id:
                        resp = True
        for i in self.nick_qq:
            if i != '' and i in message.message[0].text:
                resp = True
                break
                
        if not resp: return
        
        # 解析 session_id
        if self.unique_session or not is_group:
            session_id = message.user_id
        elif message.type == "GroupMessage":
            session_id = message.group_id
        elif message.type == "GuildMessage":
            session_id = message.channel_id
        else:
            session_id = message.user_id

        # 解析 role
        sender_id = str(message.user_id)
        if sender_id == self.cc.get('admin_qq', '') or \
        sender_id == self.cc.get('gocq_qqchan_admin', '') or \
        sender_id in self.cc.get('other_admins', []):
            role = 'admin'
        else:
            role = 'member'

        message_result = await self.message_handler(
            message=message,
            session_id=session_id,
            role=role,
            platform='gocq'
        )

        if message_result is None:
            return
        self.reply_msg(message, message_result.result_message)
        if message_result.callback is not None:
            message_result.callback()
        
        # 如果是等待回复的消息
        if session_id in self.waiting and self.waiting[session_id] == '':
            self.waiting[session_id] = message

    def reply_msg(self,
                        message: Union[GroupMessage, FriendMessage, GuildMessage, Notify],
                        result_message: list):
        """
         插件开发者请使用send方法, 可以不用直接调用这个方法。
        """
        source = message
        res = result_message

        self.gocq_cnt += 1

        gu.log("回复GOCQ消息: "+str(res), level=gu.LEVEL_INFO, tag="GOCQ", max_len=300)

        if isinstance(source, int):
            source = FakeSource("GroupMessage", source)
        
        # str convert to CQ Message Chain
        if isinstance(res, str):
            res_str = res
            res = []
            if source.type == "GroupMessage" and not isinstance(source, FakeSource):
                res.append(At(qq=source.user_id))
            res.append(Plain(text=res_str))

        # if image mode, put all Plain texts into a new picture.
        if self.pic_mode and isinstance(res, list):
            plains = []
            news = []
            for i in res:
                if isinstance(i, Plain):
                    plains.append(i.text)
                else:
                    news.append(i)
            plains_str = "".join(plains).strip()
            if plains_str != "" and len(plains_str) > 50:
                p = gu.create_markdown_image("".join(plains))
                news.append(Image.fromFileSystem(p))
                res = news

        # 回复消息链
        if isinstance(res, list) and len(res) > 0:
            if source.type == "GuildMessage":
                # await self.client.sendGuildChannelMessage(source.guild_id, source.channel_id, res)
                asyncio.run_coroutine_threadsafe(self.client.sendGuildChannelMessage(source.guild_id, source.channel_id, res), self.loop).result()
                return
            elif source.type == "FriendMessage":
                # await self.client.sendFriendMessage(source.user_id, res)
                asyncio.run_coroutine_threadsafe(self.client.sendFriendMessage(source.user_id, res), self.loop).result()
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
                if plain_text_len > self.cc.get('qq_forward_threshold', 200):
                    # 删除At
                    for i in res:
                        if isinstance(i, At):
                            res.remove(i)
                    node = Node(res)
                    # node.content = res
                    node.uin = 123456
                    node.name = f"bot"
                    node.time = int(time.time())
                    # print(node)
                    nodes=[node]
                    # await self.client.sendGroupForwardMessage(source.group_id, nodes)
                    asyncio.run_coroutine_threadsafe(self.client.sendGroupForwardMessage(source.group_id, nodes), self.loop).result()
                    return
                # await self.client.sendGroupMessage(source.group_id, res)
                asyncio.run_coroutine_threadsafe(self.client.sendGroupMessage(source.group_id, res), self.loop).result()
                return

    def send_msg(self, message: Union[GroupMessage, FriendMessage, GuildMessage, Notify], result_message: list):
        '''
        提供给插件的发送QQ消息接口。
        参数说明：第一个参数可以是消息对象，也可以是QQ群号。第二个参数是消息内容（消息内容可以是消息链列表，也可以是纯文字信息）。
        非异步
        '''
        try:
            # await self.reply_msg(message, result_message)
            self.reply_msg(message, result_message)
        except BaseException as e:
            raise e
    
    def send(self, 
            to,
            res):
        '''
        同 send_msg()
        非异步
        '''
        try:
            # await self.send_msg(to, res)
            self.reply_msg(to, res)
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

    def wait_for_message(self, group_id) -> Union[GroupMessage, FriendMessage, GuildMessage]:
        '''
        等待下一条消息，超时 300s 后抛出异常
        '''
        self.waiting[group_id] = ''
        cnt = 0
        while True:
            if group_id in self.waiting and self.waiting[group_id] != '':
                # 去掉
                ret = self.waiting[group_id]
                del self.waiting[group_id]
                return ret
            cnt += 1
            if cnt > 300:
                raise Exception("等待消息超时。")
            time.sleep(1)

    def get_client(self):
        return self.client

    def nakuru_method_invoker(self, func, *args, **kwargs):
        """
        返回一个方法调用器，可以用来立即调用nakuru的方法。
        """
        try:
            ret = asyncio.run_coroutine_threadsafe(func(*args, **kwargs), self.loop).result()
            return ret
        except BaseException as e:
            raise e
    
    def get_cnt(self):
        return self.gocq_cnt
    
    def set_cnt(self, cnt):
        self.gocq_cnt = cnt