from __future__ import annotations

from astrbot.core.message.components import Image, Record
from astrbot.core.pipeline.context import PipelineContext
from astrbot.core.pipeline.system.session_utils import build_unique_session_id
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.message_type import MessageType
from astrbot.core.utils.path_util import path_Mapping


class EventPreprocessor:
    """系统级事件预处理"""

    def __init__(self, ctx: PipelineContext):
        platform_settings = ctx.astrbot_config.get("platform_settings", {})
        self.ignore_bot_self_message = platform_settings.get(
            "ignore_bot_self_message", False
        )
        self.unique_session = platform_settings.get("unique_session", False)
        self.admins_id: list[str] = ctx.astrbot_config.get("admins_id", [])
        self.path_mapping: list[str] = platform_settings.get("path_mapping", [])

    async def preprocess(self, event: AstrMessageEvent) -> bool:
        """
        系统级预处理。

        Returns:
            是否继续处理
        """
        # 应用唯一会话 ID
        if self.unique_session and event.message_obj.type == MessageType.GROUP_MESSAGE:
            sid = build_unique_session_id(event)
            if sid:
                event.session_id = sid

        # 过滤机器人自身消息
        if (
            self.ignore_bot_self_message
            and event.get_self_id() == event.get_sender_id()
        ):
            event.stop_event()
            return False

        # 识别管理员身份
        for admin_id in self.admins_id:
            if str(event.get_sender_id()) == admin_id:
                event.role = "admin"
                break

        # 入站 Record/Image 路径映射
        if self.path_mapping:
            message_chain = event.get_messages()
            for idx, component in enumerate(message_chain):
                if isinstance(component, Record | Image):
                    if component.url:
                        component.url = path_Mapping(self.path_mapping, component.url)
                    if component.file:
                        component.file = path_Mapping(self.path_mapping, component.file)
                    message_chain[idx] = component

        return True
