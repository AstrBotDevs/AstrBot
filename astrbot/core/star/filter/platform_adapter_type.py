import enum

from astrbot.core.config import AstrBotConfig
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from . import HandlerFilter


class PlatformAdapterType(enum.Flag):
    AIOCQHTTP = enum.auto()
    QQOFFICIAL = enum.auto()
    TELEGRAM = enum.auto()
    WECOM = enum.auto()
    LARK = enum.auto()
    DINGTALK = enum.auto()
    DISCORD = enum.auto()
    SLACK = enum.auto()
    KOOK = enum.auto()
    VOCECHAT = enum.auto()
    WEIXIN_OFFICIAL_ACCOUNT = enum.auto()
    SATORI = enum.auto()
    MISSKEY = enum.auto()
    ALL = (
        AIOCQHTTP
        | QQOFFICIAL
        | TELEGRAM
        | WECOM
        | LARK
        | DINGTALK
        | DISCORD
        | SLACK
        | KOOK
        | VOCECHAT
        | WEIXIN_OFFICIAL_ACCOUNT
        | SATORI
        | MISSKEY
    )


ADAPTER_NAME_2_TYPE = {
    "aiocqhttp": PlatformAdapterType.AIOCQHTTP,
    "qq_official": PlatformAdapterType.QQOFFICIAL,
    "telegram": PlatformAdapterType.TELEGRAM,
    "wecom": PlatformAdapterType.WECOM,
    "lark": PlatformAdapterType.LARK,
    "dingtalk": PlatformAdapterType.DINGTALK,
    "discord": PlatformAdapterType.DISCORD,
    "slack": PlatformAdapterType.SLACK,
    "kook": PlatformAdapterType.KOOK,
    "vocechat": PlatformAdapterType.VOCECHAT,
    "weixin_official_account": PlatformAdapterType.WEIXIN_OFFICIAL_ACCOUNT,
    "satori": PlatformAdapterType.SATORI,
    "misskey": PlatformAdapterType.MISSKEY,
}


class PlatformAdapterTypeFilter(HandlerFilter):
    def __init__(self, platform_adapter_type_or_str: PlatformAdapterType | str):
        if isinstance(platform_adapter_type_or_str, str):
            self.platform_type = ADAPTER_NAME_2_TYPE.get(platform_adapter_type_or_str)
        else:
            self.platform_type = platform_adapter_type_or_str

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        adapter_name = event.get_platform_name()
        if adapter_name in ADAPTER_NAME_2_TYPE and self.platform_type is not None:
            return bool(ADAPTER_NAME_2_TYPE[adapter_name] & self.platform_type)
        return False
