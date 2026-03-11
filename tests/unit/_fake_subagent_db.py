"""Shared in-memory fake database for subagent tests.

Provides ``FakeSubagentDb`` — a minimal, dictionary-backed double that
implements the DB methods used by ``SubagentRuntime``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from astrbot.core.db.po import SubagentTask


class FakeSubagentDb:
    """In-memory fake of the subset of ``BaseDatabase`` used by the subagent
    runtime, planner and hooks tests."""

    def __init__(self) -> None:
        self.tasks: dict[str, SubagentTask] = {}

    async def create_subagent_task(self, **kwargs) -> SubagentTask:
        now = datetime.now(timezone.utc)
        task = SubagentTask(
            task_id=kwargs["task_id"],
            idempotency_key=kwargs["idempotency_key"],
            umo=kwargs["umo"],
            subagent_name=kwargs["subagent_name"],
            handoff_tool_name=kwargs["handoff_tool_name"],
            payload_json=kwargs["payload_json"],
            max_attempts=kwargs.get("max_attempts", 3),
            status="pending",
            attempt=0,
            next_run_at=now,
            created_at=now,
            updated_at=now,
        )
        self.tasks[task.task_id] = task
        return task

    async def get_subagent_task_by_idempotency(self, idempotency_key: str):
        for task in self.tasks.values():
            if task.idempotency_key == idempotency_key:
                return task
        return None

    async def claim_due_subagent_tasks(self, *, now: datetime, limit: int = 20):
        rows = [
            t
            for t in self.tasks.values()
            if t.status in {"pending", "retrying"}
            and (t.next_run_at is None or t.next_run_at <= now)
        ]
        rows.sort(key=lambda item: item.created_at)
        return rows[:limit]

    async def mark_subagent_task_running(self, task_id: str):
        task = self.tasks.get(task_id)
        if task is None or task.status not in {"pending", "retrying"}:
            return None
        task.status = "running"
        task.attempt += 1
        task.updated_at = datetime.now(timezone.utc)
        return task

    async def mark_subagent_task_retrying(
        self, *, task_id: str, next_run_at: datetime, error_class: str, last_error: str
    ):
        task = self.tasks.get(task_id)
        if task is None or task.status not in {"running", "retrying"}:
            return False
        task.status = "retrying"
        task.next_run_at = next_run_at
        task.error_class = error_class
        task.last_error = last_error
        task.updated_at = datetime.now(timezone.utc)
        return True

    async def reschedule_subagent_task(
        self, *, task_id: str, next_run_at: datetime, error_class: str, last_error: str
    ):
        task = self.tasks.get(task_id)
        if task is None or task.status not in {
            "failed",
            "canceled",
            "succeeded",
            "pending",
            "retrying",
        }:
            return False
        task.status = "retrying"
        task.attempt = 0
        task.next_run_at = next_run_at
        task.error_class = error_class
        task.last_error = last_error
        task.result_text = None
        task.finished_at = None
        task.updated_at = datetime.now(timezone.utc)
        return True

    async def mark_subagent_task_succeeded(self, task_id: str, *, result_text: str):
        task = self.tasks.get(task_id)
        if task is None:
            return False
        task.status = "succeeded"
        task.result_text = result_text
        task.finished_at = datetime.now(timezone.utc)
        task.updated_at = task.finished_at
        return True

    async def mark_subagent_task_failed(
        self, *, task_id: str, error_class: str, last_error: str
    ):
        task = self.tasks.get(task_id)
        if task is None:
            return False
        task.status = "failed"
        task.error_class = error_class
        task.last_error = last_error
        task.finished_at = datetime.now(timezone.utc)
        task.updated_at = task.finished_at
        return True

    async def cancel_subagent_task(self, task_id: str):
        task = self.tasks.get(task_id)
        if task is None:
            return False
        task.status = "canceled"
        task.finished_at = datetime.now(timezone.utc)
        task.updated_at = task.finished_at
        return True

    async def list_subagent_tasks(self, *, status: str | None = None, limit: int = 100):
        rows = list(self.tasks.values())
        if status:
            rows = [r for r in rows if r.status == status]
        rows.sort(key=lambda item: item.created_at, reverse=True)
        return rows[:limit]
