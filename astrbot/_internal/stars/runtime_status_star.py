"""
RuntimeStatusStar - ABP plugin that exposes core runtime internal state.

This star provides tools for querying:
- Runtime status (running state, uptime)
- Protocol client status (LSP, MCP, ACP, ABP)
- Registered stars registry
- Message counts and metrics
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class RuntimeStatusStar:
    """
    ABP star that exposes core runtime internal state as callable tools.

    Tools provided:
    - get_runtime_status: Returns running state and uptime
    - get_protocol_status: Returns LSP, MCP, ACP, ABP status
    - get_star_registry: Returns registered star names
    - get_stats: Returns message counts and metrics
    """

    name: str = "runtime-status-star"
    description: str = "ABP plugin that exposes core runtime internal state"

    _start_time: float = field(default_factory=time.time, init=False)
    _orchestrator: Any = field(default=None, init=False)

    def set_orchestrator(self, orchestrator: Any) -> None:
        """Set the orchestrator reference for status queries."""
        self._orchestrator = orchestrator

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """
        Handle tool calls from ABP client.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool result
        """
        if tool_name == "get_runtime_status":
            return self._get_runtime_status()
        elif tool_name == "get_protocol_status":
            return await self._get_protocol_status()
        elif tool_name == "get_star_registry":
            return await self._get_star_registry()
        elif tool_name == "get_stats":
            return self._get_stats()
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    def _get_runtime_status(self) -> dict[str, Any]:
        """Get overall runtime state."""
        running = (
            getattr(self._orchestrator, "running", False)
            if self._orchestrator
            else False
        )
        uptime_seconds = time.time() - self._start_time
        return {
            "running": running,
            "uptime_seconds": uptime_seconds,
        }

    async def _get_protocol_status(self) -> dict[str, Any]:
        """Get status of each protocol client."""
        if not self._orchestrator:
            return {
                "lsp": {"connected": False, "name": "lsp-client"},
                "mcp": {"connected": False, "name": "mcp-client"},
                "acp": {"connected": False, "name": "acp-client"},
                "abp": {"connected": False, "name": "abp-client"},
            }

        return {
            "lsp": {
                "connected": getattr(self._orchestrator.lsp, "connected", False),
                "name": "lsp-client",
            },
            "mcp": {
                "connected": getattr(self._orchestrator.mcp, "connected", False),
                "name": "mcp-client",
            },
            "acp": {
                "connected": getattr(self._orchestrator.acp, "connected", False),
                "name": "acp-client",
            },
            "abp": {
                "connected": getattr(self._orchestrator.abp, "connected", False),
                "name": "abp-client",
            },
        }

    async def _get_star_registry(self) -> dict[str, Any]:
        """Get list of registered stars."""
        if not self._orchestrator:
            return {"stars": []}

        stars = await self._orchestrator.list_stars()
        return {"stars": stars}

    def _get_stats(self) -> dict[str, Any]:
        """Get message counts and metrics."""
        result: dict[str, Any] = {
            "uptime_seconds": time.time() - self._start_time,
        }
        if self._orchestrator:
            result["total_messages"] = getattr(self._orchestrator, "_message_count", 0)
            last_ts = getattr(self._orchestrator, "_last_activity_timestamp", None)
            if last_ts is not None:
                result["last_activity"] = datetime.fromtimestamp(
                    last_ts, tz=timezone.utc
                ).isoformat()
            else:
                result["last_activity"] = None
        return result
