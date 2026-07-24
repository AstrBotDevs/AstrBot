from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from tempfile import gettempdir
from typing import Any

from astrbot.core.utils.astrbot_path import get_astrbot_data_path


class AgentEvidenceStore:
    """Persist bounded, redacted Agent execution traces and evidence metadata."""

    TERMINAL_STATUSES = frozenset(
        {
            "COMPLETED",
            "DEGRADED",
            "PARTIAL",
            "FAILED",
            "CANCELLED",
            "REJECTED",
            "EXPIRED",
            "INTERRUPTED",
        }
    )

    def __init__(self, database_path: Path | None = None) -> None:
        """Initialize the trace database.

        Args:
            database_path: Optional SQLite path, primarily used by tests.
        """

        self.database_path = database_path or (
            Path(get_astrbot_data_path()) / "agent_evidence.db"
        )
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()
        # A newly-created store represents a fresh process lifecycle. Any
        # previous non-terminal runs are therefore no longer executable.
        self.mark_inflight_interrupted()

    def _connect(self):
        """Open a SQLite connection that closes when its context exits."""

        conn = sqlite3.connect(self.database_path, timeout=5)
        conn.row_factory = sqlite3.Row
        return closing(conn)

    def _initialize(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_runs (
                    trace_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    principal_id TEXT NOT NULL,
                    goal_hash TEXT NOT NULL,
                    route TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    finished_at REAL,
                    final_status TEXT NOT NULL DEFAULT '',
                    run_phase TEXT NOT NULL DEFAULT 'RECEIVED',
                    last_activity_at REAL,
                    deadline_at REAL,
                    plan_json TEXT NOT NULL DEFAULT '',
                    current_step INTEGER NOT NULL DEFAULT 0,
                    checkpoint_json TEXT NOT NULL DEFAULT '',
                    terminal_reason TEXT NOT NULL DEFAULT '',
                    recovery_count INTEGER NOT NULL DEFAULT 0,
                    final_response_hash TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS tool_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    tool_version TEXT NOT NULL,
                    arguments_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_code TEXT NOT NULL DEFAULT '',
                    output_hash TEXT NOT NULL DEFAULT '',
                    started_at REAL NOT NULL,
                    finished_at REAL,
                    FOREIGN KEY(trace_id) REFERENCES agent_runs(trace_id)
                );
                CREATE TABLE IF NOT EXISTS evidence_records (
                    evidence_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    attempt_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    source_url TEXT NOT NULL DEFAULT '',
                    captured_at REAL NOT NULL,
                    freshness TEXT NOT NULL DEFAULT 'unknown',
                    confidence REAL NOT NULL DEFAULT 0,
                    content_hash TEXT NOT NULL,
                    FOREIGN KEY(trace_id) REFERENCES agent_runs(trace_id)
                );
                CREATE INDEX IF NOT EXISTS idx_tool_attempts_trace
                    ON tool_attempts(trace_id, started_at);
                CREATE INDEX IF NOT EXISTS idx_evidence_trace
                    ON evidence_records(trace_id, captured_at);
                """
            )
            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(agent_runs)").fetchall()
            }
            migrations = {
                "run_phase": "TEXT NOT NULL DEFAULT 'RECEIVED'",
                "last_activity_at": "REAL",
                "deadline_at": "REAL",
                "plan_json": "TEXT NOT NULL DEFAULT ''",
                "current_step": "INTEGER NOT NULL DEFAULT 0",
                "checkpoint_json": "TEXT NOT NULL DEFAULT ''",
                "terminal_reason": "TEXT NOT NULL DEFAULT ''",
                "recovery_count": "INTEGER NOT NULL DEFAULT 0",
                "final_response_hash": "TEXT NOT NULL DEFAULT ''",
            }
            for name, declaration in migrations.items():
                if name not in columns:
                    conn.execute(
                        f"ALTER TABLE agent_runs ADD COLUMN {name} {declaration}"
                    )
            conn.commit()

    @staticmethod
    def _hash(value: Any) -> str:
        if isinstance(value, str):
            raw = value.encode("utf-8", errors="replace")
        else:
            raw = json.dumps(
                value, ensure_ascii=False, sort_keys=True, default=str
            ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def start_run(
        self,
        *,
        trace_id: str,
        session_id: str,
        principal_id: str,
        goal: str,
        route: str,
    ) -> None:
        """Create or refresh a bounded Agent run record.

        Args:
            trace_id: Stable identifier shared by all child attempts.
            session_id: Sanitized unified message origin.
            principal_id: Sanitized requester identity.
            goal: User goal; only a hash is persisted.
            route: Selected fast/standard/deep route.
        """

        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_runs(
                    trace_id, session_id, principal_id, goal_hash, route,
                    status, started_at, run_phase, last_activity_at
                ) VALUES (?, ?, ?, ?, ?, 'running', ?, 'RECEIVED', ?)
                ON CONFLICT(trace_id) DO UPDATE SET
                    session_id=excluded.session_id,
                    principal_id=excluded.principal_id,
                    route=excluded.route,
                    status='running',
                    started_at=excluded.started_at,
                    finished_at=NULL,
                    final_status='',
                    run_phase='RECEIVED',
                    last_activity_at=excluded.last_activity_at,
                    terminal_reason='',
                    final_response_hash=''
                """,
                (
                    trace_id[:120],
                    session_id[:300],
                    principal_id[:200],
                    self._hash(goal),
                    route[:40],
                    now,
                    now,
                ),
            )
            conn.commit()

    def update_phase(
        self,
        trace_id: str,
        phase: str,
        *,
        step: int | None = None,
        plan: Any | None = None,
        deadline_at: float | None = None,
        reason: str = "",
    ) -> None:
        """Update a run phase and its bounded execution metadata.

        Args:
            trace_id: Run identifier.
            phase: Current lifecycle phase.
            step: Optional planner or tool-loop step number.
            plan: Optional structured plan; only a JSON representation is stored.
            deadline_at: Optional absolute deadline.
            reason: Sanitized transition reason.
        """

        values: list[Any] = [phase[:40], time.time()]
        assignments = ["run_phase=?", "last_activity_at=?"]
        if step is not None:
            assignments.append("current_step=?")
            values.append(max(0, int(step)))
        if plan is not None:
            assignments.append("plan_json=?")
            values.append(
                json.dumps(plan, ensure_ascii=False, sort_keys=True, default=str)[
                    :20000
                ]
            )
        if deadline_at is not None:
            assignments.append("deadline_at=?")
            values.append(float(deadline_at))
        if reason:
            assignments.append("terminal_reason=?")
            values.append(reason[:500])
        values.append(trace_id[:120])
        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE agent_runs SET {', '.join(assignments)} WHERE trace_id=?",
                values,
            )
            conn.commit()

    def save_checkpoint(self, trace_id: str, checkpoint: Any) -> None:
        """Persist a bounded checkpoint for manual recovery."""

        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE agent_runs SET checkpoint_json=?, last_activity_at=? WHERE trace_id=?",
                (
                    json.dumps(
                        checkpoint, ensure_ascii=False, sort_keys=True, default=str
                    )[:30000],
                    time.time(),
                    trace_id[:120],
                ),
            )
            conn.commit()

    def mark_inflight_interrupted(self) -> int:
        """Mark non-terminal runs as interrupted after a process restart."""

        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE agent_runs
                SET status='finished', final_status='INTERRUPTED',
                    run_phase='INTERRUPTED', terminal_reason='process_restart',
                    finished_at=?, last_activity_at=?
                WHERE status='running' AND final_status=''
                """,
                (time.time(), time.time()),
            )
            conn.commit()
            return int(cursor.rowcount)

    def finish_run(
        self,
        trace_id: str,
        final_status: str,
        *,
        reason: str = "",
        final_response: Any | None = None,
    ) -> None:
        """Mark a run as terminal without persisting response text.

        Args:
            trace_id: Run identifier.
            final_status: Sanitized completion status.
        """

        normalized_status = str(final_status or "FAILED").upper()[:40]
        normalized_status = {
            "SUCCESS": "COMPLETED",
            "DIRECT_SENT": "COMPLETED",
            "LLM_ERROR": "FAILED",
            "ERROR": "FAILED",
            "ABORTED": "CANCELLED",
            "EMPTY": "DEGRADED",
        }.get(normalized_status, normalized_status)
        if normalized_status not in self.TERMINAL_STATUSES:
            normalized_status = "FAILED"
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE agent_runs
                SET status='finished', finished_at=?, final_status=?,
                    run_phase=?, terminal_reason=?, last_activity_at=?,
                    final_response_hash=?
                WHERE trace_id=?
                """,
                (
                    time.time(),
                    normalized_status,
                    normalized_status,
                    reason[:500],
                    time.time(),
                    self._hash(final_response) if final_response is not None else "",
                    trace_id[:120],
                ),
            )
            conn.commit()

    def start_attempt(
        self,
        *,
        trace_id: str,
        tool_name: str,
        tool_version: str,
        arguments: dict[str, Any],
    ) -> str:
        """Create a tool attempt and return its opaque identifier.

        Args:
            trace_id: Parent Agent run identifier.
            tool_name: Registered tool name.
            tool_version: Capability version.
            arguments: Runtime arguments; only a hash is stored.

        Returns:
            Opaque attempt identifier.
        """

        attempt_id = f"attempt-{secrets.token_hex(8)}"
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tool_attempts(
                    attempt_id, trace_id, tool_name, tool_version,
                    arguments_hash, status, started_at
                ) VALUES (?, ?, ?, ?, ?, 'running', ?)
                """,
                (
                    attempt_id,
                    trace_id[:120],
                    tool_name[:160],
                    tool_version[:80],
                    self._hash(arguments),
                    time.time(),
                ),
            )
            conn.commit()
        return attempt_id

    def finish_attempt(
        self,
        *,
        attempt_id: str,
        status: str,
        error_code: str = "",
        output: Any = None,
    ) -> None:
        """Close a tool attempt with a hash-only result summary.

        Args:
            attempt_id: Attempt identifier returned by :meth:`start_attempt`.
            status: Normalized execution status.
            error_code: Sanitized error category.
            output: Result content; only a hash is persisted.
        """

        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE tool_attempts
                SET status=?, error_code=?, output_hash=?, finished_at=?
                WHERE attempt_id=?
                """,
                (
                    status[:40],
                    error_code[:120],
                    self._hash(output) if output is not None else "",
                    time.time(),
                    attempt_id[:120],
                ),
            )
            conn.commit()

    def record_evidence(
        self,
        *,
        trace_id: str,
        attempt_id: str,
        source_name: str,
        content: Any,
        source_url: str = "",
        freshness: str = "unknown",
        confidence: float = 0.0,
    ) -> str:
        """Record a source reference without retaining raw tool output.

        Args:
            trace_id: Parent run identifier.
            attempt_id: Producing attempt identifier.
            source_name: Tool or provider name.
            content: Evidence payload; only a content hash is stored.
            source_url: Optional already-sanitized source URL.
            freshness: Freshness label such as ``live`` or ``stale``.
            confidence: Bounded evidence confidence.

        Returns:
            Opaque evidence identifier.
        """

        evidence_id = f"evidence-{secrets.token_hex(8)}"
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO evidence_records(
                    evidence_id, trace_id, attempt_id, source_type,
                    source_name, source_url, captured_at, freshness,
                    confidence, content_hash
                ) VALUES (?, ?, ?, 'tool_result', ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_id,
                    trace_id[:120],
                    attempt_id[:120],
                    source_name[:160],
                    source_url[:500],
                    time.time(),
                    freshness[:40],
                    max(0.0, min(float(confidence), 1.0)),
                    self._hash(content),
                ),
            )
            conn.commit()
        return evidence_id

    def get_trace(self, trace_id: str) -> dict[str, Any] | None:
        """Return a sanitized trace summary for diagnostics.

        Args:
            trace_id: Run identifier.

        Returns:
            Trace, attempts and evidence metadata, or ``None``.
        """

        with self._lock, self._connect() as conn:
            run = conn.execute(
                "SELECT * FROM agent_runs WHERE trace_id = ?", (trace_id,)
            ).fetchone()
            if run is None:
                return None
            attempts = conn.execute(
                "SELECT * FROM tool_attempts WHERE trace_id=? ORDER BY started_at",
                (trace_id,),
            ).fetchall()
            evidence = conn.execute(
                "SELECT * FROM evidence_records WHERE trace_id=? ORDER BY captured_at",
                (trace_id,),
            ).fetchall()
        return {
            "run": dict(run),
            "attempts": [dict(item) for item in attempts],
            "evidence": [dict(item) for item in evidence],
        }


_evidence_store: AgentEvidenceStore | None = None


def get_agent_evidence_store() -> AgentEvidenceStore:
    """Return the process-wide Agent evidence store."""

    global _evidence_store
    # Pytest runs in the same workspace as AstrBot. Keep its traces in a
    # process-local temporary database so test fixtures cannot alter production
    # diagnostics or be mistaken for QQ/OneBot traffic.
    if os.getenv("PYTEST_CURRENT_TEST"):
        test_path = (
            Path(gettempdir()) / "astrbot-agent-evidence-tests" / f"{os.getpid()}.db"
        )
        if _evidence_store is None or _evidence_store.database_path != test_path:
            _evidence_store = AgentEvidenceStore(test_path)
    elif _evidence_store is None:
        _evidence_store = AgentEvidenceStore()
    return _evidence_store
