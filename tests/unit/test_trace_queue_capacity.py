"""Regression coverage for bounded trace writer burst capacity."""

import json
import threading
import time

import pytest

from astrbot.core.utils.trace_store import MAX_FRAME_BYTES, QUEUE_BYTES, TraceStore


@pytest.mark.parametrize("body_bytes", [32, 1536 * 1024])
def test_trace_queue_limits_bytes_without_frame_count_cap(tmp_path, monkeypatch, body_bytes):
    """Admit over 1024 small frames while bounding large frames by 128 MiB.

    Args:
        tmp_path: Isolated database directory.
        monkeypatch: Pytest patch manager.
        body_bytes: Payload length used to exercise small bursts or byte capacity.
    """
    release = threading.Event()
    original_run = TraceStore._run

    def delayed_run(self):
        """Hold the consumer until queue admission has been measured."""
        release.wait(10)
        original_run(self)

    monkeypatch.setattr(TraceStore, "_run", delayed_run)
    store = TraceStore(tmp_path / "traces.db", {})
    now = str(time.time_ns())
    packet = {
        "trace": {
            "trace_id": "a" * 32,
            "root_span_id": "b" * 16,
            "start_time_unix_nano": now,
            "state": "completed",
            "has_errors": False,
            "has_models": True,
            "has_plugins": False,
            "attributes": {"astrbot.message_outline": "x" * body_bytes},
        },
        "time_unix_nano": now,
    }
    frame_bytes = len(json.dumps(packet, ensure_ascii=False, separators=(",", ":")).encode())
    attempts = 1025 if body_bytes == 32 else QUEUE_BYTES // frame_bytes + 1
    expected = min(attempts, QUEUE_BYTES // frame_bytes)
    try:
        assert QUEUE_BYTES == 128 * 1024 * 1024
        assert MAX_FRAME_BYTES == 2 * 1024 * 1024
        assert store.queue.maxsize == 0
        accepted = sum(store.append(packet) for _ in range(attempts))
        assert accepted == expected
        assert store.queue.qsize() == expected
        assert store._pending_bytes <= QUEUE_BYTES
        assert store.dropped == attempts - expected
        release.set()
        assert store.flush(15)
        assert store._pending_bytes == 0
    finally:
        release.set()
        store.close()
