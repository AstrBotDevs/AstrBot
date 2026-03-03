from __future__ import annotations

import asyncio
import hashlib
import json
import random
import typing as T
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError

from astrbot import logger
from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import SubagentTask

from .constants import (
    DEFAULT_BASE_DELAY_MS,
    DEFAULT_JITTER_RATIO,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_MAX_CONCURRENT_TASKS,
    DEFAULT_MAX_DELAY_MS,
    MAX_CONCURRENT_TASKS,
    MIN_ATTEMPTS,
    MIN_BASE_DELAY_MS,
    MIN_CONCURRENT_TASKS,
)
from .error_classifier import DefaultErrorClassifier, ErrorClassifier
from .hooks import NoopSubagentHooks, SubagentHooks
from .models import SubagentTaskData


class SubagentRuntime:
    """Background runtime for subagent handoff tasks.

    It provides queueing, lane-based concurrency control, retry classification,
    and lifecycle logging. Task execution is delegated via a callback.
    """

    def __init__(
        self,
        db: BaseDatabase | None,
        *,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT_TASKS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        base_delay_ms: int = DEFAULT_BASE_DELAY_MS,
        max_delay_ms: int = DEFAULT_MAX_DELAY_MS,
        jitter_ratio: float = DEFAULT_JITTER_RATIO,
        hooks: SubagentHooks | None = None,
        error_classifier: ErrorClassifier | None = None,
    ) -> None:
        self._db = db
        self._max_concurrent = max(
            MIN_CONCURRENT_TASKS, min(int(max_concurrent), MAX_CONCURRENT_TASKS)
        )
        self._max_attempts = max(MIN_ATTEMPTS, int(max_attempts))
        self._base_delay_ms = max(MIN_BASE_DELAY_MS, int(base_delay_ms))
        self._max_delay_ms = max(self._base_delay_ms, int(max_delay_ms))
        self._jitter_ratio = max(0.0, min(float(jitter_ratio), 1.0))
        self._active_lanes: dict[str, str] = {}
        self._task_executor: Callable[[SubagentTaskData], Awaitable[str]] | None = None
        self._running_recovery_done = False
        self._hooks: SubagentHooks = hooks or NoopSubagentHooks()
        self._error_classifier: ErrorClassifier = (
            error_classifier or DefaultErrorClassifier()
        )

    def set_max_concurrent(self, value: int) -> None:
        self._max_concurrent = max(
            MIN_CONCURRENT_TASKS, min(int(value), MAX_CONCURRENT_TASKS)
        )

    def set_task_executor(
        self,
        executor: Callable[[SubagentTaskData], Awaitable[str]],
    ) -> None:
        self._task_executor = executor

    def set_hooks(self, hooks: SubagentHooks | None) -> None:
        self._hooks = hooks or NoopSubagentHooks()

    def set_error_classifier(self, error_classifier: ErrorClassifier | None) -> None:
        self._error_classifier = error_classifier or DefaultErrorClassifier()

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
        try:
            created = await self._db.create_subagent_task(
                task_id=task_id,
                idempotency_key=idem,
                umo=umo,
                subagent_name=subagent_name,
                handoff_tool_name=handoff_tool_name,
                payload_json=payload_json,
                max_attempts=self._max_attempts,
            )
        except IntegrityError:
            # Handle concurrent enqueue with the same idempotency key.
            existing_after_race = await self._db.get_subagent_task_by_idempotency(idem)
            if existing_after_race:
                return existing_after_race.task_id
            raise
        self._emit_event("task_enqueued", task_id, subagent_name, 0, umo)
        await self._call_hook("on_task_enqueued", _to_task_data(created))
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
        return await self._db.reschedule_subagent_task(
            task_id=task_id,
            next_run_at=datetime.now(timezone.utc),
            error_class="manual",
            last_error="manual retry requested",
        )

    async def cancel_task(self, task_id: str) -> bool:
        if not self._db:
            return False
        canceled = await self._db.cancel_subagent_task(task_id)
        if canceled:
            await self._call_hook("on_task_canceled", task_id)
        return canceled

    async def _run_one(self, task: SubagentTaskData) -> None:
        db = self._db
        task_executor = self._task_executor
        if db is None or task_executor is None:
            raise RuntimeError("Subagent runtime is not fully initialized.")

        lane = self._lane_key(task.umo, task.subagent_name)
        self._emit_event(
            "task_started", task.task_id, task.subagent_name, task.attempt, task.umo
        )
        await self._call_hook("on_task_started", task)
        try:
            result = await task_executor(task)
            updated = await db.mark_subagent_task_succeeded(
                task.task_id, result_text=result
            )
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
                await self._call_hook(
                    "on_task_result_ignored",
                    task,
                    reason="task status changed before success commit",
                )
                return
            self._emit_event(
                "task_succeeded",
                task.task_id,
                task.subagent_name,
                task.attempt,
                task.umo,
            )
            await self._call_hook("on_task_succeeded", task, result)
            return
        except Exception as exc:  # noqa: BLE001
            error_class = self._classify_error(exc)
            if (
                error_class in {"transient", "retryable"}
                and task.attempt < task.max_attempts
            ):
                delay = self._compute_delay_seconds(task.attempt)
                next_run = datetime.now(timezone.utc) + timedelta(seconds=delay)
                updated = await db.mark_subagent_task_retrying(
                    task_id=task.task_id,
                    next_run_at=next_run,
                    error_class=error_class,
                    last_error=str(exc),
                )
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
                    await self._call_hook(
                        "on_task_result_ignored",
                        task,
                        reason="task status changed before retry commit",
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
                await self._call_hook(
                    "on_task_retrying",
                    task,
                    delay_seconds=delay,
                    error_class=error_class,
                    error=exc,
                )
                return

            updated = await db.mark_subagent_task_failed(
                task_id=task.task_id,
                error_class=error_class,
                last_error=str(exc),
            )
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
                await self._call_hook(
                    "on_task_result_ignored",
                    task,
                    reason="task status changed before failure commit",
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
            await self._call_hook(
                "on_task_failed",
                task,
                error_class=error_class,
                error=exc,
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

    def _classify_error(self, exc: Exception) -> str:
        classified = self._error_classifier.classify(exc)
        if classified in {"fatal", "transient", "retryable"}:
            return classified
        return "transient"

    async def _recover_interrupted_running_tasks(self) -> int:
        db = self._db
        if not db:
            return 0
        rows = await db.list_subagent_tasks(status="running", limit=200)
        if not rows:
            return 0
        now = datetime.now(timezone.utc)
        # Only recover tasks that have been stale for at least 5 minutes;
        # recently-updated tasks may still be executing on another worker.
        stale_threshold = timedelta(minutes=5)
        recovered = 0
        for row in rows:
            if row.updated_at and (now - row.updated_at) < stale_threshold:
                continue
            ok = await db.mark_subagent_task_retrying(
                task_id=row.task_id,
                next_run_at=now,
                error_class="transient",
                last_error="Recovered interrupted running task after worker restart.",
            )
            if ok:
                recovered += 1
        return recovered

    async def _call_hook(self, hook_name: str, *args, **kwargs) -> None:
        hook = getattr(self._hooks, hook_name, None)
        if not callable(hook):
            return
        typed_hook = T.cast(Callable[..., Awaitable[None]], hook)
        try:
            await typed_hook(*args, **kwargs)
        except Exception as exc:
            exc_type = type(exc).__name__
            exc_module = type(exc).__module__
            full_exc_name = (
                exc_type if exc_module == "builtins" else f"{exc_module}.{exc_type}"
            )
            logger.error(
                "[SubagentRuntime] hook=%s failed (type=%s): %s",
                hook_name,
                full_exc_name,
                exc,
                exc_info=True,
            )

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
        logger.debug(
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
