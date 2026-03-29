"""v4 原生装饰器。

提供声明式的方法来注册 handler 和 capability。
装饰器会在方法上附加元数据，由 Star.__init_subclass__ 自动收集。

触发器装饰器：
    - @on_command: 命令触发器
    - @on_message: 消息触发器（关键词/正则）
    - @on_event: 事件触发器
    - @on_schedule: 定时任务触发器
    - @conversation_command: 带会话生命周期的命令触发器

权限与过滤装饰器：
    - @require_admin / @admin_only: 管理员权限标记
    - @require_permission: 通用角色权限标记
    - @platforms: 限定平台
    - @group_only / @private_only: 群聊/私聊限定
    - @message_types: 消息类型过滤

限流装饰器：
    - @rate_limit: 滑动窗口限流
    - @cooldown: 冷却时间

优先级装饰器：
    - @priority: 设置执行优先级

能力导出装饰器：
    - @provide_capability: 声明对外暴露的能力
    - @register_llm_tool: 注册 LLM 工具
    - @register_agent: 注册 Agent

Example:
    class MyPlugin(Star):
        @on_command("hello", aliases=["hi"])
        async def hello(self, event: MessageEvent, ctx: Context):
            await event.reply("Hello!")

        @on_message(keywords=["help"])
        async def help(self, event: MessageEvent, ctx: Context):
            await event.reply("Help info...")

        @provide_capability("my_plugin.calculate", description="计算")
        async def calculate(self, payload: dict, ctx: Context):
            return {"result": payload["x"] * 2}
"""

from __future__ import annotations

import inspect
import typing
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, TypeVar, cast

from pydantic import BaseModel

from ._internal.typing_utils import unwrap_optional
from .llm.agents import AgentSpec, BaseAgentRunner
from .llm.entities import LLMToolSpec
from .protocol.descriptors import (
    RESERVED_CAPABILITY_PREFIXES,
    CapabilityDescriptor,
    CommandRouteSpec,
    CommandTrigger,
    EventTrigger,
    FilterSpec,
    MessageTrigger,
    MessageTypeFilterSpec,
    Permissions,
    PlatformFilterSpec,
    ScheduleTrigger,
)

HandlerCallable = Callable[..., Any]
_HandlerT = TypeVar("_HandlerT", bound=Callable[..., Any])
HANDLER_META_ATTR = "__astrbot_handler_meta__"
CAPABILITY_META_ATTR = "__astrbot_capability_meta__"
LLM_TOOL_META_ATTR = "__astrbot_llm_tool_meta__"
AGENT_META_ATTR = "__astrbot_agent_meta__"
HTTP_API_META_ATTR = "__astrbot_http_api_meta__"
VALIDATE_CONFIG_META_ATTR = "__astrbot_validate_config_meta__"
PROVIDER_CHANGE_META_ATTR = "__astrbot_provider_change_meta__"
BACKGROUND_TASK_META_ATTR = "__astrbot_background_task_meta__"
MCP_SERVER_META_ATTR = "__astrbot_mcp_server_meta__"
SKILL_META_ATTR = "__astrbot_skill_meta__"

LimiterScope = Literal["session", "user", "group", "global"]
LimiterBehavior = Literal["hint", "silent", "error"]
ConversationMode = Literal["replace", "reject"]


@dataclass(slots=True)
class LimiterMeta:
    kind: Literal["rate_limit", "cooldown"]
    limit: int
    window: float
    scope: LimiterScope = "session"
    behavior: LimiterBehavior = "hint"
    message: str | None = None


@dataclass(slots=True)
class ConversationMeta:
    timeout: int = 60
    mode: ConversationMode = "replace"
    busy_message: str | None = None
    grace_period: float = 1.0


@dataclass(slots=True)
class HandlerMeta:
    """Handler 元数据。

    存储在方法上的 __astrbot_handler_meta__ 属性中。

    Attributes:
        trigger: 触发器（命令/消息/事件/定时）
        kind: handler 类型标识
        contract: 契约类型（可选）
        priority: 执行优先级（数值越大越先执行）
        permissions: 权限要求
    """

    trigger: CommandTrigger | MessageTrigger | EventTrigger | ScheduleTrigger | None = (
        None
    )
    kind: str = "handler"
    contract: str | None = None
    description: str | None = None
    priority: int = 0
    permissions: Permissions = field(default_factory=Permissions)
    filters: list[FilterSpec] = field(default_factory=list)
    local_filters: list[Any] = field(default_factory=list)
    command_route: CommandRouteSpec | None = None
    limiter: LimiterMeta | None = None
    conversation: ConversationMeta | None = None
    decorator_sources: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class CapabilityMeta:
    """Capability 元数据。

    存储在方法上的 __astrbot_capability_meta__ 属性中。

    Attributes:
        descriptor: 能力描述符
    """

    descriptor: CapabilityDescriptor


@dataclass(slots=True)
class LLMToolMeta:
    spec: LLMToolSpec


@dataclass(slots=True)
class AgentMeta:
    spec: AgentSpec


@dataclass(slots=True)
class HttpApiMeta:
    route: str
    methods: list[str] = field(default_factory=lambda: ["GET"])
    description: str = ""
    capability_name: str | None = None


@dataclass(slots=True)
class ValidateConfigMeta:
    model: type[BaseModel] | None = None
    schema: dict[str, Any] | None = None


def _is_valid_validate_config_expected_type(value: Any) -> bool:
    if isinstance(value, type):
        return True
    return (
        isinstance(value, tuple)
        and len(value) > 0
        and all(isinstance(item, type) for item in value)
    )


def _validate_validate_config_schema(schema: dict[str, Any]) -> None:
    for field_name, field_schema in schema.items():
        if not isinstance(field_schema, dict):
            raise TypeError(
                f"validate_config schema field {field_name!r} must be a dict"
            )
        expected_type = field_schema.get("type")
        if expected_type is not None and not _is_valid_validate_config_expected_type(
            expected_type
        ):
            raise TypeError(
                "validate_config schema field "
                f"{field_name!r} has invalid 'type' entry {expected_type!r}; "
                "expected a type or tuple of types"
            )


@dataclass(slots=True)
class ProviderChangeMeta:
    provider_types: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BackgroundTaskMeta:
    description: str = ""
    auto_start: bool = True
    on_error: Literal["log", "restart"] = "log"


@dataclass(slots=True)
class MCPServerMeta:
    name: str
    scope: Literal["local", "global"] = "global"
    config: dict[str, Any] | None = None
    timeout: float = 30.0
    wait_until_ready: bool = True


@dataclass(slots=True)
class SkillMeta:
    name: str
    path: str
    description: str = ""


def _get_or_create_meta(func: HandlerCallable) -> HandlerMeta:
    """获取或创建 handler 元数据。"""
    meta = getattr(func, HANDLER_META_ATTR, None)
    if meta is None:
        meta = HandlerMeta()
        setattr(func, HANDLER_META_ATTR, meta)
    return meta


def get_handler_meta(func: HandlerCallable) -> HandlerMeta | None:
    """获取方法的 handler 元数据。

    Args:
        func: 要检查的方法

    Returns:
        HandlerMeta 实例，如果没有则返回 None
    """
    return getattr(func, HANDLER_META_ATTR, None)


def get_capability_meta(func: HandlerCallable) -> CapabilityMeta | None:
    """获取方法的 capability 元数据。

    Args:
        func: 要检查的方法

    Returns:
        CapabilityMeta 实例，如果没有则返回 None
    """
    return getattr(func, CAPABILITY_META_ATTR, None)


def get_llm_tool_meta(func: HandlerCallable) -> LLMToolMeta | None:
    return getattr(func, LLM_TOOL_META_ATTR, None)


def get_agent_meta(obj: Any) -> AgentMeta | None:
    return getattr(obj, AGENT_META_ATTR, None)


def get_http_api_meta(func: HandlerCallable) -> HttpApiMeta | None:
    return getattr(func, HTTP_API_META_ATTR, None)


def get_validate_config_meta(func: HandlerCallable) -> ValidateConfigMeta | None:
    return getattr(func, VALIDATE_CONFIG_META_ATTR, None)


def get_provider_change_meta(func: HandlerCallable) -> ProviderChangeMeta | None:
    return getattr(func, PROVIDER_CHANGE_META_ATTR, None)


def get_background_task_meta(func: HandlerCallable) -> BackgroundTaskMeta | None:
    return getattr(func, BACKGROUND_TASK_META_ATTR, None)


def get_mcp_server_meta(obj: Any) -> list[MCPServerMeta]:
    values = getattr(obj, MCP_SERVER_META_ATTR, None)
    if not isinstance(values, list):
        return []
    return [item for item in values if isinstance(item, MCPServerMeta)]


def get_skill_meta(obj: Any) -> list[SkillMeta]:
    values = getattr(obj, SKILL_META_ATTR, None)
    if not isinstance(values, list):
        return []
    return [item for item in values if isinstance(item, SkillMeta)]


def _append_list_meta(obj: Any, attr_name: str, value: Any) -> None:
    values = getattr(obj, attr_name, None)
    if not isinstance(values, list):
        values = []
        setattr(obj, attr_name, values)
    values.append(value)


def _replace_filter(meta: HandlerMeta, spec: FilterSpec) -> None:
    kind = getattr(spec, "kind", None)
    meta.filters = [
        item for item in meta.filters if getattr(item, "kind", None) != kind
    ]
    meta.filters.append(spec)


def _has_filter_kind(meta: HandlerMeta, kind: str) -> bool:
    return any(getattr(item, "kind", None) == kind for item in meta.filters)


def _set_platform_filter(
    meta: HandlerMeta,
    values: list[str],
    *,
    source: str,
) -> None:
    normalized = [
        value for value in dict.fromkeys(str(item).strip() for item in values) if value
    ]
    if not normalized:
        return
    existing = meta.decorator_sources.get("platforms")
    if existing is not None and existing != source:
        raise ValueError("platforms(...) 不能与 on_message(platforms=...) 混用")
    if existing is None and _has_filter_kind(meta, "platform"):
        raise ValueError("platforms(...) 不能与已有平台过滤器混用")
    meta.decorator_sources["platforms"] = source
    _replace_filter(meta, PlatformFilterSpec(platforms=normalized))


def _set_message_type_filter(
    meta: HandlerMeta,
    values: list[str],
    *,
    source: str,
) -> None:
    normalized = [
        value
        for value in dict.fromkeys(str(item).strip().lower() for item in values)
        if value
    ]
    if not normalized:
        return
    existing = meta.decorator_sources.get("message_types")
    if existing is not None and existing != source:
        raise ValueError(
            "group_only()/private_only()/message_types(...) 不能与已有消息类型约束混用"
        )
    if existing is None and _has_filter_kind(meta, "message_type"):
        raise ValueError(
            "group_only()/private_only()/message_types(...) 不能与已有消息类型过滤器混用"
        )
    meta.decorator_sources["message_types"] = source
    _replace_filter(meta, MessageTypeFilterSpec(message_types=normalized))


def _validate_message_trigger_compatibility(meta: HandlerMeta) -> None:
    if meta.limiter is None or meta.trigger is None:
        return
    trigger_type = getattr(meta.trigger, "type", None)
    if trigger_type not in {"command", "message"}:
        raise ValueError(
            "rate_limit(...) 和 cooldown(...) 只适用于 on_command/on_message"
        )


def _set_required_role(
    meta: HandlerMeta,
    role: Literal["member", "admin"],
) -> None:
    current = meta.permissions.required_role
    if current is not None and current != role:
        raise ValueError(
            f"require_permission({role!r}) 与已有权限要求 {current!r} 冲突"
        )
    meta.permissions.required_role = role
    meta.permissions.require_admin = role == "admin"


def _normalize_description(description: str | None) -> str | None:
    if description is None:
        return None
    text = str(description).strip()
    return text or None


def _require_handler_callable(
    target: Any,
    *,
    decorator_name: str,
) -> None:
    if not callable(target):
        raise TypeError(f"{decorator_name} can only decorate callables")


def _validate_limiter_args(
    *,
    kind: str,
    limit: int,
    window: float,
    scope: LimiterScope,
    behavior: LimiterBehavior,
) -> None:
    if isinstance(limit, bool) or int(limit) <= 0:
        raise ValueError(f"{kind} requires a positive limit")
    if float(window) <= 0:
        raise ValueError(f"{kind} requires a positive window")
    if scope not in {"session", "user", "group", "global"}:
        raise ValueError(f"unsupported limiter scope: {scope}")
    if behavior not in {"hint", "silent", "error"}:
        raise ValueError(f"unsupported limiter behavior: {behavior}")


def _set_limiter(
    func: _HandlerT,
    limiter: LimiterMeta,
) -> _HandlerT:
    meta = _get_or_create_meta(func)
    if meta.limiter is not None:
        raise ValueError("rate_limit(...) 和 cooldown(...) 不能叠加在同一个 handler 上")
    meta.limiter = limiter
    _validate_message_trigger_compatibility(meta)
    return func


def _model_to_schema(
    model: type[BaseModel] | None,
    *,
    label: str,
) -> dict[str, Any] | None:
    """将 pydantic 模型转换为 JSON Schema。

    Args:
        model: pydantic BaseModel 子类
        label: 错误消息中的字段名

    Returns:
        JSON Schema 字典，如果 model 为 None 则返回 None

    Raises:
        TypeError: 如果 model 不是 BaseModel 子类
    """
    if model is None:
        return None
    if not isinstance(model, type) or not issubclass(model, BaseModel):
        raise TypeError(f"{label} 必须是 pydantic BaseModel 子类")
    return cast(dict[str, Any], model.model_json_schema())


def on_command(
    command: str | typing.Sequence[str],
    *,
    aliases: list[str] | None = None,
    description: str | None = None,
    group: str | typing.Sequence[str] | None = None,
    group_help: str | None = None,
) -> Callable[[_HandlerT], _HandlerT]:
    """注册命令处理方法。

    当用户发送指定命令时触发。命令格式为 `/{command}` 或直接 `{command}`，
    取决于平台配置。

    Args:
        command: 命令名称（不包含前缀符）
        aliases: 命令别名列表
        description: 命令描述，用于帮助信息
        group: 指令组路径。传入 "admin" 表示一级组；传入 ["admin", "user"] 表示多级组
            设置后实际命令为 ``"admin command"`` 或 ``"admin user command"``
        group_help: 指令组描述，用于帮助信息

    Returns:
        装饰器函数

    Example:
        @on_command("echo", aliases=["repeat"], description="重复消息")
        async def echo(self, event: MessageEvent, ctx: Context):
            await event.reply(event.text)

        @on_command("ban", group="admin", description="封禁用户")
        async def admin_ban(self, event: MessageEvent, ctx: Context):
            await event.reply("已封禁")
    """

    if aliases is not None and not isinstance(aliases, list):
        raise TypeError("on_command aliases must be a list of strings")

    commands = (
        [str(command).strip()]
        if isinstance(command, str)
        else [str(item).strip() for item in command]
    )
    commands = [item for item in commands if item]
    if not commands:
        raise ValueError("on_command requires at least one non-empty command name")

    group_path: list[str] = []
    if group is not None:
        group_path = (
            [str(group).strip()]
            if isinstance(group, str)
            else [str(item).strip() for item in group]
        )
        group_path = [item for item in group_path if item]

    canonical = commands[0]
    display_command = " ".join([*group_path, canonical]) if group_path else canonical
    merged_aliases: list[str] = [
        item
        for item in dict.fromkeys([*commands[1:], *(aliases or [])])
        if isinstance(item, str) and item and item != canonical
    ]
    expanded_aliases: list[str] = (
        [" ".join([*group_path, alias]) for alias in merged_aliases]
        if group_path
        else merged_aliases
    )

    def decorator(func: _HandlerT) -> _HandlerT:
        _require_handler_callable(func, decorator_name="on_command(...)")
        meta = _get_or_create_meta(func)
        normalized_description = _normalize_description(description)
        trigger_command = display_command if group_path else canonical
        meta.trigger = CommandTrigger(
            command=trigger_command,
            aliases=expanded_aliases if group_path else merged_aliases,
            description=normalized_description,
        )
        meta.description = normalized_description
        if group_path:
            meta.command_route = CommandRouteSpec(
                group_path=group_path,
                display_command=display_command,
                group_help=_normalize_description(group_help),
            )
        _validate_message_trigger_compatibility(meta)
        return func

    return decorator


def on_message(
    *,
    regex: str | None = None,
    keywords: list[str] | None = None,
    platforms: list[str] | None = None,
    message_types: list[str] | None = None,
    description: str | None = None,
) -> Callable[[_HandlerT], _HandlerT]:
    """注册消息处理方法。

    当消息匹配指定条件时触发。支持正则表达式或关键词匹配。

    Args:
        regex: 正则表达式模式
        keywords: 关键词列表（任一匹配即可）
        platforms: 限定平台列表（如 ["qq", "wechat"]）

    Returns:
        装饰器函数

    Note:
        regex 和 keywords 至少提供一个

    Example:
        @on_message(keywords=["help", "帮助"])
        async def help(self, event: MessageEvent, ctx: Context):
            await event.reply("帮助信息")

        @on_message(regex=r"\\d+")  # 匹配数字
        async def number_handler(self, event: MessageEvent, ctx: Context):
            await event.reply("收到了数字")
    """

    if keywords is not None and not isinstance(keywords, list):
        raise TypeError("on_message keywords must be a list of strings")
    if platforms is not None and not isinstance(platforms, list):
        raise TypeError("on_message platforms must be a list of strings")
    if message_types is not None and not isinstance(message_types, list):
        raise TypeError("on_message message_types must be a list of strings")

    normalized_regex = None if regex is None else str(regex).strip()
    normalized_keywords = [
        str(item).strip() for item in (keywords or []) if str(item).strip()
    ]
    if not normalized_regex and not normalized_keywords:
        raise ValueError("on_message(...) requires regex or at least one keyword")

    def decorator(func: _HandlerT) -> _HandlerT:
        _require_handler_callable(func, decorator_name="on_message(...)")
        meta = _get_or_create_meta(func)
        meta.trigger = MessageTrigger(
            regex=normalized_regex,
            keywords=normalized_keywords,
            platforms=platforms or [],
            message_types=message_types or [],
        )
        meta.description = _normalize_description(description)
        if platforms:
            _set_platform_filter(meta, list(platforms), source="trigger.platforms")
        if message_types:
            _set_message_type_filter(
                meta,
                list(message_types),
                source="trigger.message_types",
            )
        _validate_message_trigger_compatibility(meta)
        return func

    return decorator


def append_filter_meta(
    func: _HandlerT,
    *,
    specs: list[FilterSpec] | None = None,
    local_bindings: list[Any] | None = None,
) -> _HandlerT:
    """追加过滤器元数据。"""
    meta = _get_or_create_meta(func)
    if specs:
        meta.filters.extend(specs)
    if local_bindings:
        meta.local_filters.extend(local_bindings)
    return func


def set_command_route_meta(
    func: _HandlerT,
    route: CommandRouteSpec,
) -> _HandlerT:
    """设置命令路由元数据。"""
    meta = _get_or_create_meta(func)
    meta.command_route = route
    return func


def on_event(
    event_type: str,
    *,
    description: str | None = None,
) -> Callable[[_HandlerT], _HandlerT]:
    """注册事件处理方法。

    当特定类型的事件发生时触发。用于处理非消息类型的事件，
    如群成员变动、好友请求等。

    Args:
        event_type: 事件类型标识

    Returns:
        装饰器函数

    Example:
        @on_event("group_member_join")
        async def on_join(self, event, ctx):
            await ctx.platform.send(event.group_id, "欢迎新人!")
    """

    normalized_event_type = str(event_type).strip()
    if not normalized_event_type:
        raise ValueError("on_event(...) requires a non-empty event_type")

    def decorator(func: _HandlerT) -> _HandlerT:
        _require_handler_callable(func, decorator_name="on_event(...)")
        meta = _get_or_create_meta(func)
        meta.trigger = EventTrigger(event_type=normalized_event_type)
        meta.description = _normalize_description(description)
        _validate_message_trigger_compatibility(meta)
        return func

    return decorator


def on_schedule(
    *,
    name: str | None = None,
    cron: str | None = None,
    interval_seconds: int | None = None,
    timezone: str | None = None,
    description: str | None = None,
) -> Callable[[_HandlerT], _HandlerT]:
    """注册定时任务方法。

    按指定的时间计划定期执行。

    Args:
        name: 调度任务名称，默认回退为插件 ID 与 handler ID 组合
        cron: cron 表达式（如 "0 8 * * *" 表示每天 8:00）
        interval_seconds: 执行间隔（秒）
        timezone: IANA 时区名称（如 "Asia/Shanghai"）

    Returns:
        装饰器函数

    Note:
        cron 和 interval_seconds 至少提供一个

    Example:
        @on_schedule(cron="0 8 * * *")  # 每天 8:00
        async def morning_greeting(self, ctx):
            await ctx.platform.send("group_123", "早上好!")

        @on_schedule(interval_seconds=3600)  # 每小时
        async def hourly_check(self, ctx):
            pass
    """

    normalized_name = None if name is None else str(name).strip() or None
    normalized_cron = None if cron is None else str(cron).strip() or None
    normalized_timezone = None if timezone is None else str(timezone).strip() or None
    if normalized_cron is None and interval_seconds is None:
        raise ValueError("on_schedule(...) requires cron or interval_seconds")
    if interval_seconds is not None and (
        isinstance(interval_seconds, bool) or int(interval_seconds) <= 0
    ):
        raise ValueError("on_schedule(...) interval_seconds must be a positive integer")

    def decorator(func: _HandlerT) -> _HandlerT:
        _require_handler_callable(func, decorator_name="on_schedule(...)")
        meta = _get_or_create_meta(func)
        meta.trigger = ScheduleTrigger(
            name=normalized_name,
            cron=normalized_cron,
            interval_seconds=(
                None if interval_seconds is None else int(interval_seconds)
            ),
            timezone=normalized_timezone,
        )
        meta.description = _normalize_description(description)
        _validate_message_trigger_compatibility(meta)
        return func

    return decorator


def http_api(
    route: str,
    *,
    methods: list[str] | None = None,
    description: str = "",
    capability_name: str | None = None,
) -> Callable[[HandlerCallable], HandlerCallable]:
    normalized_route = str(route).strip()
    if not normalized_route:
        raise ValueError("http_api(...) requires a non-empty route")
    normalized_methods = methods or ["GET"]
    normalized_methods = [
        str(item).strip().upper() for item in normalized_methods if str(item).strip()
    ]
    if not normalized_methods:
        raise ValueError("http_api(...) requires at least one HTTP method")

    def decorator(func: HandlerCallable) -> HandlerCallable:
        _require_handler_callable(func, decorator_name="http_api(...)")
        setattr(
            func,
            HTTP_API_META_ATTR,
            HttpApiMeta(
                route=normalized_route,
                methods=normalized_methods,
                description=str(description),
                capability_name=(
                    str(capability_name).strip()
                    if capability_name is not None
                    else None
                ),
            ),
        )
        return func

    return decorator


def validate_config(
    *,
    model: type[BaseModel] | None = None,
    schema: dict[str, Any] | None = None,
) -> Callable[[HandlerCallable], HandlerCallable]:
    if model is None and schema is None:
        raise ValueError("validate_config(...) requires model or schema")
    if model is not None and schema is not None:
        raise ValueError("validate_config(...) cannot accept model and schema together")
    if model is not None and (
        not isinstance(model, type) or not issubclass(model, BaseModel)
    ):
        raise TypeError("validate_config model must be a pydantic BaseModel subclass")
    if schema is not None and not isinstance(schema, dict):
        raise TypeError("validate_config schema must be a dict")
    if isinstance(schema, dict):
        _validate_validate_config_schema(schema)

    def decorator(func: HandlerCallable) -> HandlerCallable:
        _require_handler_callable(func, decorator_name="validate_config(...)")
        setattr(
            func,
            VALIDATE_CONFIG_META_ATTR,
            ValidateConfigMeta(
                model=model,
                schema=dict(schema) if isinstance(schema, dict) else None,
            ),
        )
        return func

    return decorator


def on_provider_change(
    *,
    provider_types: list[str] | tuple[str, ...] | None = None,
) -> Callable[[HandlerCallable], HandlerCallable]:
    normalized = [
        str(item).strip().lower()
        for item in (provider_types or [])
        if str(item).strip()
    ]

    def decorator(func: HandlerCallable) -> HandlerCallable:
        _require_handler_callable(func, decorator_name="on_provider_change(...)")
        setattr(
            func,
            PROVIDER_CHANGE_META_ATTR,
            ProviderChangeMeta(provider_types=normalized),
        )
        return func

    return decorator


def background_task(
    *,
    description: str = "",
    auto_start: bool = True,
    on_error: Literal["log", "restart"] = "log",
) -> Callable[[HandlerCallable], HandlerCallable]:
    if on_error not in {"log", "restart"}:
        raise ValueError("background_task on_error must be 'log' or 'restart'")

    def decorator(func: HandlerCallable) -> HandlerCallable:
        _require_handler_callable(func, decorator_name="background_task(...)")
        setattr(
            func,
            BACKGROUND_TASK_META_ATTR,
            BackgroundTaskMeta(
                description=str(description),
                auto_start=bool(auto_start),
                on_error=on_error,
            ),
        )
        return func

    return decorator


def mcp_server(
    *,
    name: str,
    scope: Literal["local", "global"] = "global",
    config: dict[str, Any] | None = None,
    timeout: float = 30.0,
    wait_until_ready: bool = True,
):
    normalized_name = str(name).strip()
    if not normalized_name:
        raise ValueError("mcp_server(...) requires a non-empty name")
    if scope not in {"local", "global"}:
        raise ValueError("mcp_server scope must be 'local' or 'global'")
    if config is not None and not isinstance(config, dict):
        raise TypeError("mcp_server config must be a dict")
    if float(timeout) <= 0:
        raise ValueError("mcp_server timeout must be positive")

    meta = MCPServerMeta(
        name=normalized_name,
        scope=scope,
        config=dict(config) if isinstance(config, dict) else None,
        timeout=float(timeout),
        wait_until_ready=bool(wait_until_ready),
    )

    def decorator(target):
        _append_list_meta(target, MCP_SERVER_META_ATTR, meta)
        return target

    return decorator


def register_skill(
    *,
    name: str,
    path: str,
    description: str = "",
):
    normalized_name = str(name).strip()
    normalized_path = str(path).strip()
    if not normalized_name:
        raise ValueError("register_skill(...) requires a non-empty name")
    if not normalized_path:
        raise ValueError("register_skill(...) requires a non-empty path")

    meta = SkillMeta(
        name=normalized_name,
        path=normalized_path,
        description=str(description),
    )

    def decorator(target):
        _append_list_meta(target, SKILL_META_ATTR, meta)
        return target

    return decorator


def require_admin(func: _HandlerT) -> _HandlerT:
    """标记 handler 需要管理员权限。

    当用户不是管理员时，handler 将不会被调用。

    Args:
        func: 要标记的方法

    Returns:
        标记后的方法

    Example:
        @on_command("admin")
        @require_admin
        async def admin_only(self, event: MessageEvent, ctx: Context):
            await event.reply("管理员命令执行成功")
    """
    _require_handler_callable(func, decorator_name="require_admin")
    meta = _get_or_create_meta(func)
    _set_required_role(meta, "admin")
    return func


def admin_only(func: _HandlerT) -> _HandlerT:
    return require_admin(func)


def require_permission(
    role: Literal["member", "admin"],
) -> Callable[[_HandlerT], _HandlerT]:
    normalized_role = str(role).strip().lower()
    if normalized_role not in {"member", "admin"}:
        raise ValueError("require_permission(...) 只支持 'member' 或 'admin'")

    def decorator(func: _HandlerT) -> _HandlerT:
        _require_handler_callable(func, decorator_name="require_permission(...)")
        meta = _get_or_create_meta(func)
        _set_required_role(
            meta,
            cast(Literal["member", "admin"], normalized_role),
        )
        return func

    return decorator


def platforms(*names: str) -> Callable[[_HandlerT], _HandlerT]:
    normalized_names = [str(name).strip() for name in names if str(name).strip()]
    if not normalized_names:
        raise ValueError("platforms(...) requires at least one non-empty platform name")

    def decorator(func: _HandlerT) -> _HandlerT:
        _require_handler_callable(func, decorator_name="platforms(...)")
        meta = _get_or_create_meta(func)
        _set_platform_filter(meta, normalized_names, source="decorator.platforms")
        return func

    return decorator


def message_types(*types: str) -> Callable[[_HandlerT], _HandlerT]:
    normalized_types = [str(item).strip() for item in types if str(item).strip()]
    if not normalized_types:
        raise ValueError("message_types(...) requires at least one non-empty type")

    def decorator(func: _HandlerT) -> _HandlerT:
        _require_handler_callable(func, decorator_name="message_types(...)")
        meta = _get_or_create_meta(func)
        _set_message_type_filter(
            meta,
            normalized_types,
            source="decorator.message_types",
        )
        return func

    return decorator


def group_only() -> Callable[[_HandlerT], _HandlerT]:
    def decorator(func: _HandlerT) -> _HandlerT:
        _require_handler_callable(func, decorator_name="group_only()")
        meta = _get_or_create_meta(func)
        _set_message_type_filter(meta, ["group"], source="decorator.group_only")
        return func

    return decorator


def private_only() -> Callable[[_HandlerT], _HandlerT]:
    def decorator(func: _HandlerT) -> _HandlerT:
        _require_handler_callable(func, decorator_name="private_only()")
        meta = _get_or_create_meta(func)
        _set_message_type_filter(meta, ["private"], source="decorator.private_only")
        return func

    return decorator


def priority(value: int) -> Callable[[_HandlerT], _HandlerT]:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("priority(...) requires an integer")

    def decorator(func: _HandlerT) -> _HandlerT:
        _require_handler_callable(func, decorator_name="priority(...)")
        meta = _get_or_create_meta(func)
        meta.priority = value
        return func

    return decorator


def rate_limit(
    limit: int,
    window: float,
    *,
    scope: LimiterScope = "session",
    behavior: LimiterBehavior = "hint",
    message: str | None = None,
) -> Callable[[_HandlerT], _HandlerT]:
    _validate_limiter_args(
        kind="rate_limit",
        limit=limit,
        window=window,
        scope=scope,
        behavior=behavior,
    )

    def decorator(func: _HandlerT) -> _HandlerT:
        _require_handler_callable(func, decorator_name="rate_limit(...)")
        return _set_limiter(
            func,
            LimiterMeta(
                kind="rate_limit",
                limit=int(limit),
                window=float(window),
                scope=scope,
                behavior=behavior,
                message=message,
            ),
        )

    return decorator


def cooldown(
    seconds: float,
    *,
    scope: LimiterScope = "session",
    behavior: LimiterBehavior = "hint",
    message: str | None = None,
) -> Callable[[_HandlerT], _HandlerT]:
    _validate_limiter_args(
        kind="cooldown",
        limit=1,
        window=seconds,
        scope=scope,
        behavior=behavior,
    )

    def decorator(func: _HandlerT) -> _HandlerT:
        _require_handler_callable(func, decorator_name="cooldown(...)")
        return _set_limiter(
            func,
            LimiterMeta(
                kind="cooldown",
                limit=1,
                window=float(seconds),
                scope=scope,
                behavior=behavior,
                message=message,
            ),
        )

    return decorator


def conversation_command(
    command: str | typing.Sequence[str],
    *,
    aliases: list[str] | None = None,
    description: str | None = None,
    group: str | typing.Sequence[str] | None = None,
    group_help: str | None = None,
    timeout: int = 60,
    mode: ConversationMode = "replace",
    busy_message: str | None = None,
    grace_period: float = 1.0,
) -> Callable[[_HandlerT], _HandlerT]:
    """注册带会话生命周期的命令处理方法。

    在 ``on_command`` 基础上附加会话元数据，支持超时、并发策略和宽限期控制。

    Args:
        command: 命令名称或序列（首项为正式名，其余视为别名）
        aliases: 额外别名列表
        description: 命令描述
        group: 指令组路径，例如 ``"admin"`` 或 ``["admin", "user"]``
        group_help: 指令组描述，用于帮助信息
        timeout: 会话超时时间（秒），必须为正整数
        mode: 会话冲突时的行为：
            - ``"replace"``: 替换当前会话
            - ``"reject"``: 拒绝新请求
        busy_message: 拒绝新请求时的提示消息
        grace_period: 宽限期（秒），用于会话生命周期处理

    Returns:
        装饰器函数

    Raises:
        ValueError: mode 不合法、timeout 非正整数或 grace_period 非正数

    Example:
        @conversation_command("chat", timeout=120, mode="reject", busy_message="请稍后再试")
        async def chat(self, event: MessageEvent, ctx: Context):
            await event.reply("开始对话...")
    """
    if mode not in {"replace", "reject"}:
        raise ValueError("conversation_command mode must be 'replace' or 'reject'")
    # bool 是 int 子类，需单独排除
    if isinstance(timeout, bool) or int(timeout) <= 0:
        raise ValueError("conversation_command timeout must be a positive integer")
    if float(grace_period) <= 0:
        raise ValueError("conversation_command grace_period must be positive")

    command_decorator = on_command(
        command,
        aliases=aliases,
        description=description,
        group=group,
        group_help=group_help,
    )

    def decorator(func: _HandlerT) -> _HandlerT:
        _require_handler_callable(func, decorator_name="conversation_command(...)")
        decorated = command_decorator(func)
        meta = _get_or_create_meta(decorated)
        meta.conversation = ConversationMeta(
            timeout=int(timeout),
            mode=mode,
            busy_message=busy_message,
            grace_period=float(grace_period),
        )
        return decorated

    return decorator


def provide_capability(
    name: str,
    *,
    description: str,
    input_schema: dict[str, Any] | None = None,
    output_schema: dict[str, Any] | None = None,
    input_model: type[BaseModel] | None = None,
    output_model: type[BaseModel] | None = None,
    supports_stream: bool = False,
    cancelable: bool = False,
) -> Callable[[HandlerCallable], HandlerCallable]:
    """声明插件对外暴露的 capability。

    允许其他插件或 Core 通过 capability 名称调用此方法。
    支持使用 JSON Schema 或 pydantic 模型定义输入输出。

    Args:
        name: capability 名称（不能使用保留命名空间，且运行时必须以当前 plugin_id 为前缀）
        description: 能力描述
        input_schema: 输入 JSON Schema
        output_schema: 输出 JSON Schema
        input_model: 输入 pydantic 模型（与 input_schema 二选一）
        output_model: 输出 pydantic 模型（与 output_schema 二选一）
        supports_stream: 是否支持流式输出
        cancelable: 是否可取消

    Returns:
        装饰器函数

    Raises:
        ValueError: 如果使用保留命名空间，或同时提供 schema 和 model

    Example:
        @provide_capability(
            "my_plugin.calculate",
            description="执行计算",
            input_model=CalculateInput,
            output_model=CalculateOutput,
        )
        async def calculate(self, payload: dict, ctx: Context):
            return {"result": payload["x"] * 2}
    """

    normalized_name = str(name).strip()
    if not normalized_name:
        raise ValueError("provide_capability(...) requires a non-empty name")
    normalized_description = _normalize_description(description)
    if normalized_description is None:
        raise ValueError("provide_capability(...) requires a non-empty description")
    if input_schema is not None and not isinstance(input_schema, dict):
        raise TypeError("input_schema must be a dict")
    if output_schema is not None and not isinstance(output_schema, dict):
        raise TypeError("output_schema must be a dict")

    def decorator(func: HandlerCallable) -> HandlerCallable:
        _require_handler_callable(func, decorator_name="provide_capability(...)")
        if normalized_name.startswith(RESERVED_CAPABILITY_PREFIXES):
            raise ValueError(
                f"保留 capability 命名空间不能用于插件导出：{normalized_name}"
            )
        if input_schema is not None and input_model is not None:
            raise ValueError("input_schema 和 input_model 不能同时提供")
        if output_schema is not None and output_model is not None:
            raise ValueError("output_schema 和 output_model 不能同时提供")
        descriptor = CapabilityDescriptor(
            name=normalized_name,
            description=normalized_description,
            input_schema=(
                input_schema
                if input_schema is not None
                else _model_to_schema(input_model, label="input_model")
            ),
            output_schema=(
                output_schema
                if output_schema is not None
                else _model_to_schema(output_model, label="output_model")
            ),
            supports_stream=supports_stream,
            cancelable=cancelable,
        )
        setattr(func, CAPABILITY_META_ATTR, CapabilityMeta(descriptor=descriptor))
        return func

    return decorator


def _annotation_to_schema(annotation: Any) -> dict[str, Any]:
    normalized, _is_optional = unwrap_optional(annotation)
    origin = typing.get_origin(normalized)
    if normalized is str:
        return {"type": "string"}
    if normalized is int:
        return {"type": "integer"}
    if normalized is float:
        return {"type": "number"}
    if normalized is bool:
        return {"type": "boolean"}
    if normalized is dict or origin is dict:
        return {"type": "object"}
    if normalized is list or origin is list:
        args = typing.get_args(normalized)
        item_schema = _annotation_to_schema(args[0]) if args else {}
        return {"type": "array", "items": item_schema}
    return {"type": "string"}


def _callable_parameters_schema(func: HandlerCallable) -> dict[str, Any]:
    signature = inspect.signature(func)
    type_hints: dict[str, Any] = {}
    try:
        type_hints = typing.get_type_hints(func)
    except Exception:
        type_hints = {}

    properties: dict[str, Any] = {}
    required: list[str] = []
    for parameter in signature.parameters.values():
        if parameter.kind not in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            continue
        if parameter.name == "self":
            continue
        annotation = type_hints.get(parameter.name)
        normalized, _is_optional = unwrap_optional(annotation)
        if parameter.name in {"event", "ctx", "context"}:
            continue
        properties[parameter.name] = _annotation_to_schema(normalized)
        if parameter.default is inspect.Parameter.empty and not _is_optional:
            required.append(parameter.name)
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def register_llm_tool(
    name: str | None = None,
    *,
    description: str | None = None,
    parameters_schema: dict[str, Any] | None = None,
    active: bool = True,
) -> Callable[[HandlerCallable], HandlerCallable]:
    if parameters_schema is not None and not isinstance(parameters_schema, dict):
        raise TypeError("register_llm_tool parameters_schema must be a dict")
    if not isinstance(active, bool):
        raise TypeError("register_llm_tool active must be a bool")

    def decorator(func: HandlerCallable) -> HandlerCallable:
        _require_handler_callable(func, decorator_name="register_llm_tool(...)")
        tool_name = str(name or func.__name__).strip()
        if not tool_name:
            raise ValueError("LLM tool name must not be empty")
        setattr(
            func,
            LLM_TOOL_META_ATTR,
            LLMToolMeta(
                spec=LLMToolSpec.create(
                    name=tool_name,
                    description=description
                    or (inspect.getdoc(func) or "").splitlines()[0]
                    if inspect.getdoc(func)
                    else "",
                    parameters_schema=parameters_schema
                    or _callable_parameters_schema(func),
                    handler_ref=tool_name,
                    active=active,
                )
            ),
        )
        return func

    return decorator


def register_agent(
    name: str,
    *,
    description: str = "",
    tool_names: list[str] | None = None,
) -> Callable[[type[BaseAgentRunner]], type[BaseAgentRunner]]:
    if tool_names is not None and not isinstance(tool_names, list):
        raise TypeError("register_agent tool_names must be a list of strings")
    normalized_name = str(name).strip()
    if not normalized_name:
        raise ValueError("register_agent(...) requires a non-empty name")
    normalized_tool_names = [
        str(tool_name).strip()
        for tool_name in dict.fromkeys(tool_names or [])
        if str(tool_name).strip()
    ]

    def decorator(cls: type[BaseAgentRunner]) -> type[BaseAgentRunner]:
        if not inspect.isclass(cls) or not issubclass(cls, BaseAgentRunner):
            raise TypeError("@register_agent() 只接受 BaseAgentRunner 子类")
        setattr(
            cls,
            AGENT_META_ATTR,
            AgentMeta(
                spec=AgentSpec(
                    name=normalized_name,
                    description=description,
                    tool_names=normalized_tool_names,
                    runner_class=f"{cls.__module__}.{cls.__qualname__}",
                )
            ),
        )
        return cls

    return decorator


def acknowledge_global_mcp_risk(cls: type[Any]) -> type[Any]:
    """Mark an SDK plugin class as eligible to mutate global MCP state.

    This is intentionally a coarse, class-level marker. Runtime enforcement lives
    in the Core MCP capability bridge.
    """

    setattr(cls, "__astrbot_acknowledge_global_mcp_risk__", True)
    return cls
