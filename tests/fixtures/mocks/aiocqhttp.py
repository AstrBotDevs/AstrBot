"""Aiocqhttp 模块 Mock 工具。

提供统一的 aiocqhttp 相关模块 mock 设置，避免在测试文件中重复定义。
"""

import sys
from unittest.mock import AsyncMock, MagicMock

import pytest


def create_mock_aiocqhttp_modules():
    """创建 aiocqhttp 相关的 mock 模块。

    Returns:
        dict: 包含 aiocqhttp 和相关模块的 mock 对象
    """
    mock_aiocqhttp = MagicMock()
    mock_aiocqhttp.CQHttp = MagicMock
    mock_aiocqhttp.Event = MagicMock
    mock_aiocqhttp.exceptions = MagicMock()
    mock_aiocqhttp.exceptions.ActionFailed = Exception

    return mock_aiocqhttp


@pytest.fixture(scope="module", autouse=True)
def mock_aiocqhttp_modules():
    """Mock aiocqhttp 相关模块的 fixture。

    自动应用于使用此 fixture 的测试模块。
    """
    mock_aiocqhttp = create_mock_aiocqhttp_modules()
    monkeypatch = pytest.MonkeyPatch()

    monkeypatch.setitem(sys.modules, "aiocqhttp", mock_aiocqhttp)
    monkeypatch.setitem(sys.modules, "aiocqhttp.exceptions", mock_aiocqhttp.exceptions)
    yield
    monkeypatch.undo()


class MockAiocqhttpBuilder:
    """构建 aiocqhttp 测试 mock 对象的工具类。"""

    @staticmethod
    def create_bot():
        """创建 mock CQHttp bot 实例。"""
        from tests.fixtures.helpers import NoopAwaitable

        bot = MagicMock()
        bot.send = AsyncMock()
        bot.call_action = AsyncMock()
        bot.on_request = MagicMock()
        bot.on_notice = MagicMock()
        bot.on_message = MagicMock()
        bot.on_websocket_connection = MagicMock()
        bot.run_task = MagicMock(return_value=NoopAwaitable())
        return bot
