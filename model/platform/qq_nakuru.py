import time, asyncio, traceback

from nakuru.entities.components import Plain, At, Image, Node, BaseMessageComponent
from nakuru import (
    CQHTTP,
    GuildMessage,
    GroupMessage,
    FriendMessage,
    GroupMemberIncrease,
    MessageItemType
)
from typing import Union, List, Dict
from type.types import Context
from . import Platform
from type.astrbot_message import *
from type.message_event import *
from type.command import *
from SparkleLogging.utils.core import LogManager
from logging import Logger
from astrbot.message.handler import MessageHandler

logger: Logger = LogManager.GetLogger(log_name='astrbot')


class FakeSource:
    def __init__(self, type, group_id):
        self.type = type
        self.group_id = group_id


class QQGOCQ(Platform):
    def __init__(self, context: Context, message_handler: MessageHandler) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        self.message_handler = message_handler
        self.waiting = {}
        self.context = context
        self.unique_session = self.context.unique_session
        self.announcement = self.context.base_config.get("announcement", "欢迎新人！")

        self.client = CQHTTP(
            host=self.context.base_config.get("gocq_host", "127.0.0.1"),
            port=self.context.base_config.get("gocq_websocket_port", 6700),
            http_port=self.context.base_config.get("gocq_http_port", 5700),
        )
        gocq_app = self.client

        @gocq_app.receiver("GroupMessage")
        async def _(app: CQHTTP, source: GroupMessage):
            if self.context.base_config.get("gocq_react_group", True):
                abm = self.convert_message(source)
                await self.handle_msg(abm)

        @gocq_app.receiver("FriendMessage")
        async def _(app: CQHTTP, source: FriendMessage):
            if self.context.base_config.get("gocq_react_friend", True):
                abm = self.convert_message(source)
                await self.handle_msg(abm)

        @gocq_app.receiver("GroupMemberIncrease")
        async def _(app: CQHTTP, source: GroupMemberIncrease):
            if self.context.base_config.get("gocq_react_group_increase", True):
                await app.sendGroupMessage(source.group_id, [
                    Plain(text=self.announcement)
                ])

        @gocq_app.receiver("GuildMessage")
        async def _(app: CQHTTP, source: GuildMessage):
            if self.cc.get("gocq_react_guild", True):
                abm = self.convert_message(source)
                await self.handle_msg(abm)
                        
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

    def run(self):
        coro = self.client._run()
        return coro

    async def handle_msg(self, message: AstrBotMessage):
        logger.info(
            f"{message.sender.nickname}/{message.sender.user_id} -> {self.parse_message_outline(message)}")

        assert isinstance(message.raw_message,
                          (GroupMessage, FriendMessage, GuildMessage))

        # 判断是否响应消息
        if not self.pre_check(message):
            return

        # 解析 session_id
        if self.unique_session or message.type == MessageType.FRIEND_MESSAGE:
            session_id = message.raw_message.user_id
        elif message.type == MessageType.GROUP_MESSAGE:
            session_id = message.raw_message.group_id
        elif message.type == MessageType.GUILD_MESSAGE:
            session_id = message.raw_message.channel_id
        else:
            session_id = message.raw_message.user_id

        message.session_id = session_id

        # 解析 role
        sender_id = str(message.raw_message.user_id)
        if sender_id == self.context.config_helper.get('admin_qq', '') or \
                sender_id in self.context.config_helper.get('other_admins', []):
            role = 'admin'
        else:
            role = 'member'
            
        # construct astrbot message event
        ame = AstrMessageEvent.from_astrbot_message(message, self.context, "gocq", session_id, role)
        
        # transfer control to message handler
        message_result = await self.message_handler.handle(ame)
        if not message_result: return
        
        await self.reply_msg(message, message_result.result_message)
        if message_result.callback:
            message_result.callback()

        # 如果是等待回复的消息
        if session_id in self.waiting and self.waiting[session_id] == '':
            self.waiting[session_id] = message

    async def reply_msg(self,
                        message: AstrBotMessage,
                        result_message: List[BaseMessageComponent]):
        """
        回复用户唤醒机器人的消息。（被动回复）
        """
        source = message.raw_message
        res = result_message
        
        assert isinstance(source,
                (GroupMessage, FriendMessage, GuildMessage))

        logger.info(
            f"{source.user_id} <- {self.parse_message_outline(res)}")

        if isinstance(res, str):
            res = [Plain(text=res), ]

        # if image mode, put all Plain texts into a new picture.
        if self.context.config_helper.get("qq_pic_mode", False) and isinstance(res, list):
            rendered_images = await self.convert_to_t2i_chain(res)
            if rendered_images:
                try:
                    await self._reply(source, rendered_images)
                    return
                except BaseException as e:
                    logger.warn(traceback.format_exc())
                    logger.warn(f"以文本转图片的形式回复消息时发生错误: {e}，将尝试默认方式。")
            
        await self._reply(source, res)
        
    async def _reply(self, source, message_chain: List[BaseMessageComponent]):
        if isinstance(message_chain, str): 
            message_chain = [Plain(text=message_chain), ]
        
        is_dict = isinstance(source, dict)
        if source.type == "GuildMessage":
            guild_id = source['guild_id'] if is_dict else source.guild_id
            chan_id = source['channel_id'] if is_dict else source.channel_id
            await self.client.sendGuildChannelMessage(guild_id, chan_id, message_chain)
        elif source.type == "FriendMessage":
            user_id = source['user_id'] if is_dict else source.user_id
            await self.client.sendFriendMessage(user_id, message_chain)
        elif source.type == "GroupMessage":
            group_id = source['group_id'] if is_dict else source.group_id
            # 过长时forward发送
            plain_text_len = 0
            image_num = 0
            for i in message_chain:
                if isinstance(i, Plain):
                    plain_text_len += len(i.text)
                elif isinstance(i, Image):
                    image_num += 1
            if plain_text_len > self.context.config_helper.get('qq_forward_threshold', 200):
                # 删除At
                for i in message_chain:
                    if isinstance(i, At):
                        message_chain.remove(i)
                node = Node(message_chain)
                node.uin = 123456
                node.name = f"bot"
                node.time = int(time.time())
                nodes = [node]
                await self.client.sendGroupForwardMessage(group_id, nodes)
                return
            await self.client.sendGroupMessage(group_id, message_chain)
        
    async def send_msg(self, target: Dict[str, int], result_message: CommandResult):
        '''
        以主动的方式给用户、群或者频道发送一条消息。
        
        `target` 接收一个 dict 类型的值引用。
        
        - 要发给 QQ 下的某个用户，请添加 key `user_id`，值为 int 类型的 qq 号；
        - 要发给某个群聊，请添加 key `group_id`，值为 int 类型的 qq 群号；
        - 要发给某个频道，请添加 key `guild_id`, `channel_id`。均为 int 类型。
        
        guild_id 不是频道号。
        '''
        await self._reply(target, result_message.message_chain)

    def convert_message(self, message: Union[GroupMessage, FriendMessage, GuildMessage]) -> AstrBotMessage:
        abm = AstrBotMessage()
        abm.type = MessageType(message.type)
        abm.raw_message = message
        abm.message_id = message.message_id

        plain_content = ""
        for i in message.message:
            if isinstance(i, Plain):
                plain_content += i.text
        abm.message_str = plain_content.strip()
        if message.type == MessageItemType.GuildMessage:
            abm.self_id = str(message.self_tiny_id)
        else:
            abm.self_id = str(message.self_id)
        abm.sender = MessageMember(
            str(message.sender.user_id),
            str(message.sender.nickname)
        )
        abm.tag = "gocq"
        abm.message = message.message
        return abm
    
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