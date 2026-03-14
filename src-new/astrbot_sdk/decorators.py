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

from dataclasses import dataclass, field
from typing import Any, Callable, cast

from pydantic import BaseModel

from .protocol.descriptors import (
    CapabilityDescriptor,
    CommandTrigger,
    EventTrigger,
    MessageTrigger,
    Permissions,
    RESERVED_CAPABILITY_PREFIXES,
    ScheduleTrigger,
)

HandlerCallable = Callable[..., Any]
HANDLER_META_ATTR = "__astrbot_handler_meta__"
CAPABILITY_META_ATTR = "__astrbot_capability_meta__"


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


@dataclass(slots=True)
class CapabilityMeta:
    """Capability 元数据。

    存储在方法上的 __astrbot_capability_meta__ 属性中。

    Attributes:
        descriptor: 能力描述符
    """

    descriptor: CapabilityDescriptor


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
    command: str,
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

    def decorator(func: HandlerCallable) -> HandlerCallable:
        meta = _get_or_create_meta(func)
        meta.trigger = CommandTrigger(
            command=command,
            aliases=aliases or [],
            description=description,
        )
        return func

    return decorator


def on_message(
    *,
    regex: str | None = None,
    keywords: list[str] | None = None,
    platforms: list[str] | None = None,
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
        )
        return func

    return decorator


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
