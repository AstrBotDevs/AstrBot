from __future__ import annotations

from datetime import datetime, timezone

import pytest
from _fake_subagent_db import FakeSubagentDb as _FakeDb

from astrbot.core.subagent.runtime import SubagentRuntime


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
