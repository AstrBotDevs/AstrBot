"""Check externally visible management behavior after shared implementation changes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.dashboard.routes import command as command_route
from astrbot.dashboard.routes import cron as cron_route
from astrbot.dashboard.routes import tools as tools_route
from astrbot.dashboard.services import command_service
from astrbot.dashboard.services.config_service import ConfigProfileService
from astrbot.dashboard.services.tools_service import ToolsService


class _Request:
    def __init__(self, value):
        self.value = value
        self.reads = 0

    @property
    def json(self):
        async def read():
            self.reads += 1
            return self.value

        return read()


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
async def test_server_list_preserves_adapter_connection_fields(legacy):
    runtime = SimpleNamespace(
        client=SimpleNamespace(
            tools=[SimpleNamespace(name="search")], server_errlogs="log"
        )
    )
    manager = SimpleNamespace(
        load_mcp_config=lambda: {
            "mcpServers": {
                "bad": [],
                "live": {"active": False, "url": "local"},
                "off": {},
            }
        },
        mcp_server_runtime_view={"live": runtime},
    )
    instance = object.__new__(tools_route.ToolsRoute if legacy else ToolsService)
    instance.tool_mgr = manager
    result = (
        (await instance.get_mcp_servers())["data"]
        if legacy
        else instance.get_mcp_servers()
    )
    expected = [
        {
            "name": "live",
            "active": False,
            "url": "local",
            "tools": ["search"],
            "errlogs": "log",
        },
        {"name": "off", "active": True, "tools": []},
    ]
    if not legacy:
        expected[0]["connected"] = True
        expected[1]["connected"] = False
    assert result == expected


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("mode", ["present", "absent", "failure"])
def test_server_rollback_preserves_failure_and_absent_semantics(legacy, mode):
    config = {"mcpServers": {"server": {"url": "local"}} if mode != "absent" else {}}
    manager = SimpleNamespace(
        load_mcp_config=Mock(return_value=config),
        save_mcp_config=Mock(return_value=True),
    )
    if mode == "failure":
        manager.save_mcp_config.side_effect = OSError("disk unavailable")
    instance = object.__new__(tools_route.ToolsRoute if legacy else ToolsService)
    instance.tool_mgr = manager
    rollback = instance._rollback_mcp_server if legacy else instance.rollback_mcp_server
    assert rollback("server") is (mode != "failure")
    assert "server" not in config["mcpServers"]
    if mode == "absent":
        manager.save_mcp_config.assert_not_called()
    else:
        manager.save_mcp_config.assert_called_once_with(config)


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
async def test_active_update_retains_each_adapters_connected_field_policy(
    monkeypatch, legacy
):
    config = {
        "mcpServers": {"server": {"active": True, "url": "https://example.test/mcp"}}
    }
    manager = SimpleNamespace(
        load_mcp_config=Mock(return_value=config),
        save_mcp_config=Mock(return_value=True),
        mcp_server_runtime_view={},
        enable_mcp_server=AsyncMock(),
        disable_mcp_server=AsyncMock(),
    )
    payload = {"name": "server", "active": False, "connected": False}
    instance = object.__new__(tools_route.ToolsRoute if legacy else ToolsService)
    instance.tool_mgr = manager
    if legacy:
        monkeypatch.setattr(tools_route, "request", _Request(payload))
        result = await instance.update_mcp_server()
        assert result["status"] == "ok"
        expected = {"active": False, "connected": False}
    else:
        assert (
            await instance.update_mcp_server(payload)
            == "Successfully updated MCP server server"
        )
        expected = {"active": False, "url": "https://example.test/mcp"}
    assert config["mcpServers"]["server"] == expected
    manager.save_mcp_config.assert_called_once_with(config)
    manager.enable_mcp_server.assert_not_awaited()
    manager.disable_mcp_server.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["rename", "delete"])
@pytest.mark.parametrize(
    "payload,message",
    [
        (None, "缺少配置数据"),
        ({}, "缺少配置数据"),
        ({"name": "new"}, "缺少配置文件 ID"),
        ({"id": 0}, "缺少配置文件 ID"),
    ],
)
async def test_profile_payload_rejects_missing_identity_before_mutation(
    operation, payload, message
):
    service = object.__new__(ConfigProfileService)
    service.rename_profile = AsyncMock()
    service.delete_profile = AsyncMock()
    with pytest.raises(ValueError, match=message):
        await getattr(service, f"{operation}_profile_from_dashboard_payload")(payload)
    service.rename_profile.assert_not_awaited()
    service.delete_profile.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["rename", "delete"])
async def test_profile_payload_preserves_numeric_identity_conversion(operation):
    service = object.__new__(ConfigProfileService)
    service.rename_profile = AsyncMock()
    service.delete_profile = AsyncMock()
    await getattr(service, f"{operation}_profile_from_dashboard_payload")(
        {"id": 7, "name": "new"}
    )
    if operation == "rename":
        service.rename_profile.assert_awaited_once_with("7", name="new")
    else:
        service.delete_profile.assert_awaited_once_with("7")


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
async def test_command_payload_uses_adapter_loader_and_first_matching_identity(
    monkeypatch, legacy
):
    module = command_route if legacy else command_service
    first = {"handler_full_name": "plugin.command", "enabled": True}
    load = AsyncMock(
        return_value=[{"handler_full_name": "other"}, first, dict(first, enabled=False)]
    )
    monkeypatch.setattr(module, "list_commands", load)
    lookup = (
        module._get_command_payload
        if legacy
        else module.CommandService._get_command_payload
    )
    assert await lookup("plugin.command") is first
    assert await lookup("missing") == {}
    assert load.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["create_job", "update_job"])
@pytest.mark.parametrize("manager_exists", [False, True])
async def test_legacy_cron_request_errors_preserve_message_and_read_order(
    monkeypatch, operation, manager_exists
):
    request = _Request([])
    manager = SimpleNamespace(
        add_active_job=AsyncMock(), db=SimpleNamespace(get_cron_job=AsyncMock())
    )
    route = object.__new__(cron_route.CronRoute)
    route.core_lifecycle = SimpleNamespace(
        cron_manager=manager if manager_exists else None
    )
    monkeypatch.setattr(cron_route, "request", request)
    monkeypatch.setattr(cron_route, "jsonify", lambda value: value)
    args = ("job",) if operation == "update_job" else ()
    result = await getattr(route, operation)(*args)
    assert result["message"] == (
        "Invalid payload" if manager_exists else "Cron manager not initialized"
    )
    assert request.reads == int(manager_exists)
    manager.add_active_job.assert_not_awaited()
    manager.db.get_cron_job.assert_not_awaited()
