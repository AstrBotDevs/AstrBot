"""Use real OneBot SDK types with an isolated CQHttp transport."""

from unittest.mock import AsyncMock, MagicMock

import pytest


def create_mock_aiocqhttp_modules():
    """Return the real SDK for callers migrating from legacy module mocks."""
    import aiocqhttp
    import aiocqhttp.exceptions

    return aiocqhttp


@pytest.fixture(autouse=True)
def mock_aiocqhttp_modules(monkeypatch, isolated_runtime_config):
    """Replace the adapter bot factory for the current test."""
    from astrbot.core.platform.sources.aiocqhttp import aiocqhttp_platform_adapter

    factory = MagicMock(
        side_effect=lambda *args, **kwargs: MockAiocqhttpBuilder.create_bot()
    )
    monkeypatch.setattr(aiocqhttp_platform_adapter, "CQHttp", factory)
    return factory


class MockAiocqhttpBuilder:
    """Build isolated CQHttp transport test doubles."""

    @staticmethod
    def create_bot():
        """Create a local bot with asynchronous transport methods."""
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
