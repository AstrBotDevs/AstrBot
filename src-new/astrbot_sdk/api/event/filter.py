"""旧版事件过滤器兼容层。

当前兼容层保证以下能力可运行：

- ``command(name)`` -> ``on_command(name)``
- ``regex(pattern)`` -> ``on_message(regex=pattern)``
- ``permission(ADMIN)`` / ``permission_type(PermissionType.ADMIN)``
  -> ``require_admin``

其余旧版高级过滤器和生命周期钩子在 v4 运行时中没有等价执行链路，
兼容层保留名称用于导入兼容，但会在调用时显式报错，避免静默失效。
"""

from __future__ import annotations

import enum
from abc import ABCMeta, abstractmethod
from typing import Any

from ...decorators import on_command, on_message, require_admin
from ..basic.astrbot_config import AstrBotConfig
from .astr_message_event import AstrMessageEvent
from .message_type import MessageType

ADMIN = "admin"


class PermissionType(enum.Flag):
    ADMIN = enum.auto()
    MEMBER = enum.auto()


class PermissionTypeFilter:
    def __init__(self, permission_type: PermissionType, raise_error: bool = True):
        self.permission_type = permission_type
        self.raise_error = raise_error

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        if self.permission_type == PermissionType.ADMIN:
            return event.is_admin()
        return True


class EventMessageType(enum.Flag):
    GROUP_MESSAGE = enum.auto()
    PRIVATE_MESSAGE = enum.auto()
    OTHER_MESSAGE = enum.auto()
    ALL = GROUP_MESSAGE | PRIVATE_MESSAGE | OTHER_MESSAGE


MESSAGE_TYPE_2_EVENT_MESSAGE_TYPE = {
    MessageType.GROUP_MESSAGE: EventMessageType.GROUP_MESSAGE,
    MessageType.FRIEND_MESSAGE: EventMessageType.PRIVATE_MESSAGE,
    MessageType.OTHER_MESSAGE: EventMessageType.OTHER_MESSAGE,
}


class EventMessageTypeFilter:
    def __init__(self, event_message_type: EventMessageType):
        self.event_message_type = event_message_type

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        event_message_type = MESSAGE_TYPE_2_EVENT_MESSAGE_TYPE.get(
            event.get_message_type()
        )
        if event_message_type is None:
            return False
        return bool(event_message_type & self.event_message_type)


class PlatformAdapterType(enum.Flag):
    AIOCQHTTP = enum.auto()
    QQOFFICIAL = enum.auto()
    TELEGRAM = enum.auto()
    WECOM = enum.auto()
    LARK = enum.auto()
    WECHATPADPRO = enum.auto()
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
        | WECHATPADPRO
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
    "wechatpadpro": PlatformAdapterType.WECHATPADPRO,
    "vocechat": PlatformAdapterType.VOCECHAT,
    "weixin_official_account": PlatformAdapterType.WEIXIN_OFFICIAL_ACCOUNT,
    "satori": PlatformAdapterType.SATORI,
    "misskey": PlatformAdapterType.MISSKEY,
}


class PlatformAdapterTypeFilter:
    def __init__(self, platform_adapter_type_or_str: PlatformAdapterType | str):
        if isinstance(platform_adapter_type_or_str, str):
            self.platform_type = ADAPTER_NAME_2_TYPE.get(platform_adapter_type_or_str)
        else:
            self.platform_type = platform_adapter_type_or_str

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        adapter_type = ADAPTER_NAME_2_TYPE.get(event.get_platform_name())
        if adapter_type is None or self.platform_type is None:
            return False
        return bool(adapter_type & self.platform_type)


class CustomFilterMeta(ABCMeta):
    def __and__(cls, other):
        if not issubclass(other, CustomFilter):
            raise TypeError("Operands must be subclasses of CustomFilter.")
        return CustomFilterAnd(cls(), other())

    def __or__(cls, other):
        if not issubclass(other, CustomFilter):
            raise TypeError("Operands must be subclasses of CustomFilter.")
        return CustomFilterOr(cls(), other())


class CustomFilter(metaclass=CustomFilterMeta):
    def __init__(self, raise_error: bool = True, **kwargs: Any):
        self.raise_error = raise_error

    @abstractmethod
    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        raise NotImplementedError

    def __or__(self, other):
        return CustomFilterOr(self, other)

    def __and__(self, other):
        return CustomFilterAnd(self, other)


class CustomFilterOr(CustomFilter):
    def __init__(self, filter1: CustomFilter, filter2: CustomFilter):
        super().__init__()
        self.filter1 = filter1
        self.filter2 = filter2

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        return self.filter1.filter(event, cfg) or self.filter2.filter(event, cfg)


class CustomFilterAnd(CustomFilter):
    def __init__(self, filter1: CustomFilter, filter2: CustomFilter):
        super().__init__()
        self.filter1 = filter1
        self.filter2 = filter2

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        return self.filter1.filter(event, cfg) and self.filter2.filter(event, cfg)


def command(name: str):
    return on_command(name)


def regex(pattern: str):
    return on_message(regex=pattern)


def permission(level: str | PermissionType):
    if level in {ADMIN, PermissionType.ADMIN}:
        return require_admin

    def decorator(func):
        return func

    return decorator


def permission_type(level: PermissionType, raise_error: bool = True):
    return permission(level)


def _unsupported_factory(name: str, replacement: str | None = None):
    suggestion = f"请改用 {replacement}" if replacement else "当前没有直接替代实现"
    message = (
        f"astrbot_sdk.api.event.filter.{name}() 尚未在 v4 兼容层中实现。"
        f"{suggestion}，或改写为新版插件结构。"
    )

    def factory(*args, **kwargs):
        raise NotImplementedError(message)

    return factory


custom_filter = _unsupported_factory("custom_filter")
event_message_type = _unsupported_factory("event_message_type")
platform_adapter_type = _unsupported_factory("platform_adapter_type")
after_message_sent = _unsupported_factory("after_message_sent")
on_astrbot_loaded = _unsupported_factory("on_astrbot_loaded")
on_platform_loaded = _unsupported_factory("on_platform_loaded")
on_decorating_result = _unsupported_factory("on_decorating_result")
on_llm_request = _unsupported_factory("on_llm_request")
on_llm_response = _unsupported_factory("on_llm_response")
command_group = _unsupported_factory("command_group")


class _FilterNamespace:
    command = staticmethod(command)
    regex = staticmethod(regex)
    permission = staticmethod(permission)
    permission_type = staticmethod(permission_type)
    custom_filter = staticmethod(custom_filter)
    event_message_type = staticmethod(event_message_type)
    platform_adapter_type = staticmethod(platform_adapter_type)
    after_message_sent = staticmethod(after_message_sent)
    on_astrbot_loaded = staticmethod(on_astrbot_loaded)
    on_platform_loaded = staticmethod(on_platform_loaded)
    on_decorating_result = staticmethod(on_decorating_result)
    on_llm_request = staticmethod(on_llm_request)
    on_llm_response = staticmethod(on_llm_response)
    command_group = staticmethod(command_group)


filter = _FilterNamespace()

__all__ = [
    "ADMIN",
    "CustomFilter",
    "EventMessageType",
    "EventMessageTypeFilter",
    "PermissionType",
    "PermissionTypeFilter",
    "PlatformAdapterType",
    "PlatformAdapterTypeFilter",
    "after_message_sent",
    "command",
    "command_group",
    "custom_filter",
    "event_message_type",
    "filter",
    "on_astrbot_loaded",
    "on_decorating_result",
    "on_llm_request",
    "on_llm_response",
    "on_platform_loaded",
    "permission",
    "permission_type",
    "platform_adapter_type",
    "regex",
]
