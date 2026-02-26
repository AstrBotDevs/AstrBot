"""Unit tests for Telegram platform adapter.

Tests cover:
- TelegramPlatformAdapter class initialization and methods
- TelegramPlatformEvent class and message handling
- Message conversion for different message types
- Media group message handling
- Command registration

Note: Uses shared mock fixtures from tests/fixtures/mocks/
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 导入共享的辅助函数
from tests.fixtures.helpers import (
    NoopAwaitable,
    create_mock_file,
    create_mock_update,
    make_platform_config,
)

# 导入共享的 mock fixture
from tests.fixtures.mocks import mock_telegram_modules  # noqa: F401

# ============================================================================
# Fixtures (使用 conftest.py 中的 event_queue 和 platform_settings)
# ============================================================================


@pytest.fixture
def platform_config():
    """Create a platform configuration for testing."""
    return make_platform_config("telegram")


@pytest.fixture
def mock_bot():
    """Create a mock Telegram bot instance."""
    bot = MagicMock()
    bot.username = "test_bot"
    bot.id = 12345678
    bot.base_url = "https://api.telegram.org/bottest_token_123/"
    bot.send_message = AsyncMock()
    bot.send_photo = AsyncMock()
    bot.send_document = AsyncMock()
    bot.send_voice = AsyncMock()
    bot.send_chat_action = AsyncMock()
    bot.delete_my_commands = AsyncMock()
    bot.set_my_commands = AsyncMock()
    bot.set_message_reaction = AsyncMock()
    bot.edit_message_text = AsyncMock()
    return bot


@pytest.fixture
def mock_application():
    """Create a mock Telegram Application instance."""
    app = MagicMock()
    app.bot = MagicMock()
    app.bot.username = "test_bot"
    app.bot.base_url = "https://api.telegram.org/bottest_token_123/"
    app.initialize = AsyncMock()
    app.start = AsyncMock()
    app.stop = AsyncMock()
    app.add_handler = MagicMock()
    app.updater = MagicMock()
    app.updater.start_polling = MagicMock(return_value=NoopAwaitable())
    app.updater.stop = AsyncMock()
    return app


@pytest.fixture
def mock_scheduler():
    """Create a mock APScheduler instance."""
    scheduler = MagicMock()
    scheduler.add_job = MagicMock()
    scheduler.start = MagicMock()
    scheduler.running = True
    scheduler.shutdown = MagicMock()
    return scheduler


# ============================================================================
# TelegramPlatformAdapter Initialization Tests
# ============================================================================


class TestTelegramAdapterInit:
    """Tests for TelegramPlatformAdapter initialization."""

    def test_init_basic(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
    ):
        """Test basic adapter initialization."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )

            assert adapter.config == platform_config
            assert adapter.settings == platform_settings
            assert adapter.base_url == platform_config["telegram_api_base_url"]
            assert adapter.enable_command_register is True

    def test_init_with_default_urls(
        self,
        event_queue,
        platform_settings,
        mock_application,
        mock_scheduler,
    ):
        """Test adapter uses default URLs when not configured."""
        config = {
            "id": "test_telegram",
            "telegram_token": "test_token",
            "telegram_api_base_url": None,
            "telegram_file_base_url": None,
        }

        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(config, platform_settings, event_queue)

            assert adapter.base_url == "https://api.telegram.org/bot"

    def test_init_media_group_settings(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
    ):
        """Test media group settings are correctly initialized."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )

            assert adapter.media_group_timeout == 2.5
            assert adapter.media_group_max_wait == 10.0
            assert adapter.media_group_cache == {}


# ============================================================================
# TelegramPlatformAdapter Metadata Tests
# ============================================================================


class TestTelegramAdapterMetadata:
    """Tests for TelegramPlatformAdapter metadata."""

    def test_meta_returns_correct_metadata(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
    ):
        """Test meta() returns correct PlatformMetadata."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )
            meta = adapter.meta()

            assert meta.name == "telegram"
            assert "telegram" in meta.description.lower()
            assert meta.id == "test_telegram"

    def test_meta_with_missing_id_uses_default(
        self,
        event_queue,
        platform_settings,
        mock_application,
        mock_scheduler,
    ):
        """Test meta() uses 'telegram' as default id when not configured."""
        config = {
            "telegram_token": "test_token",
        }

        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(config, platform_settings, event_queue)
            meta = adapter.meta()

            assert meta.id == "telegram"


# ============================================================================
# TelegramPlatformAdapter Message Conversion Tests
# ============================================================================


class TestTelegramAdapterConvertMessage:
    """Tests for message conversion."""

    @pytest.mark.asyncio
    async def test_convert_text_message_private(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
        mock_bot,
    ):
        """Test converting a private text message."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.message_type import MessageType
            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )
            adapter.client = mock_bot

            update = create_mock_update(
                message_text="Hello World",
                chat_type="private",
                chat_id=123456789,
                user_id=987654321,
                username="test_user",
            )

            context = MagicMock()
            context.bot = mock_bot

            result = await adapter.convert_message(update, context)

            assert result is not None
            assert result.session_id == "123456789"
            assert result.type == MessageType.FRIEND_MESSAGE
            assert result.sender.user_id == "987654321"
            assert result.sender.nickname == "test_user"
            assert result.message_str == "Hello World"

    @pytest.mark.asyncio
    async def test_convert_text_message_group(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
        mock_bot,
    ):
        """Test converting a group text message."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.message_type import MessageType
            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )
            adapter.client = mock_bot

            update = create_mock_update(
                message_text="Hello Group",
                chat_type="group",
                chat_id=111111111,
                user_id=987654321,
                username="test_user",
            )

            context = MagicMock()
            context.bot = mock_bot

            result = await adapter.convert_message(update, context)

            assert result is not None
            assert result.type == MessageType.GROUP_MESSAGE
            assert result.group_id == "111111111"

    @pytest.mark.asyncio
    async def test_convert_topic_group_message(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
        mock_bot,
    ):
        """Test converting a topic (forum) group message."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.message_type import MessageType
            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )
            adapter.client = mock_bot

            update = create_mock_update(
                message_text="Hello Topic",
                chat_type="supergroup",
                chat_id=111111111,
                user_id=987654321,
                username="test_user",
                message_thread_id=222,
                is_topic_message=True,
            )

            context = MagicMock()
            context.bot = mock_bot

            result = await adapter.convert_message(update, context)

            assert result is not None
            assert result.type == MessageType.GROUP_MESSAGE
            assert result.group_id == "111111111#222"
            assert result.session_id == "111111111#222"

    @pytest.mark.asyncio
    async def test_convert_photo_message(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
        mock_bot,
    ):
        """Test converting a photo message."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )
            adapter.client = mock_bot

            # Create mock photo
            mock_photo = MagicMock()
            mock_photo.get_file = AsyncMock(
                return_value=create_mock_file("https://example.com/photo.jpg")
            )

            update = create_mock_update(
                message_text=None,
                photo=[mock_photo],  # Photo is a list, last one is largest
                caption="Photo caption",
            )

            context = MagicMock()
            context.bot = mock_bot

            result = await adapter.convert_message(update, context)

            assert result is not None
            assert result.message_str == "Photo caption"
            assert len(result.message) >= 1  # Should have at least Image component

    @pytest.mark.asyncio
    async def test_convert_video_message(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
        mock_bot,
    ):
        """Test converting a video message."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )
            adapter.client = mock_bot

            # Create mock video
            mock_video = MagicMock()
            mock_video.file_name = "test_video.mp4"
            mock_video.get_file = AsyncMock(
                return_value=create_mock_file("https://example.com/video.mp4")
            )

            update = create_mock_update(message_text=None, video=mock_video)

            context = MagicMock()
            context.bot = mock_bot

            result = await adapter.convert_message(update, context)

            assert result is not None
            assert len(result.message) >= 1

    @pytest.mark.asyncio
    async def test_convert_document_message(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
        mock_bot,
    ):
        """Test converting a document message."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )
            adapter.client = mock_bot

            # Create mock document
            mock_document = MagicMock()
            mock_document.file_name = "test_document.pdf"
            mock_document.get_file = AsyncMock(
                return_value=create_mock_file("https://example.com/document.pdf")
            )

            update = create_mock_update(message_text=None, document=mock_document)

            context = MagicMock()
            context.bot = mock_bot

            result = await adapter.convert_message(update, context)

            assert result is not None
            assert len(result.message) >= 1

    @pytest.mark.asyncio
    async def test_convert_voice_message(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
        mock_bot,
    ):
        """Test converting a voice message."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )
            adapter.client = mock_bot

            # Create mock voice
            mock_voice = MagicMock()
            mock_voice.get_file = AsyncMock(
                return_value=create_mock_file("https://example.com/voice.ogg")
            )

            update = create_mock_update(message_text=None, voice=mock_voice)

            context = MagicMock()
            context.bot = mock_bot

            result = await adapter.convert_message(update, context)

            assert result is not None
            assert len(result.message) >= 1

    @pytest.mark.asyncio
    async def test_convert_sticker_message(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
        mock_bot,
    ):
        """Test converting a sticker message."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )
            adapter.client = mock_bot

            # Create mock sticker
            mock_sticker = MagicMock()
            mock_sticker.emoji = "👍"
            mock_sticker.get_file = AsyncMock(
                return_value=create_mock_file("https://example.com/sticker.webp")
            )

            update = create_mock_update(message_text=None, sticker=mock_sticker)

            context = MagicMock()
            context.bot = mock_bot

            result = await adapter.convert_message(update, context)

            assert result is not None
            assert "Sticker: 👍" in result.message_str

    @pytest.mark.asyncio
    async def test_convert_message_without_from_user(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
        mock_bot,
    ):
        """Test converting a message without from_user returns None."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )
            adapter.client = mock_bot

            update = create_mock_update()
            update.message.from_user = None

            context = MagicMock()
            context.bot = mock_bot

            result = await adapter.convert_message(update, context)

            assert result is None

    @pytest.mark.asyncio
    async def test_convert_message_without_message(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
        mock_bot,
    ):
        """Test converting an update without message returns None."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )
            adapter.client = mock_bot

            update = MagicMock()
            update.message = None

            context = MagicMock()
            context.bot = mock_bot

            result = await adapter.convert_message(update, context)

            assert result is None

    @pytest.mark.asyncio
    async def test_convert_command_with_bot_mention(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
        mock_bot,
    ):
        """Test converting a command with bot mention in group."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )
            adapter.client = mock_bot

            update = create_mock_update(
                message_text="/help@test_bot arg1",
                chat_type="group",
            )

            context = MagicMock()
            context.bot = mock_bot

            result = await adapter.convert_message(update, context)

            assert result is not None
            # Should strip the bot mention from command
            assert "@test_bot" not in result.message_str


# ============================================================================
# TelegramPlatformAdapter Media Group Tests
# ============================================================================


class TestTelegramAdapterMediaGroup:
    """Tests for media group message handling."""

    @pytest.mark.asyncio
    async def test_handle_media_group_creates_cache(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
        mock_bot,
    ):
        """Test that media group message creates cache entry."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder

            # Create a real scheduler mock that tracks add_job calls
            scheduler = MagicMock()
            scheduler.add_job = MagicMock()
            scheduler.running = True
            scheduler.shutdown = MagicMock()
            mock_scheduler_class.return_value = scheduler

            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )
            adapter.client = mock_bot
            adapter.scheduler = scheduler

            update = create_mock_update(
                message_text="Media item",
                media_group_id="group_123",
            )

            context = MagicMock()
            context.bot = mock_bot

            await adapter.handle_media_group_message(update, context)

            assert "group_123" in adapter.media_group_cache
            assert len(adapter.media_group_cache["group_123"]["items"]) == 1
            scheduler.add_job.assert_called()

    @pytest.mark.asyncio
    async def test_handle_media_group_accumulates_items(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
        mock_bot,
    ):
        """Test that multiple media group messages accumulate in cache."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder

            scheduler = MagicMock()
            scheduler.add_job = MagicMock()
            scheduler.running = True
            mock_scheduler_class.return_value = scheduler

            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )
            adapter.client = mock_bot
            adapter.scheduler = scheduler

            context = MagicMock()
            context.bot = mock_bot

            # Send multiple messages with same media_group_id
            for i in range(3):
                update = create_mock_update(
                    message_text=f"Media item {i}",
                    media_group_id="group_456",
                    message_id=i + 1,
                )
                await adapter.handle_media_group_message(update, context)

            assert len(adapter.media_group_cache["group_456"]["items"]) == 3

    @pytest.mark.asyncio
    async def test_handle_media_group_without_message(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
        mock_bot,
    ):
        """Test handling media group without message returns early."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )
            adapter.client = mock_bot

            update = MagicMock()
            update.message = None

            context = MagicMock()

            # Should not raise exception
            await adapter.handle_media_group_message(update, context)

            assert len(adapter.media_group_cache) == 0


# ============================================================================
# TelegramPlatformAdapter Command Registration Tests
# ============================================================================


class TestTelegramAdapterCommandRegistration:
    """Tests for command registration."""

    @pytest.mark.asyncio
    async def test_register_commands_success(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
        mock_bot,
    ):
        """Test successful command registration."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )
            adapter.client = mock_bot
            adapter.collect_commands = MagicMock(
                return_value=[
                    SimpleNamespace(command="help", description="help command"),
                ]
            )

            await adapter.register_commands()

            mock_bot.delete_my_commands.assert_called_once()
            mock_bot.set_my_commands.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_commands_empty_does_not_clear_existing(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
        mock_bot,
    ):
        """Test empty command list keeps existing Telegram commands."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )
            adapter.client = mock_bot
            adapter.collect_commands = MagicMock(return_value=[])

            await adapter.register_commands()

            mock_bot.delete_my_commands.assert_not_called()
            mock_bot.set_my_commands.assert_not_called()

    def test_collect_commands_empty(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
    ):
        """Test collecting commands when no handlers are registered."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
            patch(
                "astrbot.core.platform.sources.telegram.tg_adapter.star_handlers_registry",
                [],
            ),
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )

            commands = adapter.collect_commands()

            assert commands == []

    def test_collect_commands_includes_aliases(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
    ):
        """Test collecting commands includes command/group aliases."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
            patch(
                "astrbot.core.platform.sources.telegram.tg_adapter.BotCommand",
                side_effect=lambda cmd, desc: SimpleNamespace(
                    command=cmd,
                    description=desc,
                ),
            ),
        ):
            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )
            from astrbot.core.star.filter.command import CommandFilter
            from astrbot.core.star.filter.command_group import CommandGroupFilter

            handler = SimpleNamespace(
                handler_module_path="plugin.telegram.alias",
                enabled=True,
                desc="alias command",
                event_filters=[
                    CommandFilter("help", alias={"h"}),
                    CommandGroupFilter("admin", alias={"adm"}),
                ],
            )

            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            with (
                patch(
                    "astrbot.core.platform.sources.telegram.tg_adapter.star_handlers_registry",
                    [handler],
                ),
                patch(
                    "astrbot.core.platform.sources.telegram.tg_adapter.star_map",
                    {"plugin.telegram.alias": SimpleNamespace(activated=True)},
                ),
            ):
                adapter = TelegramPlatformAdapter(
                    platform_config, platform_settings, event_queue
                )
                commands = adapter.collect_commands()

            names = sorted(cmd.command for cmd in commands)
            assert names == ["adm", "admin", "h", "help"]

    def test_collect_commands_warns_on_duplicates(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
    ):
        """Test duplicate command names log warning and keep first one."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
            patch(
                "astrbot.core.platform.sources.telegram.tg_adapter.BotCommand",
                side_effect=lambda cmd, desc: SimpleNamespace(
                    command=cmd,
                    description=desc,
                ),
            ),
            patch(
                "astrbot.core.platform.sources.telegram.tg_adapter.logger"
            ) as mock_logger,
        ):
            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )
            from astrbot.core.star.filter.command import CommandFilter

            handler_a = SimpleNamespace(
                handler_module_path="plugin.telegram.a",
                enabled=True,
                desc="first",
                event_filters=[CommandFilter("help")],
            )
            handler_b = SimpleNamespace(
                handler_module_path="plugin.telegram.b",
                enabled=True,
                desc="second",
                event_filters=[CommandFilter("help")],
            )

            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            with (
                patch(
                    "astrbot.core.platform.sources.telegram.tg_adapter.star_handlers_registry",
                    [handler_a, handler_b],
                ),
                patch(
                    "astrbot.core.platform.sources.telegram.tg_adapter.star_map",
                    {
                        "plugin.telegram.a": SimpleNamespace(activated=True),
                        "plugin.telegram.b": SimpleNamespace(activated=True),
                    },
                ),
            ):
                adapter = TelegramPlatformAdapter(
                    platform_config, platform_settings, event_queue
                )
                commands = adapter.collect_commands()

            assert [cmd.command for cmd in commands] == ["help"]
            mock_logger.warning.assert_called_once()


# ============================================================================
# TelegramPlatformAdapter Run Tests
# ============================================================================


class TestTelegramAdapterRun:
    """Tests for run method."""

    @pytest.mark.asyncio
    async def test_run_initializes_application(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
    ):
        """Test run method initializes the application."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )
            adapter.client = mock_application.bot
            adapter.register_commands = AsyncMock()

            # Start run in background and cancel after short time
            task = asyncio.create_task(adapter.run())

            # Give it a moment to start
            await asyncio.sleep(0.1)

            # Cancel the task
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            mock_application.initialize.assert_called_once()
            mock_application.start.assert_called_once()


# ============================================================================
# TelegramPlatformAdapter Terminate Tests
# ============================================================================


class TestTelegramAdapterTerminate:
    """Tests for terminate method."""

    @pytest.mark.asyncio
    async def test_terminate_stops_application(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
        mock_bot,
    ):
        """Test terminate method stops the application."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )
            adapter.client = mock_bot

            await adapter.terminate()

            mock_application.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_terminate_shuts_down_scheduler(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
        mock_bot,
    ):
        """Test terminate method shuts down the scheduler."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )
            adapter.client = mock_bot
            adapter.scheduler = mock_scheduler

            await adapter.terminate()

            mock_scheduler.shutdown.assert_called_once()


# ============================================================================
# TelegramPlatformAdapter send_by_session Tests
# ============================================================================


class TestTelegramAdapterSendBySession:
    """Tests for send_by_session method."""

    @pytest.mark.asyncio
    async def test_send_by_session_calls_send_with_client(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
        mock_bot,
    ):
        """Test send_by_session calls send_with_client."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.astr_message_event import MessageSesion
            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )
            adapter.client = mock_bot

            session = MagicMock(spec=MessageSesion)
            session.session_id = "123456789"

            message_chain = MagicMock()
            message_chain.chain = []

            with patch(
                "astrbot.core.platform.sources.telegram.tg_adapter.TelegramPlatformEvent.send_with_client",
                new_callable=AsyncMock,
            ) as mock_send:
                await adapter.send_by_session(session, message_chain)

                mock_send.assert_called_once_with(mock_bot, message_chain, "123456789")


# ============================================================================
# TelegramPlatformEvent Tests
# ============================================================================


class TestTelegramPlatformEvent:
    """Tests for TelegramPlatformEvent class."""

    def test_split_message_short_text(self):
        """Test _split_message returns single chunk for short text."""
        from astrbot.core.platform.sources.telegram.tg_event import (
            TelegramPlatformEvent,
        )

        text = "Short message"
        result = TelegramPlatformEvent._split_message(text)

        assert len(result) == 1
        assert result[0] == text

    def test_split_message_long_text(self):
        """Test _split_message splits long text into chunks."""
        from astrbot.core.platform.sources.telegram.tg_event import (
            TelegramPlatformEvent,
        )

        # Create text longer than MAX_MESSAGE_LENGTH
        text = "A" * 5000
        result = TelegramPlatformEvent._split_message(text)

        # Should be split into multiple chunks
        assert len(result) > 1
        # Each chunk should be <= MAX_MESSAGE_LENGTH
        for chunk in result:
            assert len(chunk) <= TelegramPlatformEvent.MAX_MESSAGE_LENGTH

    def test_split_message_respects_paragraph_breaks(self):
        """Test _split_message prefers paragraph breaks for splitting."""
        from astrbot.core.platform.sources.telegram.tg_event import (
            TelegramPlatformEvent,
        )

        # Create text with paragraph breaks
        para1 = "A" * 3000
        para2 = "B" * 3000
        text = f"{para1}\n\n{para2}"

        result = TelegramPlatformEvent._split_message(text)

        # Should split at paragraph break
        assert len(result) >= 2

    def test_get_chat_action_for_chain_voice(self):
        """Test _get_chat_action_for_chain returns UPLOAD_VOICE for Record."""
        from astrbot.api.message_components import Record
        from astrbot.core.platform.sources.telegram.tg_event import (
            TelegramPlatformEvent,
        )

        chain = [Record(file="test.ogg", url="test.ogg")]
        result = TelegramPlatformEvent._get_chat_action_for_chain(chain)

        assert result == "upload_voice"

    def test_get_chat_action_for_chain_image(self):
        """Test _get_chat_action_for_chain returns UPLOAD_PHOTO for Image."""
        from astrbot.api.message_components import Image
        from astrbot.core.platform.sources.telegram.tg_event import (
            TelegramPlatformEvent,
        )

        chain = [Image(file="test.jpg", url="test.jpg")]
        result = TelegramPlatformEvent._get_chat_action_for_chain(chain)

        assert result == "upload_photo"

    def test_get_chat_action_for_chain_file(self):
        """Test _get_chat_action_for_chain returns UPLOAD_DOCUMENT for File."""
        from astrbot.api.message_components import File
        from astrbot.core.platform.sources.telegram.tg_event import (
            TelegramPlatformEvent,
        )

        chain = [File(file="test.pdf", name="test.pdf")]
        result = TelegramPlatformEvent._get_chat_action_for_chain(chain)

        assert result == "upload_document"

    def test_get_chat_action_for_chain_plain(self):
        """Test _get_chat_action_for_chain returns TYPING for Plain text."""
        from astrbot.api.message_components import Plain
        from astrbot.core.platform.sources.telegram.tg_event import (
            TelegramPlatformEvent,
        )

        chain = [Plain("Hello")]
        result = TelegramPlatformEvent._get_chat_action_for_chain(chain)

        assert result == "typing"


class TestTelegramPlatformEventSend:
    """Tests for TelegramPlatformEvent send methods."""

    @pytest.fixture
    def event_setup(self, mock_bot):
        """Create a basic event setup for testing."""
        from astrbot.api.platform import AstrBotMessage, MessageType, PlatformMetadata
        from astrbot.core.platform.sources.telegram.tg_event import (
            TelegramPlatformEvent,
        )

        message_obj = AstrBotMessage()
        message_obj.type = MessageType.FRIEND_MESSAGE
        message_obj.session_id = "123456789"
        message_obj.message_id = "1"
        message_obj.group_id = None

        platform_meta = PlatformMetadata(name="telegram", description="test", id="test")

        event = TelegramPlatformEvent(
            message_str="Test message",
            message_obj=message_obj,
            platform_meta=platform_meta,
            session_id="123456789",
            client=mock_bot,
        )

        return event, mock_bot

    @pytest.mark.asyncio
    async def test_send_typing(self, event_setup):
        """Test send_typing method."""
        event, mock_bot = event_setup

        await event.send_typing()

        mock_bot.send_chat_action.assert_called()

    @pytest.mark.asyncio
    async def test_react_with_emoji(self, event_setup):
        """Test react method with regular emoji."""
        event, mock_bot = event_setup

        await event.react("👍")

        mock_bot.set_message_reaction.assert_called_once()

    @pytest.mark.asyncio
    async def test_react_with_custom_emoji(self, event_setup):
        """Test react method with custom emoji ID."""
        event, mock_bot = event_setup

        await event.react("123456789")  # Custom emoji ID

        mock_bot.set_message_reaction.assert_called_once()

    @pytest.mark.asyncio
    async def test_react_clear(self, event_setup):
        """Test react method clears reaction when None is passed."""
        event, mock_bot = event_setup

        await event.react(None)

        mock_bot.set_message_reaction.assert_called_once()
        call_args = mock_bot.set_message_reaction.call_args
        assert call_args[1]["reaction"] == []


class TestTelegramPlatformEventSendWithClient:
    """Tests for send_with_client class method."""

    @pytest.mark.asyncio
    async def test_send_with_client_plain_text(self, mock_bot):
        """Test send_with_client sends plain text message."""
        from astrbot.api.event import MessageChain
        from astrbot.api.message_components import Plain
        from astrbot.core.platform.sources.telegram.tg_event import (
            TelegramPlatformEvent,
        )

        message = MessageChain()
        message.chain = [Plain("Hello World")]

        await TelegramPlatformEvent.send_with_client(mock_bot, message, "123456789")

        mock_bot.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_send_with_client_with_reply(self, mock_bot):
        """Test send_with_client sends message with reply."""
        from astrbot.api.event import MessageChain
        from astrbot.api.message_components import Plain, Reply
        from astrbot.core.platform.sources.telegram.tg_event import (
            TelegramPlatformEvent,
        )

        message = MessageChain()
        reply = MagicMock()
        reply.id = "123"
        message.chain = [
            Reply(
                id="123",
                chain=[],
                sender_id="1",
                sender_nickname="test",
                time=0,
                message_str="",
                text="",
                qq="1",
            ),
            Plain("Reply text"),
        ]

        await TelegramPlatformEvent.send_with_client(mock_bot, message, "123456789")

        mock_bot.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_send_with_client_to_topic_group(self, mock_bot):
        """Test send_with_client handles topic group (with # in username)."""
        from astrbot.api.event import MessageChain
        from astrbot.api.message_components import Plain
        from astrbot.core.platform.sources.telegram.tg_event import (
            TelegramPlatformEvent,
        )

        message = MessageChain()
        message.chain = [Plain("Topic message")]

        # Topic group format: chat_id#thread_id
        await TelegramPlatformEvent.send_with_client(mock_bot, message, "123456789#222")

        mock_bot.send_chat_action.assert_called()


# ============================================================================
# TelegramPlatformEvent Voice Fallback Tests
# ============================================================================


class TestTelegramPlatformEventVoiceFallback:
    """Tests for voice message fallback functionality."""

    @pytest.mark.asyncio
    async def test_send_voice_with_fallback_success(self, mock_bot):
        """Test _send_voice_with_fallback sends voice normally."""
        from astrbot.core.platform.sources.telegram.tg_event import (
            TelegramPlatformEvent,
        )

        payload = {"chat_id": "123456789"}

        await TelegramPlatformEvent._send_voice_with_fallback(
            mock_bot,
            "voice.ogg",
            payload,
        )

        mock_bot.send_voice.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_voice_with_fallback_to_document(self, mock_bot):
        """Test _send_voice_with_fallback falls back to document on Voice_messages_forbidden."""
        from telegram.error import BadRequest

        from astrbot.core.platform.sources.telegram.tg_event import (
            TelegramPlatformEvent,
        )

        # Create a BadRequest with Voice_messages_forbidden message
        error = BadRequest("Voice_messages_forbidden")
        mock_bot.send_voice = AsyncMock(side_effect=error)

        payload = {"chat_id": "123456789"}

        await TelegramPlatformEvent._send_voice_with_fallback(
            mock_bot,
            "voice.ogg",
            payload,
            caption="Voice caption",
        )

        mock_bot.send_document.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_voice_with_fallback_reraises_other_errors(self, mock_bot):
        """Test _send_voice_with_fallback re-raises non-voice-forbidden errors."""
        from telegram.error import BadRequest

        from astrbot.core.platform.sources.telegram.tg_event import (
            TelegramPlatformEvent,
        )

        # Create a BadRequest with different message
        error = BadRequest("Some other error")
        mock_bot.send_voice = AsyncMock(side_effect=error)

        payload = {"chat_id": "123456789"}

        with pytest.raises(BadRequest):
            await TelegramPlatformEvent._send_voice_with_fallback(
                mock_bot,
                "voice.ogg",
                payload,
            )


# ============================================================================
# Integration-style Tests
# ============================================================================


class TestTelegramAdapterIntegration:
    """Integration-style tests for complete message flows."""

    @pytest.mark.asyncio
    async def test_message_handler_processes_text_message(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
        mock_bot,
    ):
        """Test message_handler processes a text message end-to-end."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )
            adapter.client = mock_bot

            update = create_mock_update(
                message_text="Hello bot!",
                chat_type="private",
            )

            context = MagicMock()
            context.bot = mock_bot

            await adapter.message_handler(update, context)

            # Check that an event was committed to the queue
            assert not event_queue.empty()

    @pytest.mark.asyncio
    async def test_start_command_sends_welcome_message(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
        mock_bot,
    ):
        """Test /start command sends welcome message."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )
            adapter.client = mock_bot

            update = create_mock_update(
                message_text="/start",
                chat_type="private",
            )

            context = MagicMock()
            context.bot = mock_bot

            # convert_message should return None for /start
            result = await adapter.convert_message(update, context)

            assert result is None
            mock_bot.send_message.assert_called()


# ============================================================================
# Edge Cases and Error Handling Tests
# ============================================================================


class TestTelegramAdapterEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_convert_message_with_reply(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
        mock_bot,
    ):
        """Test converting a message that replies to another message."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )
            adapter.client = mock_bot

            # Create a reply message
            reply_message = MagicMock()
            reply_message.message_id = 100
            reply_message.chat = MagicMock()
            reply_message.chat.id = 123456789
            reply_message.chat.type = "private"
            reply_message.from_user = MagicMock()
            reply_message.from_user.id = 111111111
            reply_message.from_user.username = "reply_user"
            reply_message.text = "Original message"
            reply_message.message_thread_id = None
            reply_message.is_topic_message = False
            reply_message.media_group_id = None
            reply_message.photo = None
            reply_message.video = None
            reply_message.document = None
            reply_message.voice = None
            reply_message.sticker = None
            reply_message.reply_to_message = None
            reply_message.caption = None
            reply_message.entities = None
            reply_message.caption_entities = None

            update = create_mock_update(
                message_text="Reply text",
                reply_to_message=reply_message,
            )

            context = MagicMock()
            context.bot = mock_bot

            result = await adapter.convert_message(update, context)

            assert result is not None
            # Should have Reply component in message
            assert len(result.message) >= 1

    @pytest.mark.asyncio
    async def test_process_media_group_empty_cache(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
        mock_bot,
    ):
        """Test process_media_group handles missing cache entry gracefully."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )
            adapter.client = mock_bot

            # Should not raise exception for non-existent media group
            await adapter.process_media_group("non_existent_group")

            assert True  # Just verify no exception

    @pytest.mark.asyncio
    async def test_register_commands_handles_exception(
        self,
        event_queue,
        platform_config,
        platform_settings,
        mock_application,
        mock_scheduler,
        mock_bot,
    ):
        """Test register_commands handles exceptions gracefully."""
        with (
            patch("telegram.ext.ApplicationBuilder") as mock_builder_class,
            patch(
                "apscheduler.schedulers.asyncio.AsyncIOScheduler"
            ) as mock_scheduler_class,
        ):
            mock_builder = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.base_url.return_value = mock_builder
            mock_builder.base_file_url.return_value = mock_builder
            mock_builder.build.return_value = mock_application
            mock_builder_class.return_value = mock_builder
            mock_scheduler_class.return_value = mock_scheduler

            from astrbot.core.platform.sources.telegram.tg_adapter import (
                TelegramPlatformAdapter,
            )

            adapter = TelegramPlatformAdapter(
                platform_config, platform_settings, event_queue
            )
            adapter.client = mock_bot

            # Make delete_my_commands raise an exception
            mock_bot.delete_my_commands = AsyncMock(
                side_effect=Exception("Network error")
            )

            # Should not raise exception
            await adapter.register_commands()

            assert True  # Just verify no exception
