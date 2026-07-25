import logging
import sys

from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.agent.tool_executor import BaseFunctionToolExecutor
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.star.register import register_agent as agent
from astrbot.core.star.register import register_llm_tool as llm_tool

_fallback_logger = logging.getLogger("astrbot")
_PLUGIN_LOGGER_NAME_ATTR = "__astrbot_plugin_logger_name__"


def _resolve_caller_logger(module_name: str) -> logging.Logger:
    """Resolve a plugin logger from a module marked by its live catalog."""
    module = sys.modules.get(module_name)
    plugin_name = getattr(module, _PLUGIN_LOGGER_NAME_ATTR, None)
    if isinstance(plugin_name, str) and plugin_name:
        from astrbot.core.log import LogManager

        return LogManager.get_plugin_logger(plugin_name)
    return _fallback_logger


class _PluginContextLogger:
    """Route plugin SDK logging through the caller module's catalog marker."""

    def __getattr__(self, item: str):
        module_name = sys._getframe(1).f_globals.get("__name__", "")
        return getattr(_resolve_caller_logger(module_name), item)


logger = _PluginContextLogger()
"""Plugin-facing logger resolved from the live PluginCatalog module marker."""

__all__ = [
    "AstrBotConfig",
    "BaseFunctionToolExecutor",
    "FunctionTool",
    "ToolSet",
    "agent",
    "llm_tool",
    "logger",
]
