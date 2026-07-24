from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import sqlite3
import threading
import time
from collections.abc import Awaitable, Callable
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import mcp

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .tool import ToolOutcome


@dataclass(slots=True)
class AgentJob:
    """Sanitized persistent state for one asynchronous Agent tool execution.

    Args:
        job_id: Opaque identifier safe to expose to the requester.
        tool_name: Registered Tool Manager capability name.
        requester_id: Stable platform-scoped requester identity.
        umo: Unified message origin that owns the job.
        args_hash: SHA-256 digest of canonical arguments; raw arguments are not stored.
        status: Current lifecycle state.
        created_at: Unix timestamp when the job was accepted.
        started_at: Unix timestamp when execution began.
        finished_at: Unix timestamp when execution reached a terminal state.
        expires_at: Unix timestamp after which retained results may be removed.
        progress: Bounded integer progress indication.
        result: Bounded user-readable result text.
        error_code: Stable machine-readable failure code.
        error_summary: Sanitized bounded failure detail.
        cancellable: Whether the running task may be cancelled safely.
    """

    job_id: str
    tool_name: str
    requester_id: str
    umo: str
    args_hash: str
    status: str
    created_at: float
    started_at: float | None = None
    finished_at: float | None = None
    expires_at: float | None = None
    progress: int = 0
    result: str = ""
    error_code: str = ""
    error_summary: str = ""
    cancellable: bool = True

    def to_dict(self, *, include_result: bool = True) -> dict[str, Any]:
        """Return a JSON-compatible job view.

        Args:
            include_result: Whether the retained result body should be included.

        Returns:
            Sanitized job metadata suitable for APIs and Agent tools.
        """

        data = asdict(self)
        if not include_result:
            data.pop("result", None)
        return data


class AgentJobManager:
    """Run and persist bounded asynchronous Agent tool jobs."""

    TERMINAL_STATUSES = frozenset(
        {"succeeded", "failed", "cancelled", "expired", "interrupted"}
    )

    def __init__(
        self,
        database_path: Path | None = None,
        *,
        result_ttl_seconds: int = 86400,
        max_result_chars: int = 65536,
    ) -> None:
        """Initialize the job registry and recover stale running records.

        Args:
            database_path: Optional SQLite path used by tests or alternate runtimes.
            result_ttl_seconds: Retention time for terminal job results.
            max_result_chars: Maximum persisted result length.
        """

        self.database_path = database_path or (
            Path(get_astrbot_data_path()) / "agent_jobs.db"
        )
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.result_ttl_seconds = max(300, int(result_ttl_seconds))
        self.max_result_chars = max(1024, int(max_result_chars))
        self._db_lock = threading.RLock()
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._initialize_database()

    def _connect(self):
        """Open a SQLite connection that closes when its context exits."""

        conn = sqlite3.connect(self.database_path, timeout=5)
        conn.row_factory = sqlite3.Row
        return closing(conn)

    def _initialize_database(self) -> None:
        with self._db_lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_jobs (
                    job_id TEXT PRIMARY KEY,
                    tool_name TEXT NOT NULL,
                    requester_id TEXT NOT NULL,
                    umo TEXT NOT NULL,
                    args_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    started_at REAL,
                    finished_at REAL,
                    expires_at REAL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    result TEXT NOT NULL DEFAULT '',
                    error_code TEXT NOT NULL DEFAULT '',
                    error_summary TEXT NOT NULL DEFAULT '',
                    cancellable INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            now = time.time()
            conn.execute(
                """
                UPDATE agent_jobs
                SET status = 'interrupted', finished_at = ?, progress = 100,
                    error_code = 'process_restarted',
                    error_summary = 'AstrBot restarted before this job completed.'
                WHERE status IN ('queued', 'running')
                """,
                (now,),
            )
            conn.commit()

    @staticmethod
    def _argument_hash(arguments: dict[str, Any]) -> str:
        canonical = json.dumps(
            arguments,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _outcome_text(outcome: ToolOutcome) -> str:
        result = outcome.result
        parts: list[str] = []
        if result is not None:
            for item in result.content:
                if isinstance(item, mcp.types.TextContent) and item.text:
                    parts.append(item.text)
            if result.structuredContent:
                parts.append(
                    json.dumps(
                        result.structuredContent,
                        ensure_ascii=False,
                        default=str,
                    )
                )
        if not parts and outcome.content:
            parts.append(outcome.content)
        if not parts and outcome.structured_content is not None:
            parts.append(
                json.dumps(outcome.structured_content, ensure_ascii=False, default=str)
            )
        if not parts and outcome.status == "direct_sent":
            return "The tool sent its result directly to the requester."
        return "\n".join(parts).strip()

    def _row_to_job(self, row: sqlite3.Row) -> AgentJob:
        return AgentJob(
            job_id=str(row["job_id"]),
            tool_name=str(row["tool_name"]),
            requester_id=str(row["requester_id"]),
            umo=str(row["umo"]),
            args_hash=str(row["args_hash"]),
            status=str(row["status"]),
            created_at=float(row["created_at"]),
            started_at=(
                float(row["started_at"]) if row["started_at"] is not None else None
            ),
            finished_at=(
                float(row["finished_at"]) if row["finished_at"] is not None else None
            ),
            expires_at=(
                float(row["expires_at"]) if row["expires_at"] is not None else None
            ),
            progress=int(row["progress"]),
            result=str(row["result"] or ""),
            error_code=str(row["error_code"] or ""),
            error_summary=str(row["error_summary"] or ""),
            cancellable=bool(row["cancellable"]),
        )

    def _update(self, job_id: str, **values: Any) -> None:
        allowed = {
            "status",
            "started_at",
            "finished_at",
            "expires_at",
            "progress",
            "result",
            "error_code",
            "error_summary",
        }
        updates = {key: value for key, value in values.items() if key in allowed}
        if not updates:
            return
        assignments = ", ".join(f"{key} = ?" for key in updates)
        with self._db_lock, self._connect() as conn:
            conn.execute(
                f"UPDATE agent_jobs SET {assignments} WHERE job_id = ?",  # noqa: S608
                (*updates.values(), job_id),
            )
            conn.commit()

    async def submit(
        self,
        *,
        tool_name: str,
        requester_id: str,
        umo: str,
        arguments: dict[str, Any],
        runner: Callable[[], Awaitable[ToolOutcome]],
        timeout_seconds: int = 120,
        cancellable: bool = True,
        on_complete: Callable[[AgentJob, ToolOutcome], Awaitable[None]] | None = None,
    ) -> AgentJob:
        """Submit a tool coroutine and return its persistent job record.

        Args:
            tool_name: Registered tool name.
            requester_id: Stable requester identity.
            umo: Owning unified message origin.
            arguments: Exact runtime arguments, retained only as a hash.
            runner: Coroutine factory that returns a normalized tool outcome.
            timeout_seconds: Hard execution watchdog between 5 and 3600 seconds.
            cancellable: Whether requester cancellation is safe.
            on_complete: Optional deterministic completion notifier.

        Returns:
            Newly queued job metadata.
        """

        now = time.time()
        job = AgentJob(
            job_id=f"job-{secrets.token_hex(6)}",
            tool_name=tool_name[:160],
            requester_id=requester_id[:200],
            umo=umo[:300],
            args_hash=self._argument_hash(arguments),
            status="queued",
            created_at=now,
            expires_at=now + self.result_ttl_seconds,
            cancellable=bool(cancellable),
        )
        with self._db_lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_jobs (
                    job_id, tool_name, requester_id, umo, args_hash, status,
                    created_at, expires_at, progress, cancellable
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.job_id,
                    job.tool_name,
                    job.requester_id,
                    job.umo,
                    job.args_hash,
                    job.status,
                    job.created_at,
                    job.expires_at,
                    0,
                    int(job.cancellable),
                ),
            )
            conn.commit()

        timeout = max(5, min(int(timeout_seconds), 3600))

        async def execute_job() -> None:
            self._update(
                job.job_id,
                status="running",
                started_at=time.time(),
                progress=5,
            )
            outcome: ToolOutcome
            try:
                outcome = await asyncio.wait_for(runner(), timeout=timeout)
                result_text = self._outcome_text(outcome)[: self.max_result_chars]
                if outcome.status in {"success", "direct_sent"}:
                    status = "succeeded"
                    error_code = ""
                    error_summary = ""
                elif outcome.status == "empty":
                    status = "failed"
                    error_code = outcome.error_code or "empty_result"
                    error_summary = (
                        outcome.diagnostics or "Tool returned no usable result."
                    )
                else:
                    status = "failed"
                    error_code = outcome.error_code or "tool_failed"
                    error_summary = outcome.diagnostics or result_text
                self._update(
                    job.job_id,
                    status=status,
                    finished_at=time.time(),
                    progress=100,
                    result=result_text,
                    error_code=error_code[:120],
                    error_summary=error_summary[:1000],
                )
            except TimeoutError:
                outcome = ToolOutcome(
                    status="timeout",
                    retryable=True,
                    error_code="timeout",
                    diagnostics=f"Tool exceeded the {timeout}-second watchdog.",
                )
                self._update(
                    job.job_id,
                    status="expired",
                    finished_at=time.time(),
                    progress=100,
                    error_code="timeout",
                    error_summary=outcome.diagnostics,
                )
            except asyncio.CancelledError:
                outcome = ToolOutcome(
                    status="failed",
                    error_code="cancelled",
                    diagnostics="Job was cancelled before completion.",
                )
                self._update(
                    job.job_id,
                    status="cancelled",
                    finished_at=time.time(),
                    progress=100,
                    error_code="cancelled",
                    error_summary=outcome.diagnostics,
                )
                raise
            except Exception as exc:  # noqa: BLE001
                logger.exception("Agent job %s failed", job.job_id)
                outcome = ToolOutcome(
                    status="failed",
                    retryable=True,
                    error_code="internal_error",
                    diagnostics=str(exc)[:1000],
                )
                self._update(
                    job.job_id,
                    status="failed",
                    finished_at=time.time(),
                    progress=100,
                    error_code="internal_error",
                    error_summary=outcome.diagnostics,
                )
            finally:
                self._tasks.pop(job.job_id, None)

            if on_complete is not None:
                completed = self.get(job.job_id)
                if completed is not None:
                    try:
                        await on_complete(completed, outcome)
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "Agent job %s completion notification failed", job.job_id
                        )

        task = asyncio.create_task(execute_job(), name=f"agent-job:{job.job_id}")
        self._tasks[job.job_id] = task
        return job

    def get(self, job_id: str) -> AgentJob | None:
        """Return one job and expire retained terminal results when necessary.

        Args:
            job_id: Opaque job identifier.

        Returns:
            Job metadata, or ``None`` when unknown.
        """

        with self._db_lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM agent_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        if row is None:
            return None
        job = self._row_to_job(row)
        if (
            job.status in self.TERMINAL_STATUSES
            and job.status != "expired"
            and job.expires_at is not None
            and job.expires_at <= time.time()
        ):
            self._update(
                job.job_id,
                status="expired",
                result="",
                error_code="result_expired",
                error_summary="Retained job result expired.",
            )
            return self.get(job_id)
        return job

    def list_for_requester(
        self, requester_id: str, *, owner: bool = False, limit: int = 20
    ) -> list[AgentJob]:
        """List recent jobs visible to one requester.

        Args:
            requester_id: Stable requester identity.
            owner: Whether to include jobs from all users.
            limit: Maximum records returned.

        Returns:
            Recent jobs ordered from newest to oldest.
        """

        bounded_limit = max(1, min(int(limit), 100))
        with self._db_lock, self._connect() as conn:
            if owner:
                rows = conn.execute(
                    "SELECT * FROM agent_jobs ORDER BY created_at DESC LIMIT ?",
                    (bounded_limit,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM agent_jobs WHERE requester_id = ?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (requester_id, bounded_limit),
                ).fetchall()
        return [self._row_to_job(row) for row in rows]

    async def cancel(
        self, job_id: str, *, requester_id: str, owner: bool = False
    ) -> tuple[bool, str]:
        """Cancel a safe running job after ownership verification.

        Args:
            job_id: Opaque job identifier.
            requester_id: Stable identity requesting cancellation.
            owner: Whether the caller is the configured AstrBot owner.

        Returns:
            Success flag and a user-readable status.
        """

        job = self.get(job_id)
        if job is None:
            return False, "Job not found."
        if not owner and job.requester_id != requester_id:
            return False, "This job belongs to another requester."
        if job.status in self.TERMINAL_STATUSES:
            return False, f"Job is already {job.status}."
        if not job.cancellable:
            return (
                False,
                "This job may have side effects and cannot be cancelled safely.",
            )
        task = self._tasks.get(job_id)
        if task is None:
            self._update(
                job_id,
                status="interrupted",
                finished_at=time.time(),
                progress=100,
                error_code="task_missing",
                error_summary="The in-memory task lease was not found.",
            )
            return (
                False,
                "The task lease was missing and the job was marked interrupted.",
            )
        task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
        except asyncio.CancelledError:
            pass
        except asyncio.TimeoutError:
            # A plugin that suppresses cancellation must not keep a job lease
            # forever. Persist an interrupted state and detach the orphan task;
            # the process supervisor will clean it up during shutdown.
            self._update(
                job_id,
                status="interrupted",
                finished_at=time.time(),
                progress=100,
                error_code="cancel_timeout",
                error_summary="The job did not acknowledge cancellation within 2 seconds.",
            )
            return (
                False,
                "The task did not stop within 2 seconds and was marked interrupted.",
            )
        return True, "Job cancelled."

    async def shutdown(self) -> None:
        """Cancel running task handles and persist an interrupted state."""

        tasks = list(self._tasks.items())
        for _, task in tasks:
            task.cancel()
        if tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        *(task for _, task in tasks), return_exceptions=True
                    ),
                    timeout=2.0,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Some Agent jobs did not acknowledge shutdown cancellation"
                )


_agent_job_manager: AgentJobManager | None = None


def get_agent_job_manager() -> AgentJobManager:
    """Return the process-wide Agent job manager.

    Returns:
        Lazily initialized process-wide manager.
    """

    global _agent_job_manager
    if _agent_job_manager is None:
        _agent_job_manager = AgentJobManager()
    return _agent_job_manager
