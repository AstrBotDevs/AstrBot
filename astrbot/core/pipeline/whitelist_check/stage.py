from ..stage import Stage, register_stage
from ..context import PipelineContext
from typing import List, Dict, AsyncGenerator, Union
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.message_type import MessageType
from astrbot.core import logger

@register_stage
class WhitelistCheckStage(Stage):
    '''检查是否在群聊/私聊白名单
    '''
    async def initialize(self, ctx: PipelineContext) -> None:
        self.whitelist = ctx.astrbot_config['platform_settings']['id_whitelist']
    
    async def process(self, event: AstrMessageEvent) -> Union[None, AsyncGenerator[None, None]]:
        # 检查是否在白名单
        if event.role == 'admin' and event.get_message_type() == MessageType.FRIEND_MESSAGE:
            return
        if event.unified_msg_origin not in self.whitelist:
            logger.info(f"会话 {event.unified_msg_origin} 不在会话白名单中，已终止事件传播。")
            event.stop_event()