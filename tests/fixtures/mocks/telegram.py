"""Telegram 模块 Mock 工具。

提供统一的 Telegram 相关模块 mock 设置，避免在测试文件中重复定义。
"""

import sys
from unittest.mock import AsyncMock, MagicMock

import pytest


class MockTelegramNetworkError(Exception):
    """Mock telegram.error.NetworkError used in tests."""


class MockTelegramBadRequest(Exception):
    """Mock telegram.error.BadRequest with PTB-compatible message attribute."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class MockTelegramForbidden(Exception):
    """Mock telegram.error.Forbidden used in tests."""


class MockTelegramInvalidToken(Exception):
    """Mock telegram.error.InvalidToken used in tests."""


class MockTelegramObject:
    """Small value object for Telegram classes used in tests."""

    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        for key, value in kwargs.items():
            setattr(self, key, value)


class MockBotCommand(MockTelegramObject):
    def __init__(self, command: str, description: str) -> None:
        super().__init__(command=command, description=description)


class MockBotCommandScopeDefault(MockTelegramObject):
    pass


class MockBotCommandScopeAllPrivateChats(MockTelegramObject):
    pass


class MockBotCommandScopeAllGroupChats(MockTelegramObject):
    pass


class MockBotCommandScopeAllChatAdministrators(MockTelegramObject):
    pass


class MockBotCommandScopeChat(MockTelegramObject):
    pass


class MockBotCommandScopeChatAdministrators(MockTelegramObject):
    pass


class MockBotCommandScopeChatMember(MockTelegramObject):
    pass


class MockInlineKeyboardButton(MockTelegramObject):
    def __init__(self, text: str, **kwargs) -> None:
        super().__init__(text=text, **kwargs)


class MockInlineKeyboardMarkup(MockTelegramObject):
    def __init__(self, inline_keyboard) -> None:
        super().__init__(inline_keyboard=inline_keyboard)


class MockKeyboardButton(MockTelegramObject):
    def __init__(self, text: str, **kwargs) -> None:
        super().__init__(text=text, **kwargs)


class MockReplyKeyboardMarkup(MockTelegramObject):
    def __init__(self, keyboard, **kwargs) -> None:
        super().__init__(keyboard=keyboard, **kwargs)


class MockReplyKeyboardRemove(MockTelegramObject):
    pass


class MockForceReply(MockTelegramObject):
    pass


class MockLinkPreviewOptions(MockTelegramObject):
    pass


class MockCallbackQueryHandler(MockTelegramObject):
    def __init__(self, callback, **kwargs) -> None:
        super().__init__(callback=callback, **kwargs)


class MockMessageHandler(MockTelegramObject):
    def __init__(self, filters, callback, **kwargs) -> None:
        super().__init__(filters=filters, callback=callback, **kwargs)


class MockInlineQueryHandler(MockTelegramObject):
    def __init__(self, callback, **kwargs) -> None:
        super().__init__(callback=callback, **kwargs)


class MockChosenInlineResultHandler(MockTelegramObject):
    def __init__(self, callback, **kwargs) -> None:
        super().__init__(callback=callback, **kwargs)


class MockChatMemberHandler(MockTelegramObject):
    CHAT_MEMBER = 0
    MY_CHAT_MEMBER = -1

    def __init__(self, callback, **kwargs) -> None:
        super().__init__(callback=callback, **kwargs)


def create_mock_telegram_modules():
    """创建 Telegram 相关的 mock 模块。

    Returns:
        dict: 包含 telegram 和相关模块的 mock 对象
    """
    mock_telegram = MagicMock()
    mock_telegram.BotCommand = MockBotCommand
    mock_telegram.BotCommandScopeDefault = MockBotCommandScopeDefault
    mock_telegram.BotCommandScopeAllPrivateChats = MockBotCommandScopeAllPrivateChats
    mock_telegram.BotCommandScopeAllGroupChats = MockBotCommandScopeAllGroupChats
    mock_telegram.BotCommandScopeAllChatAdministrators = (
        MockBotCommandScopeAllChatAdministrators
    )
    mock_telegram.BotCommandScopeChat = MockBotCommandScopeChat
    mock_telegram.BotCommandScopeChatAdministrators = (
        MockBotCommandScopeChatAdministrators
    )
    mock_telegram.BotCommandScopeChatMember = MockBotCommandScopeChatMember
    mock_telegram.CallbackGame = MagicMock
    mock_telegram.CopyTextButton = MockTelegramObject
    mock_telegram.ForceReply = MockForceReply
    mock_telegram.InputTextMessageContent = MockTelegramObject
    mock_telegram.InputFile = MockTelegramObject
    mock_telegram.InputMediaAudio = MockTelegramObject
    mock_telegram.InputMediaDocument = MockTelegramObject
    mock_telegram.InputMediaPhoto = MockTelegramObject
    mock_telegram.InputMediaVideo = MockTelegramObject
    mock_telegram.InlineKeyboardButton = MockInlineKeyboardButton
    mock_telegram.InlineKeyboardMarkup = MockInlineKeyboardMarkup
    inline_result_names = [
        "InlineQueryResultArticle",
        "InlineQueryResultAudio",
        "InlineQueryResultCachedAudio",
        "InlineQueryResultCachedDocument",
        "InlineQueryResultCachedGif",
        "InlineQueryResultCachedMpeg4Gif",
        "InlineQueryResultCachedPhoto",
        "InlineQueryResultCachedSticker",
        "InlineQueryResultCachedVideo",
        "InlineQueryResultCachedVoice",
        "InlineQueryResultContact",
        "InlineQueryResultDocument",
        "InlineQueryResultGame",
        "InlineQueryResultGif",
        "InlineQueryResultLocation",
        "InlineQueryResultMpeg4Gif",
        "InlineQueryResultPhoto",
        "InlineQueryResultVenue",
        "InlineQueryResultVideo",
        "InlineQueryResultVoice",
        "InlineQueryResultsButton",
    ]
    for inline_result_name in inline_result_names:
        setattr(mock_telegram, inline_result_name, MockTelegramObject)
    mock_telegram.KeyboardButton = MockKeyboardButton
    mock_telegram.LinkPreviewOptions = MockLinkPreviewOptions
    mock_telegram.LoginUrl = MockTelegramObject
    mock_telegram.ReplyKeyboardMarkup = MockReplyKeyboardMarkup
    mock_telegram.ReplyKeyboardRemove = MockReplyKeyboardRemove
    mock_telegram.SwitchInlineQueryChosenChat = MockTelegramObject
    mock_telegram.Update = MagicMock
    mock_telegram.Update.ALL_TYPES = [
        "message",
        "callback_query",
        "inline_query",
        "chosen_inline_result",
        "chat_member",
        "my_chat_member",
    ]
    mock_telegram.WebAppInfo = MockTelegramObject
    mock_telegram.constants = MagicMock()
    mock_telegram.constants.ChatType = MagicMock()
    mock_telegram.constants.ChatType.PRIVATE = "private"
    mock_telegram.constants.ChatAction = MagicMock()
    mock_telegram.constants.ChatAction.TYPING = "typing"
    mock_telegram.constants.ChatAction.UPLOAD_VOICE = "upload_voice"
    mock_telegram.constants.ChatAction.UPLOAD_DOCUMENT = "upload_document"
    mock_telegram.constants.ChatAction.UPLOAD_PHOTO = "upload_photo"
    mock_telegram.constants.ChatAction.UPLOAD_VIDEO = "upload_video"
    mock_telegram.constants.MessageLimit = MagicMock()
    mock_telegram.constants.MessageLimit.CAPTION_LENGTH = 1024
    mock_telegram.error = MagicMock()
    mock_telegram.error.BadRequest = MockTelegramBadRequest
    mock_telegram.error.Forbidden = MockTelegramForbidden
    mock_telegram.error.InvalidToken = MockTelegramInvalidToken
    mock_telegram.error.NetworkError = MockTelegramNetworkError
    mock_telegram.ReactionTypeCustomEmoji = MagicMock
    mock_telegram.ReactionTypeEmoji = MagicMock

    mock_telegram_ext = MagicMock()
    mock_telegram_ext.ApplicationBuilder = (
        MockTelegramBuilder.create_application_builder
    )
    mock_telegram_ext.ContextTypes = MagicMock()
    mock_telegram_ext.ContextTypes.DEFAULT_TYPE = MagicMock
    mock_telegram_ext.ExtBot = MagicMock
    mock_telegram_ext.filters = MagicMock()
    mock_telegram_ext.filters.ALL = MagicMock()
    mock_telegram_ext.CallbackQueryHandler = MockCallbackQueryHandler
    mock_telegram_ext.ChatMemberHandler = MockChatMemberHandler
    mock_telegram_ext.ChosenInlineResultHandler = MockChosenInlineResultHandler
    mock_telegram_ext.InlineQueryHandler = MockInlineQueryHandler
    mock_telegram_ext.MessageHandler = MockMessageHandler

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
    monkeypatch.setitem(
        sys.modules, "telegramify_markdown", mocks["telegramify_markdown"]
    )
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
        bot.send_media_group = AsyncMock()
        bot.send_document = AsyncMock()
        bot.send_voice = AsyncMock()
        bot.send_video = AsyncMock()
        bot.send_animation = AsyncMock()
        bot.send_chat_action = AsyncMock()
        bot.delete_my_commands = AsyncMock()
        bot.set_my_commands = AsyncMock()
        bot.set_message_reaction = AsyncMock()
        bot.answer_callback_query = AsyncMock()
        bot.answer_inline_query = AsyncMock()
        bot.edit_message_text = AsyncMock()
        bot.edit_message_reply_markup = AsyncMock()
        bot.delete_message = AsyncMock()
        bot.copy_message = AsyncMock()
        bot.forward_message = AsyncMock()
        bot.send_message_draft = AsyncMock()
        return bot

    @staticmethod
    def create_application_builder(app=None):
        """创建支持链式调用的 mock Telegram ApplicationBuilder 实例。"""
        builder = MagicMock()
        builder.token.return_value = builder
        builder.base_url.return_value = builder
        builder.base_file_url.return_value = builder
        builder.proxy.return_value = builder
        builder.get_updates_proxy.return_value = builder
        builder.build.return_value = app or MockTelegramBuilder.create_application()
        return builder

    @staticmethod
    def create_application():
        """创建 mock Telegram Application 实例。"""
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
        app.updater.start_webhook = MagicMock(return_value=NoopAwaitable())
        app.updater.stop = AsyncMock()
        app.updater.running = False
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
