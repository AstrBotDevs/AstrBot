"""v4 原生装饰器。

旧版 ``astrbot_sdk.api.event.filter`` 的兼容与降级边界由 compat 模块处理，
这里仅保留 v4 原生 trigger/permission 元数据建模。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .protocol.descriptors import (
    CommandTrigger,
    EventTrigger,
    MessageTrigger,
    Permissions,
    ScheduleTrigger,
)

HandlerCallable = Callable[..., Any]
HANDLER_META_ATTR = "__astrbot_handler_meta__"


@dataclass(slots=True)
class HandlerMeta:
    trigger: CommandTrigger | MessageTrigger | EventTrigger | ScheduleTrigger | None = (
        None
    )
    priority: int = 0
    permissions: Permissions = field(default_factory=Permissions)


def _get_or_create_meta(func: HandlerCallable) -> HandlerMeta:
    meta = getattr(func, HANDLER_META_ATTR, None)
    if meta is None:
        meta = HandlerMeta()
        setattr(func, HANDLER_META_ATTR, meta)
    return meta


def get_handler_meta(func: HandlerCallable) -> HandlerMeta | None:
    return getattr(func, HANDLER_META_ATTR, None)


def on_command(
    command: str,
    *,
    aliases: list[str] | None = None,
    description: str | None = None,
) -> Callable[[HandlerCallable], HandlerCallable]:
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
    def decorator(func: HandlerCallable) -> HandlerCallable:
        meta = _get_or_create_meta(func)
        meta.trigger = ScheduleTrigger(cron=cron, interval_seconds=interval_seconds)
        return func

    return decorator


def require_admin(func: HandlerCallable) -> HandlerCallable:
    meta = _get_or_create_meta(func)
    meta.permissions.require_admin = True
    return func
