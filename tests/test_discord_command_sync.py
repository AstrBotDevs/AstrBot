import asyncio
from unittest.mock import Mock

import pytest

from tests.fixtures.mocks.discord import (
    MockDiscordBuilder,
    mock_discord_modules,  # noqa: F401
)


class DiscordSyncError(Exception):
    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


def _build_adapter(monkeypatch: pytest.MonkeyPatch):
    from astrbot.core.platform.sources.discord import discord_platform_adapter
    from astrbot.core.platform.sources.discord.discord_platform_adapter import (
        DiscordPlatformAdapter,
    )

    monkeypatch.setattr(discord_platform_adapter, "star_handlers_registry", [])
    monkeypatch.setattr(
        discord_platform_adapter.discord,
        "HTTPException",
        DiscordSyncError,
        raising=False,
    )

    adapter = DiscordPlatformAdapter(
        {"discord_command_register": True},
        {},
        asyncio.Queue(),
    )
    adapter.client = MockDiscordBuilder.create_client()
    return adapter


@pytest.mark.asyncio
async def test_discord_command_sync_ignores_daily_quota(monkeypatch):
    from astrbot.core.platform.sources.discord import discord_platform_adapter

    adapter = _build_adapter(monkeypatch)
    warning = Mock()
    monkeypatch.setattr(discord_platform_adapter.logger, "warning", warning)
    adapter.client.sync_commands.side_effect = DiscordSyncError(
        "Max number of daily application command creates reached",
        code=30034,
    )

    await adapter._collect_and_register_commands()

    adapter.client.sync_commands.assert_awaited_once()
    warning.assert_called_once()
    assert "30034" in warning.call_args.args[0]
