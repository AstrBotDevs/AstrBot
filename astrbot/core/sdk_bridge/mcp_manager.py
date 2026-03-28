from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from astrbot_sdk.errors import AstrBotError

from .runtime_store import (
    SdkPluginRecord,
    _LocalMCPServerRuntime,
    _TemporaryMCPSessionRuntime,
)

if TYPE_CHECKING:
    from .plugin_bridge import SdkPluginBridge


class SdkMcpManager:
    def __init__(self, *, bridge: SdkPluginBridge) -> None:
        self.bridge = bridge

    def get_local_mcp_server(
        self,
        plugin_id: str,
        name: str,
    ) -> dict[str, Any] | None:
        runtime = self.bridge._local_mcp_record(plugin_id, name)
        if runtime is None:
            return None
        return self.bridge._serialize_local_mcp_server(runtime)

    def list_local_mcp_servers(self, plugin_id: str) -> list[dict[str, Any]]:
        record = self.bridge._records.get(plugin_id)
        if record is None:
            return []
        return [
            self.bridge._serialize_local_mcp_server(runtime)
            for runtime in sorted(
                record.local_mcp_servers.values(),
                key=lambda item: item.name,
            )
        ]

    async def connect_local_mcp_server(
        self,
        *,
        plugin_id: str,
        runtime: _LocalMCPServerRuntime,
        timeout: float,
    ) -> None:
        runtime.ready_event.clear()
        runtime.running = False
        runtime.last_error = None
        runtime.errlogs = []
        runtime.tools = []
        runtime.tool_specs = []
        self.bridge._remove_local_mcp_lease(runtime)
        await self.bridge._cleanup_mcp_client(runtime.client)
        runtime.client = None

        client = self.bridge._make_mcp_client()
        client.name = runtime.name
        try:
            await asyncio.wait_for(
                client.connect_to_server(dict(runtime.config), runtime.name),
                timeout=timeout,
            )
            await asyncio.wait_for(client.list_tools_and_save(), timeout=timeout)
        except asyncio.CancelledError:
            await self.bridge._cleanup_mcp_client(client)
            raise
        except TimeoutError:
            runtime.last_error = (
                f"Local MCP server '{runtime.name}' did not become ready within "
                f"{timeout:g} seconds"
            )
            runtime.errlogs = [runtime.last_error]
            await self.bridge._cleanup_mcp_client(client)
        except Exception as exc:
            runtime.last_error = str(exc)
            runtime.errlogs = [runtime.last_error]
            await self.bridge._cleanup_mcp_client(client)
        else:
            runtime.client = client
            runtime.running = True
            runtime.tools = [
                str(tool.name) for tool in client.tools if getattr(tool, "name", None)
            ]
            runtime.tool_specs = self.bridge._build_local_mcp_tool_specs(
                runtime.name,
                client,
            )
            runtime.errlogs = list(client.server_errlogs)
            if client.process_pid is not None:
                runtime.lease_path = self.bridge._write_local_mcp_lease(
                    plugin_id=plugin_id,
                    server_name=runtime.name,
                    pid=client.process_pid,
                )
        finally:
            runtime.ready_event.set()
            runtime.connect_task = None

    async def initialize_local_mcp_servers(self, record: SdkPluginRecord) -> None:
        tasks: list[asyncio.Task[None]] = []
        for runtime in record.local_mcp_servers.values():
            if not runtime.active:
                runtime.ready_event.set()
                continue
            task = asyncio.create_task(
                self.connect_local_mcp_server(
                    plugin_id=record.plugin_id,
                    runtime=runtime,
                    timeout=30.0,
                )
            )
            runtime.connect_task = task
            tasks.append(task)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def shutdown_local_mcp_runtime(
        self,
        runtime: _LocalMCPServerRuntime,
    ) -> None:
        connect_task = runtime.connect_task
        runtime.connect_task = None
        if connect_task is not None and not connect_task.done():
            connect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await connect_task
        self.bridge._remove_local_mcp_lease(runtime)
        await self.bridge._cleanup_mcp_client(runtime.client)
        runtime.client = None
        runtime.running = False
        runtime.tools = []
        runtime.tool_specs = []
        runtime.ready_event.clear()

    async def shutdown_local_mcp_servers(self, record: SdkPluginRecord) -> None:
        for runtime in record.local_mcp_servers.values():
            await self.shutdown_local_mcp_runtime(runtime)

    async def enable_local_mcp_server(
        self,
        plugin_id: str,
        name: str,
        *,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        runtime = self.bridge._local_mcp_record(plugin_id, name)
        if runtime is None:
            raise AstrBotError.invalid_input(f"Unknown local MCP server: {name}")
        if runtime.active and runtime.running and runtime.connect_task is None:
            return self.bridge._serialize_local_mcp_server(runtime)
        if runtime.connect_task is not None and not runtime.connect_task.done():
            runtime.active = True
            await runtime.connect_task
            return self.bridge._serialize_local_mcp_server(runtime)
        runtime.active = True
        task = asyncio.create_task(
            self.connect_local_mcp_server(
                plugin_id=plugin_id,
                runtime=runtime,
                timeout=timeout,
            )
        )
        runtime.connect_task = task
        await task
        return self.bridge._serialize_local_mcp_server(runtime)

    async def disable_local_mcp_server(
        self,
        plugin_id: str,
        name: str,
    ) -> dict[str, Any]:
        runtime = self.bridge._local_mcp_record(plugin_id, name)
        if runtime is None:
            raise AstrBotError.invalid_input(f"Unknown local MCP server: {name}")
        if not runtime.active and not runtime.running and runtime.connect_task is None:
            return self.bridge._serialize_local_mcp_server(runtime)
        runtime.active = False
        await self.shutdown_local_mcp_runtime(runtime)
        return self.bridge._serialize_local_mcp_server(runtime)

    async def wait_for_local_mcp_server(
        self,
        plugin_id: str,
        name: str,
        *,
        timeout: float,
    ) -> dict[str, Any]:
        runtime = self.bridge._local_mcp_record(plugin_id, name)
        if runtime is None:
            raise AstrBotError.invalid_input(f"Unknown local MCP server: {name}")
        await asyncio.wait_for(runtime.ready_event.wait(), timeout=timeout)
        if not runtime.running:
            raise TimeoutError(
                f"Local MCP server '{name}' did not become ready in time"
            )
        return self.bridge._serialize_local_mcp_server(runtime)

    async def open_temporary_mcp_session(
        self,
        plugin_id: str,
        *,
        name: str,
        config: dict[str, Any],
        timeout: float,
    ) -> tuple[str, list[str]]:
        client = self.bridge._make_mcp_client()
        client.name = name
        try:
            await asyncio.wait_for(
                client.connect_to_server(dict(config), name),
                timeout=timeout,
            )
            await asyncio.wait_for(client.list_tools_and_save(), timeout=timeout)
        except Exception:
            await self.bridge._cleanup_mcp_client(client)
            raise
        session_id = f"{plugin_id}:{uuid.uuid4().hex}"
        tools = [str(tool.name) for tool in client.tools if getattr(tool, "name", None)]
        self.bridge._temporary_mcp_sessions[session_id] = _TemporaryMCPSessionRuntime(
            plugin_id=plugin_id,
            name=name,
            client=client,
            tools=tools,
        )
        return session_id, tools

    async def close_temporary_mcp_session(
        self,
        plugin_id: str,
        session_id: str,
    ) -> None:
        runtime = self.bridge._temporary_mcp_sessions.get(session_id)
        if runtime is None or runtime.plugin_id != plugin_id:
            return
        self.bridge._temporary_mcp_sessions.pop(session_id, None)
        await self.bridge._cleanup_mcp_client(runtime.client)

    async def close_temporary_mcp_sessions(self, plugin_id: str) -> None:
        session_ids = [
            session_id
            for session_id, runtime in self.bridge._temporary_mcp_sessions.items()
            if runtime.plugin_id == plugin_id
        ]
        for session_id in session_ids:
            await self.close_temporary_mcp_session(plugin_id, session_id)

    def get_temporary_mcp_session_tools(
        self,
        plugin_id: str,
        session_id: str,
    ) -> list[str]:
        runtime = self.bridge._temporary_mcp_sessions.get(session_id)
        if runtime is None or runtime.plugin_id != plugin_id:
            raise AstrBotError.invalid_input("Unknown MCP session")
        return list(runtime.tools)

    async def call_temporary_mcp_tool(
        self,
        plugin_id: str,
        *,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        runtime = self.bridge._temporary_mcp_sessions.get(session_id)
        if runtime is None or runtime.plugin_id != plugin_id:
            raise AstrBotError.invalid_input("Unknown MCP session")
        result = await runtime.client.call_tool_with_reconnect(
            tool_name=tool_name,
            arguments=arguments,
            read_timeout_seconds=timedelta(seconds=60),
        )
        text = self.bridge._mcp_call_result_to_text(result)
        return {"content": text, "is_error": bool(getattr(result, "isError", False))}

    async def execute_local_mcp_tool(
        self,
        plugin_id: str,
        *,
        server_name: str,
        tool_name: str,
        tool_args: dict[str, Any],
        timeout_seconds: int = 60,
    ) -> dict[str, Any]:
        runtime = self.bridge._local_mcp_record(plugin_id, server_name)
        if (
            runtime is None
            or not runtime.active
            or not runtime.running
            or runtime.client is None
        ):
            return {
                "content": f"Local MCP server unavailable: {server_name}",
                "success": False,
            }
        if tool_name not in runtime.tools:
            return {
                "content": f"Local MCP tool not found: {server_name}.{tool_name}",
                "success": False,
            }
        try:
            result = await runtime.client.call_tool_with_reconnect(
                tool_name=tool_name,
                arguments=tool_args,
                read_timeout_seconds=timedelta(seconds=timeout_seconds),
            )
        except Exception as exc:
            return {"content": f"Tool execution failed: {exc}", "success": False}
        text = self.bridge._mcp_call_result_to_text(result)
        return {
            "content": text,
            "success": not bool(getattr(result, "isError", False)),
        }
