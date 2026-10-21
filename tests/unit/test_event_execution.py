"""Shared event lifecycle regression coverage for messages and Cron jobs."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from opentelemetry.trace import format_trace_id, get_current_span

from astrbot.core.agent.runners.base import AgentState
from astrbot.core.cron.manager import CronJobManager
from astrbot.core.log import _log_context, log_context
from astrbot.core.pipeline import scheduler as scheduler_module
from astrbot.core.platform.astr_message_event import AstrMessageEvent, event_context
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.utils import trace as trace_module
from astrbot.core.utils.active_event_registry import active_event_registry
from astrbot.core.utils.trace import trace_execution
from astrbot.core.utils.trace_store import TraceStore


@pytest.fixture
def frames(monkeypatch):
    """Capture trace updates without opening the production database.

    Args:
        monkeypatch: Pytest patch manager.

    Returns:
        Immutable persistence snapshots from the tested execution.
    """
    captured = []
    store = MagicMock()
    store.append.side_effect = lambda packet, **kwargs: (
        captured.append(json.loads(json.dumps(packet))) or True
    )
    monkeypatch.setitem(trace_module.astrbot_config, "trace_enable", True)
    monkeypatch.setattr(trace_module, "get_trace_store", lambda *_: store)
    monkeypatch.setattr(trace_module, "_get_log_broker", lambda: None)
    return captured


@pytest.fixture
def event(frames):
    """Create an event after test-only trace persistence is installed.

    Args:
        frames: Captured trace snapshots.

    Returns:
        Message event with a real trace model.
    """
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.sender = MessageMember(user_id="test-user", nickname="Test User")
    message.message = []
    return AstrMessageEvent(
        "Test event",
        message,
        PlatformMetadata(id="test", name="test-platform", description="Test"),
        "execution-test",
    )


@pytest.mark.parametrize(
    "failure", [None, RuntimeError("failed"), asyncio.CancelledError()]
)
def test_event_scope_finishes_and_restores_context(event, frames, tmp_path, failure):
    """Finish success, failure, and cancellation without swallowing exceptions.

    Args:
        event: Message event to execute.
        frames: Captured trace snapshots.
        tmp_path: Temporary attachment directory.
        failure: Optional failure raised by event processing.
    """
    attachment = tmp_path / "attachment.txt"
    attachment.write_text("temporary", encoding="utf-8")
    event.track_temporary_local_file(str(attachment))
    try:
        with (
            log_context(event.get_platform_id(), event.get_platform_name()),
            event_context(event),
            trace_execution(event.trace),
        ):
            root_context = get_current_span()
            platform_context = _log_context.get()
            assert (
                format_trace_id(root_context.get_span_context().trace_id)
                == event.trace.trace_id
            )
            assert platform_context.platform_id == "test"
            assert event in active_event_registry._events[event.unified_msg_origin]
            event.trace.record("agent_start", kind="agent")
            if failure:
                raise failure
            event.trace.record("agent_end", status="success")
            assert frames[-1]["trace"]["state"] == "running"
    except BaseException as exc:
        assert failure is exc
    else:
        assert failure is None
    root = frames[-1]["span"]
    assert frames[-1]["trace"]["state"] == "completed"
    assert root["span_id"] == event.trace.span_id
    assert root["status"]["code"] == (2 if failure else 1)
    if failure:
        assert root["status"]["message"] == (str(failure) or type(failure).__name__)
    assert not event.trace._pending
    assert not get_current_span().get_span_context().is_valid
    assert _log_context.get() is None
    assert not root_context.is_recording() and not platform_context.active
    assert event.unified_msg_origin not in active_event_registry._events
    assert not attachment.exists()


def test_nested_event_scopes_do_not_finish_early(event, frames):
    """Allow nested entry points without finishing or rebinding the event.

    Args:
        event: Message event to execute.
        frames: Captured trace snapshots.
    """
    assert not hasattr(event, "execution")
    with trace_execution(event.trace):
        with event_context(event):
            event.trace.record("agent_start")
            context = get_current_span()
            with event_context(event), trace_execution(event.trace):
                assert get_current_span() is context
            assert event in active_event_registry._events[event.unified_msg_origin]
            event.trace.record("agent_end", status="success")
        assert event.trace._summary["state"] == "running"
        assert event.unified_msg_origin not in active_event_registry._events
    final_count = len(frames)
    event.trace.record("pipeline_end", status="success")
    assert len(frames) == final_count
    assert (
        sum(
            packet.get("span", {}).get("span_id") == event.trace.span_id
            and bool(packet.get("span", {}).get("end_time_unix_nano"))
            for packet in frames
        )
        == 1
    )


def test_event_completion_reaches_sqlite(event, frames, tmp_path, monkeypatch):
    """Persist completion only after the event scope, not after its response.

    Args:
        event: Message event to execute.
        frames: Initial captured trace snapshots.
        tmp_path: Temporary database directory.
        monkeypatch: Pytest patch manager.
    """
    store = TraceStore(tmp_path / "traces.db", {})
    monkeypatch.setattr(trace_module, "get_trace_store", lambda *_: store)
    try:
        for frame in frames:
            assert store.append(frame)
        with event_context(event), trace_execution(event.trace):
            event.trace.record(
                "response_sent", kind="response", source="core", message="Done"
            )
            assert store.flush()
            assert store.get_trace(event.trace.trace_id)["trace"]["state"] == "running"
        assert store.flush()
        detail = store.get_trace(event.trace.trace_id)
        assert detail["trace"]["state"] == "completed"
        root = next(span for span in detail["spans"] if not span["parent_span_id"])
        assert root["end_time_unix_nano"]
        assert root["status"]["code"] == 1
    finally:
        store.close()


@pytest.mark.asyncio
async def test_task_cancellation_finishes_event(event, frames):
    """Close the root when an awaited event task is actually cancelled.

    Args:
        event: Message event to execute.
        frames: Captured trace snapshots.
    """
    started = asyncio.Event()

    async def execute():
        with event_context(event), trace_execution(event.trace):
            started.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(execute())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert frames[-1]["trace"]["state"] == "completed"
    assert frames[-1]["span"]["status"] == {"code": 2, "message": "CancelledError"}
    assert event.unified_msg_origin not in active_event_registry._events
    assert not get_current_span().get_span_context().is_valid


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_at", [None, "stages", "delivery"])
async def test_scheduler_uses_event_scope(event, frames, monkeypatch, failure_at):
    """Finish ordinary messages only after stages and closing delivery.

    Args:
        event: Message event to execute.
        frames: Captured trace snapshots.
        monkeypatch: Pytest patch manager.
        failure_at: Optional processing step that fails.
    """
    scheduler = object.__new__(scheduler_module.PipelineScheduler)

    async def process(current):
        assert current is event
        assert frames[-1]["trace"]["state"] == "running"
        if failure_at == "stages":
            raise RuntimeError("stage failed")

    async def deliver(message):
        assert message is None
        assert frames[-1]["trace"]["state"] == "running"
        if failure_at == "delivery":
            raise RuntimeError("delivery failed")

    scheduler._process_stages = AsyncMock(side_effect=process)
    event.send = AsyncMock(side_effect=deliver)
    monkeypatch.setattr(scheduler_module, "WebChatMessageEvent", AstrMessageEvent)
    if failure_at:
        with pytest.raises(RuntimeError):
            await scheduler.execute(event)
    else:
        await scheduler.execute(event)
    assert event.send.await_count == int(failure_at != "stages")
    assert frames[-1]["trace"]["state"] == "completed"
    assert frames[-1]["span"]["status"]["code"] == (2 if failure_at else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure_at",
    [
        None,
        "config",
        "conversation",
        "build",
        "empty",
        "run",
        "state",
        "history",
        "cancel",
    ],
)
async def test_cron_uses_event_scope(frames, monkeypatch, failure_at):
    """Cover Cron construction, execution, saving, failure, and cancellation.

    Args:
        frames: Captured trace snapshots.
        monkeypatch: Pytest patch manager.
        failure_at: Optional execution step that fails.
    """
    from astrbot.core import astr_main_agent
    from astrbot.core.cron import manager as cron_module

    ctx = MagicMock()
    ctx.get_config.return_value = {"admins_id": []}
    if failure_at == "config":
        ctx.get_config.side_effect = RuntimeError("config failed")
    manager = CronJobManager(MagicMock())
    manager.ctx = ctx
    captured = {}

    async def conversation(**kwargs):
        captured["event"] = kwargs["event"]
        assert (
            format_trace_id(get_current_span().get_span_context().trace_id)
            == captured["event"].trace.trace_id
        )
        if failure_at == "conversation":
            raise RuntimeError("conversation failed")
        return SimpleNamespace(history="[]")

    async def steps(max_steps):
        assert frames[-1]["trace"]["state"] == "running"
        if failure_at == "run":
            raise RuntimeError("run failed")
        if failure_at == "cancel":
            raise asyncio.CancelledError()
        yield None

    runner = MagicMock(
        state=AgentState.ERROR if failure_at == "state" else AgentState.DONE
    )
    runner.step_until_done.side_effect = steps
    runner.get_final_llm_resp.return_value = None

    async def build(**kwargs):
        assert (
            format_trace_id(get_current_span().get_span_context().trace_id)
            == kwargs["event"].trace.trace_id
        )
        assert _log_context.get().platform_id == "test"
        assert _log_context.get().platform_type == "cron"
        if failure_at == "build":
            raise RuntimeError("build failed")
        return (
            None
            if failure_at == "empty"
            else SimpleNamespace(agent_runner=runner, conversation_events=None)
        )

    async def persist(*args, **kwargs):
        assert frames[-1]["trace"]["state"] == "running"
        assert (
            format_trace_id(get_current_span().get_span_context().trace_id)
            == kwargs["event"].trace.trace_id
        )
        if failure_at == "history":
            raise RuntimeError("history failed")

    monkeypatch.setattr(astr_main_agent, "_get_session_conv", conversation)
    monkeypatch.setattr(astr_main_agent, "build_main_agent", build)
    save = AsyncMock(side_effect=persist)
    monkeypatch.setattr(cron_module, "persist_agent_history", save)
    execution = manager._woke_main_agent(
        message="Scheduled task",
        session_str="test:FriendMessage:cron-execution-test",
        extras={"cron_job": {"id": "test-job"}},
    )
    if failure_at:
        with pytest.raises(
            asyncio.CancelledError if failure_at == "cancel" else RuntimeError
        ):
            await execution
    else:
        await execution
    assert save.await_count == int(failure_at in (None, "history"))
    final = frames[-1]
    assert final["trace"]["state"] == "completed"
    assert final["span"]["span_id"] == final["trace"]["root_span_id"]
    assert final["span"]["status"]["code"] == (2 if failure_at else 1)
    assert "test:FriendMessage:cron-execution-test" not in active_event_registry._events
    assert not get_current_span().get_span_context().is_valid
    assert _log_context.get() is None
