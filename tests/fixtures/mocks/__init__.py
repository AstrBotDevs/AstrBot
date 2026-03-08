"""测试 Mock 模块。

提供统一的 mock 工具和 fixture，减少测试代码重复。

使用方式:
    # 在测试文件顶部导入需要的 fixture
    from tests.fixtures.mocks import mock_telegram_modules

    # 或使用 Builder 类创建 mock 对象
    from tests.fixtures.mocks import MockTelegramBuilder
    bot = MockTelegramBuilder.create_bot()
"""

from .aiocqhttp import (
    MockAiocqhttpBuilder,
    create_mock_aiocqhttp_modules,
    mock_aiocqhttp_modules,
)
from .discord import (
    MockDiscordBuilder,
    create_mock_discord_modules,
    mock_discord_modules,
)
from .telegram import (
    MockTelegramBuilder,
    create_mock_telegram_modules,
    mock_telegram_modules,
)

__all__ = [
    # Telegram
    "mock_telegram_modules",
    "create_mock_telegram_modules",
    "MockTelegramBuilder",
    # Discord
    "mock_discord_modules",
    "create_mock_discord_modules",
    "MockDiscordBuilder",
    # Aiocqhttp
    "mock_aiocqhttp_modules",
    "create_mock_aiocqhttp_modules",
    "MockAiocqhttpBuilder",
]
