from __future__ import annotations

from typing import Any

from astrbot_sdk.errors import AstrBotError

from ._host import CapabilityMixinHost


class MCPCapabilityMixin(CapabilityMixinHost):
    @staticmethod
    def _mcp_timeout(payload: dict[str, Any], capability_name: str) -> float:
        raw_timeout = payload.get("timeout", 30.0)
        try:
            timeout = float(raw_timeout)
        except (TypeError, ValueError) as exc:
            raise AstrBotError.invalid_input(
                f"{capability_name} requires numeric timeout"
            ) from exc
        if timeout <= 0:
            raise AstrBotError.invalid_input(f"{capability_name} requires timeout > 0")
        return timeout

    @staticmethod
    def _mcp_name(payload: dict[str, Any], capability_name: str) -> str:
        name = str(payload.get("name", "")).strip()
        if not name:
            raise AstrBotError.invalid_input(f"{capability_name} requires name")
        return name

    @staticmethod
    def _mcp_config(payload: dict[str, Any], capability_name: str) -> dict[str, Any]:
        config = payload.get("config")
        if not isinstance(config, dict):
            raise AstrBotError.invalid_input(
                f"{capability_name} requires config object"
            )
        return dict(config)

    async def _mcp_local_get(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        name = self._mcp_name(payload, "mcp.local.get")
        return {"server": self._plugin_bridge.get_local_mcp_server(plugin_id, name)}

    async def _mcp_local_list(
        self,
        request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        return {"servers": self._plugin_bridge.list_local_mcp_servers(plugin_id)}

    async def _mcp_local_enable(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        name = self._mcp_name(payload, "mcp.local.enable")
        timeout = self._mcp_timeout(payload, "mcp.local.enable")
        return {
            "server": await self._plugin_bridge.enable_local_mcp_server(
                plugin_id,
                name,
                timeout=timeout,
            )
        }

    async def _mcp_local_disable(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        name = self._mcp_name(payload, "mcp.local.disable")
        return {
            "server": await self._plugin_bridge.disable_local_mcp_server(
                plugin_id,
                name,
            )
        }

    async def _mcp_local_wait_until_ready(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        name = self._mcp_name(payload, "mcp.local.wait_until_ready")
        timeout = self._mcp_timeout(payload, "mcp.local.wait_until_ready")
        return {
            "server": await self._plugin_bridge.wait_for_local_mcp_server(
                plugin_id,
                name,
                timeout=timeout,
            )
        }

    async def _mcp_session_open(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        name = self._mcp_name(payload, "mcp.session.open")
        config = self._mcp_config(payload, "mcp.session.open")
        timeout = self._mcp_timeout(payload, "mcp.session.open")
        session_id, tools = await self._plugin_bridge.open_temporary_mcp_session(
            plugin_id,
            name=name,
            config=config,
            timeout=timeout,
        )
        return {"session_id": session_id, "tools": tools}

    async def _mcp_session_list_tools(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        session_id = str(payload.get("session_id", "")).strip()
        return {
            "tools": self._plugin_bridge.get_temporary_mcp_session_tools(
                plugin_id,
                session_id,
            )
        }

    async def _mcp_session_call_tool(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        session_id = str(payload.get("session_id", "")).strip()
        tool_name = str(payload.get("tool_name", "")).strip()
        if not tool_name:
            raise AstrBotError.invalid_input("mcp.session.call_tool requires tool_name")
        args = payload.get("args")
        if not isinstance(args, dict):
            raise AstrBotError.invalid_input(
                "mcp.session.call_tool requires args object"
            )
        result = await self._plugin_bridge.call_temporary_mcp_tool(
            plugin_id,
            session_id=session_id,
            tool_name=tool_name,
            arguments=dict(args),
        )
        return {"result": result}

    async def _mcp_session_close(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        session_id = str(payload.get("session_id", "")).strip()
        await self._plugin_bridge.close_temporary_mcp_session(plugin_id, session_id)
        return {}

    async def _internal_mcp_local_execute(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = str(payload.get("plugin_id", "")).strip()
        server_name = str(payload.get("server_name", "")).strip()
        tool_name = str(payload.get("tool_name", "")).strip()
        tool_args = payload.get("tool_args")
        if not plugin_id or not server_name or not tool_name:
            raise AstrBotError.invalid_input(
                "internal.mcp.local.execute requires plugin_id, server_name, and tool_name"
            )
        if not isinstance(tool_args, dict):
            raise AstrBotError.invalid_input(
                "internal.mcp.local.execute requires tool_args object"
            )
        return await self._plugin_bridge.execute_local_mcp_tool(
            plugin_id,
            server_name=server_name,
            tool_name=tool_name,
            tool_args=dict(tool_args),
        )

    def _register_mcp_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("mcp.local.get", "Get local MCP server"),
            call_handler=self._mcp_local_get,
        )
        self.register(
            self._builtin_descriptor("mcp.local.list", "List local MCP servers"),
            call_handler=self._mcp_local_list,
        )
        self.register(
            self._builtin_descriptor("mcp.local.enable", "Enable local MCP server"),
            call_handler=self._mcp_local_enable,
        )
        self.register(
            self._builtin_descriptor("mcp.local.disable", "Disable local MCP server"),
            call_handler=self._mcp_local_disable,
        )
        self.register(
            self._builtin_descriptor(
                "mcp.local.wait_until_ready",
                "Wait until local MCP server is ready",
            ),
            call_handler=self._mcp_local_wait_until_ready,
        )
        self.register(
            self._builtin_descriptor("mcp.session.open", "Open temporary MCP session"),
            call_handler=self._mcp_session_open,
        )
        self.register(
            self._builtin_descriptor(
                "mcp.session.list_tools",
                "List temporary MCP session tools",
            ),
            call_handler=self._mcp_session_list_tools,
        )
        self.register(
            self._builtin_descriptor(
                "mcp.session.call_tool",
                "Call tool on temporary MCP session",
            ),
            call_handler=self._mcp_session_call_tool,
        )
        self.register(
            self._builtin_descriptor(
                "mcp.session.close", "Close temporary MCP session"
            ),
            call_handler=self._mcp_session_close,
        )
