"""Telegram 模块 Mock 工具。

提供统一的 Telegram 相关模块 mock 设置，避免在测试文件中重复定义。
"""

import sys
from unittest.mock import AsyncMock, MagicMock

import pytest


def create_mock_telegram_modules():
    """创建 Telegram 相关的 mock 模块。

    Returns:
        dict: 包含 telegram 和相关模块的 mock 对象
    """
    mock_telegram = MagicMock()
    mock_telegram.BotCommand = MagicMock
    mock_telegram.Update = MagicMock
    mock_telegram.constants = MagicMock()
    mock_telegram.constants.ChatType = MagicMock()
    mock_telegram.constants.ChatType.PRIVATE = "private"
    mock_telegram.constants.ChatAction = MagicMock()
    mock_telegram.constants.ChatAction.TYPING = "typing"
    mock_telegram.constants.ChatAction.UPLOAD_VOICE = "upload_voice"
    mock_telegram.constants.ChatAction.UPLOAD_DOCUMENT = "upload_document"
    mock_telegram.constants.ChatAction.UPLOAD_PHOTO = "upload_photo"
    mock_telegram.error = MagicMock()
    mock_telegram.error.BadRequest = Exception
    mock_telegram.ReactionTypeCustomEmoji = MagicMock
    mock_telegram.ReactionTypeEmoji = MagicMock

    mock_telegram_ext = MagicMock()
    mock_telegram_ext.ApplicationBuilder = MagicMock
    mock_telegram_ext.ContextTypes = MagicMock
    mock_telegram_ext.ExtBot = MagicMock
    mock_telegram_ext.filters = MagicMock()
    mock_telegram_ext.filters.ALL = MagicMock()
    mock_telegram_ext.MessageHandler = MagicMock

    # Mock telegramify_markdown
    mock_telegramify = MagicMock()
    mock_telegramify.markdownify = lambda text, **kwargs: text

    # Mock apscheduler
    mock_apscheduler = MagicMock()
    mock_apscheduler.schedulers = MagicMock()
    mock_apscheduler.schedulers.asyncio = MagicMock()
    mock_apscheduler.schedulers.asyncio.AsyncIOScheduler = MagicMock
    mock_apscheduler.schedulers.background = MagicMock()
    mock_apscheduler.schedulers.background.BackgroundScheduler = MagicMock

    return {
        "telegram": mock_telegram,
        "telegram.ext": mock_telegram_ext,
        "telegramify_markdown": mock_telegramify,
        "apscheduler": mock_apscheduler,
    }


@pytest.fixture(scope="module", autouse=True)
def mock_telegram_modules():
    """Mock Telegram 相关模块的 fixture。

    自动应用于使用此 fixture 的测试模块。
    """
    mocks = create_mock_telegram_modules()
    monkeypatch = pytest.MonkeyPatch()

    monkeypatch.setitem(sys.modules, "telegram", mocks["telegram"])
    monkeypatch.setitem(sys.modules, "telegram.constants", mocks["telegram"].constants)
    monkeypatch.setitem(sys.modules, "telegram.error", mocks["telegram"].error)
    monkeypatch.setitem(sys.modules, "telegram.ext", mocks["telegram.ext"])
    monkeypatch.setitem(sys.modules, "telegramify_markdown", mocks["telegramify_markdown"])
    monkeypatch.setitem(sys.modules, "apscheduler", mocks["apscheduler"])
    monkeypatch.setitem(
        sys.modules, "apscheduler.schedulers", mocks["apscheduler"].schedulers
    )
    monkeypatch.setitem(
        sys.modules,
        "apscheduler.schedulers.asyncio",
        mocks["apscheduler"].schedulers.asyncio,
    )
    monkeypatch.setitem(
        sys.modules,
        "apscheduler.schedulers.background",
        mocks["apscheduler"].schedulers.background,
    )
    yield
    monkeypatch.undo()


class MockTelegramBuilder:
    """构建 Telegram 测试 mock 对象的工具类。"""

    @staticmethod
    def create_bot():
        """创建 mock Telegram bot 实例。"""
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

    @staticmethod
    def create_application():
        """创建 mock Telegram Application 实例。"""
        from tests.fixtures.helpers import NoopAwaitable

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

    @staticmethod
    def create_scheduler():
        """创建 mock APScheduler 实例。"""
        scheduler = MagicMock()
        scheduler.add_job = MagicMock()
        scheduler.start = MagicMock()
        scheduler.running = True
        scheduler.shutdown = MagicMock()
        return scheduler
