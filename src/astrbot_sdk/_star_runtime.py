from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .context import Context
    from .star import Star


_CURRENT_STAR_CONTEXT: ContextVar[Context | None] = ContextVar(
    "astrbot_sdk_current_star_context",
    default=None,
)
_CURRENT_STAR_INSTANCE: ContextVar[Star | None] = ContextVar(
    "astrbot_sdk_current_star_instance",
    default=None,
)


def current_star_context() -> Context | None:
    return _CURRENT_STAR_CONTEXT.get()


def current_runtime_context() -> Context | None:
    return _CURRENT_STAR_CONTEXT.get()


def current_star_instance() -> Star | None:
    return _CURRENT_STAR_INSTANCE.get()


@contextmanager
def bind_star_runtime(star: Star | None, ctx: Context | None) -> Iterator[None]:
    context_token = _CURRENT_STAR_CONTEXT.set(ctx)
    star_token = _CURRENT_STAR_INSTANCE.set(star)
    instance_token = star._bind_runtime_context(ctx) if star is not None else None
    try:
        yield
    finally:
        if star is not None and instance_token is not None:
            star._reset_runtime_context(instance_token)
        _CURRENT_STAR_INSTANCE.reset(star_token)
        _CURRENT_STAR_CONTEXT.reset(context_token)
