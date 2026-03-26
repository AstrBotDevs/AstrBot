from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..errors import AstrBotError
from ._proxy import CapabilityProxy


class MCPServerScope(str, Enum):
    local = "local"
    global_ = "global"


@dataclass(slots=True)
class MCPServerRecord:
    name: str
    scope: MCPServerScope
    active: bool
    running: bool
    config: dict[str, Any] = field(default_factory=dict)
    tools: list[str] = field(default_factory=list)
    errlogs: list[str] = field(default_factory=list)
    last_error: str | None = None

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> MCPServerRecord | None:
        if not isinstance(payload, dict):
            return None
        scope_value = str(payload.get("scope") or MCPServerScope.local.value).strip()
        try:
            scope = MCPServerScope(scope_value)
        except ValueError:
            scope = MCPServerScope.local
        return cls(
            name=str(payload.get("name", "")),
            scope=scope,
            active=bool(payload.get("active", False)),
            running=bool(payload.get("running", False)),
            config=(
                dict(payload.get("config"))
                if isinstance(payload.get("config"), dict)
                else {}
            ),
            tools=[
                str(item)
                for item in payload.get("tools", [])
                if isinstance(item, str) and item
            ]
            if isinstance(payload.get("tools"), list)
            else [],
            errlogs=[
                str(item)
                for item in payload.get("errlogs", [])
                if isinstance(item, str)
            ]
            if isinstance(payload.get("errlogs"), list)
            else [],
            last_error=(
                str(payload.get("last_error"))
                if payload.get("last_error") is not None
                else None
            ),
        )


class MCPSession(AbstractAsyncContextManager["MCPSession"]):
    def __init__(
        self,
        proxy: CapabilityProxy,
        *,
        name: str,
        config: dict[str, Any],
        timeout: float,
    ) -> None:
        self._proxy = proxy
        self._name = str(name)
        self._config = dict(config)
        self._timeout = float(timeout)
        self._session_id: str | None = None
        self._tools: list[str] = []

    async def __aenter__(self) -> MCPSession:
        output = await self._proxy.call(
            "mcp.session.open",
            {
                "name": self._name,
                "config": dict(self._config),
                "timeout": self._timeout,
            },
        )
        session_id = str(output.get("session_id", "")).strip()
        if not session_id:
            raise ValueError("mcp.session.open returned no session_id")
        self._session_id = session_id
        tools = output.get("tools")
        self._tools = (
            [str(item) for item in tools if isinstance(item, str)]
            if isinstance(tools, list)
            else []
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        session_id = self._session_id
        self._session_id = None
        self._tools = []
        if not session_id:
            return
        try:
            await self._proxy.call("mcp.session.close", {"session_id": session_id})
        except AstrBotError:
            raise
        except Exception:
            # Session cleanup should not mask the original error raised inside the
            # managed block.
            if exc_type is None:
                raise

    async def call_tool(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session_id = self._require_session_id()
        output = await self._proxy.call(
            "mcp.session.call_tool",
            {
                "session_id": session_id,
                "tool_name": str(tool_name),
                "args": dict(args or {}),
            },
        )
        result = output.get("result")
        if not isinstance(result, dict):
            raise ValueError("mcp.session.call_tool returned no result object")
        return dict(result)

    async def list_tools(self) -> list[str]:
        session_id = self._require_session_id()
        output = await self._proxy.call(
            "mcp.session.list_tools",
            {"session_id": session_id},
        )
        tools = output.get("tools")
        self._tools = (
            [str(item) for item in tools if isinstance(item, str)]
            if isinstance(tools, list)
            else []
        )
        return list(self._tools)

    def _require_session_id(self) -> str:
        if self._session_id is None:
            raise RuntimeError("MCP session is not active; use 'async with'")
        return self._session_id


class MCPManagerClient:
    def __init__(self, proxy: CapabilityProxy) -> None:
        self._proxy = proxy

    async def get_server(self, name: str) -> MCPServerRecord | None:
        output = await self._proxy.call("mcp.local.get", {"name": str(name)})
        return MCPServerRecord.from_payload(output.get("server"))

    async def list_servers(self) -> list[MCPServerRecord]:
        output = await self._proxy.call("mcp.local.list", {})
        items = output.get("servers")
        if not isinstance(items, list):
            return []
        return [
            record
            for record in (
                MCPServerRecord.from_payload(item) if isinstance(item, dict) else None
                for item in items
            )
            if record is not None
        ]

    async def enable_server(self, name: str) -> MCPServerRecord:
        output = await self._proxy.call("mcp.local.enable", {"name": str(name)})
        record = MCPServerRecord.from_payload(output.get("server"))
        if record is None:
            raise ValueError("mcp.local.enable returned no server")
        return record

    async def disable_server(self, name: str) -> MCPServerRecord:
        output = await self._proxy.call("mcp.local.disable", {"name": str(name)})
        record = MCPServerRecord.from_payload(output.get("server"))
        if record is None:
            raise ValueError("mcp.local.disable returned no server")
        return record

    async def wait_until_ready(
        self,
        name: str,
        *,
        timeout: float = 30.0,
    ) -> MCPServerRecord:
        output = await self._proxy.call(
            "mcp.local.wait_until_ready",
            {"name": str(name), "timeout": float(timeout)},
        )
        record = MCPServerRecord.from_payload(output.get("server"))
        if record is None:
            raise ValueError("mcp.local.wait_until_ready returned no server")
        return record

    def session(
        self,
        name: str,
        config: dict[str, Any],
        *,
        timeout: float = 30.0,
    ) -> MCPSession:
        return MCPSession(
            self._proxy,
            name=str(name),
            config=dict(config),
            timeout=float(timeout),
        )

    async def register_global_server(
        self,
        name: str,
        config: dict[str, Any],
        *,
        timeout: float = 30.0,
    ) -> MCPServerRecord:
        output = await self._proxy.call(
            "mcp.global.register",
            {
                "name": str(name),
                "config": dict(config),
                "timeout": float(timeout),
            },
        )
        record = MCPServerRecord.from_payload(output.get("server"))
        if record is None:
            raise ValueError("mcp.global.register returned no server")
        return record

    async def get_global_server(self, name: str) -> MCPServerRecord | None:
        output = await self._proxy.call("mcp.global.get", {"name": str(name)})
        return MCPServerRecord.from_payload(output.get("server"))

    async def list_global_servers(self) -> list[MCPServerRecord]:
        output = await self._proxy.call("mcp.global.list", {})
        items = output.get("servers")
        if not isinstance(items, list):
            return []
        return [
            record
            for record in (
                MCPServerRecord.from_payload(item) if isinstance(item, dict) else None
                for item in items
            )
            if record is not None
        ]

    async def enable_global_server(
        self,
        name: str,
        *,
        timeout: float = 30.0,
    ) -> MCPServerRecord:
        output = await self._proxy.call(
            "mcp.global.enable",
            {"name": str(name), "timeout": float(timeout)},
        )
        record = MCPServerRecord.from_payload(output.get("server"))
        if record is None:
            raise ValueError("mcp.global.enable returned no server")
        return record

    async def disable_global_server(self, name: str) -> MCPServerRecord:
        output = await self._proxy.call("mcp.global.disable", {"name": str(name)})
        record = MCPServerRecord.from_payload(output.get("server"))
        if record is None:
            raise ValueError("mcp.global.disable returned no server")
        return record

    async def unregister_global_server(self, name: str) -> MCPServerRecord:
        output = await self._proxy.call("mcp.global.unregister", {"name": str(name)})
        record = MCPServerRecord.from_payload(output.get("server"))
        if record is None:
            raise ValueError("mcp.global.unregister returned no server")
        return record


__all__ = [
    "MCPManagerClient",
    "MCPSession",
    "MCPServerRecord",
    "MCPServerScope",
]
