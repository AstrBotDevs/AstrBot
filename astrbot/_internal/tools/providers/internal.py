"""Internal tools provider for AstrBot.

This provider wraps the logic for loading built-in internal tools from
the provider modules: cron_tools, kb_query, and send_message.
"""

from typing import TYPE_CHECKING

from astrbot import logger
from astrbot._internal.tools.base import FunctionTool

if TYPE_CHECKING:
    pass


# Provider modules that supply internal tools
_INTERNAL_PROVIDER_MODULES: list[str] = [
    "astrbot.core.tools.cron_tools",
    "astrbot.core.tools.kb_query",
    "astrbot.core.tools.send_message",
]


class InternalToolProvider:
    """Provider for AstrBot built-in internal tools.

    This class wraps the logic previously found in
    ``FunctionToolManager._INTERNAL_TOOL_PROVIDERS`` and provides
    a unified interface for loading tools from the internal provider
    modules.

    Each provider module is expected to expose a ``get_all_tools()``
    function that returns a list of ``FunctionTool`` instances.

    Tools are marked with ``source='internal'`` so the WebUI can
    distinguish them from plugin and MCP tools.
    """

    @staticmethod
    def get_all_tools() -> list[FunctionTool]:
        """Return all internal tools from all provider modules.

        Iterates through the provider modules and collects tools
        from each module's ``get_all_tools()`` function.

        Returns:
            list[FunctionTool]: A list of all internal FunctionTool instances.
        """
        all_tools: list[FunctionTool] = []
        existing_names: set[str] = set()

        for module_path in _INTERNAL_PROVIDER_MODULES:
            try:
                import importlib

                mod = importlib.import_module(module_path)
                provider_tools = mod.get_all_tools()
            except Exception as e:
                logger.warning(
                    "Failed to load internal tool provider %s: %s",
                    module_path,
                    e,
                )
                continue

            for tool in provider_tools:
                tool.source = "internal"
                if tool.name not in existing_names:
                    all_tools.append(tool)
                    existing_names.add(tool.name)
                    logger.debug("Loaded internal tool: %s", tool.name)

        return all_tools
