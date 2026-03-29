"""MCP 管理客户端。

提供本地 MCP 服务、全局 MCP 服务和临时 MCP session 的 SDK 封装。
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from enum import Enum
from types import TracebackType
from typing import Any

from ..errors import AstrBotError
from ._errors import wrap_client_exception
from ._proxy import CapabilityProxy


class MCPServerScope(str, Enum):
    local = "local"
    global_ = "global"


@dataclass(slots=True)
class MCPServerRecord:
    """MCP 服务快照。"""

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


def _server_records_from_payload(items: Any) -> list[MCPServerRecord]:
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


def _require_server_record(
    payload: dict[str, Any],
    *,
    action: str,
) -> MCPServerRecord:
    record = MCPServerRecord.from_payload(payload.get("server"))
    if record is None:
        raise ValueError(f"{action} returned no server")
    return record


class MCPSession(AbstractAsyncContextManager["MCPSession"]):
    """临时 MCP session 的异步上下文封装。"""

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
        try:
            output = await self._proxy.call(
                "mcp.session.open",
                {
                    "name": self._name,
                    "config": dict(self._config),
                    "timeout": self._timeout,
                },
            )
        except Exception as exc:
            raise wrap_client_exception(
                client_name="MCPSession",
                method_name="open",
                details=f"name={self._name!r}, timeout={self._timeout!r}",
                exc=exc,
            ) from exc
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

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
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
        try:
            output = await self._proxy.call(
                "mcp.session.call_tool",
                {
                    "session_id": session_id,
                    "tool_name": str(tool_name),
                    "args": dict(args or {}),
                },
            )
        except Exception as exc:
            raise wrap_client_exception(
                client_name="MCPSession",
                method_name="call_tool",
                details=f"session_id={session_id!r}, tool_name={str(tool_name)!r}",
                exc=exc,
            ) from exc
        result = output.get("result")
        if not isinstance(result, dict):
            raise ValueError("mcp.session.call_tool returned no result object")
        return dict(result)

    async def list_tools(self) -> list[str]:
        session_id = self._require_session_id()
        try:
            output = await self._proxy.call(
                "mcp.session.list_tools",
                {"session_id": session_id},
            )
        except Exception as exc:
            raise wrap_client_exception(
                client_name="MCPSession",
                method_name="list_tools",
                details=f"session_id={session_id!r}",
                exc=exc,
            ) from exc
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
    """MCP 服务管理客户端。"""

    def __init__(self, proxy: CapabilityProxy) -> None:
        self._proxy = proxy

    async def get_server(self, name: str) -> MCPServerRecord | None:
        try:
            output = await self._proxy.call("mcp.local.get", {"name": str(name)})
        except Exception as exc:
            raise wrap_client_exception(
                client_name="MCPManagerClient",
                method_name="get_server",
                details=f"name={str(name)!r}",
                exc=exc,
            ) from exc
        return MCPServerRecord.from_payload(output.get("server"))

    async def list_servers(self) -> list[MCPServerRecord]:
        try:
            output = await self._proxy.call("mcp.local.list", {})
        except Exception as exc:
            raise wrap_client_exception(
                client_name="MCPManagerClient",
                method_name="list_servers",
                exc=exc,
            ) from exc
        return _server_records_from_payload(output.get("servers"))

    async def enable_server(self, name: str) -> MCPServerRecord:
        try:
            output = await self._proxy.call("mcp.local.enable", {"name": str(name)})
        except Exception as exc:
            raise wrap_client_exception(
                client_name="MCPManagerClient",
                method_name="enable_server",
                details=f"name={str(name)!r}",
                exc=exc,
            ) from exc
        return _require_server_record(output, action="mcp.local.enable")

    async def disable_server(self, name: str) -> MCPServerRecord:
        try:
            output = await self._proxy.call("mcp.local.disable", {"name": str(name)})
        except Exception as exc:
            raise wrap_client_exception(
                client_name="MCPManagerClient",
                method_name="disable_server",
                details=f"name={str(name)!r}",
                exc=exc,
            ) from exc
        return _require_server_record(output, action="mcp.local.disable")

    async def wait_until_ready(
        self,
        name: str,
        *,
        timeout: float = 30.0,
    ) -> MCPServerRecord:
        try:
            output = await self._proxy.call(
                "mcp.local.wait_until_ready",
                {"name": str(name), "timeout": float(timeout)},
            )
        except Exception as exc:
            raise wrap_client_exception(
                client_name="MCPManagerClient",
                method_name="wait_until_ready",
                details=f"name={str(name)!r}, timeout={float(timeout)!r}",
                exc=exc,
            ) from exc
        return _require_server_record(output, action="mcp.local.wait_until_ready")

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
        try:
            output = await self._proxy.call(
                "mcp.global.register",
                {
                    "name": str(name),
                    "config": dict(config),
                    "timeout": float(timeout),
                },
            )
        except Exception as exc:
            raise wrap_client_exception(
                client_name="MCPManagerClient",
                method_name="register_global_server",
                details=f"name={str(name)!r}, timeout={float(timeout)!r}",
                exc=exc,
            ) from exc
        return _require_server_record(output, action="mcp.global.register")

    async def get_global_server(self, name: str) -> MCPServerRecord | None:
        try:
            output = await self._proxy.call("mcp.global.get", {"name": str(name)})
        except Exception as exc:
            raise wrap_client_exception(
                client_name="MCPManagerClient",
                method_name="get_global_server",
                details=f"name={str(name)!r}",
                exc=exc,
            ) from exc
        return MCPServerRecord.from_payload(output.get("server"))

    async def list_global_servers(self) -> list[MCPServerRecord]:
        try:
            output = await self._proxy.call("mcp.global.list", {})
        except Exception as exc:
            raise wrap_client_exception(
                client_name="MCPManagerClient",
                method_name="list_global_servers",
                exc=exc,
            ) from exc
        return _server_records_from_payload(output.get("servers"))

    async def enable_global_server(
        self,
        name: str,
        *,
        timeout: float = 30.0,
    ) -> MCPServerRecord:
        try:
            output = await self._proxy.call(
                "mcp.global.enable",
                {"name": str(name), "timeout": float(timeout)},
            )
        except Exception as exc:
            raise wrap_client_exception(
                client_name="MCPManagerClient",
                method_name="enable_global_server",
                details=f"name={str(name)!r}, timeout={float(timeout)!r}",
                exc=exc,
            ) from exc
        return _require_server_record(output, action="mcp.global.enable")

    async def disable_global_server(self, name: str) -> MCPServerRecord:
        try:
            output = await self._proxy.call("mcp.global.disable", {"name": str(name)})
        except Exception as exc:
            raise wrap_client_exception(
                client_name="MCPManagerClient",
                method_name="disable_global_server",
                details=f"name={str(name)!r}",
                exc=exc,
            ) from exc
        return _require_server_record(output, action="mcp.global.disable")

    async def unregister_global_server(self, name: str) -> MCPServerRecord:
        try:
            output = await self._proxy.call(
                "mcp.global.unregister", {"name": str(name)}
            )
        except Exception as exc:
            raise wrap_client_exception(
                client_name="MCPManagerClient",
                method_name="unregister_global_server",
                details=f"name={str(name)!r}",
                exc=exc,
            ) from exc
        return _require_server_record(output, action="mcp.global.unregister")


__all__ = [
    "MCPManagerClient",
    "MCPSession",
    "MCPServerRecord",
    "MCPServerScope",
]
