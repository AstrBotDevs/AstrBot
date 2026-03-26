from __future__ import annotations

import pytest
from astrbot_sdk.testing import MockContext

from tests.test_sdk.unit._mcp_contract import exercise_local_mcp_contract


class _MockMCPBackend:
    def __init__(self, ctx: MockContext) -> None:
        self._ctx = ctx

    async def get_server(self, name: str):
        return await self._ctx.mcp.get_server(name)

    async def list_servers(self):
        return await self._ctx.mcp.list_servers()

    async def enable_server(self, name: str):
        return await self._ctx.mcp.enable_server(name)

    async def disable_server(self, name: str):
        return await self._ctx.mcp.disable_server(name)

    async def wait_until_ready(self, name: str, *, timeout: float):
        return await self._ctx.mcp.wait_until_ready(name, timeout=timeout)


def _local_server_payload(name: str, *, running: bool, delay: float = 0.0) -> dict:
    return {
        "name": name,
        "scope": "local",
        "active": True,
        "running": running,
        "config": {
            "mock_tools": ["lookup"],
            "mock_connect_delay": delay,
        },
        "tools": ["lookup"] if running else [],
        "errlogs": [],
        "last_error": None,
    }


@pytest.mark.asyncio
async def test_mock_context_mcp_local_contract_and_alias() -> None:
    ctx = MockContext(
        plugin_id="sdk-demo",
        plugin_metadata={
            "local_mcp_servers": {
                "demo": _local_server_payload("demo", running=True),
            }
        },
    )

    assert ctx.mcp is ctx.mcp_manager

    await exercise_local_mcp_contract(_MockMCPBackend(ctx))


@pytest.mark.asyncio
async def test_mock_context_mcp_wait_until_ready_success_and_timeout() -> None:
    ctx = MockContext(
        plugin_id="sdk-demo",
        plugin_metadata={
            "local_mcp_servers": {
                "demo": _local_server_payload("demo", running=False, delay=0.01),
                "slow": _local_server_payload("slow", running=False, delay=0.2),
            }
        },
    )

    ready = await ctx.mcp.wait_until_ready("demo", timeout=0.1)
    assert ready.running is True
    assert ready.tools == ["lookup"]

    with pytest.raises(TimeoutError):
        await ctx.mcp.wait_until_ready("slow", timeout=0.01)


@pytest.mark.asyncio
async def test_mock_context_mcp_session_round_trip_and_tool_loop_isolation() -> None:
    ctx = MockContext(plugin_id="sdk-demo")

    async with ctx.mcp.session(
        "adhoc",
        {
            "mock_tools": ["inspect"],
            "mock_tool_results": {"inspect": {"ok": True}},
        },
        timeout=0.1,
    ) as session:
        assert await session.list_tools() == ["inspect"]
        assert await session.call_tool("inspect", {"x": 1}) == {"ok": True}
        tool_loop = await ctx.tool_loop_agent(prompt="hello mcp")
        assert "inspect" not in tool_loop.text

    assert ctx.router._mcp_session_store == {}


@pytest.mark.asyncio
async def test_mock_context_local_mcp_tools_are_plugin_scoped() -> None:
    ctx_a = MockContext(
        plugin_id="plugin-a",
        plugin_metadata={
            "local_mcp_servers": {
                "alpha": {
                    "name": "alpha",
                    "scope": "local",
                    "active": True,
                    "running": True,
                    "config": {"mock_tools": ["lookup"]},
                    "tools": ["lookup"],
                    "errlogs": [],
                    "last_error": None,
                }
            }
        },
    )
    ctx_b = MockContext(
        plugin_id="plugin-b",
        plugin_metadata={
            "local_mcp_servers": {
                "beta": {
                    "name": "beta",
                    "scope": "local",
                    "active": True,
                    "running": True,
                    "config": {"mock_tools": ["lookup"]},
                    "tools": ["lookup"],
                    "errlogs": [],
                    "last_error": None,
                }
            }
        },
    )

    resp_a = await ctx_a.tool_loop_agent(prompt="hello")
    resp_b = await ctx_b.tool_loop_agent(prompt="hello")

    assert "mcp.alpha.lookup" in resp_a.text
    assert "mcp.beta.lookup" not in resp_a.text
    assert "mcp.beta.lookup" in resp_b.text
    assert "mcp.alpha.lookup" not in resp_b.text
    assert ctx_a.router._mcp_global_servers == {}
    assert ctx_b.router._mcp_global_servers == {}


@pytest.mark.asyncio
async def test_mock_context_global_mcp_requires_ack_and_audits() -> None:
    plain_ctx = MockContext(plugin_id="plain-plugin")
    with pytest.raises(PermissionError):
        await plain_ctx.mcp.register_global_server(
            "global-demo",
            {"mock_tools": ["inspect"]},
        )
    with pytest.raises(PermissionError):
        await plain_ctx.mcp.list_global_servers()
    with pytest.raises(PermissionError):
        await plain_ctx.mcp.get_global_server("global-demo")

    ctx = MockContext(
        plugin_id="privileged-plugin",
        plugin_metadata={"acknowledge_global_mcp_risk": True},
    )
    record = await ctx.mcp.register_global_server(
        "global-demo",
        {"mock_tools": ["inspect"]},
    )

    assert record.scope.value == "global"
    assert record.running is True
    assert [item.name for item in await ctx.mcp.list_global_servers()] == [
        "global-demo"
    ]
    assert (await ctx.mcp.get_global_server("global-demo")).name == "global-demo"
    assert ctx.router._mcp_audit_logs == [
        {
            "plugin_id": "privileged-plugin",
            "action": "register",
            "server_name": "global-demo",
            "request_id": "local_0001",
        }
    ]
