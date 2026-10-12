"""Canonical trace model, correlation, bounded storage, and migration tests."""

import asyncio
import json
import logging
import re
import sqlite3
import threading
import time

import pytest

from astrbot.core.log import LogBroker, LogManager
from astrbot.core.utils import trace as trace_module
from astrbot.core.utils.migra_helper import migrate_config_on_load
from astrbot.core.utils.storage_cleaner import StorageCleaner
from astrbot.core.utils.telemetry import (
    MAX_ATTRIBUTE_BYTES,
    bounded_attributes,
    current_trace_context,
)
from astrbot.core.utils.trace import TraceSpan
from astrbot.core.utils.trace_store import QUEUE_BYTES, TraceStore


@pytest.fixture
def capture(monkeypatch):
    """Capture immutable snapshots without writing to the default path."""
    frames = []

    class CaptureStore:
        def append(self, payload):
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
        trace.record("event_received", platform_id="qq", kind="message")
        trace.record(
            "handler_start",
            kind="plugin_handler",
            plugin="test",
            handler_full_name="test.handler",
        )
        handler_id = current_trace_context.get().span_id
        trace.record("agent_start", kind="agent")
        agent_id = current_trace_context.get().span_id
        trace.record("agent_tool_call", tool_name="weather")
        trace.record("agent_tool_result", tool_result="Sunny")
        trace.record("agent_end", status="success")
        assert current_trace_context.get().span_id == handler_id
        trace.record("handler_end", handler_full_name="test.handler", status="success")
        assert current_trace_context.get().span_id == trace.span_id
        trace.record("response_sent", kind="response", source="core", message="Sunny")
        trace.record("pipeline_end", status="success")
    assert current_trace_context.get() is None
    spans = {
        frame["span"]["span_id"]: frame["span"] for frame in capture if "span" in frame
    }
    assert len(spans) == 4
    assert spans[handler_id]["parent_span_id"] == trace.span_id
    assert spans[agent_id]["parent_span_id"] == handler_id
    assert all(span["end_time_unix_nano"] for span in spans.values())
    assert capture[0]["span"]["end_time_unix_nano"] is None
    assert capture[0]["trace"]["state"] == "running"
    assert capture[-1]["trace"]["state"] == "completed"
    assert not trace._pending


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
        child_id = current_trace_context.get().span_id
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
        context = current_trace_context.get()
        await release.wait()
        assert context.active is False

    with trace.context():
        trace.record("event_received")
        tasks = [asyncio.create_task(child(name)) for name in ("a", "b")]
        await asyncio.sleep(0)
        trace.record("pipeline_end", status="error", error="Cancelled")
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
    with trace.context():
        trace.record("event_received")
        trace.record("handler_start", handler_full_name="test.handler")
        monkeypatch.setitem(trace_module.astrbot_config, "trace_enable", False)
        trace.record("agent_start")
        trace.record("handler_end", handler_full_name="test.handler", status="success")
        trace.record("pipeline_end", status="success")
    count = len(capture)
    TraceSpan("disabled").record("event_received")
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
    assert first["total"] == 4
    assert len(first["traces"]) == len(second["traces"]) == 2
    assert {item["trace_id"] for item in first["traces"]}.isdisjoint(
        item["trace_id"] for item in second["traces"]
    )
    assert persisted.list_traces(errors=True)["total"] == 1
    assert persisted.list_traces(plugins=True, query="Display Test")["total"] == 4
    assert persisted.list_traces(models=True)["total"] == 0
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
    assert persisted.append({"oversized": "x" * QUEUE_BYTES}) is False
    assert persisted.dropped == 1
    assert persisted._pending_bytes == 0


def test_stale_updates_do_not_reopen_completed_trace(persisted, capture):
    trace = TraceSpan("message", message_outline="Literal % _")
    trace.record("event_received")
    trace.record("pipeline_end", status="success")
    for frame in reversed(capture):
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
        frame["trace"]["attributes"]["astrbot.payload"] = "x" * 20000
        assert persisted.append(frame)
        if index % 16 == 0:
            assert persisted.flush()
    assert persisted.flush()
    persisted.config["trace_db_max_mb"] = 1
    with sqlite3.connect(persisted.path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        persisted._prune(connection)
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
            < 1024 * 1024
        )


def test_writer_queue_has_byte_and_count_limits(tmp_path, monkeypatch, capture):
    release = threading.Event()
    original_run = TraceStore._run

    def delayed_run(self):
        """Hold the writer to simulate a slow disk."""
        release.wait(5)
        original_run(self)

    monkeypatch.setattr(TraceStore, "_run", delayed_run)
    trace = TraceSpan("message")
    trace.record("event_received")
    payload = capture[0]
    payload["trace"]["attributes"]["astrbot.payload"] = "x" * 40000
    store = TraceStore(tmp_path / "traces.db", {})
    try:
        accepted = sum(store.append(payload) for _ in range(200))
        assert accepted < 128
        assert store._pending_bytes <= QUEUE_BYTES
        assert store.queue.qsize() == accepted
        assert store.dropped == 200 - accepted
        release.set()
        assert store.flush()
    finally:
        release.set()
        store.close()


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
