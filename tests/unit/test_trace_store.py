"""Canonical trace model, correlation, bounded storage, and migration tests."""

import asyncio
import gc
import json
import logging
import re
import runpy
import sqlite3
import threading
import time
import weakref
from pathlib import Path

import pytest
from opentelemetry.sdk.trace import Span, TracerProvider
from opentelemetry.trace import format_span_id, get_current_span, get_tracer_provider

from astrbot.core.log import LogBroker, LogManager
from astrbot.core.utils import trace as trace_module
from astrbot.core.utils.migra_helper import migrate_config_on_load
from astrbot.core.utils.storage_cleaner import StorageCleaner
from astrbot.core.utils.telemetry import (
    MAX_ATTRIBUTE_BYTES,
    bounded_attributes,
)
from astrbot.core.utils.trace import TraceSpan, trace_execution
from astrbot.core.utils.trace_store import MAX_FRAME_BYTES, TraceStore


@pytest.fixture
def capture(monkeypatch):
    """Capture immutable snapshots without writing to the default path."""
    frames = []

    class CaptureStore:
        def append(self, payload, **kwargs):
            frames.append(json.loads(json.dumps(payload)))
            return True

    monkeypatch.setitem(trace_module.astrbot_config, "trace_enable", True)
    monkeypatch.setattr(trace_module, "get_trace_store", lambda *_: CaptureStore())
    monkeypatch.setattr(trace_module, "_get_log_broker", lambda: None)
    return frames


def test_standard_ids_parents_and_immutable_snapshots(capture):
    trace = TraceSpan("message", "qq:Group:123", "Test", "Hello")
    assert re.fullmatch("[0-9a-f]{32}", trace.trace_id)
    assert re.fullmatch("[0-9a-f]{16}", trace.span_id)
    with trace.context():
        root = get_current_span()
        trace.record("event_received", platform_id="qq", kind="message")
        trace.record(
            "handler_start",
            kind="plugin_handler",
            plugin="test",
            handler_full_name="test.handler",
        )
        handler = get_current_span()
        handler_id = format_span_id(handler.get_span_context().span_id)
        trace.record("agent_start", kind="agent")
        agent = get_current_span()
        agent_id = format_span_id(agent.get_span_context().span_id)
        trace.record("agent_tool_call", tool_name="weather")
        trace.record("agent_tool_result", tool_result="Sunny")
        trace.record("agent_end", status="success")
        assert (
            format_span_id(get_current_span().get_span_context().span_id) == handler_id
        )
        trace.record("handler_end", handler_full_name="test.handler", status="success")
        assert (
            format_span_id(get_current_span().get_span_context().span_id)
            == trace.span_id
        )
        trace.record("response_sent", kind="response", source="core", message="Sunny")
        trace.record("pipeline_end", status="success")
    assert not get_current_span().get_span_context().is_valid
    spans = {
        frame["span"]["span_id"]: frame["span"] for frame in capture if "span" in frame
    }
    assert len(spans) == 4
    assert spans[trace.span_id]["attributes"]["astrbot.kind"] == "message"
    assert spans[handler_id]["attributes"]["astrbot.kind"] == "plugin_handler"
    assert spans[agent_id]["attributes"]["astrbot.kind"] == "agent"
    assert any(span["attributes"]["astrbot.kind"] == "tool" for span in spans.values())
    for frame in capture:
        for model in (frame.get("span", {}), frame.get("event", {})):
            assert (
                not {"astrbot.action", "astrbot.end_action", "astrbot.duration_ms"}
                & model.get("attributes", {}).keys()
            )
    assert spans[handler_id]["parent_span_id"] == trace.span_id
    assert spans[agent_id]["parent_span_id"] == handler_id
    assert all(span["end_time_unix_nano"] for span in spans.values())
    assert capture[0]["span"]["end_time_unix_nano"] is None
    assert capture[0]["trace"]["state"] == "running"
    assert capture[-1]["trace"]["state"] == "completed"
    assert not trace._pending
    assert agent.parent == handler.get_span_context()
    for sdk_span in (root, handler, agent):
        assert isinstance(sdk_span, Span) and not sdk_span.is_recording()
        packet = spans[format_span_id(sdk_span.context.span_id)]
        assert str(sdk_span.start_time) == packet["start_time_unix_nano"]
        assert str(sdk_span.end_time) == packet["end_time_unix_nano"]
        assert sdk_span.status.status_code.value == packet["status"]["code"]
        assert dict(sdk_span.attributes) == packet["attributes"]
    events = [frame["event"] for frame in capture if "event" in frame]
    assert len(events) == len(root.events) == 1
    assert root.events[0].name == events[0]["name"] == "response_sent"
    assert str(root.events[0].timestamp) == events[0]["time_unix_nano"]
    assert dict(root.events[0].attributes) == events[0]["attributes"]
    assert all("events" not in frame.get("span", {}) for frame in capture)


def test_sdk_context_is_isolated_and_restores_foreign_span(capture):
    """Use standard context without taking ownership of other providers.

    Args:
        capture: Immutable trace snapshots.
    """
    global_provider = get_tracer_provider()
    provider = TracerProvider(shutdown_on_exit=False)
    try:
        with provider.get_tracer("plugin").start_as_current_span("plugin") as foreign:
            trace = TraceSpan("message")
            assert trace._root.parent is None
            assert trace._root.context.trace_id != foreign.context.trace_id
            with trace_execution(trace):
                assert get_current_span() is trace._root
            assert get_current_span() is foreign
            assert foreign.is_recording()
        assert get_tracer_provider() is global_provider
    finally:
        provider.shutdown()


def test_sdk_disabled_does_not_break_messages(capture, monkeypatch):
    """Respect the SDK kill switch without emitting invalid trace IDs.

    Args:
        capture: Immutable trace snapshots.
        monkeypatch: Pytest patch manager.
    """
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    module = runpy.run_path(trace_module.__file__)
    trace = module["TraceSpan"]("disabled")
    with trace_execution(trace):
        assert not get_current_span().is_recording()
        trace.record("event_received")
        trace.record("agent_start")
    assert not capture


def test_agent_and_command_types_are_independent_and_persisted(persisted, capture):
    """Keep listener hooks distinct while preserving both call classifications.

    Args:
        persisted: Isolated trace database.
        capture: Immutable trace snapshots.
    """
    trace = TraceSpan("message")
    with trace.context():
        trace.record(
            "handler_start",
            handler_full_name="plugin.listener",
            handler_category="listener",
        )
        trace.record(
            "handler_end", handler_full_name="plugin.listener", status="success"
        )
        assert trace._summary["has_commands"] is False
        trace.record(
            "handler_start",
            handler_full_name="plugin.command",
            handler_category="command",
        )
        trace.record(
            "handler_end", handler_full_name="plugin.command", status="success"
        )
        assert trace._summary["has_commands"] is True
        assert trace._summary["has_models"] is False
        trace.record("agent_start")
        trace.record("agent_end", status="success")
        trace.record("pipeline_end", status="success")
    for frame in capture:
        assert persisted.append(frame)
    assert persisted.flush()
    summary = persisted.list_traces()["traces"][0]
    assert summary["has_commands"] is True and summary["has_models"] is True
    with sqlite3.connect(persisted.path) as connection:
        summary.pop("has_commands")
        connection.execute(
            "UPDATE traces SET data=? WHERE trace_id=?",
            (json.dumps(summary), trace.trace_id),
        )
    legacy = persisted.list_traces()["traces"][0]
    assert legacy["has_commands"] is True
    assert persisted.get_trace(trace.trace_id)["trace"].get("has_commands") is None


def test_internal_transitions_and_timing_are_not_persisted(capture):
    """Keep call matching internal while preserving handler metadata.

    Args:
        capture: Immutable trace snapshots.
    """
    trace = TraceSpan("message")
    with trace.context():
        trace.record("event_received")
        trace.record(
            "handler_start",
            handler_full_name="plugin.handler",
            handler_type="AdapterMessageEvent",
            duration_ms=999,
        )
        handler_id = format_span_id(get_current_span().get_span_context().span_id)
        trace.record(
            "handler_end",
            handler_full_name="plugin.handler",
            status="success",
            duration_ms=999,
        )
        trace.record("pipeline_end", status="success", duration_ms=999)
    handler = next(
        frame["span"]
        for frame in reversed(capture)
        if frame.get("span", {}).get("span_id") == handler_id
    )
    assert handler["attributes"]["astrbot.kind"] == "plugin_handler"
    assert handler["attributes"]["astrbot.handler_type"] == "AdapterMessageEvent"
    assert handler["end_time_unix_nano"]
    for frame in capture:
        assert (
            not {"astrbot.action", "astrbot.end_action", "astrbot.duration_ms"}
            & frame.get("span", {}).get("attributes", {}).keys()
        )


@pytest.mark.asyncio
async def test_logs_correlate_and_detached_contexts_expire(capture):
    trace = TraceSpan("message")
    broker = LogBroker()
    log = logging.Logger("astrbot.trace_test")
    LogManager.set_queue_handler(log, broker)
    release = asyncio.Event()

    async def late_log():
        await release.wait()
        log.info("Detached")

    with trace.context():
        trace.record("event_received")
        log.info("Root")
        trace.record("handler_start", handler_full_name="plugin.handler")
        child_id = format_span_id(get_current_span().get_span_context().span_id)
        task = asyncio.create_task(late_log())
        log.warning("Handler")
        trace.record(
            "handler_end", handler_full_name="plugin.handler", status="success"
        )
        log.info("Root again")
        trace.record("pipeline_end", status="success")
    release.set()
    await task
    entries = list(broker.log_cache)
    assert entries[0]["trace_id"] == trace.trace_id
    assert entries[0]["span_id"] == trace.span_id
    assert entries[1]["span_id"] == child_id
    assert entries[1]["severity_number"] == 13
    assert entries[1]["body"] == "Handler"
    assert entries[2]["span_id"] == trace.span_id
    assert "trace_id" not in entries[-1]


@pytest.mark.asyncio
async def test_concurrent_abandoned_spans_end(capture):
    trace = TraceSpan("message")
    release = asyncio.Event()

    async def child(name):
        trace.record("handler_start", handler_full_name=name)
        context = get_current_span()
        await release.wait()
        assert not context.is_recording()

    with pytest.raises(RuntimeError, match="Cancelled"), trace_execution(trace):
        trace.record("event_received")
        tasks = [asyncio.create_task(child(name)) for name in ("a", "b")]
        await asyncio.sleep(0)
        raise RuntimeError("Cancelled")
    release.set()
    await asyncio.gather(*tasks)
    assert not trace._pending
    ended = [
        frame["span"]
        for frame in capture
        if frame.get("span", {}).get("end_time_unix_nano")
    ]
    assert len(ended) == 3
    assert all(span["status"]["code"] == 2 for span in ended)


def test_pause_preserves_completion(capture, monkeypatch):
    trace = TraceSpan("message")
    with trace_execution(trace):
        trace.record("event_received")
        trace.record("handler_start", handler_full_name="test.handler")
        monkeypatch.setitem(trace_module.astrbot_config, "trace_enable", False)
        trace.record("agent_start")
        trace.record("handler_end", handler_full_name="test.handler", status="success")
    count = len(capture)
    with trace_execution(TraceSpan("disabled")):
        assert not get_current_span().get_span_context().is_valid
    assert len(capture) == count
    assert capture[-1]["trace"]["state"] == "completed"
    assert capture[-1]["trace"]["span_count"] == 2


def test_limits_preserve_completion(capture):
    attrs = bounded_attributes(
        {
            "astrbot.body": "字" * 50000,
            "astrbot.object": {"nested": ["x" * 50000] * 100},
        }
    )
    assert len(json.dumps(attrs, ensure_ascii=False).encode()) <= MAX_ATTRIBUTE_BYTES
    assert attrs["astrbot.truncated"] is True
    assert all(isinstance(value, (str, bool, int, float)) for value in attrs.values())
    trace = TraceSpan("message")
    with trace.context():
        trace.record("event_received")
        for index in range(400):
            trace.record("handler_start", handler_full_name=str(index))
            trace.record("handler_end", handler_full_name=str(index), status="success")
        trace.record("pipeline_end", status="success")
    assert trace._span_count <= 128
    assert trace._summary["truncated"] is True
    assert capture[-1]["trace"]["state"] == "completed"


@pytest.fixture
def persisted(tmp_path, capture):
    """Create an isolated dedicated database."""
    store = TraceStore(
        tmp_path / "traces.db", {"trace_db_max_mb": 8, "trace_retention_days": 7}
    )
    yield store
    store.close()


def test_trace_cleanup_matches_exact_adapter(persisted, capture):
    """Remove a complete trace and its children without SQL wildcard matching."""
    ids = ["bot_%", "BOT_%", "bot_ab", "bot_%-other"]
    traces = []
    for platform_id in ids:
        trace = TraceSpan("message", f"{platform_id}:GroupMessage:room:1")
        trace.record("event_received")
        trace.record("response_sent", message="Reply")
        trace.record("pipeline_end", status="success")
        traces.append(trace)
    for frame in capture:
        assert persisted.append(frame)
    assert persisted.flush()

    assert persisted.clear_history(platform_id="bot_%") == {"removed_traces": 1}
    assert persisted.get_trace(traces[0].trace_id) is None
    assert all(persisted.get_trace(trace.trace_id) for trace in traces[1:])
    with sqlite3.connect(persisted.path) as connection:
        for table in ("spans", "events"):
            assert connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE trace_id = ?", (traces[0].trace_id,)
            ).fetchone()[0] == 0


def test_database_pages_filters_details_and_restart(persisted, capture):
    traces = []
    for index in range(4):
        trace = TraceSpan("message", "qq:Group:123", "Test", f"Message {index}")
        with trace.context():
            trace.record("event_received")
            trace.record(
                "handler_start",
                plugin="test",
                plugin_display_name="Display Test",
                handler_full_name="test.handler",
                handler_category="command" if index == 0 else "listener",
            )
            trace.record(
                "handler_end",
                handler_full_name="test.handler",
                status="error" if index == 2 else "success",
            )
            trace.record(
                "response_sent", kind="response", source="plugin:test", message="Reply"
            )
            if index != 3:
                trace.record("pipeline_end", status="success")
        traces.append(trace)
    for frame in capture:
        assert persisted.append(frame)
    assert persisted.flush()
    first = persisted.list_traces(limit=2)
    second = persisted.list_traces(limit=2, cursor=first["cursor"])
    numbered = persisted.list_traces(limit=2, page=2)
    assert numbered["page"] == 2
    assert [item["trace_id"] for item in numbered["traces"]] == [
        item["trace_id"] for item in second["traces"]
    ]
    assert persisted.list_traces(limit=2, page=999)["page"] == 2
    assert persisted.list_traces(limit=2, errors=True, page=999)["page"] == 1
    with pytest.raises(ValueError):
        persisted.list_traces(page=0)
    with pytest.raises(ValueError):
        persisted.list_traces(page=2, cursor=first["cursor"])
    assert first["total"] == 4
    assert len(first["traces"]) == len(second["traces"]) == 2
    assert {item["trace_id"] for item in first["traces"]}.isdisjoint(
        item["trace_id"] for item in second["traces"]
    )
    assert persisted.list_traces(errors=True)["total"] == 1
    assert persisted.list_traces(plugins=True, query="Display Test")["total"] == 4
    assert persisted.list_traces(models=True)["total"] == 0
    assert persisted.list_traces(commands=True)["total"] == 1
    assert persisted.list_traces(status="running")["total"] == 1
    assert persisted.list_traces(status="completed")["total"] == 2
    assert persisted.list_traces(status="error")["total"] == 1
    assert persisted.list_traces(platforms=["qq"])["total"] == 4
    assert persisted.list_traces(platforms=["telegram"])["total"] == 0
    assert persisted.list_traces(message_types=["Group"])["total"] == 4
    assert persisted.list_traces(message_types=["FriendMessage"])["total"] == 0
    assert persisted.list_traces(umo="qq:Group:123")["total"] == 4
    detail = persisted.get_trace(traces[0].trace_id)
    assert len(detail["spans"]) == 2
    assert any(
        event["name"] == "response_sent"
        for span in detail["spans"]
        for event in span.get("events", [])
    )
    assert persisted.get_trace("0" * 32) is None
    persisted.close()
    restarted = TraceStore(persisted.path, persisted.config)
    try:
        assert restarted.flush()
        detail = restarted.get_trace(traces[3].trace_id)
        assert detail["trace"]["state"] == "interrupted"
        assert detail["trace"]["has_errors"] is True
        assert all(span["end_time_unix_nano"] for span in detail["spans"])
    finally:
        restarted.close()


# Keep node IDs below Windows' PYTEST_CURRENT_TEST environment variable limit.
@pytest.mark.parametrize(
    "prompt",
    ["x" * 8192, "字" * 20000, "x" * 131072],
    ids=["ascii-8k", "unicode-20k", "ascii-128k"],
)
def test_long_prompt_is_preserved_in_spans_events_and_database(
    persisted, capture, prompt
):
    trace = TraceSpan("message")
    with trace.context():
        trace.record("event_received")
        trace.record("agent_start", system_prompt=prompt)
        trace.record("astr_agent_prepare", system_prompt=prompt)
        trace.record("agent_end", status="success")
        trace.record("pipeline_end", status="success")
    assert capture[-1]["trace"]["truncated"] is False
    for frame in capture:
        assert persisted.append(frame)
    assert persisted.flush()
    detail = persisted.get_trace(trace.trace_id)
    agent = next(span for span in detail["spans"] if span["parent_span_id"])
    assert agent["attributes"]["astrbot.system_prompt"] == prompt
    assert agent["events"][0]["attributes"]["astrbot.system_prompt"] == prompt
    assert detail["trace"]["truncated"] is False


def test_retention_deletes_whole_traces(persisted, capture):
    trace = TraceSpan("message")
    trace.record("event_received")
    trace.record("response_sent", message="Reply")
    trace.record("pipeline_end", status="success")
    for frame in capture:
        assert persisted.append(frame)
    assert persisted.flush()
    with sqlite3.connect(persisted.path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "UPDATE traces SET updated_ns=?", (time.time_ns() - 8 * 86400 * 10**9,)
        )
        persisted._prune(connection)
        for table in ("traces", "spans", "events"):
            assert (
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
            )


def test_oversized_queue_records_are_rejected(persisted):
    assert persisted.append({"oversized": "x" * MAX_FRAME_BYTES}) is False
    assert persisted.dropped == 1
    assert persisted._pending_bytes == 0


def test_orphan_cleanup_preserves_live_and_pending_traces(persisted, capture, monkeypatch):
    """Recover dropped completion frames without retaining dead trace objects.

    Args:
        persisted: Isolated trace database.
        capture: Enable recording without production storage or live clients.
        monkeypatch: Pytest patch manager.
    """
    monkeypatch.setattr(trace_module, "get_trace_store", lambda *_: persisted)
    assert persisted.flush()
    live = TraceSpan("live")
    live.record("event_received")
    abandoned = TraceSpan("abandoned")
    abandoned.record("event_received")
    abandoned_id = abandoned.trace_id
    reference = weakref.ref(abandoned)
    del abandoned
    gc.collect()
    assert reference() is None
    assert abandoned_id not in persisted._active_traces
    assert persisted.flush()

    entered, release = threading.Event(), threading.Event()
    original_write = persisted._write

    def held_write(connection, batch):
        """Pause persistence to force a rejected terminal frame."""
        entered.set()
        assert release.wait(5)
        original_write(connection, batch)

    monkeypatch.setattr(persisted, "_write", held_write)
    persisted.queue.maxsize = 1
    lost = TraceSpan("lost completion")
    try:
        lost.record("event_received")
        assert entered.wait(5)
        lost.record("response_sent", message="done")
        lost.record("pipeline_end", status="success")
        assert persisted.dropped == 1
        # Even a finished owner must remain protected until queued frames drain.
        with sqlite3.connect(persisted.path) as connection:
            persisted._interrupt_inactive(connection)
            assert connection.execute(
                "SELECT trace_id FROM protected_traces WHERE trace_id=?", (lost.trace_id,)
            ).fetchone()
        assert persisted.get_trace(live.trace_id)["trace"]["state"] == "running"
        release.set()
        assert persisted.flush()
        assert not persisted._pending_traces
        assert lost.trace_id not in persisted._active_traces
        with sqlite3.connect(persisted.path) as connection:
            persisted._interrupt_inactive(connection)
        detail = persisted.get_trace(lost.trace_id)
        assert detail["trace"]["state"] == "interrupted"
        assert all(span["end_time_unix_nano"] for span in detail["spans"])
        assert persisted.clear_history()["removed_traces"] == 2
        assert persisted.get_trace(live.trace_id)["trace"]["state"] == "running"
    finally:
        release.set()
        live.record("pipeline_end", status="success")
    assert persisted.flush()
    assert persisted.dropped == 1
    assert persisted._pending_bytes == 0


@pytest.mark.parametrize("same_timestamp", [False, True])
def test_stale_updates_do_not_reopen_completed_trace(
    persisted, capture, same_timestamp
):
    trace = TraceSpan("message", message_outline="Literal % _")
    trace.record("event_received")
    trace.record("pipeline_end", status="success")
    for frame in reversed(capture):
        # Wall-clock timestamps can collide on Windows even for distinct updates.
        if same_timestamp:
            frame["time_unix_nano"] = capture[-1]["time_unix_nano"]
            frame["trace"]["updated_time_unix_nano"] = frame["time_unix_nano"]
        assert persisted.append(frame)
    assert persisted.flush()
    detail = persisted.get_trace(trace.trace_id)
    assert detail["trace"]["state"] == "completed"
    assert detail["spans"][0]["end_time_unix_nano"]
    assert persisted.list_traces(query="% _")["total"] == 1
    assert persisted.list_traces(query="other%")["total"] == 0


def test_capacity_prunes_complete_traces_with_cascade(persisted, capture):
    trace = TraceSpan("message")
    trace.record("event_received")
    trace.record("pipeline_end", status="success")
    for index in range(80):
        frame = json.loads(json.dumps(capture[-1]))
        frame["trace"]["trace_id"] = frame["span"]["trace_id"] = f"{index:032x}"
        frame["trace"]["root_span_id"] = frame["span"]["span_id"] = f"{index:016x}"
        frame["trace"]["attributes"]["astrbot.payload"] = "x" * 340000
        assert persisted.append(frame)
        if index % 16 == 0:
            assert persisted.flush()
    assert persisted.flush()
    persisted.config["trace_db_max_mb"] = 1
    with sqlite3.connect(persisted.path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        persisted._prune(connection)
        assert connection.execute("PRAGMA max_page_count").fetchone()[0] == 8192
        count = connection.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
        assert 0 < count < 80
        assert connection.execute("SELECT COUNT(*) FROM spans").fetchone()[0] == count
        assert (
            sum(
                connection.execute(
                    f"SELECT COALESCE(SUM(size_bytes), 0) FROM {table}"
                ).fetchone()[0]
                for table in ("traces", "spans", "events")
            )
            < 32 * 1024 * 1024
        )


@pytest.mark.asyncio
async def test_background_broker_delivery_is_bounded_and_wakes_reader():
    broker = LogBroker()
    queue = broker.register()
    try:
        waiting = asyncio.create_task(queue.get())
        await asyncio.to_thread(broker.publish, {"type": "trace", "value": 1})
        assert (await asyncio.wait_for(waiting, 1))["value"] == 1
        thread = threading.Thread(
            target=lambda: [broker.publish({"type": "trace"}) for _ in range(5000)]
        )
        thread.start()
        thread.join()
        assert broker._pending_callbacks[queue] <= queue.maxsize
        await asyncio.sleep(0)
        assert queue.qsize() <= queue.maxsize
        assert not broker.log_cache
    finally:
        broker.unregister(queue)


def test_foreign_database_is_not_modified(tmp_path):
    path = tmp_path / "business.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE important(value TEXT)")
        connection.execute("INSERT INTO important VALUES ('keep')")
    store = TraceStore(path, {})
    try:
        assert store._ready.wait(5)
        assert store._failed
        assert not store.append({})
        with sqlite3.connect(path) as connection:
            assert connection.execute("SELECT * FROM important").fetchall() == [
                ("keep",)
            ]
            assert (
                connection.execute(
                    "SELECT name FROM sqlite_master WHERE name='trace_meta'"
                ).fetchone()
                is None
            )
    finally:
        store.close()


@pytest.mark.parametrize(
    "size,expected", [(20, 80), (50, 200), (0, 80), (-1, 80), ("bad", 80)]
)
def test_config_migration(tmp_path, size, expected):
    config = {
        "trace_enable": False,
        "trace_log_enable": True,
        "trace_log_path": "logs/old.jsonl",
        "trace_log_max_mb": size,
    }
    old = tmp_path / "old.jsonl"
    old.write_text("keep", encoding="utf-8")
    assert migrate_config_on_load(config, tmp_path / "cmd_config.json")
    assert config["trace_enable"] is False
    assert config["trace_db_path"] == "logs/traces.db"
    assert config["trace_db_max_mb"] == expected
    assert not any(key.startswith("trace_log_") for key in config)
    assert old.read_text() == "keep"
    config["trace_db_max_mb"] = 123
    config["trace_log_max_mb"] = 5
    migrate_config_on_load(config, tmp_path / "cmd_config.json")
    assert config["trace_db_max_mb"] == 123


def test_log_cleanup_protects_databases(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    for name in ("traces.db", "traces.db-wal", "traces.db-shm", "astrbot.log"):
        (logs / name).write_bytes(b"keep")
    with sqlite3.connect(logs / "old-custom-name") as connection:
        connection.execute("CREATE TABLE important(value TEXT)")
    (logs / "old-custom-name-wal").write_bytes(b"keep")
    cleaner = StorageCleaner(
        {"trace_db_path": "logs/traces.db"},
        data_dir=tmp_path,
        temp_dir=tmp_path / "temp",
    )
    cleaner.cleanup("logs")
    for name in ("traces.db", "traces.db-wal", "traces.db-shm"):
        assert (logs / name).read_bytes() == b"keep"
    assert not (logs / "astrbot.log").exists()
    assert (logs / "old-custom-name").exists()
    assert (logs / "old-custom-name-wal").exists()


@pytest.mark.parametrize(
    "relative_path", ["logs/traces.db", "other/history.db", "temp/history.db"]
)
def test_trace_usage_and_cleanup_preserve_running_traces(
    tmp_path, capture, monkeypatch, relative_path
):
    """Count all sidecars and clear history without removing active files."""
    from astrbot.core.utils import trace_store as storage_module

    path = tmp_path / relative_path
    store = TraceStore(path, {})
    monkeypatch.setattr(storage_module, "get_trace_store", lambda *_: store)
    try:
        finished = TraceSpan("finished", message_outline="x" * 3000)
        finished.record("event_received")
        finished.record("response_sent", message="x" * 30000)
        finished.record("pipeline_end", status="success")
        running = TraceSpan("running")
        running.record("event_received")
        for frame in capture:
            assert store.append(
                frame, owner=running if frame["trace"]["trace_id"] == running.trace_id else finished
            )
        assert store.flush()
        log = tmp_path / "logs" / "astrbot.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_bytes(b"x" * 128)
        cleaner = StorageCleaner(
            {"trace_db_path": relative_path},
            data_dir=tmp_path,
            temp_dir=tmp_path / "temp",
        )
        before = cleaner.get_status()
        expected = sum(
            sidecar.stat().st_size
            for suffix in ("", "-wal", "-shm", "-journal")
            if (sidecar := Path(str(path) + suffix)).exists()
        )
        assert before["traces"]["size_bytes"] == expected
        assert before["logs"]["size_bytes"] == 128
        assert before["cache"]["size_bytes"] == 0
        assert before["total_bytes"] == expected + 128
        result = cleaner.cleanup("traces")
        assert result["removed_traces"] == 1
        assert result["deleted_files"] == result["truncated_files"] == 0
        assert store.get_trace(finished.trace_id) is None
        assert store.get_trace(running.trace_id)["trace"]["state"] == "running"
        assert log.read_bytes() == b"x" * 128
        assert path.exists()
        # Even a database placed inside temp is protected from cache cleanup.
        cleaner.cleanup("cache")
        assert path.exists()
        running.record("pipeline_end", status="success")
        assert store.append(capture[-1])
        assert store.flush()
        assert store.get_trace(running.trace_id)["trace"]["state"] == "completed"
        result = cleaner.cleanup("all")
        assert result["removed_traces"] == 1
        assert result["status"]["traces"]["size_bytes"] > 0
        assert result["status"]["logs"]["size_bytes"] == 0
        assert store.list_traces()["total"] == 0
        with sqlite3.connect(path) as connection:
            for table in ("traces", "spans", "events"):
                assert (
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    == 0
                )
    finally:
        store.close()


def test_trace_cleanup_barrier_preserves_later_writes(persisted, capture, monkeypatch):
    """Ensure a cleanup command never deletes writes queued after it."""
    old = TraceSpan("old")
    old.record("event_received")
    old.record("pipeline_end", status="success")
    old_frame = capture[-1]
    new = TraceSpan("new")
    new.record("event_received")
    new.record("pipeline_end", status="success")
    new_frame = capture[-1]
    entered = threading.Event()
    release = threading.Event()
    original_write = persisted._write

    def held_write(connection, batch):
        """Hold the first write while cleanup and another write are queued."""
        if not entered.is_set():
            entered.set()
            assert release.wait(5)
        original_write(connection, batch)

    monkeypatch.setattr(persisted, "_write", held_write)
    results = []
    cleanup = threading.Thread(target=lambda: results.append(persisted.clear_history()))
    try:
        assert persisted.append(old_frame)
        assert entered.wait(5)
        cleanup.start()
        # Inspect the synchronized queue to avoid timing-dependent sleeps.
        with persisted.queue.not_empty:
            assert persisted.queue.not_empty.wait_for(
                lambda: bool(persisted.queue.queue), 5
            )
        assert persisted.append(new_frame)
        release.set()
        cleanup.join(5)
        assert not cleanup.is_alive()
        assert results[0]["removed_traces"] == 1
        assert persisted.flush()
        assert persisted.get_trace(old.trace_id) is None
        assert persisted.get_trace(new.trace_id)["trace"]["state"] == "completed"
    finally:
        release.set()
        if cleanup.ident is not None:
            cleanup.join(5)
