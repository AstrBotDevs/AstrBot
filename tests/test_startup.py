"""Core construction and shutdown keep local state and dependency order intact."""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from astrbot.core import core_lifecycle as lifecycle_module
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle, LifecycleState
from astrbot.core.event_bus import EventBus
from astrbot.core.message.components import Plain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.utils import trace_store


@pytest.fixture
def make_core(database, monkeypatch):
    for name in ("http_proxy", "https_proxy", "no_proxy"):
        monkeypatch.setenv(name, "inherited-value")

    def create(config=None):
        monkeypatch.setattr(lifecycle_module, "astrbot_config", config or {})
        return AstrBotCoreLifecycle(log_broker=Mock(), db=database)

    return create


@pytest.fixture
def track_disposal(database, monkeypatch):
    calls = AsyncMock()
    original_dispose = AsyncEngine.dispose

    async def dispose(engine: AsyncEngine, close: bool = True) -> None:
        if engine is database.engine:
            await calls()
        await original_dispose(engine, close=close)

    monkeypatch.setattr(AsyncEngine, "dispose", dispose)
    return calls


def test_new_core_exposes_an_unstarted_lifecycle(make_core):
    core = make_core()
    assert core.lifecycle_state is LifecycleState.CREATED
    assert core.core_initialized is False
    assert core.runtime_ready is False
    assert core.runtime_failed is False
    assert not core.runtime_ready_event.is_set()
    assert not core.runtime_failed_event.is_set()
    assert core.runtime_bootstrap_task is None
    assert core.curr_tasks == []
    assert core.agent_runtimes == {}


def test_explicit_proxy_configuration_sets_both_protocols_and_bypass_list(make_core):
    make_core(
        {
            "http_proxy": "http://127.0.0.1:8123",
            "no_proxy": ["localhost", "127.0.0.1", "internal.example"],
        }
    )
    assert os.environ["http_proxy"] == "http://127.0.0.1:8123"
    assert os.environ["https_proxy"] == "http://127.0.0.1:8123"
    assert os.environ["no_proxy"] == "localhost,127.0.0.1,internal.example"


def test_no_proxy_configuration_clears_inherited_proxy_and_keeps_loopback_local(
    make_core,
):
    make_core()
    assert "http_proxy" not in os.environ
    assert "https_proxy" not in os.environ
    assert os.environ["no_proxy"] == "localhost,127.0.0.1,::1"


@pytest.mark.asyncio
async def test_partial_core_shutdown_closes_preferences_database_and_dashboard(
    make_core, database, monkeypatch, track_disposal
):
    core = make_core()
    core.dashboard_shutdown_event = asyncio.Event()
    preferences = SimpleNamespace(db_helper=database, close=AsyncMock())
    monkeypatch.setattr(lifecycle_module, "sp", preferences)
    close_traces = Mock()
    monkeypatch.setattr(trace_store, "close_trace_store", close_traces)

    await core.stop()

    preferences.close.assert_awaited_once()
    close_traces.assert_called_once()
    track_disposal.assert_awaited_once()
    assert core.dashboard_shutdown_event.is_set()


@pytest.mark.asyncio
async def test_shutdown_waits_for_pipeline_finally_before_closing_dependencies(
    make_core, database, monkeypatch, track_disposal
):
    core = make_core()
    order = []
    entered = asyncio.Event()
    cleanup_entered = asyncio.Event()
    allow_cleanup = asyncio.Event()
    provider_open = True
    umo = "adapter:FriendMessage:alice"
    await database.create_conversation(
        user_id=umo, platform_id="adapter", cid="cleanup-id", content=[]
    )

    async def execute(_event):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup_entered.set()
            await allow_cleanup.wait()
            assert provider_open
            conversations = await database.get_conversations(umo)
            assert [conversation.conversation_id for conversation in conversations] == [
                "cleanup-id"
            ]
            order.append("pipeline")

    async def close_provider():
        nonlocal provider_open
        provider_open = False
        order.append("provider")

    async def close_preferences():
        order.append("preferences")

    async def dispose():
        order.append("database")

    track_disposal.side_effect = dispose
    monkeypatch.setattr(
        lifecycle_module,
        "sp",
        SimpleNamespace(
            db_helper=database, close=AsyncMock(side_effect=close_preferences)
        ),
    )
    monkeypatch.setattr(
        trace_store, "close_trace_store", lambda: order.append("traces")
    )
    core.provider_manager = SimpleNamespace(
        terminate=AsyncMock(side_effect=close_provider)
    )
    scheduler = SimpleNamespace(
        ctx=SimpleNamespace(astrbot_config={}), execute=AsyncMock(side_effect=execute)
    )
    event_bus = EventBus(
        asyncio.Queue(),
        {"main": scheduler},
        SimpleNamespace(get_conf_info=Mock(return_value={"id": "main"})),
    )
    core.event_bus = event_bus
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.sender = MessageMember(user_id="alice", nickname="Alice")
    message.message = [Plain("start")]
    message.message_str = "start"
    message.raw_message = "start"
    event = AstrMessageEvent(
        "start",
        message,
        PlatformMetadata(name="test", description="Test", id="adapter"),
        "alice",
    )
    await core.event_bus.event_queue.put(event)
    dispatch = asyncio.create_task(core.event_bus.dispatch())
    core.curr_tasks = [dispatch]
    stopping = None
    try:
        await asyncio.wait_for(entered.wait(), 2)
        stopping = asyncio.create_task(core.stop())
        await asyncio.wait_for(cleanup_entered.wait(), 2)
        assert not stopping.done()
        assert order == []
        allow_cleanup.set()
        await asyncio.wait_for(stopping, 2)
    finally:
        allow_cleanup.set()
        if stopping is not None:
            await asyncio.gather(stopping, return_exceptions=True)
        if not dispatch.done():
            dispatch.cancel()
        await asyncio.gather(dispatch, return_exceptions=True)

    assert dispatch.cancelled()
    assert event_bus._pending_tasks == {}
    assert core.event_bus is None
    assert order == ["pipeline", "provider", "preferences", "traces", "database"]


@pytest.mark.asyncio
async def test_plugin_cleanup_failure_does_not_skip_other_plugins_or_provider(
    make_core, database, monkeypatch, track_disposal
):
    core = make_core()
    first, second = object(), object()
    terminate_plugin = AsyncMock(side_effect=[RuntimeError("plugin failed"), None])
    core.plugin_manager = SimpleNamespace(
        context=SimpleNamespace(get_all_stars=lambda: [first, second]),
        _terminate_plugin=terminate_plugin,
    )
    core.provider_manager = SimpleNamespace(terminate=AsyncMock())
    monkeypatch.setattr(
        lifecycle_module, "sp", SimpleNamespace(db_helper=database, close=AsyncMock())
    )
    monkeypatch.setattr(trace_store, "close_trace_store", Mock())

    await core.stop()

    assert [call.args[0] for call in terminate_plugin.await_args_list] == [
        first,
        second,
    ]
    core.provider_manager.terminate.assert_awaited_once()
    track_disposal.assert_awaited_once()
