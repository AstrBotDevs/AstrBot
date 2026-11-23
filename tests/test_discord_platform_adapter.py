"""Exercise Discord registration and shutdown with real Pycord types."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from astrbot.core.platform.sources.discord import discord_platform_adapter as module


@pytest.fixture
def adapter(monkeypatch):
    """Create an adapter with fixture-owned transport boundaries."""
    monkeypatch.setattr(module, "star_handlers_registry", [])
    result = module.DiscordPlatformAdapter(
        {"id": "discord", "discord_token": "test-token"}, {}, asyncio.Queue()
    )
    result.client = SimpleNamespace(
        sync_commands=AsyncMock(), close=AsyncMock(), add_application_command=Mock()
    )
    return result


@pytest.mark.asyncio
async def test_collect_and_register_commands_ignores_daily_create_limit(adapter):
    response = SimpleNamespace(status=400, reason="Bad Request", headers={})
    adapter.client.sync_commands.side_effect = discord.HTTPException(
        response, {"code": 30034, "message": "daily limit"}
    )

    await adapter._collect_and_register_commands()

    adapter.client.sync_commands.assert_awaited_once_with()
    adapter.client.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_terminate_skips_command_cleanup_before_polling(adapter):
    assert adapter._polling_task is None

    await adapter.terminate()

    assert adapter.shutdown_event.is_set()
    adapter.client.sync_commands.assert_not_awaited()
    adapter.client.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_sdk_bridge_builds_real_slash_commands_and_filters_invalid_names(adapter):
    candidates = [
        {"name": "hello", "description": "A" * 120},
        {"name": "Invalid Name", "description": "invalid"},
        {"name": "", "description": "empty"},
    ]
    bridge = SimpleNamespace(
        list_native_command_candidates=Mock(return_value=candidates)
    )
    adapter.sdk_plugin_bridge = bridge

    await adapter._collect_and_register_commands()

    bridge.list_native_command_candidates.assert_called_once_with("discord")
    adapter.client.add_application_command.assert_called_once()
    command = adapter.client.add_application_command.call_args.args[0]
    assert isinstance(command, discord.SlashCommand)
    assert command.name == "hello"
    assert command.description == "A" * 97 + "..."
    assert [option.name for option in command.options] == ["params"]
    assert command.options[0].required is False
    adapter.client.sync_commands.assert_awaited_once_with()
