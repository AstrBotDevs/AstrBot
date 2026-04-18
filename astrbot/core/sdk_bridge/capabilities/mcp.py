from __future__ import annotations

from typing import Any

from astrbot_sdk.errors import AstrBotError

from astrbot.core import logger

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

    def _func_tool_manager(self):
        return self._star_context.get_llm_tool_manager()

    @staticmethod
    def _global_mcp_record_from_state(
        *,
        name: str,
        config: dict[str, Any],
        runtime: Any | None,
    ) -> dict[str, Any]:
        client = getattr(runtime, "client", None) if runtime is not None else None
        return {
            "name": name,
            "scope": "global",
            "active": bool(config.get("active", True)),
            "running": runtime is not None,
            "config": dict(config),
            "tools": [
                str(tool.name)
                for tool in getattr(client, "tools", [])
                if getattr(tool, "name", None)
            ]
            if client is not None
            else [],
            "errlogs": list(getattr(client, "server_errlogs", []))
            if client is not None
            else [],
            "last_error": None,
        }

    def _get_global_mcp_record(self, name: str) -> dict[str, Any] | None:
        func_tool_manager = self._func_tool_manager()
        config_payload = func_tool_manager.load_mcp_config()
        servers = config_payload.get("mcpServers")
        if not isinstance(servers, dict):
            return None
        config = servers.get(name)
        if not isinstance(config, dict):
            return None
        runtime = func_tool_manager.mcp_server_runtime_view.get(name)
        return self._global_mcp_record_from_state(
            name=name,
            config=dict(config),
            runtime=runtime,
        )

    def _list_global_mcp_records(self) -> list[dict[str, Any]]:
        func_tool_manager = self._func_tool_manager()
        config_payload = func_tool_manager.load_mcp_config()
        servers = config_payload.get("mcpServers")
        if not isinstance(servers, dict):
            return []
        return [
            self._global_mcp_record_from_state(
                name=str(name),
                config=dict(config),
                runtime=func_tool_manager.mcp_server_runtime_view.get(str(name)),
            )
            for name, config in sorted(servers.items(), key=lambda item: str(item[0]))
            if str(name).strip() and isinstance(config, dict)
        ]

    def _require_global_mcp_ack(self, request_id: str, capability_name: str) -> str:
        plugin_id = self._resolve_plugin_id(request_id)
        if self._plugin_bridge.acknowledges_global_mcp_risk(plugin_id):
            return plugin_id
        raise PermissionError(
            f"{capability_name} requires @acknowledge_global_mcp_risk"
        )

    @staticmethod
    def _audit_global_mcp_mutation(
        *,
        plugin_id: str,
        action: str,
        server_name: str,
        request_id: str,
    ) -> None:
        audit_entry = {
            "plugin_id": plugin_id,
            "action": action,
            "server_name": server_name,
            "request_id": request_id,
        }
        logger.info("SDK global MCP mutation: {}", audit_entry)

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

    async def _mcp_global_register(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._require_global_mcp_ack(request_id, "mcp.global.register")
        name = self._mcp_name(payload, "mcp.global.register")
        config = self._mcp_config(payload, "mcp.global.register")
        timeout = self._mcp_timeout(payload, "mcp.global.register")
        func_tool_manager = self._func_tool_manager()
        config_payload = func_tool_manager.load_mcp_config()
        servers = config_payload.setdefault("mcpServers", {})
        if not isinstance(servers, dict):
            raise AstrBotError.invalid_input("Invalid global MCP config shape")
        if name in servers:
            raise AstrBotError.invalid_input(
                f"Global MCP server already exists: {name}"
            )
        normalized_config = dict(config)
        normalized_config.setdefault("active", True)
        servers[name] = normalized_config
        func_tool_manager.save_mcp_config(config_payload)
        if bool(normalized_config.get("active", True)):
            await func_tool_manager.enable_mcp_server(
                name, normalized_config, timeout=timeout
            )
        record = self._get_global_mcp_record(name)
        self._audit_global_mcp_mutation(
            plugin_id=plugin_id,
            action="register",
            server_name=name,
            request_id=request_id,
        )
        return {"server": record}

    async def _mcp_global_get(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        self._require_global_mcp_ack(request_id, "mcp.global.get")
        name = self._mcp_name(payload, "mcp.global.get")
        return {"server": self._get_global_mcp_record(name)}

    async def _mcp_global_list(
        self,
        request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        self._require_global_mcp_ack(request_id, "mcp.global.list")
        return {"servers": self._list_global_mcp_records()}

    async def _mcp_global_enable(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._require_global_mcp_ack(request_id, "mcp.global.enable")
        name = self._mcp_name(payload, "mcp.global.enable")
        timeout = self._mcp_timeout(payload, "mcp.global.enable")
        func_tool_manager = self._func_tool_manager()
        config_payload = func_tool_manager.load_mcp_config()
        servers = config_payload.get("mcpServers")
        if (
            not isinstance(servers, dict)
            or name not in servers
            or not isinstance(servers[name], dict)
        ):
            raise AstrBotError.invalid_input(f"Unknown global MCP server: {name}")
        servers[name]["active"] = True
        func_tool_manager.save_mcp_config(config_payload)
        await func_tool_manager.enable_mcp_server(
            name, dict(servers[name]), timeout=timeout
        )
        record = self._get_global_mcp_record(name)
        self._audit_global_mcp_mutation(
            plugin_id=plugin_id,
            action="enable",
            server_name=name,
            request_id=request_id,
        )
        return {"server": record}

    async def _mcp_global_disable(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._require_global_mcp_ack(request_id, "mcp.global.disable")
        name = self._mcp_name(payload, "mcp.global.disable")
        func_tool_manager = self._func_tool_manager()
        config_payload = func_tool_manager.load_mcp_config()
        servers = config_payload.get("mcpServers")
        if (
            not isinstance(servers, dict)
            or name not in servers
            or not isinstance(servers[name], dict)
        ):
            raise AstrBotError.invalid_input(f"Unknown global MCP server: {name}")
        servers[name]["active"] = False
        func_tool_manager.save_mcp_config(config_payload)
        await func_tool_manager.disable_mcp_server(name)
        record = self._get_global_mcp_record(name)
        self._audit_global_mcp_mutation(
            plugin_id=plugin_id,
            action="disable",
            server_name=name,
            request_id=request_id,
        )
        return {"server": record}

    async def _mcp_global_unregister(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._require_global_mcp_ack(request_id, "mcp.global.unregister")
        name = self._mcp_name(payload, "mcp.global.unregister")
        func_tool_manager = self._func_tool_manager()
        existing_record = self._get_global_mcp_record(name)
        if existing_record is None:
            raise AstrBotError.invalid_input(f"Unknown global MCP server: {name}")
        config_payload = func_tool_manager.load_mcp_config()
        servers = config_payload.get("mcpServers")
        if not isinstance(servers, dict):
            raise AstrBotError.invalid_input("Invalid global MCP config shape")
        servers.pop(name, None)
        func_tool_manager.save_mcp_config(config_payload)
        await func_tool_manager.disable_mcp_server(name)
        existing_record["running"] = False
        self._audit_global_mcp_mutation(
            plugin_id=plugin_id,
            action="unregister",
            server_name=name,
            request_id=request_id,
        )
        return {"server": existing_record}

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
