"""旧版事件过滤器兼容层。

当前兼容层保证以下能力可运行：

- ``command(name, alias=..., priority=...)`` -> ``CommandTrigger``
- ``regex(pattern, priority=...)`` -> ``MessageTrigger``
- ``custom_filter(...)`` -> 记录旧自定义过滤器，运行时在分发前执行
- ``event_message_type(...)`` -> 记录消息类型约束
- ``platform_adapter_type(...)`` -> 记录平台约束
- ``permission(ADMIN)`` / ``permission_type(PermissionType.ADMIN)``
  -> ``require_admin``
- ``after_message_sent`` / ``on_llm_request`` / ``llm_tool`` 等旧 hook
  -> 记录 compat 元数据，由 legacy 运行时在可映射链路中执行

其余没有等价执行链路的旧 helper 仍然显式报错，避免静默失效。
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
import enum
from abc import ABCMeta, abstractmethod
from typing import Any

from ...decorators import _get_or_create_meta, require_admin
from ...protocol.descriptors import CommandTrigger, MessageTrigger
from ..basic.astrbot_config import AstrBotConfig
from .astr_message_event import AstrMessageEvent
from .message_type import MessageType

ADMIN = "admin"
COMPAT_HOOKS_ATTR = "__astrbot_compat_hooks__"
COMPAT_LLM_TOOL_ATTR = "__astrbot_compat_llm_tool__"
COMPAT_CUSTOM_FILTERS_ATTR = "__astrbot_compat_custom_filters__"


@dataclass(slots=True)
class CompatHookMeta:
    name: str
    priority: int = 0


@dataclass(slots=True)
class CompatLLMToolMeta:
    name: str
    description: str
    parameters: list[dict[str, Any]]


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

_LLM_TOOL_PARAM_TYPES: dict[type[Any], str] = {
    str: "string",
    int: "number",
    float: "number",
    bool: "boolean",
    dict: "object",
    list: "array",
}


def _append_compat_hook(func, name: str, *, priority: int | None = None):
    hooks = list(getattr(func, COMPAT_HOOKS_ATTR, ()))
    hooks.append(CompatHookMeta(name=name, priority=priority or 0))
    setattr(func, COMPAT_HOOKS_ATTR, hooks)
    return func


def get_compat_hook_metas(func) -> list[CompatHookMeta]:
    return list(getattr(func, COMPAT_HOOKS_ATTR, ()))


def _append_custom_filter(func, filter_obj: Any):
    filters = list(getattr(func, COMPAT_CUSTOM_FILTERS_ATTR, ()))
    filters.append(filter_obj)
    setattr(func, COMPAT_CUSTOM_FILTERS_ATTR, filters)
    return func


def get_compat_custom_filters(func) -> list[Any]:
    return list(getattr(func, COMPAT_CUSTOM_FILTERS_ATTR, ()))


def _doc_description(func) -> str:
    doc = inspect.getdoc(func) or ""
    if not doc:
        return ""
    return doc.split("\n\n", 1)[0].strip()


def _parameter_description(func, parameter_name: str) -> str:
    doc = inspect.getdoc(func) or ""
    if not doc:
        return ""
    in_args = False
    for raw_line in doc.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped in {"Args:", "Arguments:"}:
            in_args = True
            continue
        if in_args and stripped and not raw_line.startswith((" ", "\t")):
            break
        if not in_args:
            continue
        if stripped.startswith(f"{parameter_name}(") or stripped.startswith(
            f"{parameter_name}:"
        ):
            _, _, tail = stripped.partition(":")
            return tail.strip()
    return ""


def _resolve_json_schema(
    func,
    parameter: inspect.Parameter,
    annotations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    annotation = (
        annotations.get(parameter.name, parameter.annotation)
        if annotations is not None
        else parameter.annotation
    )
    origin = getattr(annotation, "__origin__", None)
    args = getattr(annotation, "__args__", ())
    item_type = None
    if annotation in _LLM_TOOL_PARAM_TYPES:
        type_name = _LLM_TOOL_PARAM_TYPES[annotation]
    elif origin in {list, tuple}:
        type_name = "array"
        if args:
            item_type = _LLM_TOOL_PARAM_TYPES.get(args[0], "string")
    elif origin is dict:
        type_name = "object"
    else:
        type_name = "string"
    schema = {
        "type": type_name,
        "name": parameter.name,
        "description": _parameter_description(func, parameter.name),
    }
    if item_type is not None:
        schema["items"] = {"type": item_type}
    return schema


def _build_llm_tool_meta(func, tool_name: str | None) -> CompatLLMToolMeta:
    signature = inspect.signature(func)
    annotations = inspect.get_annotations(func, eval_str=True)
    parameters: list[dict[str, Any]] = []
    for parameter in signature.parameters.values():
        if parameter.kind not in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            continue
        if parameter.name in {
            "self",
            "event",
            "ctx",
            "context",
            "cancel_token",
            "token",
        }:
            continue
        parameters.append(_resolve_json_schema(func, parameter, annotations))
    return CompatLLMToolMeta(
        name=tool_name or func.__name__,
        description=_doc_description(func),
        parameters=parameters,
    )


def get_compat_llm_tool_meta(func) -> CompatLLMToolMeta | None:
    return getattr(func, COMPAT_LLM_TOOL_ATTR, None)


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


class LegacyCommandGroup:
    """旧版命令组兼容对象。

    当前运行时还没有旧版树状帮助与多层命令组执行链，所以 compat 层先把
    `group sub` 展平为普通命令名，确保真实旧插件至少能无感加载与分发。
    """

    def __init__(
        self,
        *parts: str,
        priority: int | None = None,
        desc: str | None = None,
    ) -> None:
        self._parts = tuple(str(part) for part in parts if str(part))
        self._priority = priority
        self._desc = desc

    def __call__(self, func):
        return self

    def command(
        self,
        name: str,
        alias: set[str] | list[str] | tuple[str, ...] | str | None = None,
        *,
        aliases: set[str] | list[str] | tuple[str, ...] | str | None = None,
        priority: int | None = None,
        desc: str | None = None,
    ):
        return command(
            " ".join((*self._parts, name)),
            alias=alias,
            aliases=aliases,
            priority=self._priority if priority is None else priority,
            desc=desc,
        )

    def group(
        self,
        name: str,
        *,
        priority: int | None = None,
        desc: str | None = None,
    ) -> "LegacyCommandGroup":
        return LegacyCommandGroup(
            *self._parts,
            name,
            priority=self._priority if priority is None else priority,
            desc=desc,
        )


def _unsupported_factory(name: str, replacement: str | None = None):
    suggestion = f"请改用 {replacement}" if replacement else "当前没有直接替代实现"
    message = (
        f"astrbot_sdk.api.event.filter.{name}() 尚未在 v4 兼容层中实现。"
        f"{suggestion}，或改写为新版插件结构。"
    )

    def factory(*args, **kwargs):
        raise NotImplementedError(message)

    return factory


def custom_filter(custom_type_filter, raise_error: bool = True, **kwargs):
    """旧版自定义过滤器兼容入口。

    当前 compat 层支持最常见的函数级 `@custom_filter(MyFilter)` 用法。
    指令组级自定义过滤链路仍然依赖旧 command_group 树，不在 v4 主链里复刻。
    """

    def decorator(func):
        if isinstance(custom_type_filter, (CustomFilterAnd, CustomFilterOr)):
            filter_obj = custom_type_filter
        elif isinstance(custom_type_filter, type) and issubclass(
            custom_type_filter, CustomFilter
        ):
            filter_obj = custom_type_filter(raise_error=raise_error, **kwargs)
        elif isinstance(custom_type_filter, CustomFilter):
            filter_obj = custom_type_filter
        else:
            raise TypeError("custom_filter 只支持 CustomFilter 子类或实例")
        return _append_custom_filter(func, filter_obj)

    return decorator


def _compat_hook(name: str):
    def factory(*, priority: int | None = None, **_kwargs):
        def decorator(func):
            return _append_compat_hook(func, name, priority=priority)

        return decorator

    return factory


after_message_sent = _compat_hook("after_message_sent")
on_astrbot_loaded = _compat_hook("on_astrbot_loaded")
on_platform_loaded = _compat_hook("on_platform_loaded")
on_decorating_result = _compat_hook("on_decorating_result")
on_llm_request = _compat_hook("on_llm_request")
on_llm_response = _compat_hook("on_llm_response")
on_waiting_llm_request = _compat_hook("on_waiting_llm_request")
on_using_llm_tool = _compat_hook("on_using_llm_tool")
on_llm_tool_respond = _compat_hook("on_llm_tool_respond")
on_plugin_error = _compat_hook("on_plugin_error")
on_plugin_loaded = _compat_hook("on_plugin_loaded")
on_plugin_unloaded = _compat_hook("on_plugin_unloaded")


def llm_tool(name: str | None = None, **_kwargs):
    def decorator(func):
        setattr(func, COMPAT_LLM_TOOL_ATTR, _build_llm_tool_meta(func, name))
        return func

    return decorator


def command_group(
    name: str,
    alias: set[str] | list[str] | tuple[str, ...] | str | None = None,
    *,
    aliases: set[str] | list[str] | tuple[str, ...] | str | None = None,
    priority: int | None = None,
    desc: str | None = None,
) -> LegacyCommandGroup:
    del alias, aliases
    return LegacyCommandGroup(name, priority=priority, desc=desc)


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
    ADMIN = ADMIN
    PermissionType = PermissionType
    EventMessageType = EventMessageType
    PlatformAdapterType = PlatformAdapterType
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
    llm_tool = staticmethod(llm_tool)
    on_waiting_llm_request = staticmethod(on_waiting_llm_request)
    on_using_llm_tool = staticmethod(on_using_llm_tool)
    on_llm_tool_respond = staticmethod(on_llm_tool_respond)
    on_plugin_error = staticmethod(on_plugin_error)
    on_plugin_loaded = staticmethod(on_plugin_loaded)
    on_plugin_unloaded = staticmethod(on_plugin_unloaded)
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
    "llm_tool",
    "on_astrbot_loaded",
    "on_decorating_result",
    "on_llm_tool_respond",
    "on_llm_request",
    "on_llm_response",
    "on_platform_loaded",
    "on_plugin_error",
    "on_plugin_loaded",
    "on_plugin_unloaded",
    "on_using_llm_tool",
    "on_waiting_llm_request",
    "permission",
    "permission_type",
    "platform_adapter_type",
    "regex",
]
