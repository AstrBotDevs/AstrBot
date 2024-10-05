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
from . import Platform, T2IException
from type.astrbot_message import *
from type.message_event import *
from type.command import *
from util.log import LogManager
from logging import Logger
from astrbot.message.handler import MessageHandler
from util.cmd_config import PlatformConfig, NakuruPlatformConfig

logger: Logger = LogManager.GetLogger(log_name='astrbot')


class FakeSource:
    def __init__(self, type, group_id):
        self.type = type
        self.group_id = group_id


class QQNakuru(Platform):
    def __init__(self, context: Context, 
                 message_handler: MessageHandler,
                 platform_config: PlatformConfig) -> None:
        super().__init__("nakuru", context)
        assert isinstance(platform_config, NakuruPlatformConfig), "gocq: 无法识别的配置类型。"
        
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        self.message_handler = message_handler
        self.context = context
        self.unique_session = context.config_helper.platform_settings.unique_session
        self.config = platform_config
        
        self.client = CQHTTP(
            host=self.config.host,
            port=self.config.websocket_port,
            http_port=self.config.port
        )
        gocq_app = self.client

        @gocq_app.receiver("GroupMessage")
        async def _(app: CQHTTP, source: GroupMessage):
            if self.config.enable_group:
                abm = self.convert_message(source)
                await self.handle_msg(abm)

        @gocq_app.receiver("FriendMessage")
        async def _(app: CQHTTP, source: FriendMessage):
            if self.config.enable_direct_message:
                abm = self.convert_message(source)
                await self.handle_msg(abm)

        @gocq_app.receiver("GuildMessage")
        async def _(app: CQHTTP, source: GuildMessage):
            if self.config.enable_guild:
                abm = self.convert_message(source)
                await self.handle_msg(abm)
                        
    def pre_check(self, message: AstrBotMessage) -> bool:
        # if message chain contains Plain components or At components which points to self_id, return True
        if message.type == MessageType.FRIEND_MESSAGE:
            return True, "friend"
        for comp in message.message:
            if isinstance(comp, At) and str(comp.qq) == message.self_id:
                return True, "at"
        # check commands which ignore prefix
        if self.context.command_manager.check_command_ignore_prefix(message.message_str):
            return True, "command"
        # check nicks
        if self.check_nick(message.message_str):
            return True, "nick"
        return False, "none"

    def run(self):
        coro = self.client._run()
        return coro

    async def handle_msg(self, message: AstrBotMessage):
        logger.info(
            f"{message.sender.nickname}/{message.sender.user_id} -> {self.parse_message_outline(message)}")

        assert isinstance(message.raw_message,
                          (GroupMessage, FriendMessage, GuildMessage))

        # 判断是否响应消息
        ok, reason = self.pre_check(message)
        if not ok:
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
            
        # parse unified message origin
        unified_msg_origin = None
        if message.type == MessageType.GROUP_MESSAGE:
            assert isinstance(message.raw_message, GroupMessage)
            unified_msg_origin = f"nakuru:{message.type.value}:{message.raw_message.group_id}"
        elif message.type == MessageType.FRIEND_MESSAGE:
            assert isinstance(message.raw_message, FriendMessage)
            unified_msg_origin = f"nakuru:{message.type.value}:{message.sender.user_id}"
        elif message.type == MessageType.GUILD_MESSAGE:
            assert isinstance(message.raw_message, GuildMessage)
            unified_msg_origin = f"nakuru:{message.type.value}:{message.raw_message.channel_id}"
        
        logger.debug(f"unified_msg_origin: {unified_msg_origin}")

            
        # construct astrbot message event
        ame = AstrMessageEvent.from_astrbot_message(message, 
                                                    self.context, 
                                                    "nakuru", 
                                                    session_id, 
                                                    unified_msg_origin,
                                                    reason == 'command') # only_command
        
        # transfer control to message handler
        message_result = await self.message_handler.handle(ame)
        if not message_result: return
        
        await self.reply_msg(message, message_result.result_message, message_result.use_t2i)
        if message_result.callback:
            message_result.callback()

    async def reply_msg(self,
                        message: AstrBotMessage,
                        result_message: List[BaseMessageComponent],
                        use_t2i: bool = None):
        """
        回复用户唤醒机器人的消息。（被动回复）
        """        
        assert isinstance(message.raw_message, (GroupMessage, FriendMessage, GuildMessage))

        try:
            await self._reply(message, result_message, use_t2i)
        except T2IException as e:
            logger.error(traceback.format_exc())
            logger.warning(f"文本转图片时发生错误，将使用纯文本发送。")
            await self._reply(message, result_message, False)
        return result_message
        
    async def _reply(self, message: Union[AstrBotMessage, Dict], message_chain: List[BaseMessageComponent], use_t2i: bool = None):
        await self.record_metrics()
        if isinstance(message_chain, str): 
            message_chain = [Plain(text=message_chain), ]
            
        # 文转图处理
        if (use_t2i or (use_t2i == None and self.context.config_helper.t2i)) and isinstance(message_chain, list):
            try:
                message_chain = await self.convert_to_t2i_chain(message_chain)
                if not message_chain: raise T2IException()
            except BaseException as e:
                raise T2IException()
                
        # log
        if isinstance(message, AstrBotMessage):
            logger.info(
                f"{message.sender.nickname}/{message.sender.user_id} <- {self.parse_message_outline(message_chain)}")
        else:
            logger.info(f"回复消息: {message_chain}")
        
        source = message.raw_message
        is_dict = isinstance(source, dict)
        
        # 发消息
        typ = None
        if is_dict:
            if "group_id" in source:
                typ = "GroupMessage"
            elif "user_id" in source:
                typ = "FriendMessage"
            elif "guild_id" in source:
                typ = "GuildMessage"
        else:
            typ = source.type
        
        if typ == "GuildMessage":
            guild_id = source['guild_id'] if is_dict else source.guild_id
            chan_id = source['channel_id'] if is_dict else source.channel_id
            await self.client.sendGuildChannelMessage(guild_id, chan_id, message_chain)
        elif typ == "FriendMessage":
            user_id = source['user_id'] if is_dict else source.user_id
            await self.client.sendFriendMessage(user_id, message_chain)
        elif typ == "GroupMessage":
            group_id = source['group_id'] if is_dict else source.group_id
            # 过长时forward发送
            plain_text_len = 0
            image_num = 0
            for i in message_chain:
                if isinstance(i, Plain):
                    plain_text_len += len(i.text)
                elif isinstance(i, Image):
                    image_num += 1
            if plain_text_len > self.context.config_helper.platform_settings.forward_threshold or image_num > 1:
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
        try:
            await self._reply(target, result_message, result_message.is_use_t2i)
        except T2IException as e:
            logger.error(traceback.format_exc())
            logger.warning(f"文本转图片时发生错误，将使用纯文本发送。")
            await self._reply(target, result_message, False)
        return result_message
        
    async def send_msg_new(self, message_type: MessageType, target: str, result_message: CommandResult):
        '''
        以主动的方式给用户、群或者频道发送一条消息。
        
        `message_type` 为 MessageType 枚举类型。
        
        - 要发给 QQ 下的某个用户，请使用 MessageType.FRIEND_MESSAGE；
        - 要发给某个群聊，请使用 MessageType.GROUP_MESSAGE；
        - 要发给某个频道，请使用 MessageType.GUILD_MESSAGE。
        '''
        if message_type == MessageType.FRIEND_MESSAGE:
            await self.send_msg({"user_id": int(target)}, result_message)
        elif message_type == MessageType.GROUP_MESSAGE:
            await self.send_msg({"group_id": int(target)}, result_message)
        elif message_type == MessageType.GUILD_MESSAGE:
            await self.send_msg({"channel_id": int(target)}, result_message)

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
        abm.tag = "nakuru"
        abm.message = message.message
        return abm