import sys, time, datetime, uuid
import asyncio

from astrbot.api import Platform
from astrbot.api import MessageChain, MessageEventResult, AstrBotMessage, MessageMember, MessageType, PlatformMetadata
from typing import Union, List, Dict
from nakuru.entities.components import *
from astrbot.api import logger
from astrbot.core.platform.astr_message_event import MessageSesion
from .wechat_message_event import WechatPlatformEvent
from astrbot.core.config.astrbot_config import PlatformConfig, WechatPlatformConfig, PlatformSettings
from astrbot.core.utils.io import save_temp_img, download_image_by_url

from vchat import Core
from vchat import model

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override
        
class WechatPlatformAdapter(Platform):

    def __init__(self, platform_config: WechatPlatformConfig, platform_settings: PlatformSettings, event_queue: asyncio.Queue) -> None:
        super().__init__(event_queue)
        self.config = platform_config
        self.test_mode = os.environ.get('TEST_MODE', 'off') == 'on'
        self.client_self_id = uuid.uuid4().hex[:8]
    
    @override
    async def send_by_session(self, session: MessageSesion, message_chain: MessageChain):
        from_username = session.session_id.split('$$')[0]
        await WechatPlatformEvent.send_with_client(self.client, message_chain, from_username)
        await super().send_by_session(session, message_chain)
    
    @override
    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            "wechat",
            "基于 VChat 的 Wechat 适配器",
        )

    @override
    def run(self):
        self.client = Core()
        @self.client.msg_register(msg_types=model.ContentTypes.TEXT, 
                                  contact_type=model.ContactTypes.CHATROOM | model.ContactTypes.USER)
        async def _(msg: model.Message):
            if isinstance(msg.content, model.UselessContent):
                return
            if msg.create_time < self.start_time:
                logger.debug(f"忽略旧消息: {msg}")
                return
            if self.config.wechat_id_whitelist and msg.from_.username not in self.config.wechat_id_whitelist:
                logger.debug(f"忽略不在白名单的微信消息。username: {msg.from_.username}")
                return
            logger.info(f"收到消息: {msg.todict()}")
            abmsg = self.convert_message(msg)
            # await self.handle_msg(abmsg) # 不能直接调用，否则会阻塞
            asyncio.create_task(self.handle_msg(abmsg))
        
        # TODO: 对齐微信服务器时间
        self.start_time = int(time.time())
        return self._run()
    
            
    async def _run(self):
        await self.client.init()
        await self.client.auto_login(hot_reload=True)
        await self.client.run()
    
    def convert_message(self, msg: model.Message) -> AstrBotMessage:
        # credits: https://github.com/z2z63/astrbot_plugin_vchat/blob/master/main.py#L49
        assert isinstance(msg.content, model.TextContent)
        amsg = AstrBotMessage()
        amsg.message = [Plain(msg.content.content)]
        amsg.self_id = self.client_self_id
        if msg.content.is_at_me:
            amsg.message.insert(0, At(qq=amsg.self_id))
        
        sender = msg.chatroom_sender or msg.from_
        amsg.sender = MessageMember(sender.username, sender.nickname)
        amsg.message_str = msg.content.content
        amsg.message_id = msg.message_id
        if isinstance(msg.from_, model.User):
            amsg.type = MessageType.FRIEND_MESSAGE
        elif isinstance(msg.from_, model.Chatroom):
            amsg.type = MessageType.GROUP_MESSAGE
        else:
            logger.error(f"不支持的 Wechat 消息类型: {msg.from_}")
            
        amsg.raw_message = msg
        
        session_id = msg.from_.username + "$$" + msg.to.username
        if msg.chatroom_sender is not None:
            session_id += '$$' + msg.chatroom_sender.username
            
        amsg.session_id = session_id
        return amsg
    
    async def handle_msg(self, message: AstrBotMessage):
        message_event = WechatPlatformEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            client=self.client
        )
        
        logger.info(f"处理消息: {message_event}")
        
        self.commit_event(message_event)