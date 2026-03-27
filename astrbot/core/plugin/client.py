"""ABP Plugin Client for out-of-process communication"""

import asyncio
import logging
from typing import Any

from .const import (
    ABP_VERSION,
)
from .models import (
    HandleEventResult,
    InitializeParams,
    InitializeResult,
    MessageChainItem,
    PluginCapabilities,
    PluginConfig,
    PluginMetadata,
    Tool,
    ToolContent,
    ToolResult,
)
from .transport import HttpTransport, StdioTransport, Transport, UnixSocketTransport

logger = logging.getLogger("astrbot.plugin.client")


class PluginClient:
    """Client for communicating with out-of-process plugins.

    This client implements the ABP protocol for plugin communication,
    supporting JSON-RPC 2.0 over various transports.
    """

    def __init__(self, config: PluginConfig) -> None:
        self._config = config
        self._transport: Transport | None = None
        self._initialized = False
        self._capabilities = PluginCapabilities()
        self._metadata: PluginMetadata | None = None
        self._tools: list[Tool] = []

    @property
    def name(self) -> str:
        return self._config.name

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def capabilities(self) -> PluginCapabilities:
        return self._capabilities

    @property
    def metadata(self) -> PluginMetadata | None:
        return self._metadata

    @property
    def tools(self) -> list[Tool]:
        return self._tools

    async def start(
        self, process: asyncio.subprocess.Process | None = None
    ) -> InitializeResult:
        """Start and initialize the plugin.

        Args:
            process: For stdio transport, the subprocess handle

        Returns:
            InitializeResult from the plugin
        """
        # Create transport based on config
        if self._config.transport == "stdio":
            if not process:
                raise ValueError("stdio transport requires a subprocess")
            self._transport = StdioTransport(process)
        elif self._config.transport == "unix_socket":
            if not self._config.url:
                raise ValueError("unix_socket transport requires socket path in url")
            self._transport = UnixSocketTransport(self._config.url)
            await self._transport.connect()
        elif self._config.transport == "http":
            if not self._config.url:
                raise ValueError("http transport requires URL")
            self._transport = HttpTransport(self._config.url)
            await self._transport.connect()
        else:
            raise ValueError(f"Unknown transport: {self._config.transport}")

        # Send initialize request
        result = await self._send_initialize()

        # Parse result
        self._capabilities = PluginCapabilities(
            tools=result.capabilities.tools,
            handlers=result.capabilities.handlers,
            events=result.capabilities.events,
            resources=result.capabilities.resources,
        )
        self._metadata = result.metadata
        self._initialized = True

        return result

    async def _send_initialize(self) -> InitializeResult:
        """Send initialize request to plugin."""
        assert self._transport

        # Get data directories
        from pathlib import Path

        from astrbot.core.utils.astrbot_path import get_astrbot_data_path

        data_path = Path(get_astrbot_data_path())
        plugin_data_path = data_path / "plugins" / self._config.name

        params = InitializeParams(
            protocol_version=ABP_VERSION,
            client_info={"name": "astrbot", "version": "4.25.0"},
            capabilities={
                "streaming": True,
                "events": True,
            },
            plugin_config={"user_config": {}},
            data_dirs={
                "root": str(data_path),
                "plugin_data": str(plugin_data_path),
                "temp": str(data_path / "temp"),
            },
        )

        result = await self._transport.send(
            "initialize",
            {
                "protocolVersion": params.protocol_version,
                "clientInfo": params.client_info,
                "capabilities": params.capabilities,
                "pluginConfig": params.plugin_config,
                "dataDirs": params.data_dirs,
            },
        )

        return InitializeResult(
            protocol_version=result.get("protocolVersion", ABP_VERSION),
            server_info=result.get(
                "serverInfo", {"name": self._config.name, "version": "1.0.0"}
            ),
            capabilities=PluginCapabilities(
                tools=result.get("capabilities", {}).get("tools", False),
                handlers=result.get("capabilities", {}).get("handlers", False),
                events=result.get("capabilities", {}).get("events", False),
                resources=result.get("capabilities", {}).get("resources", False),
            ),
            config_schema=result.get("configSchema"),
            metadata=PluginMetadata(
                display_name=result.get("metadata", {}).get("display_name"),
                description=result.get("metadata", {}).get("description"),
                author=result.get("metadata", {}).get("author"),
                homepage=result.get("metadata", {}).get("homepage"),
                support_platforms=result.get("metadata", {}).get(
                    "support_platforms", []
                ),
                astrbot_version=result.get("metadata", {}).get("astrbot_version"),
            ),
        )

    async def list_tools(self) -> list[Tool]:
        """List available tools from plugin."""
        if not self._initialized:
            raise RuntimeError("Plugin not initialized")
        assert self._transport

        result = await self._transport.send("tools/list", {})

        self._tools = [
            Tool(
                name=t.get("name", ""),
                description=t.get("description", ""),
                input_schema=t.get("parameters", {}),
            )
            for t in result.get("tools", [])
        ]

        return self._tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        """Call a tool on the plugin."""
        if not self._initialized:
            raise RuntimeError("Plugin not initialized")
        assert self._transport

        result = await self._transport.send(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments,
            },
        )

        return ToolResult(
            content=[
                ToolContent(
                    type=c.get("type", "text"),
                    text=c.get("text"),
                    image=c.get("image"),
                    url=c.get("url"),
                )
                for c in result.get("content", [])
            ]
        )

    async def handle_event(
        self, event_type: str, event_data: dict[str, Any]
    ) -> HandleEventResult:
        """Handle an event with the plugin."""
        if not self._initialized:
            raise RuntimeError("Plugin not initialized")
        assert self._transport

        result = await self._transport.send(
            "plugin.handle_event",
            {
                "event_type": event_type,
                "event": event_data,
            },
        )

        return HandleEventResult(
            handled=result.get("handled", False),
            results=[
                MessageChainItem(type=r.get("type", "plain"), text=r.get("text"))
                for r in result.get("results", [])
            ],
            stop_propagation=result.get("stop_propagation", False),
        )

    async def notify(self, event_type: str, data: dict[str, Any]) -> None:
        """Send an event notification to the plugin."""
        if not self._initialized:
            raise RuntimeError("Plugin not initialized")
        assert self._transport

        await self._transport.notify(
            "plugin.notify",
            {
                "event_type": event_type,
                "data": data,
            },
        )

    async def stop(self) -> None:
        """Stop the plugin."""
        if self._transport:
            await self._transport.close()
            self._transport = None
            self._initialized = False

    async def reload(self) -> None:
        """Reload the plugin (re-initialize without restarting process)."""
        if self._transport:
            await self._transport.send("plugin.reload", {})
            self._initialized = False

    async def update_config(self, user_config: dict[str, Any]) -> None:
        """Update plugin configuration."""
        if not self._initialized:
            raise RuntimeError("Plugin not initialized")
        assert self._transport

        await self._transport.notify(
            "plugin.config_update",
            {"user_config": user_config},
        )

    async def subscribe(self, event_type: str) -> None:
        """Subscribe to an event type.

        Args:
            event_type: Event type to subscribe to (e.g., "llm_request", "tool_called")
        """
        if not self._initialized:
            raise RuntimeError("Plugin not initialized")
        assert self._transport

        await self._transport.send(
            "plugin.subscribe",
            {"event_type": event_type},
        )
        logger.debug(f"Plugin {self._config.name} subscribed to {event_type}")

    async def unsubscribe(self, event_type: str) -> None:
        """Unsubscribe from an event type.

        Args:
            event_type: Event type to unsubscribe from
        """
        if not self._initialized:
            raise RuntimeError("Plugin not initialized")
        assert self._transport

        await self._transport.send(
            "plugin.unsubscribe",
            {"event_type": event_type},
        )
        logger.debug(f"Plugin {self._config.name} unsubscribed from {event_type}")

    async def send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no response expected).

        Args:
            method: The JSON-RPC method name
            params: The method parameters
        """
        if not self._initialized:
            raise RuntimeError("Plugin not initialized")
        assert self._transport

        await self._transport.notify(method, params)
