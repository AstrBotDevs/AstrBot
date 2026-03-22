from __future__ import annotations

import asyncio
import uuid
from typing import Any

from ....errors import AstrBotError
from ..bridge_base import CapabilityRouterBridgeBase


def _mock_tools_from_config(name: str, config: dict[str, Any]) -> list[str]:
    configured = config.get("mock_tools")
    if isinstance(configured, list):
        tools = [str(item) for item in configured if str(item).strip()]
        if tools:
            return tools
    return [f"{name}_tool"]


def _mock_server_record(
    *,
    name: str,
    scope: str,
    active: bool,
    running: bool,
    config: dict[str, Any],
    tools: list[str],
    errlogs: list[str] | None = None,
    last_error: str | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "scope": scope,
        "active": bool(active),
        "running": bool(running),
        "config": dict(config),
        "tools": list(tools),
        "errlogs": list(errlogs or []),
        "last_error": last_error,
    }


class McpCapabilityMixin(CapabilityRouterBridgeBase):
    def _plugin_local_mcp_servers(self, plugin_id: str) -> dict[str, dict[str, Any]]:
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            raise AstrBotError.invalid_input(f"Unknown plugin: {plugin_id}")
        return plugin.local_mcp_servers

    @staticmethod
    def _require_server_name(payload: dict[str, Any], capability_name: str) -> str:
        name = str(payload.get("name", "")).strip()
        if not name:
            raise AstrBotError.invalid_input(f"{capability_name} requires name")
        return name

    @staticmethod
    def _normalized_timeout(payload: dict[str, Any], default: float = 30.0) -> float:
        raw_value = payload.get("timeout", default)
        try:
            timeout = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise AstrBotError.invalid_input("timeout must be numeric") from exc
        if timeout <= 0:
            raise AstrBotError.invalid_input("timeout must be greater than 0")
        return timeout

    def _mock_connect_outcome(
        self,
        *,
        name: str,
        config: dict[str, Any],
        scope: str,
    ) -> dict[str, Any]:
        if bool(config.get("mock_fail", False)):
            last_error = str(config.get("mock_error") or f"{name} failed")
            return _mock_server_record(
                name=name,
                scope=scope,
                active=bool(config.get("active", True)),
                running=False,
                config=config,
                tools=[],
                errlogs=[last_error],
                last_error=last_error,
            )
        return _mock_server_record(
            name=name,
            scope=scope,
            active=bool(config.get("active", True)),
            running=True,
            config=config,
            tools=_mock_tools_from_config(name, config),
            errlogs=[],
            last_error=None,
        )

    async def _mcp_local_get(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("mcp.local.get")
        name = self._require_server_name(payload, "mcp.local.get")
        return {
            "server": self._plugin_local_mcp_servers(plugin_id).get(name),
        }

    async def _mcp_local_list(
        self, _request_id: str, _payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("mcp.local.list")
        servers = sorted(
            self._plugin_local_mcp_servers(plugin_id).values(),
            key=lambda item: str(item.get("name", "")),
        )
        return {"servers": [dict(item) for item in servers]}

    async def _mcp_local_enable(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("mcp.local.enable")
        name = self._require_server_name(payload, "mcp.local.enable")
        servers = self._plugin_local_mcp_servers(plugin_id)
        server = servers.get(name)
        if server is None:
            raise AstrBotError.invalid_input(f"Unknown local MCP server: {name}")
        if bool(server.get("active", False)) and bool(server.get("running", False)):
            return {"server": dict(server)}
        updated = self._mock_connect_outcome(
            name=name,
            config=dict(server.get("config", {})),
            scope="local",
        )
        updated["active"] = True
        servers[name] = updated
        return {"server": dict(updated)}

    async def _mcp_local_disable(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("mcp.local.disable")
        name = self._require_server_name(payload, "mcp.local.disable")
        servers = self._plugin_local_mcp_servers(plugin_id)
        server = servers.get(name)
        if server is None:
            raise AstrBotError.invalid_input(f"Unknown local MCP server: {name}")
        if not bool(server.get("active", False)) and not bool(
            server.get("running", False)
        ):
            return {"server": dict(server)}
        updated = dict(server)
        updated["active"] = False
        updated["running"] = False
        servers[name] = updated
        return {"server": updated}

    async def _mcp_local_wait_until_ready(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("mcp.local.wait_until_ready")
        name = self._require_server_name(payload, "mcp.local.wait_until_ready")
        timeout = self._normalized_timeout(payload)
        server = self._plugin_local_mcp_servers(plugin_id).get(name)
        if server is None:
            raise AstrBotError.invalid_input(f"Unknown local MCP server: {name}")
        if bool(server.get("running", False)):
            return {"server": dict(server)}
        delay = float(server.get("config", {}).get("mock_connect_delay", 0.0) or 0.0)
        if delay > timeout:
            raise TimeoutError(
                f"Local MCP server '{name}' did not become ready in time"
            )
        if delay > 0:
            await asyncio.sleep(delay)
        if bool(server.get("active", False)) and not bool(
            server.get("config", {}).get("mock_fail", False)
        ):
            refreshed = self._mock_connect_outcome(
                name=name,
                config=dict(server.get("config", {})),
                scope="local",
            )
            refreshed["active"] = bool(server.get("active", False))
            self._plugin_local_mcp_servers(plugin_id)[name] = refreshed
        refreshed = self._plugin_local_mcp_servers(plugin_id).get(name)
        if refreshed is None or not bool(refreshed.get("running", False)):
            raise TimeoutError(
                f"Local MCP server '{name}' did not become ready in time"
            )
        return {"server": dict(refreshed)}

    async def _mcp_session_open(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("mcp.session.open")
        name = self._require_server_name(payload, "mcp.session.open")
        config = payload.get("config")
        if not isinstance(config, dict):
            raise AstrBotError.invalid_input("mcp.session.open requires config object")
        timeout = self._normalized_timeout(payload)
        delay = float(config.get("mock_connect_delay", 0.0) or 0.0)
        if bool(config.get("mock_fail", False)) or delay > timeout:
            raise TimeoutError(f"MCP session '{name}' failed to connect in time")
        if delay > 0:
            await asyncio.sleep(delay)
        session_id = f"{plugin_id}:{uuid.uuid4().hex}"
        tools = _mock_tools_from_config(name, dict(config))
        self._mcp_session_store[session_id] = {
            "plugin_id": plugin_id,
            "name": name,
            "config": dict(config),
            "tools": tools,
            "tool_results": dict(config.get("mock_tool_results", {}))
            if isinstance(config.get("mock_tool_results"), dict)
            else {},
        }
        return {"session_id": session_id, "tools": list(tools)}

    async def _mcp_session_list_tools(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session_id = str(payload.get("session_id", "")).strip()
        session = self._mcp_session_store.get(session_id)
        if session is None:
            raise AstrBotError.invalid_input("Unknown MCP session")
        return {"tools": list(session.get("tools", []))}

    async def _mcp_session_call_tool(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session_id = str(payload.get("session_id", "")).strip()
        session = self._mcp_session_store.get(session_id)
        if session is None:
            raise AstrBotError.invalid_input("Unknown MCP session")
        tool_name = str(payload.get("tool_name", "")).strip()
        if not tool_name:
            raise AstrBotError.invalid_input("mcp.session.call_tool requires tool_name")
        args = payload.get("args")
        if not isinstance(args, dict):
            raise AstrBotError.invalid_input(
                "mcp.session.call_tool requires args object"
            )
        tool_results = session.get("tool_results", {})
        if isinstance(tool_results, dict) and tool_name in tool_results:
            result = tool_results[tool_name]
            return {
                "result": dict(result)
                if isinstance(result, dict)
                else {"value": result}
            }
        return {
            "result": {
                "tool_name": tool_name,
                "arguments": dict(args),
                "content": f"mock:{session['name']}:{tool_name}",
            }
        }

    async def _mcp_session_close(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session_id = str(payload.get("session_id", "")).strip()
        self._mcp_session_store.pop(session_id, None)
        return {}

    def _require_global_mcp_risk_ack(
        self,
        plugin_id: str,
        capability_name: str,
    ) -> None:
        plugin = self._plugins.get(plugin_id)
        metadata = plugin.metadata if plugin is not None else {}
        if bool(metadata.get("acknowledge_global_mcp_risk", False)):
            return
        raise PermissionError(
            f"{capability_name} requires @acknowledge_global_mcp_risk"
        )

    def _audit_global_mcp_mutation(
        self,
        *,
        plugin_id: str,
        action: str,
        server_name: str,
        request_id: str,
    ) -> None:
        self._mcp_audit_logs.append(
            {
                "plugin_id": plugin_id,
                "action": action,
                "server_name": server_name,
                "request_id": request_id,
            }
        )

    async def _mcp_global_register(
        self, request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("mcp.global.register")
        self._require_global_mcp_risk_ack(plugin_id, "mcp.global.register")
        name = self._require_server_name(payload, "mcp.global.register")
        config = payload.get("config")
        if not isinstance(config, dict):
            raise AstrBotError.invalid_input(
                "mcp.global.register requires config object"
            )
        if name in self._mcp_global_servers:
            raise AstrBotError.invalid_input(
                f"Global MCP server already exists: {name}"
            )
        record = self._mock_connect_outcome(
            name=name,
            config=dict(config),
            scope="global",
        )
        self._mcp_global_servers[name] = record
        self._audit_global_mcp_mutation(
            plugin_id=plugin_id,
            action="register",
            server_name=name,
            request_id=request_id,
        )
        return {"server": dict(record)}

    async def _mcp_global_get(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("mcp.global.get")
        self._require_global_mcp_risk_ack(plugin_id, "mcp.global.get")
        name = self._require_server_name(payload, "mcp.global.get")
        return {"server": self._mcp_global_servers.get(name)}

    async def _mcp_global_list(
        self, _request_id: str, _payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("mcp.global.list")
        self._require_global_mcp_risk_ack(plugin_id, "mcp.global.list")
        servers = sorted(
            self._mcp_global_servers.values(),
            key=lambda item: str(item.get("name", "")),
        )
        return {"servers": [dict(item) for item in servers]}

    async def _mcp_global_enable(
        self, request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("mcp.global.enable")
        self._require_global_mcp_risk_ack(plugin_id, "mcp.global.enable")
        name = self._require_server_name(payload, "mcp.global.enable")
        record = self._mcp_global_servers.get(name)
        if record is None:
            raise AstrBotError.invalid_input(f"Unknown global MCP server: {name}")
        updated = self._mock_connect_outcome(
            name=name,
            config=dict(record.get("config", {})),
            scope="global",
        )
        updated["active"] = True
        self._mcp_global_servers[name] = updated
        self._audit_global_mcp_mutation(
            plugin_id=plugin_id,
            action="enable",
            server_name=name,
            request_id=request_id,
        )
        return {"server": dict(updated)}

    async def _mcp_global_disable(
        self, request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("mcp.global.disable")
        self._require_global_mcp_risk_ack(plugin_id, "mcp.global.disable")
        name = self._require_server_name(payload, "mcp.global.disable")
        record = self._mcp_global_servers.get(name)
        if record is None:
            raise AstrBotError.invalid_input(f"Unknown global MCP server: {name}")
        updated = dict(record)
        updated["active"] = False
        updated["running"] = False
        self._mcp_global_servers[name] = updated
        self._audit_global_mcp_mutation(
            plugin_id=plugin_id,
            action="disable",
            server_name=name,
            request_id=request_id,
        )
        return {"server": dict(updated)}

    async def _mcp_global_unregister(
        self, request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("mcp.global.unregister")
        self._require_global_mcp_risk_ack(plugin_id, "mcp.global.unregister")
        name = self._require_server_name(payload, "mcp.global.unregister")
        record = self._mcp_global_servers.pop(name, None)
        if record is None:
            raise AstrBotError.invalid_input(f"Unknown global MCP server: {name}")
        self._audit_global_mcp_mutation(
            plugin_id=plugin_id,
            action="unregister",
            server_name=name,
            request_id=request_id,
        )
        return {"server": dict(record)}

    async def _internal_mcp_local_execute(
        self, _request_id: str, payload: dict[str, Any], _token
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
        plugin = self._plugins.get(plugin_id)
        server = (
            plugin.local_mcp_servers.get(server_name) if plugin is not None else None
        )
        if server is None or not bool(server.get("running", False)):
            return {
                "content": f"Local MCP server unavailable: {server_name}",
                "success": False,
            }
        if tool_name not in server.get("tools", []):
            return {
                "content": f"Local MCP tool not found: {server_name}.{tool_name}",
                "success": False,
            }
        return {
            "content": f"mock:{server_name}:{tool_name}:{tool_args}",
            "success": True,
        }

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
                "List tools in temporary MCP session",
            ),
            call_handler=self._mcp_session_list_tools,
        )
        self.register(
            self._builtin_descriptor(
                "mcp.session.call_tool",
                "Call tool in temporary MCP session",
            ),
            call_handler=self._mcp_session_call_tool,
        )
        self.register(
            self._builtin_descriptor(
                "mcp.session.close", "Close temporary MCP session"
            ),
            call_handler=self._mcp_session_close,
        )
        self.register(
            self._builtin_descriptor(
                "mcp.global.register",
                "Register global MCP server",
            ),
            call_handler=self._mcp_global_register,
        )
        self.register(
            self._builtin_descriptor("mcp.global.get", "Get global MCP server"),
            call_handler=self._mcp_global_get,
        )
        self.register(
            self._builtin_descriptor("mcp.global.list", "List global MCP servers"),
            call_handler=self._mcp_global_list,
        )
        self.register(
            self._builtin_descriptor("mcp.global.enable", "Enable global MCP server"),
            call_handler=self._mcp_global_enable,
        )
        self.register(
            self._builtin_descriptor(
                "mcp.global.disable",
                "Disable global MCP server",
            ),
            call_handler=self._mcp_global_disable,
        )
        self.register(
            self._builtin_descriptor(
                "mcp.global.unregister",
                "Unregister global MCP server",
            ),
            call_handler=self._mcp_global_unregister,
        )
        self.register(
            self._builtin_descriptor(
                "internal.mcp.local.execute",
                "Execute local MCP tool",
            ),
            call_handler=self._internal_mcp_local_execute,
            exposed=False,
        )
