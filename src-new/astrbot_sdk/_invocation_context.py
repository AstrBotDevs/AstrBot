"""插件调用者身份上下文管理。

本模块使用 contextvars 实现跨异步任务传播插件身份，
用于在 capability 调用时自动识别调用者插件。

典型场景：
    - http.register_api: 记录哪个插件注册了 API
    - metadata.get_plugin_config: 只允许查询当前插件自己的配置
    - 能力路由层权限校验

使用方式：
    with caller_plugin_scope("my_plugin"):
        # 在此作用域内，current_caller_plugin_id() 返回 "my_plugin"
        await ctx.http.register_api(...)

注意：
    contextvars 会自动传播到子任务（asyncio.create_task），
    无需手动传递。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

# 存储当前调用者插件 ID 的上下文变量
_CALLER_PLUGIN_ID: ContextVar[str | None] = ContextVar(
    "astrbot_sdk_caller_plugin_id",
    default=None,
)


def current_caller_plugin_id() -> str | None:
    """获取当前上下文中的调用者插件 ID。

    Returns:
        当前插件 ID，如果不在插件调用上下文中则返回 None
    """
    return _CALLER_PLUGIN_ID.get()


def bind_caller_plugin_id(plugin_id: str | None) -> Token[str | None]:
    """绑定调用者插件 ID 到当前上下文。

    Args:
        plugin_id: 插件 ID，空字符串会被视为 None

    Returns:
        用于后续 reset 的 Token

    Note:
        通常使用 caller_plugin_scope 上下文管理器而非直接调用此函数
    """
    normalized = plugin_id.strip() if isinstance(plugin_id, str) else ""
    return _CALLER_PLUGIN_ID.set(normalized or None)


def reset_caller_plugin_id(token: Token[str | None]) -> None:
    """重置调用者插件 ID 到之前的状态。

    Args:
        token: bind_caller_plugin_id 返回的 Token
    """
    _CALLER_PLUGIN_ID.reset(token)


@contextmanager
def caller_plugin_scope(plugin_id: str | None) -> Iterator[None]:
    """创建一个绑定插件身份的上下文作用域。

    Args:
        plugin_id: 要绑定的插件 ID

    Yields:
        None

    示例:
        with caller_plugin_scope("my_plugin"):
            await some_capability_call()
    """
    token = bind_caller_plugin_id(plugin_id)
    try:
        yield
    finally:
        reset_caller_plugin_id(token)
