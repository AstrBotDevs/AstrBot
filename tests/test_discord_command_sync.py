"""Check command-sync error handling with the real Discord HTTP exception."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from astrbot.core.platform.sources.discord import discord_platform_adapter as module


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [30034, 50013])
async def test_command_sync_logs_failure_without_repeating_api_call(monkeypatch, code):
    monkeypatch.setattr(module, "star_handlers_registry", [])
    warning = Mock()
    monkeypatch.setattr(module.logger, "warning", warning)
    adapter = module.DiscordPlatformAdapter(
        {"discord_command_register": True}, {}, asyncio.Queue()
    )
    response = SimpleNamespace(status=403, reason="Forbidden", headers={})
    error = discord.HTTPException(
        response, {"code": code, "message": "command sync rejected"}
    )
    adapter.client = SimpleNamespace(sync_commands=AsyncMock(side_effect=error))

    await adapter._collect_and_register_commands()

    adapter.client.sync_commands.assert_awaited_once_with()
    warning.assert_called_once()
    if code == 30034:
        assert "30034" in warning.call_args.args[0]
    else:
        assert warning.call_args.args[-1] is error
