import json

import pytest

from astrbot.core.provider import func_tool_manager
from astrbot.core.provider.func_tool_manager import FunctionToolManager


@pytest.mark.asyncio
async def test_init_mcp_clients_passes_timeout_seconds_keyword(
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

    summary = await manager.init_mcp_clients()

    assert summary.total == 1
    assert summary.success == 1
    assert summary.failed == []
    assert called["demo"]["cfg"] == {"active": True}
    assert called["demo"]["shutdown_event_type"] == "Event"
    assert called["demo"]["timeout_seconds"] == manager._init_timeout_default


@pytest.mark.asyncio
async def test_init_mcp_clients_passes_overridden_init_timeout(
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

    summary = await manager.init_mcp_clients(init_timeout=3.5)

    assert summary.total == 1
    assert summary.success == 1
    assert summary.failed == []
    assert called["demo"]["cfg"] == {"active": True}
    assert called["demo"]["shutdown_event_type"] == "Event"
    assert called["demo"]["timeout_seconds"] == 3.5


@pytest.mark.asyncio
async def test_init_mcp_clients_reads_env_timeout_when_not_overridden(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    manager = FunctionToolManager()
    manager._init_timeout_default = 20.0  # ensure env override is observable
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
    monkeypatch.setenv("ASTRBOT_MCP_INIT_TIMEOUT", "3.5")

    called = {}

    async def fake_start_mcp_server(*, name, cfg, shutdown_event, timeout_seconds):
        called[name] = {
            "cfg": cfg,
            "shutdown_event_type": type(shutdown_event).__name__,
            "timeout_seconds": timeout_seconds,
        }

    monkeypatch.setattr(manager, "_start_mcp_server", fake_start_mcp_server)

    summary = await manager.init_mcp_clients()

    assert summary.total == 1
    assert summary.success == 1
    assert summary.failed == []
    assert called["demo"]["cfg"] == {"active": True}
    assert called["demo"]["shutdown_event_type"] == "Event"
    assert called["demo"]["timeout_seconds"] == 3.5
