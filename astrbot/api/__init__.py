import logging
import sys

from astrbot.core import html_renderer, sp
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.agent.tool_executor import BaseFunctionToolExecutor
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.star.register import register_agent as agent
from astrbot.core.star.register import register_llm_tool as llm_tool

_fallback_logger = logging.getLogger("astrbot")
_logger_cache: dict[
    str,
    tuple[str | None, str | None, logging.Logger],
] = {}

# Caller modules under these roots may belong to plugins that are not
# registered yet, so resolution failures for them are never cached.
_PLUGIN_MODULE_ROOTS = ("data.plugins.", "astrbot.builtin_stars.")


def _resolve_caller_logger(module_name: str) -> logging.Logger:
    """Resolve the dedicated plugin logger for a caller module.

    Args:
        module_name: The ``__name__`` of the module that called the logger.

    Returns:
        The plugin's dedicated logger, or the global ``astrbot`` logger when
        the caller does not belong to a registered plugin.
    """
    # Imported lazily to avoid a circular import with astrbot.core.star.
    from astrbot.core.star.star import star_map

    cached = _logger_cache.get(module_name)
    if cached is not None:
        module_path, plugin_name, cached_logger = cached
        if module_path is None:
            return cached_logger
        metadata = star_map.get(module_path)
        if metadata is not None and metadata.name == plugin_name:
            return cached_logger
        _logger_cache.pop(module_name, None)

    for module_path, metadata in star_map.items():
        if not module_path or not metadata.name:
            continue
        package = module_path.rpartition(".")[0]
        if module_name == module_path or module_name.startswith(package + "."):
            resolved = logging.getLogger(f"astrbot.plugin.{metadata.name}")
            _logger_cache[module_name] = (module_path, metadata.name, resolved)
            return resolved

    if not module_name.startswith(_PLUGIN_MODULE_ROOTS):
        _logger_cache[module_name] = (None, None, _fallback_logger)
    return _fallback_logger


class _PluginContextLogger:
    """Proxy routing ``astrbot.api.logger`` calls to the caller plugin's logger."""

    def __getattr__(self, item: str):
        module_name = sys._getframe(1).f_globals.get("__name__", "")
        return getattr(_resolve_caller_logger(module_name), item)


logger = _PluginContextLogger()
"""Plugin-facing logger. Calls are routed to the calling plugin's dedicated
logger (``astrbot.plugin.<plugin_name>``) so each plugin's log level can be
tuned independently; non-plugin callers fall back to the global logger."""

__all__ = [
    "AstrBotConfig",
    "BaseFunctionToolExecutor",
    "FunctionTool",
    "ToolSet",
    "agent",
    "html_renderer",
    "llm_tool",
    "logger",
    "sp",
]
