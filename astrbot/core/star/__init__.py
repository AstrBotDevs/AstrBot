from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

from .star import StarMetadata, star_map, star_registry

if TYPE_CHECKING:
    from astrbot.core.provider import Provider

    from .base import Star
    from .context import Context
    from .star_manager import PluginManager
    from .star_tools import StarTools
else:
    Provider: Any
    Star: Any
    Context: Any
    PluginManager: Any
    StarTools: Any

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


def __getattr__(name: str) -> Any:
    if name == "Provider":
        return import_module("astrbot.core.provider").Provider
    if name == "Star":
        return import_module(".base", __name__).Star
    if name == "Context":
        return import_module(".context", __name__).Context
    if name == "PluginManager":
        return import_module(".star_manager", __name__).PluginManager
    if name == "StarTools":
        return import_module(".star_tools", __name__).StarTools
    raise AttributeError(name)
