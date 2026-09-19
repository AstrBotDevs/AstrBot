from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.dashboard.services import command_service as command_service_module
from astrbot.dashboard.services.command_service import CommandService


@pytest.mark.asyncio
async def test_toggle_command_refreshes_platform_commands(monkeypatch):
    platform = SimpleNamespace(refresh_registered_commands=AsyncMock())
    platform_manager = SimpleNamespace(get_insts=lambda: [platform])
    lifecycle = SimpleNamespace(platform_manager=platform_manager)
    service = CommandService({}, lifecycle)
    toggle = AsyncMock()
    monkeypatch.setattr(command_service_module, "toggle_command", toggle)
    monkeypatch.setattr(
        command_service_module,
        "list_commands",
        AsyncMock(
            return_value=[
                {
                    "handler_full_name": "plugin.handler",
                    "enabled": False,
                }
            ]
        ),
    )

    payload = await service.toggle_command("plugin.handler", False)

    toggle.assert_awaited_once_with("plugin.handler", False)
    platform.refresh_registered_commands.assert_awaited_once()
    assert payload["enabled"] is False


@pytest.mark.asyncio
async def test_rename_command_refreshes_platform_commands(monkeypatch):
    platform = SimpleNamespace(refresh_registered_commands=AsyncMock())
    platform_manager = SimpleNamespace(get_insts=lambda: [platform])
    lifecycle = SimpleNamespace(platform_manager=platform_manager)
    service = CommandService({}, lifecycle)
    rename = AsyncMock()
    monkeypatch.setattr(command_service_module, "rename_command", rename)
    monkeypatch.setattr(
        command_service_module,
        "list_commands",
        AsyncMock(
            return_value=[
                {
                    "handler_full_name": "plugin.handler",
                    "enabled": True,
                    "effective_command": "renamed",
                }
            ]
        ),
    )

    payload = await service.rename_command("plugin.handler", "renamed", aliases=["r"])

    rename.assert_awaited_once_with("plugin.handler", "renamed", aliases=["r"])
    platform.refresh_registered_commands.assert_awaited_once()
    assert payload["effective_command"] == "renamed"
