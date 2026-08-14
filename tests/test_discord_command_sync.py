import asyncio
from types import SimpleNamespace
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
    monkeypatch.setattr(
        discord_platform_adapter.discord,
        "Option",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        discord_platform_adapter.discord,
        "SlashCommand",
        lambda **kwargs: SimpleNamespace(**kwargs),
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

    adapter.client.sync_commands.assert_awaited_once_with(check_guilds=[])
    warning.assert_called_once()
    assert "30034" in warning.call_args.args[0]


@pytest.mark.asyncio
async def test_discord_command_sync_removes_disabled_commands(monkeypatch):
    from astrbot.core.platform.sources.discord import discord_platform_adapter
    from astrbot.core.star.filter.command import CommandFilter

    adapter = _build_adapter(monkeypatch)
    handler = SimpleNamespace(
        handler_module_path="test_plugin",
        enabled=True,
        event_filters=[CommandFilter("ping")],
        desc="Ping command",
    )
    monkeypatch.setattr(discord_platform_adapter, "star_handlers_registry", [handler])
    monkeypatch.setattr(
        discord_platform_adapter,
        "star_map",
        {"test_plugin": SimpleNamespace(activated=True)},
    )

    await adapter._collect_and_register_commands()

    assert adapter.client.add_application_command.call_count == 1
    assert len(adapter._managed_application_commands) == 1
    assert adapter.client.sync_commands.await_args_list[0].kwargs["check_guilds"] == []

    handler.enabled = False
    await adapter._collect_and_register_commands()

    assert adapter.client.remove_application_command.call_count == 1
    assert adapter.client.sync_commands.await_args_list[1].kwargs["check_guilds"] == []
    assert adapter._managed_application_commands == []


@pytest.mark.asyncio
async def test_discord_command_sync_checks_debug_guild_when_empty(monkeypatch):
    adapter = _build_adapter(monkeypatch)
    adapter.guild_id = 123456

    await adapter._collect_and_register_commands()

    adapter.client.sync_commands.assert_awaited_once_with(check_guilds=[123456])


@pytest.mark.asyncio
async def test_discord_command_sync_rolls_back_local_registry_on_failure(monkeypatch):
    adapter = _build_adapter(monkeypatch)
    previous_command = Mock(name="previous_command")
    adapter._managed_application_commands = [previous_command]
    adapter.client.sync_commands.side_effect = DiscordSyncError("sync failed", code=50000)

    await adapter._collect_and_register_commands()

    assert adapter._managed_application_commands == [previous_command]
    adapter.client.remove_application_command.assert_called_once_with(previous_command)
    adapter.client.add_application_command.assert_called_once_with(previous_command)
