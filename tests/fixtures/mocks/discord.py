"""Discord 模块 Mock 工具。

提供统一的 Discord 相关模块 mock 设置，避免在测试文件中重复定义。
"""

import sys
from unittest.mock import AsyncMock, MagicMock

import pytest


def create_mock_discord_modules():
    """创建 Discord 相关的 mock 模块。

    Returns:
        dict: 包含 discord 和相关模块的 mock 对象
    """
    mock_discord = MagicMock()

    # Mock discord.Intents
    mock_intents = MagicMock()
    mock_intents.default = MagicMock(return_value=mock_intents)
    mock_discord.Intents = mock_intents

    # Mock discord.Status
    mock_discord.Status = MagicMock()
    mock_discord.Status.online = "online"

    # Mock discord.Bot
    mock_bot = MagicMock()
    mock_discord.Bot = MagicMock(return_value=mock_bot)

    # Mock discord.Embed
    mock_embed = MagicMock()
    mock_discord.Embed = MagicMock(return_value=mock_embed)

    # Mock discord.ui
    mock_ui = MagicMock()
    mock_ui.View = MagicMock
    mock_ui.Button = MagicMock
    mock_discord.ui = mock_ui

    # Mock discord.Message
    mock_discord.Message = MagicMock

    # Mock discord.Interaction
    mock_discord.Interaction = MagicMock
    mock_discord.InteractionType = MagicMock()
    mock_discord.InteractionType.application_command = 2
    mock_discord.InteractionType.component = 3

    # Mock discord.File
    mock_discord.File = MagicMock

    # Mock discord.SlashCommand
    mock_discord.SlashCommand = MagicMock

    # Mock discord.Option
    mock_discord.Option = MagicMock

    # Mock discord.SlashCommandOptionType
    mock_discord.SlashCommandOptionType = MagicMock()
    mock_discord.SlashCommandOptionType.string = 3

    # Mock discord.errors
    mock_discord.errors = MagicMock()
    mock_discord.errors.LoginFailure = Exception
    mock_discord.errors.ConnectionClosed = Exception
    mock_discord.errors.NotFound = Exception
    mock_discord.errors.Forbidden = Exception

    # Mock discord.abc
    mock_discord.abc = MagicMock()
    mock_discord.abc.GuildChannel = MagicMock
    mock_discord.abc.Messageable = MagicMock
    mock_discord.abc.PrivateChannel = MagicMock

    # Mock discord.channel
    mock_channel = MagicMock()
    mock_channel.DMChannel = MagicMock
    mock_discord.channel = mock_channel

    # Mock discord.types
    mock_discord.types = MagicMock()
    mock_discord.types.interactions = MagicMock()

    # Mock discord.ApplicationContext
    mock_discord.ApplicationContext = MagicMock

    # Mock discord.CustomActivity
    mock_discord.CustomActivity = MagicMock

    return mock_discord


@pytest.fixture(scope="module", autouse=True)
def mock_discord_modules():
    """Mock Discord 相关模块的 fixture。

    自动应用于使用此 fixture 的测试模块。
    """
    mock_discord = create_mock_discord_modules()
    monkeypatch = pytest.MonkeyPatch()

    monkeypatch.setitem(sys.modules, "discord", mock_discord)
    monkeypatch.setitem(sys.modules, "discord.abc", mock_discord.abc)
    monkeypatch.setitem(sys.modules, "discord.channel", mock_discord.channel)
    monkeypatch.setitem(sys.modules, "discord.errors", mock_discord.errors)
    monkeypatch.setitem(sys.modules, "discord.types", mock_discord.types)
    monkeypatch.setitem(
        sys.modules,
        "discord.types.interactions",
        mock_discord.types.interactions,
    )
    monkeypatch.setitem(sys.modules, "discord.ui", mock_discord.ui)
    yield
    monkeypatch.undo()


class MockDiscordBuilder:
    """构建 Discord 测试 mock 对象的工具类。"""

    @staticmethod
    def create_client():
        """创建 mock Discord client 实例。"""
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
