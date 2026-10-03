from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.platform.sources.telegram.tg_adapter import TelegramPlatformAdapter


@pytest.mark.asyncio
async def test_telegram_command_sync_deletes_stale_commands_when_empty():
    adapter = object.__new__(TelegramPlatformAdapter)
    adapter.last_command_hash = None
    adapter.collect_commands = lambda: []
    adapter.client = SimpleNamespace(
        delete_my_commands=AsyncMock(),
        set_my_commands=AsyncMock(),
    )

    await adapter.register_commands()

    adapter.client.delete_my_commands.assert_awaited_once()
    adapter.client.set_my_commands.assert_not_awaited()
    assert adapter.last_command_hash == hash(())

    await adapter.register_commands()
    adapter.client.delete_my_commands.assert_awaited_once()


@pytest.mark.asyncio
async def test_telegram_refresh_only_runs_for_started_registration():
    adapter = object.__new__(TelegramPlatformAdapter)
    adapter.enable_command_register = True
    adapter._application_started = True
    adapter.register_commands = AsyncMock()

    await adapter.refresh_registered_commands()
    adapter.register_commands.assert_awaited_once()

    adapter.register_commands.reset_mock()
    adapter._application_started = False
    await adapter.refresh_registered_commands()
    adapter.register_commands.assert_not_awaited()
