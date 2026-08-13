import logging
import sys
from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from astrbot.core.agent.tool import FunctionTool, ToolSet
    from astrbot.core.agent.tool_executor import BaseFunctionToolExecutor
    from astrbot.core.auth import AuthContext, Decision, Resource, Role, Subject
    from astrbot.core.config.astrbot_config import AstrBotConfig
    from astrbot.core.star.register import register_agent as agent
    from astrbot.core.star.register import register_llm_tool as llm_tool

_EXPORTS = {
    "AuthContext": ("astrbot.core.auth", "AuthContext"),
    "Decision": ("astrbot.core.auth", "Decision"),
    "Resource": ("astrbot.core.auth", "Resource"),
    "Role": ("astrbot.core.auth", "Role"),
    "Subject": ("astrbot.core.auth", "Subject"),
    "FunctionTool": ("astrbot.core.agent.tool", "FunctionTool"),
    "ToolSet": ("astrbot.core.agent.tool", "ToolSet"),
    "BaseFunctionToolExecutor": (
        "astrbot.core.agent.tool_executor",
        "BaseFunctionToolExecutor",
    ),
    "AstrBotConfig": ("astrbot.core.config.astrbot_config", "AstrBotConfig"),
    "agent": ("astrbot.core.star.register", "register_agent"),
    "llm_tool": ("astrbot.core.star.register", "register_llm_tool"),
}


def __getattr__(name: str):
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module = import_module(target[0])
    value = getattr(module, target[1])
    globals()[name] = value
    return value


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
    "AuthContext",
    "BaseFunctionToolExecutor",
    "FunctionTool",
    "Decision",
    "Resource",
    "Role",
    "Subject",
    "ToolSet",
    "agent",
    "llm_tool",
    "logger",
]
