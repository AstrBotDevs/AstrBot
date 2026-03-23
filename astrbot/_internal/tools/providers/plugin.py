"""Plugin tools provider for AstrBot.

This provider handles loading tools from star plugins. Plugin tools
are discovered through the star plugin system and made available
through the unified provider interface.
"""

from astrbot._internal.tools.base import FunctionTool


class PluginToolProvider:
    """Provider for tools from star plugins.

    This class handles loading tools that are registered by star plugins.
    Plugin tools are discovered through the plugin system and integrated
    into the tool registry.

    Note: Plugin tools are typically registered dynamically through the
    plugin context (``Context.register_llm_tool()``) and are managed
    by the ``FunctionToolManager`` in the provider module.

    This provider class serves as an integration point for the plugin
    tool system with the unified internal tools architecture.
    """

    @staticmethod
    def get_all_tools() -> list[FunctionTool]:
        """Return all plugin-registered tools.

        This method retrieves tools that have been registered by plugins
        through the ``FunctionToolManager``. It accesses the global
        ``llm_tools`` instance from ``astrbot.core.provider.register``.

        Returns:
            list[FunctionTool]: A list of all plugin FunctionTool instances.
        """
        from astrbot.core.provider.register import llm_tools
        from astrbot.core.star.star import star_map

        # Get all tools from the FunctionToolManager that are from plugins
        plugin_tools: list[FunctionTool] = []
        existing_names: set[str] = set()

        for tool in llm_tools.func_list:
            # Only include tools that are marked as 'plugin' source
            # and belong to an activated plugin
            if tool.source == "plugin":
                if tool.name not in existing_names:
                    if tool.handler_module_path:
                        star_meta = star_map.get(tool.handler_module_path)
                        if star_meta and star_meta.activated:
                            plugin_tools.append(tool)
                            existing_names.add(tool.name)
                    else:
                        # Tools without handler_module_path are treated as plugin tools
                        plugin_tools.append(tool)
                        existing_names.add(tool.name)

        return plugin_tools

    @staticmethod
    def get_tool(name: str) -> FunctionTool | None:
        """Get a specific plugin tool by name.

        Args:
            name: The name of the tool to retrieve.

        Returns:
            FunctionTool | None: The tool if found, None otherwise.
        """
        from astrbot.core.provider.register import llm_tools

        return llm_tools.get_func(name)
