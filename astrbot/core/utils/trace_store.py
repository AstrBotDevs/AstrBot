"""Independent, bounded SQLite storage for local trace history."""

from __future__ import annotations

import atexit
import json
import logging
import sqlite3
import threading
import time
from collections.abc import Mapping
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeoutError
from contextlib import closing
from pathlib import Path
from queue import Empty, Full, Queue
from typing import Any
from weakref import WeakValueDictionary

from astrbot.core.utils.astrbot_path import get_astrbot_data_path

logger = logging.getLogger("astrbot")
QUEUE_BYTES = 128 * 1024 * 1024
MAX_WAL_BYTES = 4 * 1024 * 1024
MAX_FRAME_BYTES = 2 * 1024 * 1024


class TraceStore:
    """Store span updates and events using one bounded background writer."""

    def __init__(self, path: Path, config: Mapping[str, Any]) -> None:
        self.path = path
        self.config = config
        self.queue: Queue = Queue()
        self._lock = threading.Lock()
        self._pending_bytes = 0
        self._pending_traces: dict[str, int] = {}
        self._active_traces: WeakValueDictionary[str, Any] = WeakValueDictionary()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._failed = False
        self.dropped = 0
        self.last_error: str | None = None
        self._last_warning = 0.0
        self._thread = threading.Thread(
            target=self._run, name="trace-sqlite", daemon=True
        )
        self._thread.start()

    def append(self, payload: dict, *, owner: Any = None) -> bool:
        """Queue an immutable snapshot without blocking message processing.

        Args:
            payload: A trace summary with a span update or event.
            owner: Live trace object, held weakly until execution finishes.

        Returns:
            Whether the bounded queue accepted the snapshot.
        """
        encoded = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        )
        size = len(encoded.encode())
        trace_id = payload.get("trace", {}).get("trace_id")
        with self._lock:
            if owner is not None:
                if owner._finished:
                    self._active_traces.pop(trace_id, None)
                else:
                    self._active_traces[trace_id] = owner
            if (
                self._stop.is_set()
                or self._failed
                or size > MAX_FRAME_BYTES
                or self._pending_bytes + size > QUEUE_BYTES
            ):
                accepted = False
            else:
                try:
                    self.queue.put_nowait((encoded, size))
                    self._pending_bytes += size
                    self._pending_traces[trace_id] = (
                        self._pending_traces.get(trace_id, 0) + 1
                    )
                    accepted = True
                except Full:
                    accepted = False
            if not accepted:
                self.dropped += 1
        if not accepted and time.monotonic() - self._last_warning > 30:
            self._last_warning = time.monotonic()
            logger.warning(
                "Trace persistence rejected a record: queue/capacity unavailable (dropped=%s).",
                self.dropped,
            )
        return accepted

    def flush(self, timeout: float = 5) -> bool:
        """Wait for accepted snapshots to commit.

        Args:
            timeout: Maximum seconds to wait.

        Returns:
            Whether the barrier committed without a storage error.
        """
        if self._failed or self._stop.is_set():
            return False
        done = threading.Event()
        try:
            self.queue.put((done, 0), timeout=timeout)
        except Full:
            return False
        return done.wait(timeout) and self.last_error is None

    def close(self) -> None:
        """Drain the writer and close its SQLite connection."""
        self._stop.set()
        self._thread.join(timeout=5)
        if self._thread.is_alive():
            logger.error(
                "Trace database writer did not finish within the shutdown deadline."
            )

    def clear_history(self) -> dict:
        """Clear finished history using the same queue as trace writes.

        Running traces are retained so their later updates remain complete.

        Returns:
            The number of removed message traces.

        Raises:
            RuntimeError: If the writer is unavailable or cleanup times out.
        """
        if not self._ready.wait(5) or self._failed or self._stop.is_set():
            raise RuntimeError(self.last_error or "Trace writer is unavailable.")
        result = Future()
        try:
            self.queue.put((result, 0), timeout=5)
        except Full as exc:
            raise RuntimeError("Trace cleanup queue is full.") from exc
        try:
            return result.result(timeout=15)
        except FutureTimeoutError as exc:
            result.cancel()
            raise RuntimeError(
                "Trace cleanup timed out; check storage status."
            ) from exc

    def _interrupt_inactive(self, connection: sqlite3.Connection) -> None:
        """Close orphaned records without interrupting live or queued traces.

        Args:
            connection: Writer-owned connection.
        """
        with self._lock:
            protected = set(self._pending_traces)
            protected.update(
                trace_id
                for trace_id, owner in self._active_traces.items()
                if not owner._finished
            )
        # A temporary table avoids SQLite's parameter limit at high concurrency.
        connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS protected_traces(trace_id TEXT PRIMARY KEY)"
        )
        connection.execute("DELETE FROM protected_traces")
        connection.executemany(
            "INSERT INTO protected_traces VALUES (?)", ((item,) for item in protected)
        )
        connection.execute("""UPDATE traces SET state='interrupted', has_errors=1,
            data=json_set(data, '$.state', 'interrupted', '$.has_errors', json('true'),
                '$.end_time_unix_nano', CAST(updated_ns AS TEXT))
            WHERE state='running' AND trace_id NOT IN (SELECT trace_id FROM protected_traces)""")
        connection.execute("""UPDATE spans SET data=json_set(data,
            '$.end_time_unix_nano', CAST((SELECT updated_ns FROM traces WHERE traces.trace_id=spans.trace_id) AS TEXT),
            '$.status.code', 2, '$.status.message', 'Execution ended before persistence completed')
            WHERE trace_id IN (SELECT trace_id FROM traces WHERE state='interrupted')
                AND json_extract(data, '$.end_time_unix_nano') IS NULL""")

    def _prune(self, connection: sqlite3.Connection, force: bool = False) -> None:
        """Evict complete traces as units and reclaim reusable database pages.

        Args:
            connection: Writer-owned connection.
            force: Whether to free additional space after a full-disk error.
        """
        self._interrupt_inactive(connection)
        max_mb = self.config.get("trace_db_max_mb", 80)
        max_mb = (
            max(32, max_mb)
            if isinstance(max_mb, int) and not isinstance(max_mb, bool) and max_mb > 0
            else 80
        )
        days = self.config.get("trace_retention_days", 7)
        days = (
            days
            if isinstance(days, int) and not isinstance(days, bool) and days > 0
            else 7
        )
        connection.execute(
            "DELETE FROM traces WHERE state != 'running' AND updated_ns < ?",
            (time.time_ns() - days * 86400 * 10**9,),
        )
        logical = sum(
            connection.execute(
                f"SELECT COALESCE(SUM(size_bytes), 0) FROM {table}"
            ).fetchone()[0]
            for table in ("traces", "spans", "events")
        )
        physical = connection.execute("PRAGMA page_count").fetchone()[0] * 4096
        free = connection.execute("PRAGMA freelist_count").fetchone()[0] * 4096
        budget = max_mb * 1024 * 1024
        if force or logical > budget * 0.75 or physical - free > budget * 0.85:
            target = max(0, logical - max(budget // 4, logical - int(budget * 0.6)))
            while logical > target:
                oldest = connection.execute(
                    "SELECT trace_id FROM traces WHERE state != 'running' ORDER BY start_ns, trace_id LIMIT 32"
                ).fetchall()
                if not oldest:
                    break
                connection.executemany("DELETE FROM traces WHERE trace_id = ?", oldest)
                logical = sum(
                    connection.execute(
                        f"SELECT COALESCE(SUM(size_bytes), 0) FROM {table}"
                    ).fetchone()[0]
                    for table in ("traces", "spans", "events")
                )
        connection.commit()
        connection.execute("PRAGMA incremental_vacuum(256)")
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        connection.execute(f"PRAGMA max_page_count={max(256, budget // 4096)}")

    def _write(self, connection: sqlite3.Connection, batch: list[dict]) -> None:
        """Upsert bounded snapshots in one transaction.

        Args:
            connection: Writer-owned connection.
            batch: Snapshots to persist atomically.
        """
        with connection:
            for payload in batch:
                summary = payload["trace"]
                trace_id = summary["trace_id"]
                data = json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
                attrs = summary["attributes"]
                search = " ".join(
                    str(attrs.get("astrbot." + key, ""))
                    for key in ("umo", "sender_name", "message_outline", "plugins")
                )
                connection.execute(
                    """INSERT INTO traces VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(trace_id) DO UPDATE SET
                    updated_ns=excluded.updated_ns, state=excluded.state,
                    has_errors=MAX(traces.has_errors, excluded.has_errors),
                    has_models=MAX(traces.has_models, excluded.has_models),
                    has_plugins=MAX(traces.has_plugins, excluded.has_plugins),
                    search=excluded.search, data=excluded.data, size_bytes=excluded.size_bytes
                    WHERE excluded.updated_ns >= traces.updated_ns
                        AND (traces.state = 'running' OR excluded.state != 'running')""",
                    (
                        trace_id,
                        int(summary["start_time_unix_nano"]),
                        int(payload["time_unix_nano"]),
                        summary["state"],
                        summary["has_errors"],
                        summary["has_models"],
                        summary["has_plugins"],
                        search,
                        data,
                        len(data.encode()),
                        summary["root_span_id"],
                    ),
                )
                if "span" in payload:
                    span = payload["span"]
                    data = json.dumps(span, ensure_ascii=False, separators=(",", ":"))
                    connection.execute(
                        """INSERT INTO spans VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(span_id) DO UPDATE SET data=excluded.data, size_bytes=excluded.size_bytes
                        WHERE json_extract(spans.data, '$.end_time_unix_nano') IS NULL
                            OR json_extract(excluded.data, '$.end_time_unix_nano') IS NOT NULL""",
                        (
                            span["span_id"],
                            trace_id,
                            span["parent_span_id"],
                            data,
                            len(data.encode()),
                        ),
                    )
                if "event" in payload:
                    event = payload["event"]
                    data = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                    connection.execute(
                        "INSERT OR IGNORE INTO events VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            event["event_id"],
                            trace_id,
                            event["span_id"],
                            int(event["time_unix_nano"]),
                            data,
                            len(data.encode()),
                        ),
                    )

    def _run(self) -> None:
        """Own the connection, batch writes, and perform bounded retention."""
        connection = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=1)
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if tables and "trace_meta" not in tables:
                raise ValueError(
                    "Trace path contains a different database; choose a separate path."
                )
            application_id = connection.execute("PRAGMA application_id").fetchone()[0]
            if application_id not in (0, 0x41535452):
                raise ValueError("Trace path belongs to a different application.")
            if "trace_meta" in tables:
                if (
                    connection.execute("SELECT version FROM trace_meta").fetchone()[0]
                    != 1
                ):
                    raise ValueError("Unsupported trace database schema version.")
            connection.execute("PRAGMA application_id=1095980114")
            connection.execute("PRAGMA page_size=4096")
            connection.execute("PRAGMA auto_vacuum=INCREMENTAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA journal_size_limit=4194304")
            connection.execute("PRAGMA wal_autocheckpoint=128")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS trace_meta(version INTEGER NOT NULL);
                INSERT INTO trace_meta SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM trace_meta);
                CREATE TABLE IF NOT EXISTS traces(
                    trace_id TEXT PRIMARY KEY, start_ns INTEGER NOT NULL,
                    updated_ns INTEGER NOT NULL, state TEXT NOT NULL,
                    has_errors INTEGER NOT NULL, has_models INTEGER NOT NULL,
                    has_plugins INTEGER NOT NULL, search TEXT NOT NULL,
                    data TEXT NOT NULL, size_bytes INTEGER NOT NULL,
                    root_span_id TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS traces_time ON traces(start_ns DESC, trace_id DESC);
                CREATE INDEX IF NOT EXISTS traces_errors ON traces(has_errors, start_ns DESC);
                CREATE INDEX IF NOT EXISTS traces_models ON traces(has_models, start_ns DESC);
                CREATE INDEX IF NOT EXISTS traces_plugins ON traces(has_plugins, start_ns DESC);
                CREATE TABLE IF NOT EXISTS spans(
                    span_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL REFERENCES traces(trace_id) ON DELETE CASCADE,
                    parent_span_id TEXT, data TEXT NOT NULL, size_bytes INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS spans_trace ON spans(trace_id);
                CREATE TABLE IF NOT EXISTS events(
                    event_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL REFERENCES traces(trace_id) ON DELETE CASCADE,
                    span_id TEXT NOT NULL, time_ns INTEGER NOT NULL,
                    data TEXT NOT NULL, size_bytes INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS events_trace ON events(trace_id, time_ns);
            """)
            if connection.execute("SELECT version FROM trace_meta").fetchone()[0] != 1:
                raise ValueError("Unsupported trace database schema version.")
            # A process restart cannot resume spans from a previous process.
            self._interrupt_inactive(connection)
            connection.commit()
            self._prune(connection)
            self._ready.set()
            last_prune = time.monotonic()
            while not self._stop.is_set() or not self.queue.empty():
                try:
                    first = self.queue.get(timeout=0.1)
                except Empty:
                    if time.monotonic() - last_prune >= 60:
                        self._prune(connection)
                        last_prune = time.monotonic()
                    continue
                items = [first]
                for _ in range(31):
                    # Cleanup is a barrier: never batch later writes before it.
                    if isinstance(items[-1][0], Future):
                        break
                    try:
                        items.append(self.queue.get_nowait())
                    except Empty:
                        break
                batch = [json.loads(item) for item, _ in items if isinstance(item, str)]
                written = False
                try:
                    wal = Path(str(self.path) + "-wal")
                    if wal.exists() and wal.stat().st_size > MAX_WAL_BYTES:
                        self._prune(connection)
                        if wal.exists() and wal.stat().st_size > MAX_WAL_BYTES:
                            raise sqlite3.OperationalError(
                                "Trace WAL cannot checkpoint within its capacity budget."
                            )
                    try:
                        self._write(connection, batch)
                    except sqlite3.OperationalError as exc:
                        # A lock or I/O error must not trigger early eviction.
                        if "database or disk is full" not in str(exc).lower():
                            raise
                        self._prune(connection, force=True)
                        self._write(connection, batch)
                    written = True
                    # All frames in this batch have committed. Later queued frames
                    # still protect their trace from orphan reconciliation.
                    with self._lock:
                        for payload in batch:
                            trace_id = payload["trace"]["trace_id"]
                            self._pending_traces[trace_id] -= 1
                            if not self._pending_traces[trace_id]:
                                del self._pending_traces[trace_id]
                    if batch:
                        self.last_error = None
                    if time.monotonic() - last_prune >= 10:
                        self._prune(connection)
                        last_prune = time.monotonic()
                    command = items[-1][0]
                    if (
                        isinstance(command, Future)
                        and command.set_running_or_notify_cancel()
                    ):
                        with connection:
                            self._interrupt_inactive(connection)
                            removed = connection.execute(
                                "DELETE FROM traces WHERE state != 'running'"
                            ).rowcount
                        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                        connection.execute("VACUUM")
                        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                        self.last_error = None
                        command.set_result({"removed_traces": removed})
                except Exception as exc:
                    self.last_error = str(exc)
                    self.dropped += len(batch) if not written else 0
                    if not written:
                        with self._lock:
                            for payload in batch:
                                trace_id = payload["trace"]["trace_id"]
                                self._pending_traces[trace_id] -= 1
                                if not self._pending_traces[trace_id]:
                                    del self._pending_traces[trace_id]
                    logger.error("Trace database write failed: %s", exc)
                    for item, _ in items:
                        if isinstance(item, Future) and not item.done():
                            item.set_exception(exc)
                finally:
                    for item, size in items:
                        with self._lock:
                            self._pending_bytes -= size
                        if isinstance(item, threading.Event):
                            item.set()
                        self.queue.task_done()
        except Exception as exc:
            self._failed = True
            self.last_error = str(exc)
            logger.error("Trace database initialization failed: %s", exc)
            while True:
                try:
                    item, size = self.queue.get_nowait()
                except Empty:
                    break
                with self._lock:
                    self._pending_bytes -= size
                    self.dropped += int(size > 0)
                    if isinstance(item, str):
                        trace_id = json.loads(item)["trace"]["trace_id"]
                        self._pending_traces[trace_id] -= 1
                        if not self._pending_traces[trace_id]:
                            del self._pending_traces[trace_id]
                if isinstance(item, threading.Event):
                    item.set()
                elif isinstance(item, Future) and not item.done():
                    item.set_exception(RuntimeError(self.last_error))
                self.queue.task_done()
        finally:
            self._ready.set()
            if connection is not None:
                connection.close()

    def list_traces(
        self,
        *,
        limit: int = 50,
        page: int = 1,
        cursor: str | None = None,
        query: str = "",
        errors: bool = False,
        models: bool = False,
        plugins: bool = False,
    ) -> dict:
        """Read one numbered or keyset page, never all stored span bodies.

        Args:
            limit: Maximum summaries, capped at 100.
            page: One-based page number; mutually exclusive with a cursor.
            cursor: Previous page's timestamp and trace ID.
            query: Message, session, sender, or plugin search.
            errors: Require an error.
            models: Require an Agent call.
            plugins: Require a plugin call.

        Returns:
            Summaries, filtered count, next cursor, and storage health.

        Raises:
            RuntimeError: If initialization failed.
            ValueError: If the page or cursor is invalid.
        """
        if not self._ready.wait(5) or self._failed:
            raise RuntimeError(self.last_error or "Trace database is not ready.")
        limit = min(100, max(1, limit))
        if page < 1 or (cursor and page != 1):
            raise ValueError("Invalid trace page.")
        conditions, values = [], []
        for key, enabled in (
            ("has_errors", errors),
            ("has_models", models),
            ("has_plugins", plugins),
        ):
            if enabled:
                conditions.append(key + "=1")
        if query:
            conditions.append("search LIKE ? ESCAPE '\\'")
            values.append(
                "%"
                + query[:256]
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
                + "%"
            )
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        with closing(sqlite3.connect(self.path, timeout=1)) as connection:
            connection.execute("BEGIN")
            total = connection.execute(
                "SELECT COUNT(*) FROM traces" + where, values
            ).fetchone()[0]
            page = min(page, max(1, (total + limit - 1) // limit))
            if cursor:
                stamp, trace_id = cursor.split(":", 1)
                if len(trace_id) != 32 or any(
                    c not in "0123456789abcdef" for c in trace_id
                ):
                    raise ValueError("Invalid trace cursor.")
                conditions.append("(start_ns < ? OR (start_ns = ? AND trace_id < ?))")
                values.extend((int(stamp), int(stamp), trace_id))
            where = " WHERE " + " AND ".join(conditions) if conditions else ""
            rows = connection.execute(
                "SELECT data, start_ns, trace_id FROM traces"
                + where
                + " ORDER BY start_ns DESC, trace_id DESC LIMIT ? OFFSET ?",
                [*values, limit + 1, (page - 1) * limit],
            ).fetchall()
            summaries = [json.loads(row[0]) for row in rows[:limit]]
            # Older summaries predate command flags; derive only those flags
            # from this page's indexed spans without loading full trace detail.
            legacy = {
                summary["trace_id"]: summary
                for summary in summaries
                if "has_commands" not in summary
            }
            if legacy:
                placeholders = ",".join("?" for _ in legacy)
                for trace_id, data in connection.execute(
                    f"SELECT trace_id, data FROM spans WHERE trace_id IN ({placeholders})",
                    list(legacy),
                ):
                    if (
                        json.loads(data)
                        .get("attributes", {})
                        .get("astrbot.handler_category")
                        == "command"
                    ):
                        legacy[trace_id]["has_commands"] = True
                for summary in legacy.values():
                    summary.setdefault("has_commands", False)
        return {
            "traces": summaries,
            "total": total,
            "page": page,
            "cursor": f"{rows[limit - 1][1]}:{rows[limit - 1][2]}"
            if len(rows) > limit
            else None,
            "storage": {"dropped": self.dropped, "error": self.last_error},
        }

    def get_trace(self, trace_id: str) -> dict | None:
        """Read one bounded trace and its spans/events.

        Args:
            trace_id: ID of the requested trace.

        Returns:
            Complete detail, or None when evicted or absent.

        Raises:
            RuntimeError: If storage initialization failed.
        """
        if not self._ready.wait(5) or self._failed:
            raise RuntimeError(self.last_error or "Trace database is not ready.")
        connection = sqlite3.connect(self.path, timeout=1)
        try:
            connection.execute("BEGIN")
            row = connection.execute(
                "SELECT data FROM traces WHERE trace_id=?", (trace_id,)
            ).fetchone()
            if not row:
                return None
            spans = [
                json.loads(item[0])
                for item in connection.execute(
                    "SELECT data FROM spans WHERE trace_id=? LIMIT 128", (trace_id,)
                )
            ]
            events = [
                json.loads(item[0])
                for item in connection.execute(
                    "SELECT data FROM events WHERE trace_id=? ORDER BY time_ns, event_id LIMIT 256",
                    (trace_id,),
                )
            ]
            by_id = {span["span_id"]: span for span in spans}
            for event in events:
                owner = by_id.get(event["span_id"])
                if owner is not None:
                    owner.setdefault("events", []).append(event)
            return {"trace": json.loads(row[0]), "spans": spans}
        finally:
            connection.close()


_store: TraceStore | None = None
_store_lock = threading.Lock()


def get_trace_store(config: Mapping[str, Any] | None = None) -> TraceStore:
    """Get the process-wide dedicated writer.

    Args:
        config: Global configuration, or None to resolve it lazily.

    Returns:
        The local trace store.
    """
    global _store
    with _store_lock:
        if _store is None:
            if config is None:
                from astrbot.core import astrbot_config

                config = astrbot_config
            path = Path(config.get("trace_db_path") or "logs/traces.db")
            if not path.is_absolute():
                path = Path(get_astrbot_data_path()) / path
            _store = TraceStore(path.resolve(), config)
            atexit.register(_store.close)
        return _store


def close_trace_store() -> None:
    """Flush an initialized trace store without creating a new one."""
    if _store is not None:
        _store.close()
