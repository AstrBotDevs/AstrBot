import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest
import pytest_asyncio

from astrbot.core.platform.manager import PlatformManager
from astrbot.core.platform.platform import PlatformStatus
from astrbot.core.platform.sources.discord import discord_platform_adapter


@pytest_asyncio.fixture
async def discord_lifecycle(monkeypatch):
    """Load a real adapter and manager with controllable Discord clients.

    Args:
        monkeypatch: Pytest patch fixture.

    Yields:
        Manager, adapter configuration, and simulated clients.
    """
    clients = []
    for _ in range(2):
        started = asyncio.Event()
        outcome = asyncio.get_running_loop().create_future()

        async def start_polling(started=started, outcome=outcome):
            """Wait for the test to choose the receiver's outcome.

            Args:
                started: Signal that this client has started receiving.
                outcome: Future controlling this client's exit.
            """
            started.set()
            await outcome

        clients.append(
            SimpleNamespace(
                started=started,
                outcome=outcome,
                start_polling=AsyncMock(side_effect=start_polling),
                close=AsyncMock(),
                sync_commands=AsyncMock(),
                user=SimpleNamespace(id=1),
            )
        )
    monkeypatch.setattr(
        discord_platform_adapter, "DiscordBotClient", Mock(side_effect=clients)
    )
    config = {
        "id": "discord-lifecycle",
        "type": "discord",
        "enable": True,
        "discord_token": "test-token",
    }
    manager = PlatformManager(
        {"platform": [config], "platform_settings": {}}, asyncio.Queue()
    )
    existing_tasks = asyncio.all_tasks()
    await manager.load_platform(config)
    await asyncio.wait_for(clients[0].started.wait(), timeout=1)
    clients[0].tasks = asyncio.all_tasks() - existing_tasks
    try:
        yield manager, config, clients
    finally:
        await asyncio.wait_for(manager.terminate(), timeout=2)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["exception", "return", "cancel", "close_failure"])
async def test_discord_receive_exit_reports_error(discord_lifecycle, case):
    """Report every unexpected receiver exit through the real platform manager.

    Args:
        discord_lifecycle: Loaded manager and fake clients.
        case: Receiver exit scenario.
    """
    manager, _, clients = discord_lifecycle
    adapter = manager.platform_insts[0]
    tasks = manager._platform_tasks[adapter.client_self_id]
    failure = RuntimeError("Receiver failed")
    if case == "close_failure":
        clients[0].close.side_effect = RuntimeError("Close failed too")
    if case == "cancel":
        adapter._polling_task.cancel()
    elif case == "return":
        clients[0].outcome.set_result(None)
    else:
        clients[0].outcome.set_exception(failure)

    await asyncio.wait_for(asyncio.shield(tasks.wrapper), timeout=1)

    assert adapter.status == PlatformStatus.ERROR
    assert adapter.get_stats()["error_count"] == 1
    assert adapter.last_error.traceback
    if case in ("exception", "close_failure"):
        assert tasks.run.exception() is failure
        assert adapter.last_error.message == str(failure)
    else:
        assert "unexpected" in adapter.last_error.message.lower()
    assert all(task.done() for task in clients[0].tasks)
    clients[0].close.assert_awaited_once()
    clients[0].sync_commands.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["stop", "cancel_run", "stop_and_error"])
async def test_discord_shutdown_releases_tasks(discord_lifecycle, mode):
    """Stop without recording errors and finish command cleanup before closing.

    Args:
        discord_lifecycle: Loaded manager and fake clients.
        mode: Requested shutdown or outer task cancellation.
    """
    manager, config, clients = discord_lifecycle
    adapter = manager.platform_insts[0]
    tasks = manager._platform_tasks[adapter.client_self_id]
    calls = Mock()
    calls.attach_mock(clients[0].sync_commands, "sync_commands")
    calls.attach_mock(clients[0].close, "close")
    if mode == "cancel_run":
        tasks.run.cancel()
        await asyncio.wait_for(asyncio.shield(tasks.wrapper), timeout=1)
    else:
        if mode == "stop_and_error":
            adapter.shutdown_event.set()
            clients[0].outcome.set_exception(RuntimeError("Exit during shutdown"))
        await asyncio.wait_for(manager.terminate_platform(config["id"]), timeout=1)

    assert adapter.status == PlatformStatus.STOPPED
    assert not adapter.errors
    assert all(task.done() for task in clients[0].tasks)
    clients[0].close.assert_awaited_once()
    if mode != "cancel_run":
        assert [call[0] for call in calls.mock_calls] == ["sync_commands", "close"]


@pytest.mark.asyncio
async def test_discord_cancel_during_command_cleanup(discord_lifecycle):
    """Still close the client when shutdown is interrupted during command cleanup.

    Args:
        discord_lifecycle: Loaded manager and fake clients.
    """
    manager, config, clients = discord_lifecycle
    adapter = manager.platform_insts[0]
    tasks = manager._platform_tasks[adapter.client_self_id]
    cleaning_commands = asyncio.Event()

    async def sync_commands(**kwargs):
        """Block command cleanup until the run task is cancelled.

        Args:
            **kwargs: Command synchronization arguments.
        """
        cleaning_commands.set()
        await asyncio.Event().wait()

    clients[0].sync_commands.side_effect = sync_commands
    stopping = asyncio.create_task(manager.terminate_platform(config["id"]))
    try:
        await asyncio.wait_for(cleaning_commands.wait(), timeout=1)
        tasks.run.cancel()
        await asyncio.wait_for(asyncio.shield(stopping), timeout=1)
        assert adapter.status == PlatformStatus.STOPPED
        assert not adapter.errors
        assert all(task.done() for task in clients[0].tasks)
        clients[0].close.assert_awaited_once()
    finally:
        stopping.cancel()
        await asyncio.gather(stopping, return_exceptions=True)


@pytest.mark.asyncio
async def test_discord_reload_receives_messages(discord_lifecycle):
    """Reload a failed adapter and deliver a message to the real event queue.

    Args:
        discord_lifecycle: Loaded manager and fake clients.
    """
    manager, config, clients = discord_lifecycle
    previous = manager.platform_insts[0]
    old_tasks = manager._platform_tasks[previous.client_self_id]
    clients[0].outcome.set_exception(RuntimeError("Receiver failed"))
    await asyncio.wait_for(asyncio.shield(old_tasks.wrapper), timeout=1)

    await asyncio.wait_for(manager.reload(config), timeout=1)
    await asyncio.wait_for(clients[1].started.wait(), timeout=1)
    adapter = manager.platform_insts[0]
    message = Mock(
        spec=discord.Message,
        id=42,
        type=discord.MessageType.default,
        content="Message after reload",
        author=SimpleNamespace(id=2, display_name="Tester"),
        channel=SimpleNamespace(id=123, guild=None),
        guild=None,
        attachments=[],
        mentions=[],
        role_mentions=[],
        reference=None,
    )
    await clients[1].on_message_received({"bot_id": "1", "message": message})
    event = await asyncio.wait_for(manager.event_queue.get(), timeout=1)
    assert event.message_str == "Message after reload"
    assert adapter is not previous
    assert adapter.status == PlatformStatus.RUNNING
    assert not adapter.errors
    assert all(task.done() for task in clients[0].tasks)
    clients[0].close.assert_awaited_once()
