"""事件过滤器模块。

提供事件处理器的注册装饰器，用于声明式地定义事件触发条件。
此模块是旧版 filter API 的兼容层。

使用方式：
    # 方式一：直接使用函数
    @command("hello")
    async def handle_hello(ctx):
        ...

    # 方式二：使用 filter 命名空间（旧版风格）
    @filter.command("hello")
    async def handle_hello(ctx):
        ...

新版建议直接使用 astrbot_sdk.decorators 模块中的装饰器。
"""

from __future__ import annotations

from ...decorators import on_command, on_message, require_admin

# 管理员权限级别常量
ADMIN = "admin"


def command(name: str):
    """注册命令处理器装饰器。

    Args:
        name: 命令名称，用户发送以此开头的消息时触发

    Returns:
        装饰器函数

    示例:
        @command("hello")
        async def handle_hello(ctx):
            await ctx.reply("Hello!")
    """
    return on_command(name)


def regex(pattern: str):
    """注册正则匹配处理器装饰器。

    Args:
        pattern: 正则表达式模式，匹配的消息将触发处理器

    Returns:
        装饰器函数

    示例:
        @regex(r"hello\\s+(\\w+)")
        async def handle_hello(ctx, match):
            name = match.group(1)
            await ctx.reply(f"Hello, {name}!")
    """
    return on_message(regex=pattern)


def permission(level):
    """权限检查装饰器。

    Args:
        level: 权限级别，目前仅支持 ADMIN

    Returns:
        装饰器函数，仅当用户具有指定权限时才执行处理器

    示例:
        @command("admin_cmd")
        @permission(ADMIN)
        async def admin_only(ctx):
            await ctx.reply("管理员命令已执行")
    """
    if level == ADMIN:
        return require_admin

    def decorator(func):
        return func

    return decorator


class _FilterNamespace:
    """过滤器命名空间，提供旧版风格的方法调用。

    用于支持 filter.command()、filter.regex() 等调用方式，
    保持与旧版 API 的兼容性。

    示例:
        @filter.command("hello")
        async def handle_hello(ctx):
            ...
    """

    command = staticmethod(command)
    regex = staticmethod(regex)
    permission = staticmethod(permission)


# 过滤器命名空间实例，支持 filter.command() 等调用方式
filter = _FilterNamespace()

__all__ = ["ADMIN", "command", "regex", "permission", "filter"]
