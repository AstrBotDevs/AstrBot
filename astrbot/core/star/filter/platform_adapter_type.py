import enum
from . import HandlerFilter
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.config import AstrBotConfig
from typing import Union


class PlatformAdapterType(enum.Flag):
    AIOCQHTTP = enum.auto()
    QQOFFICIAL = enum.auto()
    VCHAT = enum.auto()
    GEWECHAT = enum.auto()
    TELEGRAM = enum.auto()
    WECOM = enum.auto()
    LARK = enum.auto()
    WECHATPADPRO = enum.auto()
    ALL = AIOCQHTTP | QQOFFICIAL | VCHAT | GEWECHAT | TELEGRAM | WECOM | LARK | WECHATPADPRO


ADAPTER_NAME_2_TYPE = {
    "aiocqhttp": PlatformAdapterType.AIOCQHTTP,
    "qq_official": PlatformAdapterType.QQOFFICIAL,
    "vchat": PlatformAdapterType.VCHAT,
    "gewechat": PlatformAdapterType.GEWECHAT,
    "telegram": PlatformAdapterType.TELEGRAM,
    "wecom": PlatformAdapterType.WECOM,
    "lark": PlatformAdapterType.LARK,
    "wechatpadpro": PlatformAdapterType.WECHATPADPRO,
}


class PlatformAdapterTypeFilter(HandlerFilter):
    def __init__(self, platform_adapter_type_or_str: Union[PlatformAdapterType, str]):
        self.type_or_str = platform_adapter_type_or_str

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        adapter_name = event.get_platform_name()
        if adapter_name in ADAPTER_NAME_2_TYPE:
            return ADAPTER_NAME_2_TYPE[adapter_name] & self.type_or_str
        return False
