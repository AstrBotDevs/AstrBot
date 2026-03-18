"""v4 原生装饰器。

提供声明式的方法来注册 handler 和 capability。
装饰器会在方法上附加元数据，由 Star.__init_subclass__ 自动收集。

可用的装饰器：
    - @on_command: 命令触发器
    - @on_message: 消息触发器（关键词/正则）
    - @on_event: 事件触发器
    - @on_schedule: 定时任务触发器
    - @require_admin: 权限标记
    - @provide_capability: 声明对外暴露的能力

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
from typing import Any, Literal, cast

from pydantic import BaseModel

from ._typing_utils import unwrap_optional
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
HANDLER_META_ATTR = "__astrbot_handler_meta__"
CAPABILITY_META_ATTR = "__astrbot_capability_meta__"
LLM_TOOL_META_ATTR = "__astrbot_llm_tool_meta__"
AGENT_META_ATTR = "__astrbot_agent_meta__"

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


def _replace_filter(meta: HandlerMeta, spec: FilterSpec) -> None:
    kind = getattr(spec, "kind", None)
    meta.filters = [
        item for item in meta.filters if getattr(item, "kind", None) != kind
    ]
    meta.filters.append(spec)


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
    func: HandlerCallable,
    limiter: LimiterMeta,
) -> HandlerCallable:
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
) -> Callable[[HandlerCallable], HandlerCallable]:
    """注册命令处理方法。

    当用户发送指定命令时触发。命令格式为 `/{command}` 或直接 `{command}`，
    取决于平台配置。

    Args:
        command: 命令名称（不包含前缀符）
        aliases: 命令别名列表
        description: 命令描述，用于帮助信息

    Returns:
        装饰器函数

    Example:
        @on_command("echo", aliases=["repeat"], description="重复消息")
        async def echo(self, event: MessageEvent, ctx: Context):
            await event.reply(event.text)
    """

    commands = (
        [str(command).strip()]
        if isinstance(command, str)
        else [str(item).strip() for item in command]
    )
    commands = [item for item in commands if item]
    if not commands:
        raise ValueError("on_command requires at least one non-empty command name")
    canonical = commands[0]
    merged_aliases: list[str] = [
        item
        for item in dict.fromkeys([*commands[1:], *(aliases or [])])
        if isinstance(item, str) and item and item != canonical
    ]

    def decorator(func: HandlerCallable) -> HandlerCallable:
        meta = _get_or_create_meta(func)
        meta.trigger = CommandTrigger(
            command=canonical,
            aliases=merged_aliases,
            description=description,
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
) -> Callable[[HandlerCallable], HandlerCallable]:
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

    def decorator(func: HandlerCallable) -> HandlerCallable:
        meta = _get_or_create_meta(func)
        meta.trigger = MessageTrigger(
            regex=regex,
            keywords=keywords or [],
            platforms=platforms or [],
            message_types=message_types or [],
        )
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
    func: HandlerCallable,
    *,
    specs: list[FilterSpec] | None = None,
    local_bindings: list[Any] | None = None,
) -> HandlerCallable:
    """追加过滤器元数据。"""
    meta = _get_or_create_meta(func)
    if specs:
        meta.filters.extend(specs)
    if local_bindings:
        meta.local_filters.extend(local_bindings)
    return func


def set_command_route_meta(
    func: HandlerCallable,
    route: CommandRouteSpec,
) -> HandlerCallable:
    """设置命令路由元数据。"""
    meta = _get_or_create_meta(func)
    meta.command_route = route
    return func


def on_event(event_type: str) -> Callable[[HandlerCallable], HandlerCallable]:
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

    def decorator(func: HandlerCallable) -> HandlerCallable:
        meta = _get_or_create_meta(func)
        meta.trigger = EventTrigger(event_type=event_type)
        _validate_message_trigger_compatibility(meta)
        return func

    return decorator


def on_schedule(
    *,
    cron: str | None = None,
    interval_seconds: int | None = None,
) -> Callable[[HandlerCallable], HandlerCallable]:
    """注册定时任务方法。

    按指定的时间计划定期执行。

    Args:
        cron: cron 表达式（如 "0 8 * * *" 表示每天 8:00）
        interval_seconds: 执行间隔（秒）

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

    def decorator(func: HandlerCallable) -> HandlerCallable:
        meta = _get_or_create_meta(func)
        meta.trigger = ScheduleTrigger(cron=cron, interval_seconds=interval_seconds)
        _validate_message_trigger_compatibility(meta)
        return func

    return decorator


def require_admin(func: HandlerCallable) -> HandlerCallable:
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
    meta = _get_or_create_meta(func)
    meta.permissions.require_admin = True
    return func


def admin_only(func: HandlerCallable) -> HandlerCallable:
    return require_admin(func)


def platforms(*names: str) -> Callable[[HandlerCallable], HandlerCallable]:
    def decorator(func: HandlerCallable) -> HandlerCallable:
        meta = _get_or_create_meta(func)
        _set_platform_filter(meta, list(names), source="decorator.platforms")
        return func

    return decorator


def message_types(*types: str) -> Callable[[HandlerCallable], HandlerCallable]:
    def decorator(func: HandlerCallable) -> HandlerCallable:
        meta = _get_or_create_meta(func)
        _set_message_type_filter(
            meta,
            list(types),
            source="decorator.message_types",
        )
        return func

    return decorator


def group_only() -> Callable[[HandlerCallable], HandlerCallable]:
    def decorator(func: HandlerCallable) -> HandlerCallable:
        meta = _get_or_create_meta(func)
        _set_message_type_filter(meta, ["group"], source="decorator.group_only")
        return func

    return decorator


def private_only() -> Callable[[HandlerCallable], HandlerCallable]:
    def decorator(func: HandlerCallable) -> HandlerCallable:
        meta = _get_or_create_meta(func)
        _set_message_type_filter(meta, ["private"], source="decorator.private_only")
        return func

    return decorator


def priority(value: int) -> Callable[[HandlerCallable], HandlerCallable]:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("priority(...) requires an integer")

    def decorator(func: HandlerCallable) -> HandlerCallable:
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
) -> Callable[[HandlerCallable], HandlerCallable]:
    _validate_limiter_args(
        kind="rate_limit",
        limit=limit,
        window=window,
        scope=scope,
        behavior=behavior,
    )

    def decorator(func: HandlerCallable) -> HandlerCallable:
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
) -> Callable[[HandlerCallable], HandlerCallable]:
    _validate_limiter_args(
        kind="cooldown",
        limit=1,
        window=seconds,
        scope=scope,
        behavior=behavior,
    )

    def decorator(func: HandlerCallable) -> HandlerCallable:
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
    timeout: int = 60,
    mode: ConversationMode = "replace",
    busy_message: str | None = None,
    grace_period: float = 1.0,
) -> Callable[[HandlerCallable], HandlerCallable]:
    if mode not in {"replace", "reject"}:
        raise ValueError("conversation_command mode must be 'replace' or 'reject'")
    if isinstance(timeout, bool) or int(timeout) <= 0:
        raise ValueError("conversation_command timeout must be a positive integer")
    if float(grace_period) <= 0:
        raise ValueError("conversation_command grace_period must be positive")

    command_decorator = on_command(
        command,
        aliases=aliases,
        description=description,
    )

    def decorator(func: HandlerCallable) -> HandlerCallable:
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
        name: capability 名称（不能使用保留命名空间）
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

    def decorator(func: HandlerCallable) -> HandlerCallable:
        if name.startswith(RESERVED_CAPABILITY_PREFIXES):
            raise ValueError(f"保留 capability 命名空间不能用于插件导出：{name}")
        if input_schema is not None and input_model is not None:
            raise ValueError("input_schema 和 input_model 不能同时提供")
        if output_schema is not None and output_model is not None:
            raise ValueError("output_schema 和 output_model 不能同时提供")
        descriptor = CapabilityDescriptor(
            name=name,
            description=description,
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
    def decorator(func: HandlerCallable) -> HandlerCallable:
        tool_name = str(name or func.__name__).strip()
        if not tool_name:
            raise ValueError("LLM tool name must not be empty")
        setattr(
            func,
            LLM_TOOL_META_ATTR,
            LLMToolMeta(
                spec=LLMToolSpec(
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
    def decorator(cls: type[BaseAgentRunner]) -> type[BaseAgentRunner]:
        if not inspect.isclass(cls) or not issubclass(cls, BaseAgentRunner):
            raise TypeError("@register_agent() 只接受 BaseAgentRunner 子类")
        setattr(
            cls,
            AGENT_META_ATTR,
            AgentMeta(
                spec=AgentSpec(
                    name=name,
                    description=description,
                    tool_names=list(tool_names or []),
                    runner_class=f"{cls.__module__}.{cls.__qualname__}",
                )
            ),
        )
        return cls

    return decorator
