"""旧版事件过滤器兼容层。

当前兼容层保证以下能力可运行：

- ``command(name, alias=..., priority=...)`` -> ``CommandTrigger``
- ``regex(pattern, priority=...)`` -> ``MessageTrigger``
- ``event_message_type(...)`` -> 记录消息类型约束
- ``platform_adapter_type(...)`` -> 记录平台约束
- ``permission(ADMIN)`` / ``permission_type(PermissionType.ADMIN)``
  -> ``require_admin``

其余旧版高级过滤器和生命周期钩子在 v4 运行时中没有等价执行链路，
兼容层保留名称用于导入兼容，但会在调用时显式报错，避免静默失效。
"""

from __future__ import annotations

import enum
from abc import ABCMeta, abstractmethod
from typing import Any

from ...decorators import _get_or_create_meta, require_admin
from ...protocol.descriptors import CommandTrigger, MessageTrigger
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
    GEWECHAT = enum.auto()
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
        | GEWECHAT
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
    "gewechat": PlatformAdapterType.GEWECHAT,
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


EVENT_MESSAGE_TYPE_NAMES = {
    EventMessageType.GROUP_MESSAGE: "group",
    EventMessageType.PRIVATE_MESSAGE: "private",
    EventMessageType.OTHER_MESSAGE: "other",
}


def _merge_unique(existing: list[str], additions: list[str]) -> list[str]:
    merged: list[str] = []
    for item in [*existing, *additions]:
        if item not in merged:
            merged.append(item)
    return merged


def _normalize_aliases(*alias_groups: Any) -> list[str]:
    aliases: list[str] = []
    for alias_group in alias_groups:
        if alias_group is None:
            continue
        if isinstance(alias_group, str):
            values = [alias_group]
        elif isinstance(alias_group, set):
            values = sorted(str(item) for item in alias_group)
        else:
            values = [str(item) for item in alias_group]
        aliases = _merge_unique(aliases, values)
    return aliases


def _existing_trigger_constraints(
    trigger: CommandTrigger | MessageTrigger | None,
) -> tuple[list[str], list[str], list[str]]:
    if isinstance(trigger, CommandTrigger):
        return list(trigger.platforms), list(trigger.message_types), []
    if isinstance(trigger, MessageTrigger):
        return (
            list(trigger.platforms),
            list(trigger.message_types),
            list(trigger.keywords),
        )
    return [], [], []


def _apply_priority(meta, priority: int | None) -> None:
    if priority is not None:
        meta.priority = priority


def _selected_message_types(event_type: EventMessageType) -> list[str]:
    selected: list[str] = []
    for flag, name in EVENT_MESSAGE_TYPE_NAMES.items():
        if event_type & flag:
            selected.append(name)
    return selected


def _selected_platforms(
    platform_type: PlatformAdapterType | str,
) -> list[str]:
    if isinstance(platform_type, str):
        return [platform_type]
    selected: list[str] = []
    for name, flag in ADAPTER_NAME_2_TYPE.items():
        if platform_type & flag:
            selected.append(name)
    return selected


def command(
    name: str,
    alias: set[str] | list[str] | tuple[str, ...] | str | None = None,
    *,
    aliases: set[str] | list[str] | tuple[str, ...] | str | None = None,
    priority: int | None = None,
    desc: str | None = None,
):
    def decorator(func):
        meta = _get_or_create_meta(func)
        platforms, message_types, _ = _existing_trigger_constraints(meta.trigger)
        meta.trigger = CommandTrigger(
            command=name,
            aliases=_normalize_aliases(alias, aliases),
            description=desc,
            platforms=platforms,
            message_types=message_types,
        )
        _apply_priority(meta, priority)
        return func

    return decorator


def regex(pattern: str, *, priority: int | None = None):
    def decorator(func):
        meta = _get_or_create_meta(func)
        platforms, message_types, keywords = _existing_trigger_constraints(meta.trigger)
        meta.trigger = MessageTrigger(
            regex=pattern,
            keywords=keywords,
            platforms=platforms,
            message_types=message_types,
        )
        _apply_priority(meta, priority)
        return func

    return decorator


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
after_message_sent = _unsupported_factory("after_message_sent")
on_astrbot_loaded = _unsupported_factory("on_astrbot_loaded")
on_platform_loaded = _unsupported_factory("on_platform_loaded")
on_decorating_result = _unsupported_factory("on_decorating_result")
on_llm_request = _unsupported_factory("on_llm_request")
on_llm_response = _unsupported_factory("on_llm_response")
command_group = _unsupported_factory("command_group")


def event_message_type(
    level: EventMessageType,
    *,
    priority: int | None = None,
):
    message_types = _selected_message_types(level)

    def decorator(func):
        meta = _get_or_create_meta(func)
        if meta.trigger is None:
            meta.trigger = MessageTrigger(message_types=message_types)
        elif isinstance(meta.trigger, MessageTrigger):
            meta.trigger.message_types = _merge_unique(
                meta.trigger.message_types,
                message_types,
            )
        elif isinstance(meta.trigger, CommandTrigger):
            meta.trigger.message_types = _merge_unique(
                meta.trigger.message_types,
                message_types,
            )
        else:
            raise NotImplementedError(
                "event_message_type() 目前只支持消息/命令处理器。"
            )
        _apply_priority(meta, priority)
        return func

    return decorator


def platform_adapter_type(
    level: PlatformAdapterType | str,
    *,
    priority: int | None = None,
):
    platforms = _selected_platforms(level)

    def decorator(func):
        meta = _get_or_create_meta(func)
        if meta.trigger is None:
            meta.trigger = MessageTrigger(platforms=platforms)
        elif isinstance(meta.trigger, MessageTrigger):
            meta.trigger.platforms = _merge_unique(meta.trigger.platforms, platforms)
        elif isinstance(meta.trigger, CommandTrigger):
            meta.trigger.platforms = _merge_unique(meta.trigger.platforms, platforms)
        else:
            raise NotImplementedError(
                "platform_adapter_type() 目前只支持消息/命令处理器。"
            )
        _apply_priority(meta, priority)
        return func

    return decorator


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
