"""Keep real Telegram SDK types while replacing network client construction."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.error import Forbidden, InvalidToken, NetworkError

MockTelegramNetworkError = NetworkError
MockTelegramForbidden = Forbidden
MockTelegramInvalidToken = InvalidToken


def create_mock_telegram_modules():
    """Return real SDK modules for callers migrating from legacy module mocks."""
    import apscheduler.schedulers.asyncio
    import apscheduler.schedulers.background
    import telegram
    import telegram.ext
    import telegramify_markdown

    return {
        "telegram": telegram,
        "telegram.ext": telegram.ext,
        "telegramify_markdown": telegramify_markdown,
        "apscheduler": apscheduler,
    }


@pytest.fixture(autouse=True)
def mock_telegram_modules(monkeypatch, isolated_runtime_config):
    """Replace only adapter client and scheduler factories for this test."""
    from astrbot.core.platform.sources.telegram import tg_adapter

    def application_builder():
        builder = MagicMock()
        builder.token.return_value = builder
        builder.base_url.return_value = builder
        builder.base_file_url.return_value = builder
        builder.build.return_value = MockTelegramBuilder.create_application()
        return builder

    monkeypatch.setattr(tg_adapter, "ApplicationBuilder", application_builder)
    monkeypatch.setattr(
        tg_adapter, "AsyncIOScheduler", MockTelegramBuilder.create_scheduler
    )
    return application_builder


class MockTelegramBuilder:
    """Build isolated Telegram transport test doubles."""

    @staticmethod
    def create_bot():
        """Create a bot with asynchronous network methods."""
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
        bot.send_message_draft = AsyncMock()
        return bot

    @staticmethod
    def create_application():
        """Create an application whose lifecycle stays local."""
        from tests.fixtures.helpers import NoopAwaitable

        app = MagicMock()
        app.bot = MockTelegramBuilder.create_bot()
        app.initialize = AsyncMock()
        app.start = AsyncMock()
        app.stop = AsyncMock()
        app.shutdown = AsyncMock()
        app.add_handler = MagicMock()
        app.updater = MagicMock()
        app.updater.start_polling = MagicMock(return_value=NoopAwaitable())
        app.updater.stop = AsyncMock()
        app.updater.running = False
        return app

    @staticmethod
    def create_scheduler():
        """Create a scheduler without background jobs."""
        scheduler = MagicMock()
        scheduler.add_job = MagicMock()
        scheduler.start = MagicMock()
        scheduler.running = True
        scheduler.shutdown = MagicMock()
        return scheduler
