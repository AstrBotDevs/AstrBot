"""跨任务传播插件调用者身份。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

_CALLER_PLUGIN_ID: ContextVar[str | None] = ContextVar(
    "astrbot_sdk_caller_plugin_id",
    default=None,
)


def current_caller_plugin_id() -> str | None:
    return _CALLER_PLUGIN_ID.get()


def bind_caller_plugin_id(plugin_id: str | None) -> Token[str | None]:
    normalized = plugin_id.strip() if isinstance(plugin_id, str) else ""
    return _CALLER_PLUGIN_ID.set(normalized or None)


def reset_caller_plugin_id(token: Token[str | None]) -> None:
    _CALLER_PLUGIN_ID.reset(token)


@contextmanager
def caller_plugin_scope(plugin_id: str | None) -> Iterator[None]:
    token = bind_caller_plugin_id(plugin_id)
    try:
        yield
    finally:
        reset_caller_plugin_id(token)
