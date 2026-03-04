import json

import pytest

from astrbot.core.provider import func_tool_manager
from astrbot.core.provider.func_tool_manager import FunctionToolManager


@pytest.fixture
def mcp_init_harness(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    manager = FunctionToolManager()
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    (data_dir / "mcp_server.json").write_text(
        json.dumps({"mcpServers": {"demo": {"active": True}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        func_tool_manager,
        "get_astrbot_data_path",
        lambda: data_dir,
    )

    called = {}

    async def fake_start_mcp_server(*, name, cfg, shutdown_event, timeout_seconds):
        called[name] = {
            "cfg": cfg,
            "shutdown_event_type": type(shutdown_event).__name__,
            "timeout_seconds": timeout_seconds,
        }

    monkeypatch.setattr(manager, "_start_mcp_server", fake_start_mcp_server)
    return manager, called


def assert_demo_init_result(summary, called, *, timeout_seconds: float) -> None:
    assert summary.total == 1
    assert summary.success == 1
    assert summary.failed == []
    assert called["demo"]["cfg"] == {"active": True}
    assert called["demo"]["shutdown_event_type"] == "Event"
    assert called["demo"]["timeout_seconds"] == timeout_seconds


@pytest.mark.asyncio
async def test_init_mcp_clients_passes_timeout_seconds_keyword(mcp_init_harness):
    manager, called = mcp_init_harness

    summary = await manager.init_mcp_clients()

    assert_demo_init_result(
        summary,
        called,
        timeout_seconds=manager._init_timeout_default,
    )


@pytest.mark.asyncio
async def test_init_mcp_clients_passes_overridden_init_timeout(
    mcp_init_harness,
):
    manager, called = mcp_init_harness

    summary = await manager.init_mcp_clients(init_timeout=3.5)

    assert_demo_init_result(summary, called, timeout_seconds=3.5)


@pytest.mark.asyncio
async def test_init_mcp_clients_reads_env_timeout_when_not_overridden(
    mcp_init_harness,
    monkeypatch: pytest.MonkeyPatch,
):
    manager, called = mcp_init_harness
    manager._init_timeout_default = 20.0  # ensure env override is observable
    monkeypatch.setenv("ASTRBOT_MCP_INIT_TIMEOUT", "3.5")

    summary = await manager.init_mcp_clients()

    assert_demo_init_result(summary, called, timeout_seconds=3.5)


@pytest.mark.asyncio
async def test_init_mcp_clients_prefers_explicit_timeout_over_env(
    mcp_init_harness,
    monkeypatch: pytest.MonkeyPatch,
):
    manager, called = mcp_init_harness
    monkeypatch.setenv("ASTRBOT_MCP_INIT_TIMEOUT", "7.0")

    summary = await manager.init_mcp_clients(init_timeout=3.5)

    assert_demo_init_result(summary, called, timeout_seconds=3.5)
