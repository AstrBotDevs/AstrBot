"""Star package - Plugin system for AstrBot.

This module uses lazy imports to avoid circular dependencies.
Use TYPE_CHECKING for type hints and direct submodule imports at runtime.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

# Core data structures - safe to import at module level
from .star import StarMetadata, star_map, star_registry

if TYPE_CHECKING:
    # Type-only imports to avoid circular dependencies
    from astrbot.core.provider import Provider

    from .base import Star
    from .context import Context
    from .star_manager import PluginManager
    from .star_tools import StarTools


# Lazy-loaded cached module references
_import_cache: dict[str, object] = {}


def __getattr__(name: str) -> object:
    """Lazy load heavy dependencies to avoid circular imports."""
    if name in _import_cache:
        return _import_cache[name]

    if name == "Star":
        from .base import Star as _Star

        _import_cache[name] = _Star
        return _Star
    elif name == "Context":
        from .context import Context as _Context

        _import_cache[name] = _Context
        return _Context
    elif name == "PluginManager":
        from .star_manager import PluginManager as _PluginManager

        _import_cache[name] = _PluginManager
        return _PluginManager
    elif name == "StarTools":
        from .star_tools import StarTools as _StarTools

        _import_cache[name] = _StarTools
        return _StarTools
    elif name == "Provider":
        from astrbot.core.provider import Provider as _Provider

        _import_cache[name] = _Provider
        return _Provider

    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}. "
        f"Available: {', '.join(__all__)}"
    )


def __dir__() -> list[str]:
    """Support IDE autocompletion by listing all available attributes."""
    return list(globals().keys()) + list(__all__)


__all__ = [
    "Context",
    "PluginManager",
    "Provider",
    "Star",
    "StarMetadata",
    "StarTools",
    "star_map",
    "star_registry",
]
