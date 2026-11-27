"""Plugin identity propagated through host callbacks and their child tasks."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

current_plugin_id: ContextVar[str | None] = ContextVar(
    "current_plugin_id", default=None
)


def plugin_id_for_callback(callback: Any, module_path: str | None = None) -> str | None:
    """Resolve ownership for a registered callback or tool method.

    Args:
        callback: Registered callable.
        module_path: Module recorded by the tool registry, when available.

    Returns:
        The owning plugin ID if the callback belongs to a loaded plugin.
    """
    from astrbot.core.star.star import star_map

    callback = getattr(callback, "func", callback)
    owner_id = getattr(getattr(callback, "__self__", None), "plugin_id", None)
    if isinstance(owner_id, str):
        return owner_id
    module = module_path or getattr(callback, "__module__", "")
    if plugin := star_map.get(module):
        return plugin.plugin_id
    if module.startswith(("data.plugins.", "astrbot.builtin_stars.")):
        package = ".".join(module.split(".")[:3]) + "."
        for main, plugin in star_map.items():
            if main.startswith(package):
                return plugin.plugin_id
    return None


@contextmanager
def plugin_scope(plugin_id: str | None) -> Iterator[None]:
    """Bind a plugin identity for the duration of one callback.

    Args:
        plugin_id: Registered plugin ID, or None to inherit the current identity.

    Yields:
        Control while the plugin identity is active.
    """
    if plugin_id is None:
        yield
        return
    token = current_plugin_id.set(plugin_id)
    try:
        yield
    finally:
        current_plugin_id.reset(token)
