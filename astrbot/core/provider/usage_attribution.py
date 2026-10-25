"""Attribute async work without retaining a ContextVar across a consumer yield."""

from collections.abc import AsyncIterator
from functools import partial
from typing import Any

from astrbot.core.provider.usage_recorder import event_usage_scope


def plugin_for_handler(handler: Any) -> str | None:
    """Return the registered plugin name for a callback, when known."""
    from astrbot.core.star.star import star_map

    while isinstance(handler, partial):
        handler = handler.func
    metadata = star_map.get(getattr(handler, "__module__", ""))
    if metadata is None:
        owner = getattr(handler, "__self__", None)
        metadata = star_map.get(getattr(type(owner), "__module__", ""))
    return metadata.name if metadata is not None else None


async def iter_with_usage(
    iterator: AsyncIterator[Any],
    *,
    event: Any,
    plugin_id: str | None = None,
    origin_type: str = "chat",
    conversation_id: str | None = None,
) -> AsyncIterator[Any]:
    """Run each generator advance in its own attribution scope.

    Args:
        iterator: Owned asynchronous iterator, closed when consumption stops.
        event: Message event associated with the work.
        plugin_id: Registered caller plugin, if available.
        origin_type: Category of the caller.
        conversation_id: Associated conversation, if available.

    Yields:
        Original values with the caller's ContextVars restored.
    """
    try:
        while True:
            with event_usage_scope(
                event,
                plugin_id=plugin_id,
                origin_type=origin_type,
                conversation_id=conversation_id,
            ):
                try:
                    value = await anext(iterator)
                except StopAsyncIteration:
                    break
            yield value
    finally:
        close = getattr(iterator, "aclose", None)
        if close is not None:
            with event_usage_scope(
                event,
                plugin_id=plugin_id,
                origin_type=origin_type,
                conversation_id=conversation_id,
            ):
                await close()
