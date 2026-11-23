"""Use real Discord SDK types and isolated client transports."""

from unittest.mock import AsyncMock, MagicMock

import pytest


def create_mock_discord_modules():
    """Return the real SDK for callers migrating from legacy module mocks."""
    import discord
    import discord.abc
    import discord.channel
    import discord.errors
    import discord.types.interactions
    import discord.ui

    return discord


@pytest.fixture(autouse=True)
def mock_discord_modules(monkeypatch, isolated_runtime_config):
    """Replace the adapter client factory without changing imported modules."""
    from astrbot.core.platform.sources.discord import discord_platform_adapter

    factory = MagicMock(
        side_effect=lambda *args, **kwargs: MockDiscordBuilder.create_client()
    )
    monkeypatch.setattr(discord_platform_adapter, "DiscordBotClient", factory)
    return factory


class MockDiscordBuilder:
    """Build isolated Discord client transports."""

    @staticmethod
    def create_client():
        """Create a client whose network methods are asynchronous doubles."""
        client = MagicMock()
        client.user = MagicMock()
        client.user.id = 123456789
        client.user.display_name = "TestBot"
        client.user.name = "TestBot"
        client.get_channel = MagicMock()
        client.fetch_channel = AsyncMock()
        client.get_message = MagicMock()
        client.start = AsyncMock()
        client.close = AsyncMock()
        client.is_closed = MagicMock(return_value=False)
        client.add_application_command = MagicMock()
        client.sync_commands = AsyncMock()
        client.change_presence = AsyncMock()
        return client
