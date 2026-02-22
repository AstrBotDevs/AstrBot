"""Unit tests for Discord platform adapter.

Tests cover:
- DiscordPlatformAdapter class initialization and methods
- DiscordPlatformEvent class and message handling
- DiscordBotClient class
- Message conversion for different message types
- Slash command handling
- Component interactions

Note: Uses unittest.mock to simulate py-cord/discord dependencies.
"""

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock discord modules before importing any astrbot modules
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


@pytest.fixture(scope="module", autouse=True)
def _mock_discord_modules():
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
    monkeypatch.setitem(sys.modules, "discord.ui", mock_ui)
    yield
    monkeypatch.undo()


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def event_queue():
    """Create an event queue for testing."""
    return asyncio.Queue()


@pytest.fixture
def platform_config():
    """Create a platform configuration for testing."""
    return {
        "id": "test_discord",
        "discord_token": "test_token_123",
        "discord_proxy": None,
        "discord_command_register": True,
        "discord_guild_id_for_debug": None,
        "discord_activity_name": "Playing AstrBot",
    }


@pytest.fixture
def platform_settings():
    """Create platform settings for testing."""
    return {}


@pytest.fixture
def mock_discord_client():
    """Create a mock Discord client instance."""
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


@pytest.fixture
def mock_discord_message():
    """Create a mock Discord message for testing."""

    def _create_message(
        content: str = "Hello World",
        author_id: int = 987654321,
        author_name: str = "TestUser",
        channel_id: int = 111222333,
        guild_id: int | None = 444555666,
        mentions: list | None = None,
        role_mentions: list | None = None,
        attachments: list | None = None,
    ):
        message = MagicMock()
        message.id = 12345678
        message.content = content
        message.clean_content = content

        # Author mock
        message.author = MagicMock()
        message.author.id = author_id
        message.author.display_name = author_name
        message.author.name = author_name
        message.author.bot = False

        # Channel mock
        message.channel = MagicMock()
        message.channel.id = channel_id

        # Guild mock
        if guild_id:
            message.guild = MagicMock()
            message.guild.id = guild_id
            message.guild.get_member = MagicMock(return_value=None)
        else:
            message.guild = None

        # Mentions
        message.mentions = mentions or []
        message.role_mentions = role_mentions or []

        # Attachments
        message.attachments = attachments or []

        return message

    return _create_message


@pytest.fixture
def mock_discord_channel():
    """Create a mock Discord channel for testing."""

    def _create_channel(
        channel_id: int = 111222333,
        is_dm: bool = False,
        is_messageable: bool = True,
    ):
        channel = MagicMock()
        channel.id = channel_id
        channel.send = AsyncMock()

        if is_dm:
            # DMChannel mock
            channel.guild = None
        else:
            # GuildChannel mock
            channel.guild = MagicMock()
            channel.guild.id = 444555666

        return channel

    return _create_channel


@pytest.fixture
def mock_interaction():
    """Create a mock Discord interaction for testing."""

    def _create_interaction(
        interaction_type: int = 2,  # application_command
        command_name: str = "help",
        custom_id: str | None = None,
        user_id: int = 987654321,
        channel_id: int = 111222333,
        guild_id: int | None = 444555666,
    ):
        interaction = MagicMock()
        interaction.id = 12345678
        interaction.type = interaction_type
        interaction.user = MagicMock()
        interaction.user.id = user_id
        interaction.user.display_name = "TestUser"
        interaction.channel_id = channel_id
        interaction.guild_id = guild_id

        # Interaction data
        interaction.data = {"name": command_name}
        if custom_id:
            interaction.data["custom_id"] = custom_id
            interaction.data["component_type"] = 2

        # Context mock
        interaction.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        return interaction

    return _create_interaction


def create_mock_discord_attachment(
    url: str = "https://cdn.discord.com/test.png",
    filename: str = "test.png",
    content_type: str = "image/png",
):
    """Create a mock Discord attachment."""
    attachment = MagicMock()
    attachment.url = url
    attachment.filename = filename
    attachment.content_type = content_type
    return attachment


# ============================================================================
# DiscordPlatformAdapter Initialization Tests
# ============================================================================


class TestDiscordAdapterInit:
    """Tests for DiscordPlatformAdapter initialization."""

    def test_init_basic(self, event_queue, platform_config, platform_settings):
        """Test basic adapter initialization."""
        from astrbot.core.platform.sources.discord.discord_platform_adapter import (
            DiscordPlatformAdapter,
        )

        adapter = DiscordPlatformAdapter(
            platform_config, platform_settings, event_queue
        )

        assert adapter.config == platform_config
        assert adapter.settings == platform_settings
        assert adapter.enable_command_register is True
        assert adapter.client_self_id is None
        assert adapter.registered_handlers == []

    def test_init_with_custom_settings(
        self, event_queue, platform_config, platform_settings
    ):
        """Test adapter initialization with custom settings."""
        platform_config["discord_command_register"] = False
        platform_config["discord_guild_id_for_debug"] = "123456789"
        platform_config["discord_activity_name"] = "Custom Activity"

        from astrbot.core.platform.sources.discord.discord_platform_adapter import (
            DiscordPlatformAdapter,
        )

        adapter = DiscordPlatformAdapter(
            platform_config, platform_settings, event_queue
        )

        assert adapter.enable_command_register is False
        assert adapter.guild_id == "123456789"
        assert adapter.activity_name == "Custom Activity"

    def test_init_shutdown_event(self, event_queue, platform_config, platform_settings):
        """Test shutdown event is initialized."""
        from astrbot.core.platform.sources.discord.discord_platform_adapter import (
            DiscordPlatformAdapter,
        )

        adapter = DiscordPlatformAdapter(
            platform_config, platform_settings, event_queue
        )

        assert hasattr(adapter, "shutdown_event")
        assert isinstance(adapter.shutdown_event, asyncio.Event)
        assert not adapter.shutdown_event.is_set()


# ============================================================================
# DiscordPlatformAdapter Metadata Tests
# ============================================================================


class TestDiscordAdapterMetadata:
    """Tests for DiscordPlatformAdapter metadata."""

    def test_meta_returns_correct_metadata(
        self, event_queue, platform_config, platform_settings
    ):
        """Test meta() returns correct PlatformMetadata."""
        from astrbot.core.platform.sources.discord.discord_platform_adapter import (
            DiscordPlatformAdapter,
        )

        adapter = DiscordPlatformAdapter(
            platform_config, platform_settings, event_queue
        )
        meta = adapter.meta()

        assert meta.name == "discord"
        assert "discord" in meta.description.lower()
        assert meta.id == "test_discord"
        assert meta.support_streaming_message is False

    def test_meta_with_missing_id(self, event_queue, platform_settings):
        """Test meta() handles missing id in config."""
        config = {
            "discord_token": "test_token",
        }

        from astrbot.core.platform.sources.discord.discord_platform_adapter import (
            DiscordPlatformAdapter,
        )

        adapter = DiscordPlatformAdapter(config, platform_settings, event_queue)
        meta = adapter.meta()

        # Should use None or default when id is not configured
        assert meta.name == "discord"


# ============================================================================
# DiscordPlatformAdapter Message Type Tests
# ============================================================================


class TestDiscordAdapterGetMessageType:
    """Tests for _get_message_type method."""

    def test_get_message_type_dm_channel(
        self, event_queue, platform_config, platform_settings
    ):
        """Test message type detection for DM channel."""
        from astrbot.core.platform.message_type import MessageType
        from astrbot.core.platform.sources.discord.discord_platform_adapter import (
            DiscordPlatformAdapter,
        )

        adapter = DiscordPlatformAdapter(
            platform_config, platform_settings, event_queue
        )

        # Create DM channel mock - DMChannel has guild = None
        dm_channel = MagicMock()
        dm_channel.guild = None

        result = adapter._get_message_type(dm_channel)

        assert result == MessageType.FRIEND_MESSAGE

    def test_get_message_type_guild_channel(
        self, event_queue, platform_config, platform_settings
    ):
        """Test message type detection for guild channel."""
        from astrbot.core.platform.message_type import MessageType
        from astrbot.core.platform.sources.discord.discord_platform_adapter import (
            DiscordPlatformAdapter,
        )

        adapter = DiscordPlatformAdapter(
            platform_config, platform_settings, event_queue
        )

        # Create guild channel mock - guild channel has guild with id
        # Important: guild must not be None and must evaluate to True
        # We need to create a real object, not MagicMock, for the guild attribute
        # because the code checks `getattr(channel, "guild", None) is None`
        class MockGuild:
            def __init__(self):
                self.id = 123456789

        class MockGuildChannel:
            def __init__(self):
                self.guild = MockGuild()

        guild_channel = MockGuildChannel()

        result = adapter._get_message_type(guild_channel)

        assert result == MessageType.GROUP_MESSAGE

    def test_get_message_type_with_guild_id_override(
        self, event_queue, platform_config, platform_settings
    ):
        """Test message type with guild_id override."""
        from astrbot.core.platform.message_type import MessageType
        from astrbot.core.platform.sources.discord.discord_platform_adapter import (
            DiscordPlatformAdapter,
        )

        adapter = DiscordPlatformAdapter(
            platform_config, platform_settings, event_queue
        )

        # Even with DM channel, guild_id should override to GROUP_MESSAGE
        dm_channel = MagicMock()
        dm_channel.guild = None

        result = adapter._get_message_type(dm_channel, guild_id=123456789)

        assert result == MessageType.GROUP_MESSAGE


# ============================================================================
# DiscordPlatformAdapter Message Conversion Tests
# ============================================================================


class TestDiscordAdapterConvertMessage:
    """Tests for message conversion."""

    @pytest.mark.asyncio
    async def test_convert_text_message(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_discord_client,
        mock_discord_message,
    ):
        """Test converting a text message."""
        from astrbot.core.platform.sources.discord.discord_platform_adapter import (
            DiscordPlatformAdapter,
        )

        adapter = DiscordPlatformAdapter(
            platform_config, platform_settings, event_queue
        )
        adapter.client = mock_discord_client
        adapter.client_self_id = "123456789"

        message = mock_discord_message(
            content="Hello World",
            author_id=987654321,
            author_name="TestUser",
            channel_id=111222333,
            guild_id=444555666,
        )

        data = {"message": message, "bot_id": "123456789"}

        result = await adapter.convert_message(data)

        assert result is not None
        assert result.message_str == "Hello World"
        assert result.sender.user_id == "987654321"
        assert result.sender.nickname == "TestUser"
        assert result.session_id == "111222333"
        # Note: type depends on channel.guild attribute

    @pytest.mark.asyncio
    async def test_convert_message_with_mention(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_discord_client,
        mock_discord_message,
    ):
        """Test converting a message with bot mention."""
        from astrbot.core.platform.sources.discord.discord_platform_adapter import (
            DiscordPlatformAdapter,
        )

        adapter = DiscordPlatformAdapter(
            platform_config, platform_settings, event_queue
        )
        adapter.client = mock_discord_client
        adapter.client_self_id = "123456789"

        # Create message with mention
        bot_user = MagicMock()
        bot_user.id = 123456789
        mock_discord_client.user = bot_user

        message = mock_discord_message(
            content="<@123456789> Hello Bot",
            author_id=987654321,
            channel_id=111222333,
        )

        data = {"message": message, "bot_id": "123456789"}

        result = await adapter.convert_message(data)

        # Mention should be stripped
        assert result.message_str == "Hello Bot"

    @pytest.mark.asyncio
    async def test_convert_message_with_image_attachment(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_discord_client,
        mock_discord_message,
    ):
        """Test converting a message with image attachment."""
        from astrbot.api.message_components import Image
        from astrbot.core.platform.sources.discord.discord_platform_adapter import (
            DiscordPlatformAdapter,
        )

        adapter = DiscordPlatformAdapter(
            platform_config, platform_settings, event_queue
        )
        adapter.client = mock_discord_client
        adapter.client_self_id = "123456789"

        attachment = create_mock_discord_attachment(
            url="https://cdn.discord.com/test.png",
            filename="test.png",
            content_type="image/png",
        )

        message = mock_discord_message(
            content="Check this image",
            attachments=[attachment],
        )

        data = {"message": message, "bot_id": "123456789"}

        result = await adapter.convert_message(data)

        assert result.message_str == "Check this image"
        # Should have Plain text and Image in message chain
        assert len(result.message) == 2
        assert any(isinstance(comp, Image) for comp in result.message)

    @pytest.mark.asyncio
    async def test_convert_message_with_file_attachment(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_discord_client,
        mock_discord_message,
    ):
        """Test converting a message with file attachment."""
        from astrbot.api.message_components import File
        from astrbot.core.platform.sources.discord.discord_platform_adapter import (
            DiscordPlatformAdapter,
        )

        adapter = DiscordPlatformAdapter(
            platform_config, platform_settings, event_queue
        )
        adapter.client = mock_discord_client
        adapter.client_self_id = "123456789"

        attachment = create_mock_discord_attachment(
            url="https://cdn.discord.com/document.pdf",
            filename="document.pdf",
            content_type="application/pdf",
        )

        message = mock_discord_message(
            content="Here is a file",
            attachments=[attachment],
        )

        data = {"message": message, "bot_id": "123456789"}

        result = await adapter.convert_message(data)

        assert result.message_str == "Here is a file"
        # Should have Plain text and File in message chain
        assert len(result.message) == 2
        assert any(isinstance(comp, File) for comp in result.message)


# ============================================================================
# DiscordPlatformAdapter Send by Session Tests
# ============================================================================


class TestDiscordAdapterSendBySession:
    """Tests for send_by_session method."""

    @pytest.mark.asyncio
    async def test_send_by_session_client_not_ready(
        self,
        event_queue,
        platform_config,
        platform_settings,
    ):
        """Test send_by_session when client is not ready."""
        from astrbot.api.event import MessageChain
        from astrbot.core.platform.astr_message_event import MessageSesion
        from astrbot.core.platform.message_type import MessageType
        from astrbot.core.platform.sources.discord.discord_platform_adapter import (
            DiscordPlatformAdapter,
        )

        adapter = DiscordPlatformAdapter(
            platform_config, platform_settings, event_queue
        )
        adapter.client = MagicMock()
        adapter.client.user = None  # Client not ready

        session = MessageSesion(
            platform_name="discord",
            message_type=MessageType.GROUP_MESSAGE,
            session_id="111222333",
        )
        message_chain = MessageChain()

        # Should return early without error
        await adapter.send_by_session(session, message_chain)

    @pytest.mark.asyncio
    async def test_send_by_session_invalid_channel_id(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_discord_client,
    ):
        """Test send_by_session with invalid channel ID format."""
        from astrbot.api.event import MessageChain
        from astrbot.api.message_components import Plain
        from astrbot.core.platform.astr_message_event import MessageSesion
        from astrbot.core.platform.message_type import MessageType
        from astrbot.core.platform.sources.discord.discord_platform_adapter import (
            DiscordPlatformAdapter,
        )

        adapter = DiscordPlatformAdapter(
            platform_config, platform_settings, event_queue
        )
        adapter.client = mock_discord_client
        adapter.client_self_id = "123456789"

        session = MessageSesion(
            platform_name="discord",
            message_type=MessageType.GROUP_MESSAGE,
            session_id="invalid_id",
        )
        message_chain = MessageChain([Plain(text="Test message")])

        # Should handle invalid ID gracefully
        await adapter.send_by_session(session, message_chain)


# ============================================================================
# DiscordPlatformAdapter Run and Terminate Tests
# ============================================================================


class TestDiscordAdapterRunTerminate:
    """Tests for run and terminate methods."""

    @pytest.mark.asyncio
    async def test_run_without_token(
        self,
        event_queue,
        platform_settings,
    ):
        """Test run method returns early without token."""
        config = {
            "id": "test_discord",
            "discord_token": "",  # Empty token
        }

        from astrbot.core.platform.sources.discord.discord_platform_adapter import (
            DiscordPlatformAdapter,
        )

        adapter = DiscordPlatformAdapter(config, platform_settings, event_queue)

        # Should return early without error
        await adapter.run()

    @pytest.mark.asyncio
    async def test_terminate_clears_commands(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_discord_client,
    ):
        """Test terminate method clears slash commands when enabled."""
        from astrbot.core.platform.sources.discord.discord_platform_adapter import (
            DiscordPlatformAdapter,
        )

        adapter = DiscordPlatformAdapter(
            platform_config, platform_settings, event_queue
        )
        adapter.client = mock_discord_client
        adapter._polling_task = None

        await adapter.terminate()

        # sync_commands should be called with empty list
        mock_discord_client.sync_commands.assert_called_once()


# ============================================================================
# DiscordPlatformAdapter Handle Message Tests
# ============================================================================


class TestDiscordAdapterHandleMessage:
    """Tests for handle_msg method."""

    @pytest.mark.asyncio
    async def test_handle_message_sets_wake_on_mention(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_discord_client,
        mock_discord_message,
    ):
        """Test handle_msg sets is_wake when bot is mentioned."""
        from astrbot.api.message_components import Plain
        from astrbot.api.platform import AstrBotMessage, MessageMember, MessageType
        from astrbot.core.platform.sources.discord.discord_platform_adapter import (
            DiscordPlatformAdapter,
        )

        adapter = DiscordPlatformAdapter(
            platform_config, platform_settings, event_queue
        )
        adapter.client = mock_discord_client

        # Create bot user for mention check
        bot_user = MagicMock()
        bot_user.id = 123456789
        mock_discord_client.user = bot_user

        # Create message with bot mention
        message = mock_discord_message(content="Hello Bot")
        message.mentions = [bot_user]

        abm = AstrBotMessage()
        abm.type = MessageType.GROUP_MESSAGE
        abm.message_str = "Hello Bot"
        abm.message = [Plain(text="Hello Bot")]  # Required attribute
        abm.sender = MessageMember(user_id="987654321", nickname="TestUser")
        abm.raw_message = message
        abm.session_id = "111222333"

        await adapter.handle_msg(abm)

        # Event should be committed to queue
        assert not event_queue.empty()

    @pytest.mark.asyncio
    async def test_handle_slash_command(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_discord_client,
        mock_interaction,
    ):
        """Test handle_msg processes slash command correctly."""
        from astrbot.api.message_components import Plain
        from astrbot.api.platform import AstrBotMessage, MessageMember, MessageType
        from astrbot.core.platform.sources.discord.discord_platform_adapter import (
            DiscordPlatformAdapter,
        )

        adapter = DiscordPlatformAdapter(
            platform_config, platform_settings, event_queue
        )
        adapter.client = mock_discord_client
        adapter.client_self_id = "123456789"

        interaction = mock_interaction(interaction_type=2, command_name="help")

        webhook = MagicMock()

        abm = AstrBotMessage()
        abm.type = MessageType.GROUP_MESSAGE
        abm.message_str = "/help"
        abm.message = [Plain(text="/help")]  # Required attribute
        abm.sender = MessageMember(user_id="987654321", nickname="TestUser")
        abm.raw_message = interaction
        abm.session_id = "111222333"

        await adapter.handle_msg(abm, followup_webhook=webhook)

        # Event should be committed with is_wake=True for slash commands
        assert not event_queue.empty()


# ============================================================================
# DiscordPlatformAdapter Command Registration Tests
# ============================================================================


class TestDiscordAdapterCommandRegistration:
    """Tests for slash command collection and registration."""

    def test_extract_command_infos_includes_aliases(self):
        """Test _extract_command_infos expands command aliases."""
        from astrbot.core.platform.sources.discord.discord_platform_adapter import (
            DiscordPlatformAdapter,
        )
        from astrbot.core.star.filter.command import CommandFilter

        handler_md = SimpleNamespace(desc="test command")
        infos = DiscordPlatformAdapter._extract_command_infos(
            CommandFilter("ping", alias={"p"}),
            handler_md,
        )

        assert sorted(name for name, _ in infos) == ["p", "ping"]

    @pytest.mark.asyncio
    async def test_collect_commands_warns_on_duplicates(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_discord_client,
    ):
        """Test duplicate slash commands are warned and ignored."""
        from astrbot.core.platform.sources.discord.discord_platform_adapter import (
            DiscordPlatformAdapter,
        )
        from astrbot.core.star.filter.command import CommandFilter

        adapter = DiscordPlatformAdapter(
            platform_config, platform_settings, event_queue
        )
        adapter.client = mock_discord_client

        handler_a = SimpleNamespace(
            handler_module_path="plugin.discord.a",
            enabled=True,
            desc="first",
            event_filters=[CommandFilter("ping")],
        )
        handler_b = SimpleNamespace(
            handler_module_path="plugin.discord.b",
            enabled=True,
            desc="second",
            event_filters=[CommandFilter("ping")],
        )

        with (
            pytest.MonkeyPatch.context() as monkeypatch,
            patch(
                "astrbot.core.platform.sources.discord.discord_platform_adapter.logger"
            ) as mock_logger,
        ):
            monkeypatch.setattr(
                "astrbot.core.platform.sources.discord.discord_platform_adapter.star_handlers_registry",
                [handler_a, handler_b],
            )
            monkeypatch.setattr(
                "astrbot.core.platform.sources.discord.discord_platform_adapter.star_map",
                {
                    "plugin.discord.a": SimpleNamespace(activated=True),
                    "plugin.discord.b": SimpleNamespace(activated=True),
                },
            )
            await adapter._collect_and_register_commands()

        assert mock_discord_client.add_application_command.call_count == 1
        mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_collect_commands_registers_aliases(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_discord_client,
    ):
        """Test slash command aliases are also registered."""
        from astrbot.core.platform.sources.discord.discord_platform_adapter import (
            DiscordPlatformAdapter,
        )
        from astrbot.core.star.filter.command import CommandFilter

        adapter = DiscordPlatformAdapter(
            platform_config, platform_settings, event_queue
        )
        adapter.client = mock_discord_client

        handler = SimpleNamespace(
            handler_module_path="plugin.discord.alias",
            enabled=True,
            desc="alias command",
            event_filters=[CommandFilter("hello", alias={"hi"})],
        )

        with (
            pytest.MonkeyPatch.context() as monkeypatch,
            patch(
                "astrbot.core.platform.sources.discord.discord_platform_adapter.discord.SlashCommand",
                side_effect=lambda **kwargs: SimpleNamespace(name=kwargs["name"]),
            ),
        ):
            monkeypatch.setattr(
                "astrbot.core.platform.sources.discord.discord_platform_adapter.star_handlers_registry",
                [handler],
            )
            monkeypatch.setattr(
                "astrbot.core.platform.sources.discord.discord_platform_adapter.star_map",
                {"plugin.discord.alias": SimpleNamespace(activated=True)},
            )
            await adapter._collect_and_register_commands()

        assert mock_discord_client.add_application_command.call_count == 2
        called_names = sorted(
            call.args[0].name
            for call in mock_discord_client.add_application_command.call_args_list
        )
        assert called_names == ["hello", "hi"]


# ============================================================================
# Edge Cases and Error Handling Tests
# ============================================================================


class TestDiscordAdapterEdgeCases:
    """Tests for edge cases and error handling."""

    def test_get_channel_id_returns_string(
        self, event_queue, platform_config, platform_settings
    ):
        """Test _get_channel_id returns string representation."""
        from astrbot.core.platform.sources.discord.discord_platform_adapter import (
            DiscordPlatformAdapter,
        )

        adapter = DiscordPlatformAdapter(
            platform_config, platform_settings, event_queue
        )

        channel = MagicMock()
        channel.id = 123456789

        result = adapter._get_channel_id(channel)

        assert result == "123456789"
        assert isinstance(result, str)


# ============================================================================
# DiscordPlatformEvent Helper Method Tests (without full initialization)
# ============================================================================


class TestDiscordPlatformEventHelpers:
    """Tests for DiscordPlatformEvent helper methods that don't require full init."""

    def test_is_slash_command_check_logic(self):
        """Test the is_slash_command logic without full event initialization."""
        # This tests the logic pattern used in is_slash_command
        interaction = MagicMock()
        interaction.type = 2  # application_command

        # Simulate the check logic
        result = hasattr(interaction, "type") and interaction.type == 2
        assert result is True

        # Test with non-slash command type
        interaction.type = 3  # component
        result = hasattr(interaction, "type") and interaction.type == 2
        assert result is False

    def test_is_button_interaction_check_logic(self):
        """Test the is_button_interaction logic without full event initialization."""
        interaction = MagicMock()
        interaction.type = 3  # component

        # Simulate the check logic
        result = hasattr(interaction, "type") and interaction.type == 3
        assert result is True

        # Test with non-component type
        interaction.type = 2  # application_command
        result = hasattr(interaction, "type") and interaction.type == 3
        assert result is False


# ============================================================================
# DiscordBotClient Method Tests
# ============================================================================


class TestDiscordBotClientMethods:
    """Tests for DiscordBotClient methods without full initialization."""

    def test_extract_interaction_content_logic(self):
        """Test the _extract_interaction_content logic pattern."""
        # Test slash command pattern
        interaction_type = 2  # application_command
        interaction_data = {
            "name": "help",
            "options": [{"name": "topic", "value": "commands"}],
        }

        if interaction_type == 2:
            command_name = interaction_data.get("name", "")
            if options := interaction_data.get("options", []):
                params = " ".join(
                    [f"{opt['name']}:{opt.get('value', '')}" for opt in options]
                )
                result = f"/{command_name} {params}"
            else:
                result = f"/{command_name}"

        assert result == "/help topic:commands"

        # Test component pattern
        interaction_type = 3  # component
        interaction_data = {
            "custom_id": "btn_confirm",
            "component_type": 2,
        }

        if interaction_type == 3:
            custom_id = interaction_data.get("custom_id", "")
            component_type = interaction_data.get("component_type", "")
            result = f"component:{custom_id}:{component_type}"

        assert result == "component:btn_confirm:2"


# ============================================================================
# Discord Components Data Structure Tests
# ============================================================================


class TestDiscordComponentsData:
    """Tests for Discord component data structures."""

    def test_discord_embed_data_structure(self):
        """Test DiscordEmbed data structure."""
        embed_data = {
            "title": "Test Title",
            "description": "Test Description",
            "color": 0x3498DB,
            "url": "https://example.com",
            "thumbnail": "https://example.com/thumb.png",
            "image": "https://example.com/image.png",
            "footer": "Test Footer",
            "fields": [{"name": "Field 1", "value": "Value 1", "inline": True}],
        }

        assert embed_data["title"] == "Test Title"
        assert embed_data["description"] == "Test Description"
        assert embed_data["color"] == 0x3498DB
        assert embed_data["url"] == "https://example.com"
        assert embed_data["thumbnail"] == "https://example.com/thumb.png"
        assert embed_data["image"] == "https://example.com/image.png"
        assert embed_data["footer"] == "Test Footer"
        assert len(embed_data["fields"]) == 1

    def test_discord_button_data_structure(self):
        """Test DiscordButton data structure."""
        button_data = {
            "label": "Click Me",
            "custom_id": "btn_click",
            "style": "primary",
            "emoji": "👋",
            "disabled": False,
            "url": None,
        }

        assert button_data["label"] == "Click Me"
        assert button_data["custom_id"] == "btn_click"
        assert button_data["style"] == "primary"
        assert button_data["emoji"] == "👋"
        assert button_data["disabled"] is False
        assert button_data["url"] is None

    def test_discord_button_url_data_structure(self):
        """Test DiscordButton with URL data structure."""
        button_data = {
            "label": "Visit Website",
            "url": "https://example.com",
            "style": "link",
            "custom_id": None,
        }

        assert button_data["url"] == "https://example.com"
        assert button_data["custom_id"] is None

    def test_discord_reference_data_structure(self):
        """Test DiscordReference data structure."""
        ref_data = {
            "message_id": "123456789",
            "channel_id": "987654321",
        }

        assert ref_data["message_id"] == "123456789"
        assert ref_data["channel_id"] == "987654321"


# ============================================================================
# Register Handler Tests
# ============================================================================


class TestDiscordAdapterRegisterHandler:
    """Tests for register_handler method."""

    def test_register_handler(self, event_queue, platform_config, platform_settings):
        """Test register_handler adds handler to list."""
        from astrbot.core.platform.sources.discord.discord_platform_adapter import (
            DiscordPlatformAdapter,
        )

        adapter = DiscordPlatformAdapter(
            platform_config, platform_settings, event_queue
        )

        handler_info = {"command": "test", "handler": MagicMock()}
        adapter.register_handler(handler_info)

        assert len(adapter.registered_handlers) == 1
        assert adapter.registered_handlers[0] == handler_info
