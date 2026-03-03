from __future__ import annotations

from datetime import datetime, timezone

import pytest

from astrbot.core.db.po import SubagentTask
from astrbot.core.subagent.runtime import SubagentRuntime


class _FakeDb:
    def __init__(self):
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
        if task is None:
            return False
        task.status = "retrying"
        task.next_run_at = next_run_at
        task.error_class = error_class
        task.last_error = last_error
        task.updated_at = datetime.now(timezone.utc)
        return True

    async def mark_subagent_task_succeeded(self, task_id: str, *, result_text: str):
        task = self.tasks.get(task_id)
        if task is None:
            return False
        task.status = "succeeded"
        task.result_text = result_text
        task.updated_at = datetime.now(timezone.utc)
        task.finished_at = task.updated_at
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
        task.updated_at = datetime.now(timezone.utc)
        task.finished_at = task.updated_at
        return True

    async def cancel_subagent_task(self, task_id: str):
        task = self.tasks.get(task_id)
        if task is None:
            return False
        task.status = "canceled"
        task.updated_at = datetime.now(timezone.utc)
        task.finished_at = task.updated_at
        return True

    async def list_subagent_tasks(self, *, status: str | None = None, limit: int = 100):
        rows = list(self.tasks.values())
        if status:
            rows = [row for row in rows if row.status == status]
        return rows[:limit]


class _RecorderHooks:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def on_task_enqueued(self, task) -> None:
        self.events.append(f"enqueued:{task.task_id}")

    async def on_task_started(self, task) -> None:
        self.events.append(f"started:{task.task_id}")

    async def on_task_retrying(
        self, task, *, delay_seconds: float, error_class: str, error: Exception
    ) -> None:
        _ = delay_seconds
        _ = error
        self.events.append(f"retrying:{task.task_id}:{error_class}")

    async def on_task_succeeded(self, task, result: str) -> None:
        _ = result
        self.events.append(f"succeeded:{task.task_id}")

    async def on_task_failed(self, task, *, error_class: str, error: Exception) -> None:
        _ = error
        self.events.append(f"failed:{task.task_id}:{error_class}")

    async def on_task_canceled(self, task_id: str) -> None:
        self.events.append(f"canceled:{task_id}")

    async def on_task_result_ignored(self, task, *, reason: str) -> None:
        _ = reason
        self.events.append(f"ignored:{task.task_id}")


@pytest.mark.asyncio
async def test_runtime_hooks_called_in_success_order():
    db = _FakeDb()
    hooks = _RecorderHooks()
    runtime = SubagentRuntime(db=db, hooks=hooks)

    async def _executor(_task):
        return "done"

    runtime.set_task_executor(_executor)
    task_id = await runtime.enqueue(
        umo="umo:1",
        subagent_name="writer",
        handoff_tool_name="transfer_to_writer",
        payload={"tool_args": {"input": "x"}},
        tool_call_id="call_1",
    )
    await runtime.process_once(batch_size=8)

    assert hooks.events == [
        f"enqueued:{task_id}",
        f"started:{task_id}",
        f"succeeded:{task_id}",
    ]


@pytest.mark.asyncio
async def test_runtime_hook_failure_does_not_block_task_processing():
    db = _FakeDb()
    hooks = _RecorderHooks()

    async def _broken_started(task) -> None:
        hooks.events.append(f"started:{task.task_id}")
        raise RuntimeError("hook boom")

    hooks.on_task_started = _broken_started
    runtime = SubagentRuntime(db=db, hooks=hooks)

    async def _executor(_task):
        return "done"

    runtime.set_task_executor(_executor)
    task_id = await runtime.enqueue(
        umo="umo:2",
        subagent_name="writer",
        handoff_tool_name="transfer_to_writer",
        payload={"tool_args": {"input": "x"}},
        tool_call_id="call_2",
    )
    await runtime.process_once(batch_size=8)

    assert db.tasks[task_id].status == "succeeded"
    assert f"succeeded:{task_id}" in hooks.events


@pytest.mark.asyncio
async def test_runtime_hooks_called_on_retry_and_failure():
    db = _FakeDb()
    hooks = _RecorderHooks()
    runtime = SubagentRuntime(db=db, hooks=hooks, max_attempts=2)
    calls = {"n": 0}

    async def _executor(_task):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("retry")
        raise ValueError("fatal")

    runtime.set_task_executor(_executor)
    task_id = await runtime.enqueue(
        umo="umo:3",
        subagent_name="writer",
        handoff_tool_name="transfer_to_writer",
        payload={"tool_args": {"input": "x"}},
        tool_call_id="call_3",
    )
    await runtime.process_once(batch_size=8)
    db.tasks[task_id].next_run_at = datetime.now(timezone.utc)
    await runtime.process_once(batch_size=8)

    assert f"retrying:{task_id}:transient" in hooks.events
    assert f"failed:{task_id}:fatal" in hooks.events
