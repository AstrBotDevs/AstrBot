from __future__ import annotations

import asyncio
import hashlib
import json
import random
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from astrbot import logger
from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import SubagentTask

from .models import SubagentTaskData

TransientErrors = (
    asyncio.TimeoutError,
    TimeoutError,
    ConnectionError,
    ConnectionResetError,
)
FatalErrors = (ValueError, PermissionError, KeyError)


class SubagentRuntime:
    """Background runtime for subagent handoff tasks.

    It provides queueing, lane-based concurrency control, retry classification,
    and lifecycle logging. Task execution is delegated via a callback.
    """

    def __init__(
        self,
        db: BaseDatabase | None,
        *,
        max_concurrent: int = 8,
        max_attempts: int = 3,
        base_delay_ms: int = 500,
        max_delay_ms: int = 30000,
        jitter_ratio: float = 0.1,
    ) -> None:
        self._db = db
        self._max_concurrent = max(1, min(int(max_concurrent), 64))
        self._max_attempts = max(1, int(max_attempts))
        self._base_delay_ms = max(100, int(base_delay_ms))
        self._max_delay_ms = max(self._base_delay_ms, int(max_delay_ms))
        self._jitter_ratio = max(0.0, min(float(jitter_ratio), 1.0))
        self._active_lanes: dict[str, str] = {}
        self._task_executor: Callable[[SubagentTaskData], Awaitable[str]] | None = None
        self._running_recovery_done = False

    def set_max_concurrent(self, value: int) -> None:
        self._max_concurrent = max(1, min(int(value), 64))

    def set_task_executor(
        self,
        executor: Callable[[SubagentTaskData], Awaitable[str]],
    ) -> None:
        self._task_executor = executor

    async def enqueue(
        self,
        *,
        umo: str,
        subagent_name: str,
        handoff_tool_name: str,
        payload: dict[str, Any],
        tool_call_id: str | None,
    ) -> str:
        if not self._db:
            raise RuntimeError("Subagent runtime database is not available.")
        payload_json = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, default=str
        )
        idem = self._build_idempotency_key(
            umo=umo,
            handoff_tool_name=handoff_tool_name,
            tool_call_id=tool_call_id,
            payload_json=payload_json,
        )
        existing = await self._db.get_subagent_task_by_idempotency(idem)
        if existing:
            return existing.task_id

        task_id = uuid.uuid4().hex
        await self._db.create_subagent_task(
            task_id=task_id,
            idempotency_key=idem,
            umo=umo,
            subagent_name=subagent_name,
            handoff_tool_name=handoff_tool_name,
            payload_json=payload_json,
            max_attempts=self._max_attempts,
        )
        self._emit_event("task_enqueued", task_id, subagent_name, 0, umo)
        return task_id

    async def process_once(self, *, batch_size: int = 8) -> int:
        if not self._db:
            return 0
        if not self._task_executor:
            return 0
        if not self._running_recovery_done:
            try:
                recovered = await self._recover_interrupted_running_tasks()
                if recovered > 0:
                    logger.info(
                        "[SubagentRuntime] recovered %d interrupted running task(s).",
                        recovered,
                    )
            finally:
                self._running_recovery_done = True
        now = datetime.now(timezone.utc)
        candidates = await self._db.claim_due_subagent_tasks(
            now=now, limit=batch_size * 2
        )
        selected: list[SubagentTaskData] = []
        for task in candidates:
            lane = self._lane_key(task.umo, task.subagent_name)
            if lane in self._active_lanes:
                continue
            if len(self._active_lanes) >= self._max_concurrent:
                break
            running = await self._db.mark_subagent_task_running(task.task_id)
            if not running:
                continue
            self._active_lanes[lane] = running.task_id
            selected.append(_to_task_data(running))
            if len(selected) >= batch_size:
                break

        if not selected:
            return 0
        await asyncio.gather(*(self._run_one(task) for task in selected))
        return len(selected)

    async def list_tasks(
        self, *, status: str | None = None, limit: int = 100
    ) -> list[dict]:
        if not self._db:
            return []
        rows = await self._db.list_subagent_tasks(status=status, limit=limit)
        return [_serialize_task(row) for row in rows]

    async def retry_task(self, task_id: str) -> bool:
        if not self._db:
            return False
        return await self._db.mark_subagent_task_retrying(
            task_id=task_id,
            next_run_at=datetime.now(timezone.utc),
            error_class="manual",
            last_error="manual retry requested",
        )

    async def cancel_task(self, task_id: str) -> bool:
        if not self._db:
            return False
        return await self._db.cancel_subagent_task(task_id)

    async def _run_one(self, task: SubagentTaskData) -> None:
        lane = self._lane_key(task.umo, task.subagent_name)
        self._emit_event(
            "task_started", task.task_id, task.subagent_name, task.attempt, task.umo
        )
        try:
            result = await self._task_executor(task)
            updated = await self._db.mark_subagent_task_succeeded(
                task.task_id, result_text=result
            )  # type: ignore[arg-type]
            if not updated:
                self._emit_event(
                    "task_result_ignored",
                    task.task_id,
                    task.subagent_name,
                    task.attempt,
                    task.umo,
                    error_class="state_changed",
                    error_message="task status changed before success commit",
                )
                return
            self._emit_event(
                "task_succeeded",
                task.task_id,
                task.subagent_name,
                task.attempt,
                task.umo,
            )
            return
        except Exception as exc:  # noqa: BLE001
            error_class = self._classify_error(exc)
            if error_class == "transient" and task.attempt < task.max_attempts:
                delay = self._compute_delay_seconds(task.attempt)
                next_run = datetime.now(timezone.utc) + timedelta(seconds=delay)
                updated = await self._db.mark_subagent_task_retrying(
                    task_id=task.task_id,
                    next_run_at=next_run,
                    error_class=error_class,
                    last_error=str(exc),
                )  # type: ignore[arg-type]
                if not updated:
                    self._emit_event(
                        "task_result_ignored",
                        task.task_id,
                        task.subagent_name,
                        task.attempt,
                        task.umo,
                        error_class="state_changed",
                        error_message="task status changed before retry commit",
                    )
                    return
                self._emit_event(
                    "task_retrying",
                    task.task_id,
                    task.subagent_name,
                    task.attempt,
                    task.umo,
                    delay_seconds=delay,
                    error_class=error_class,
                    error_message=str(exc),
                )
                return

            updated = await self._db.mark_subagent_task_failed(
                task_id=task.task_id,
                error_class=error_class,
                last_error=str(exc),
            )  # type: ignore[arg-type]
            if not updated:
                self._emit_event(
                    "task_result_ignored",
                    task.task_id,
                    task.subagent_name,
                    task.attempt,
                    task.umo,
                    error_class="state_changed",
                    error_message="task status changed before failure commit",
                )
                return
            self._emit_event(
                "task_failed",
                task.task_id,
                task.subagent_name,
                task.attempt,
                task.umo,
                error_class=error_class,
                error_message=str(exc),
            )
            return
        finally:
            self._active_lanes.pop(lane, None)

    @staticmethod
    def _lane_key(umo: str, subagent_name: str) -> str:
        return f"session:{umo}:{subagent_name}"

    @staticmethod
    def _build_idempotency_key(
        *,
        umo: str,
        handoff_tool_name: str,
        tool_call_id: str | None,
        payload_json: str,
    ) -> str:
        raw = f"{umo}:{handoff_tool_name}:{tool_call_id or ''}:{payload_json}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _compute_delay_seconds(self, attempt: int) -> float:
        delay_ms = min(self._max_delay_ms, self._base_delay_ms * (2 ** max(0, attempt)))
        jitter_ms = delay_ms * self._jitter_ratio * random.random()  # noqa: S311
        return (delay_ms + jitter_ms) / 1000.0

    @staticmethod
    def _classify_error(exc: Exception) -> str:
        if isinstance(exc, FatalErrors):
            return "fatal"
        if isinstance(exc, TransientErrors):
            return "transient"
        return "transient"

    async def _recover_interrupted_running_tasks(self) -> int:
        if not self._db:
            return 0
        rows = await self._db.list_subagent_tasks(status="running", limit=10000)
        if not rows:
            return 0
        now = datetime.now(timezone.utc)
        recovered = 0
        for row in rows:
            ok = await self._db.mark_subagent_task_retrying(
                task_id=row.task_id,
                next_run_at=now,
                error_class="transient",
                last_error="Recovered interrupted running task after worker restart.",
            )
            if ok:
                recovered += 1
        return recovered

    @staticmethod
    def _emit_event(
        event_type: str,
        task_id: str,
        subagent_name: str,
        attempt: int,
        umo: str,
        *,
        delay_seconds: float | None = None,
        error_class: str | None = None,
        error_message: str | None = None,
    ) -> None:
        logger.info(
            "[SubagentRuntime] event=%s task_id=%s subagent=%s attempt=%s umo=%s delay=%s error_class=%s error=%s",
            event_type,
            task_id,
            subagent_name,
            attempt,
            umo,
            delay_seconds,
            error_class,
            error_message,
        )


def _to_task_data(task: SubagentTask) -> SubagentTaskData:
    return SubagentTaskData(
        task_id=task.task_id,
        idempotency_key=task.idempotency_key,
        umo=task.umo,
        subagent_name=task.subagent_name,
        handoff_tool_name=task.handoff_tool_name,
        status=task.status,
        attempt=task.attempt,
        max_attempts=task.max_attempts,
        next_run_at=task.next_run_at,
        payload_json=task.payload_json,
        error_class=task.error_class,
        last_error=task.last_error,
        result_text=task.result_text,
        created_at=task.created_at,
        updated_at=task.updated_at,
        finished_at=task.finished_at,
    )


def _serialize_task(task: SubagentTask) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "idempotency_key": task.idempotency_key,
        "umo": task.umo,
        "subagent_name": task.subagent_name,
        "handoff_tool_name": task.handoff_tool_name,
        "status": task.status,
        "attempt": task.attempt,
        "max_attempts": task.max_attempts,
        "next_run_at": task.next_run_at.isoformat() if task.next_run_at else None,
        "error_class": task.error_class,
        "last_error": task.last_error,
        "result_text": task.result_text,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
    }
