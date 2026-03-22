from __future__ import annotations

import asyncio

import pytest

from tests.fixtures.mocks.discord import (  # noqa: F401
    MockDiscordBuilder,
    mock_discord_modules,
)


@pytest.mark.asyncio
async def test_collect_and_register_commands_ignores_daily_create_limit() -> None:
    from astrbot.core.platform.sources.discord import discord_platform_adapter as module

    DiscordPlatformAdapter = module.DiscordPlatformAdapter
    HTTPException = module.HTTPException

    adapter = DiscordPlatformAdapter(
        platform_config={"id": "discord", "discord_token": "token"},
        platform_settings={},
        event_queue=asyncio.Queue(),
    )
    adapter.client = MockDiscordBuilder.create_client()

    exc = HTTPException("daily limit")
    exc.code = 30034  # type: ignore[attr-defined]
    adapter.client.sync_commands.side_effect = exc

    await adapter._collect_and_register_commands()

    adapter.client.sync_commands.assert_awaited_once()


@pytest.mark.asyncio
async def test_terminate_skips_command_cleanup() -> None:
    from astrbot.core.platform.sources.discord.discord_platform_adapter import (
        DiscordPlatformAdapter,
    )

    adapter = DiscordPlatformAdapter(
        platform_config={"id": "discord", "discord_token": "token"},
        platform_settings={},
        event_queue=asyncio.Queue(),
    )
    adapter.client = MockDiscordBuilder.create_client()
    adapter.client.close.return_value = None
    adapter._polling_task = None

    await adapter.terminate()

    adapter.client.sync_commands.assert_not_called()
    adapter.client.close.assert_awaited_once()
