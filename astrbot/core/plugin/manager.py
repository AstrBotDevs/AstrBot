"""ABP Plugin Manager

Manages plugin lifecycle, loading, and communication.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

from .client import PluginClient
from .const import LOAD_MODE_IN_PROCESS, LOAD_MODE_OUT_OF_PROCESS
from .models import PluginCapabilities, PluginConfig, PluginInfo, Tool

logger = logging.getLogger("astrbot.plugin.manager")


class PluginManager:
    """Manages ABP plugins.

    Responsible for:
    - Plugin discovery and registration
    - Plugin lifecycle (load, start, stop, reload)
    - Tool routing across plugins
    - Event distribution
    """

    def __init__(self) -> None:
        self._plugins: dict[str, PluginClient] = {}
        self._in_process_handlers: dict[str, Any] = {}
        self._event_subscribers: dict[str, list[str]] = {}
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    async def initialize(
        self,
        plugin_configs: list[PluginConfig],
        data_root: Path,
    ) -> None:
        """Initialize the plugin manager and load plugins.

        Args:
            plugin_configs: List of plugin configurations
            data_root: Root data directory for AstrBot
        """
        logger.info(f"Initializing plugin manager with {len(plugin_configs)} plugins")

        # Load each plugin
        for config in plugin_configs:
            await self.load_plugin(config, data_root)

        self._initialized = True
        logger.info(f"Plugin manager initialized with {len(self._plugins)} plugins")

    async def load_plugin(self, config: PluginConfig, data_root: Path) -> None:
        """Load a plugin.

        Args:
            config: Plugin configuration
            data_root: Root data directory
        """
        logger.info(f"Loading plugin: {config.name} (mode: {config.load_mode})")

        if config.load_mode == LOAD_MODE_IN_PROCESS:
            await self._load_in_process_plugin(config, data_root)
        elif config.load_mode == LOAD_MODE_OUT_OF_PROCESS:
            await self._load_out_of_process_plugin(config, data_root)
        else:
            raise ValueError(f"Unknown load mode: {config.load_mode}")

    async def _load_in_process_plugin(
        self, config: PluginConfig, data_root: Path
    ) -> None:
        """Load an in-process plugin (Python module).

        For in-process plugins, we would import the module directly.
        This is a placeholder for when the Rust FFI exposes plugin loading.
        """
        logger.debug(f"Loading in-process plugin: {config.name}")
        # In-process plugins would be loaded via Python import
        # For now, just register a placeholder
        self._in_process_handlers[config.name] = {
            "config": config,
            "capabilities": PluginCapabilities(),
            "metadata": None,
            "tools": [],
        }

    async def _load_out_of_process_plugin(
        self, config: PluginConfig, data_root: Path
    ) -> None:
        """Load an out-of-process plugin (subprocess).

        Args:
            config: Plugin configuration
            data_root: Root data directory
        """
        if not config.command:
            raise ValueError(f"Out-of-process plugin {config.name} requires 'command'")

        # Spawn subprocess
        cmd = config.command
        args = [cmd, *config.args]

        logger.debug(f"Spawning plugin process: {' '.join(args)}")

        process = await asyncio.create_subprocess_exec(
            *args,
            env={**asyncio.get_running_loop().run_in_executor, **config.env}
            if config.env
            else None,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Create client and start plugin
        client = PluginClient(config)
        await client.start(process=process)

        self._plugins[config.name] = client
        logger.info(f"Loaded out-of-process plugin: {config.name}")

    async def unload_plugin(self, name: str) -> None:
        """Unload a plugin.

        Args:
            name: Plugin name
        """
        if name in self._plugins:
            await self._plugins[name].stop()
            del self._plugins[name]
            logger.info(f"Unloaded plugin: {name}")

        if name in self._in_process_handlers:
            del self._in_process_handlers[name]
            logger.info(f"Unloaded in-process plugin: {name}")

    async def start_plugin(self, name: str) -> None:
        """Start a plugin (already loaded)."""
        if name not in self._plugins:
            raise KeyError(f"Plugin not found: {name}")
        # Plugin is already started if it's in the registry
        pass

    async def stop_plugin(self, name: str) -> None:
        """Stop a plugin."""
        await self.unload_plugin(name)

    async def reload_plugin(self, name: str) -> None:
        """Reload a plugin."""
        if name not in self._plugins:
            raise KeyError(f"Plugin not found: {name}")
        await self._plugins[name].reload()
        logger.info(f"Reloaded plugin: {name}")

    async def update_plugin_config(
        self, name: str, user_config: dict[str, Any]
    ) -> None:
        """Update plugin configuration.

        Args:
            name: Plugin name
            user_config: New user configuration
        """
        if name in self._plugins:
            await self._plugins[name].update_config(user_config)
        elif name in self._in_process_handlers:
            # In-process plugins handle config differently
            pass
        else:
            raise KeyError(f"Plugin not found: {name}")

    def list_plugins(self) -> list[PluginInfo]:
        """List all loaded plugins.

        Returns:
            List of PluginInfo for each loaded plugin
        """
        result: list[PluginInfo] = []

        for name, client in self._plugins.items():
            result.append(
                PluginInfo(
                    name=client.name,
                    version="1.0.0",
                    load_mode=client._config.load_mode,
                    capabilities=client.capabilities,
                    metadata=client.metadata,
                    tools_count=len(client.tools),
                )
            )

        for name, handler in self._in_process_handlers.items():
            result.append(
                PluginInfo(
                    name=name,
                    version=handler["config"].version,
                    load_mode=LOAD_MODE_IN_PROCESS,
                    capabilities=handler["capabilities"],
                    metadata=handler["metadata"],
                    tools_count=len(handler["tools"]),
                )
            )

        return result

    def get_plugin(self, name: str) -> PluginInfo | None:
        """Get info for a specific plugin.

        Args:
            name: Plugin name

        Returns:
            PluginInfo or None if not found
        """
        for info in self.list_plugins():
            if info.name == name:
                return info
        return None

    def get_all_tools(self) -> list[tuple[str, Tool]]:
        """Get all tools from all plugins.

        Returns:
            List of (plugin_name, Tool) tuples
        """
        tools: list[tuple[str, Tool]] = []

        for name, client in self._plugins.items():
            for tool in client.tools:
                tools.append((name, tool))

        for name, handler in self._in_process_handlers.items():
            for tool in handler["tools"]:
                tools.append((name, tool))

        return tools

    async def call_tool(
        self, plugin_name: str, tool_name: str, arguments: dict[str, Any]
    ) -> Any:
        """Call a tool on a specific plugin.

        Args:
            plugin_name: Plugin name
            tool_name: Tool name
            arguments: Tool arguments

        Returns:
            Tool result
        """
        if plugin_name in self._plugins:
            result = await self._plugins[plugin_name].call_tool(tool_name, arguments)
            return result
        elif plugin_name in self._in_process_handlers:
            # In-process tool calling would go through Python directly
            raise NotImplementedError("In-process tool calling not implemented")
        else:
            raise KeyError(f"Plugin not found: {plugin_name}")

    async def route_tool_call(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> tuple[str, Any]:
        """Route a tool call to the appropriate plugin.

        Args:
            tool_name: Tool name
            arguments: Tool arguments

        Returns:
            Tuple of (plugin_name, tool_result)
        """
        for name, client in self._plugins.items():
            if any(t.name == tool_name for t in client.tools):
                result = await client.call_tool(tool_name, arguments)
                return (name, result)

        for name, handler in self._in_process_handlers.items():
            if any(t.name == tool_name for t in handler["tools"]):
                # In-process tool calling
                raise NotImplementedError("In-process tool calling not implemented")

        raise KeyError(f"Tool not found: {tool_name}")

    async def subscribe_event(self, plugin_name: str, event_type: str) -> None:
        """Subscribe a plugin to an event type.

        Args:
            plugin_name: Plugin name
            event_type: Event type to subscribe to
        """
        if plugin_name not in self._plugins:
            raise KeyError(f"Plugin not found: {plugin_name}")

        if event_type not in self._event_subscribers:
            self._event_subscribers[event_type] = []
        if plugin_name not in self._event_subscribers[event_type]:
            self._event_subscribers[event_type].append(plugin_name)
            await self._plugins[plugin_name]._transport.send(
                "plugin.subscribe", {"event_type": event_type}
            )
            logger.info(f"Plugin {plugin_name} subscribed to {event_type}")

    async def unsubscribe_event(self, plugin_name: str, event_type: str) -> None:
        """Unsubscribe a plugin from an event type.

        Args:
            plugin_name: Plugin name
            event_type: Event type to unsubscribe from
        """
        if plugin_name not in self._plugins:
            raise KeyError(f"Plugin not found: {plugin_name}")

        if event_type in self._event_subscribers:
            if plugin_name in self._event_subscribers[event_type]:
                self._event_subscribers[event_type].remove(plugin_name)
                await self._plugins[plugin_name]._transport.send(
                    "plugin.unsubscribe", {"event_type": event_type}
                )
                logger.info(f"Plugin {plugin_name} unsubscribed from {event_type}")

    async def broadcast_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Broadcast an event to all subscribed plugins.

        Args:
            event_type: Event type
            data: Event data
        """
        if event_type in self._event_subscribers:
            for plugin_name in self._event_subscribers[event_type]:
                await self._plugins[plugin_name].notify(event_type, data)

    async def shutdown(self) -> None:
        """Shutdown the plugin manager and all plugins."""
        logger.info("Shutting down plugin manager")
        for name in list(self._plugins.keys()):
            await self.unload_plugin(name)
        self._in_process_handlers.clear()
        self._event_subscribers.clear()
        self._initialized = False
