from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from _fake_subagent_db import FakeSubagentDb as _FakeDb
from sqlalchemy.exc import IntegrityError

from astrbot.core.db.po import SubagentTask
from astrbot.core.subagent.error_classifier import ErrorClassifier
from astrbot.core.subagent.runtime import SubagentRuntime


@pytest.mark.asyncio
async def test_runtime_enqueue_is_idempotent():
    db = _FakeDb()
    runtime = SubagentRuntime(db)
    payload = {"tool_args": {"input": "hello"}}
    task1 = await runtime.enqueue(
        umo="webchat:FriendMessage:webchat!u!s",
        subagent_name="writer",
        handoff_tool_name="transfer_to_writer",
        payload=payload,
        tool_call_id="call_1",
    )
    task2 = await runtime.enqueue(
        umo="webchat:FriendMessage:webchat!u!s",
        subagent_name="writer",
        handoff_tool_name="transfer_to_writer",
        payload=payload,
        tool_call_id="call_1",
    )
    assert task1 == task2


@pytest.mark.asyncio
async def test_runtime_enqueue_diff_tool_call_id_not_deduped():
    db = _FakeDb()
    runtime = SubagentRuntime(db)
    payload = {"tool_args": {"input": "hello"}}
    task1 = await runtime.enqueue(
        umo="webchat:FriendMessage:webchat!u!s",
        subagent_name="writer",
        handoff_tool_name="transfer_to_writer",
        payload=payload,
        tool_call_id="call_1",
    )
    task2 = await runtime.enqueue(
        umo="webchat:FriendMessage:webchat!u!s",
        subagent_name="writer",
        handoff_tool_name="transfer_to_writer",
        payload=payload,
        tool_call_id="call_2",
    )
    assert task1 != task2


@pytest.mark.asyncio
async def test_runtime_retries_transient_then_succeeds():
    db = _FakeDb()
    runtime = SubagentRuntime(db, base_delay_ms=100, max_delay_ms=100, max_attempts=3)
    calls = {"n": 0}

    async def _executor(_task):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("transient")
        return "done"

    runtime.set_task_executor(_executor)
    task_id = await runtime.enqueue(
        umo="webchat:FriendMessage:webchat!u!s",
        subagent_name="writer",
        handoff_tool_name="transfer_to_writer",
        payload={"tool_args": {"input": "x"}},
        tool_call_id="call_2",
    )
    processed = await runtime.process_once(batch_size=8)
    assert processed == 1
    assert db.tasks[task_id].status == "retrying"

    db.tasks[task_id].next_run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    processed = await runtime.process_once(batch_size=8)
    assert processed == 1
    assert db.tasks[task_id].status == "succeeded"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_runtime_respects_session_lane_serialization():
    db = _FakeDb()
    runtime = SubagentRuntime(db)

    async def _executor(_task):
        await asyncio.sleep(0.05)
        return "ok"

    runtime.set_task_executor(_executor)

    await runtime.enqueue(
        umo="webchat:FriendMessage:webchat!u!s",
        subagent_name="writer",
        handoff_tool_name="transfer_to_writer",
        payload={"tool_args": {"input": "a"}},
        tool_call_id="call_a",
    )
    await runtime.enqueue(
        umo="webchat:FriendMessage:webchat!u!s",
        subagent_name="writer",
        handoff_tool_name="transfer_to_writer",
        payload={"tool_args": {"input": "b"}},
        tool_call_id="call_b",
    )

    processed = await runtime.process_once(batch_size=8)
    assert processed == 1
    pending = [task for task in db.tasks.values() if task.status == "pending"]
    assert len(pending) == 1


@pytest.mark.asyncio
async def test_runtime_fatal_error_fails_without_retry():
    db = _FakeDb()
    runtime = SubagentRuntime(db, max_attempts=3)

    async def _executor(_task):
        raise ValueError("fatal")

    runtime.set_task_executor(_executor)
    task_id = await runtime.enqueue(
        umo="webchat:FriendMessage:webchat!u!s",
        subagent_name="writer",
        handoff_tool_name="transfer_to_writer",
        payload={"tool_args": {"input": "fatal"}},
        tool_call_id="call_fatal",
    )
    processed = await runtime.process_once(batch_size=8)
    assert processed == 1
    assert db.tasks[task_id].status == "failed"
    assert db.tasks[task_id].error_class == "fatal"


@pytest.mark.asyncio
async def test_runtime_respects_global_concurrency_limit():
    db = _FakeDb()
    runtime = SubagentRuntime(db, max_concurrent=1)

    async def _executor(_task):
        await asyncio.sleep(0.05)
        return "ok"

    runtime.set_task_executor(_executor)
    await runtime.enqueue(
        umo="umo:1",
        subagent_name="writer_a",
        handoff_tool_name="transfer_to_writer_a",
        payload={"tool_args": {"input": "a"}},
        tool_call_id="call_a",
    )
    await runtime.enqueue(
        umo="umo:2",
        subagent_name="writer_b",
        handoff_tool_name="transfer_to_writer_b",
        payload={"tool_args": {"input": "b"}},
        tool_call_id="call_b",
    )
    processed = await runtime.process_once(batch_size=8)
    assert processed == 1
    pending = [task for task in db.tasks.values() if task.status == "pending"]
    assert len(pending) == 1


@pytest.mark.asyncio
async def test_runtime_canceled_task_is_not_claimed():
    db = _FakeDb()
    runtime = SubagentRuntime(db)

    async def _executor(_task):
        return "ok"

    runtime.set_task_executor(_executor)
    task_id = await runtime.enqueue(
        umo="webchat:FriendMessage:webchat!u!s",
        subagent_name="writer",
        handoff_tool_name="transfer_to_writer",
        payload={"tool_args": {"input": "x"}},
        tool_call_id="call_cancel",
    )
    canceled = await runtime.cancel_task(task_id)
    assert canceled is True
    processed = await runtime.process_once(batch_size=8)
    assert processed == 0
    assert db.tasks[task_id].status == "canceled"


@pytest.mark.asyncio
async def test_runtime_recovers_running_tasks_after_restart():
    db = _FakeDb()
    runtime = SubagentRuntime(db)

    async def _executor(_task):
        return "ok"

    runtime.set_task_executor(_executor)
    task_id = await runtime.enqueue(
        umo="webchat:FriendMessage:webchat!u!s",
        subagent_name="writer",
        handoff_tool_name="transfer_to_writer",
        payload={"tool_args": {"input": "recover"}},
        tool_call_id="call_recover",
    )
    running = await db.mark_subagent_task_running(task_id)
    assert running is not None
    assert db.tasks[task_id].status == "running"
    # Simulate a stale task by setting updated_at beyond the recovery threshold.
    db.tasks[task_id].updated_at = datetime.now(timezone.utc) - timedelta(minutes=10)

    restarted_runtime = SubagentRuntime(db)
    restarted_runtime.set_task_executor(_executor)
    processed = await restarted_runtime.process_once(batch_size=8)
    assert processed == 1
    assert db.tasks[task_id].status == "succeeded"
    assert db.tasks[task_id].attempt == 2


class _RetryableClassifier(ErrorClassifier):
    def classify(self, exc: Exception) -> str:
        _ = exc
        return "retryable"


@pytest.mark.asyncio
async def test_runtime_retryable_classification_follows_retry_branch():
    db = _FakeDb()
    runtime = SubagentRuntime(
        db,
        base_delay_ms=100,
        max_delay_ms=100,
        max_attempts=2,
        error_classifier=_RetryableClassifier(),
    )

    async def _executor(_task):
        raise RuntimeError("retryable")

    runtime.set_task_executor(_executor)
    task_id = await runtime.enqueue(
        umo="webchat:FriendMessage:webchat!u!s",
        subagent_name="writer",
        handoff_tool_name="transfer_to_writer",
        payload={"tool_args": {"input": "x"}},
        tool_call_id="call_retryable",
    )
    processed = await runtime.process_once(batch_size=8)
    assert processed == 1
    assert db.tasks[task_id].status == "retrying"


@pytest.mark.asyncio
async def test_runtime_manual_retry_reschedules_failed_task():
    db = _FakeDb()
    runtime = SubagentRuntime(db, max_attempts=3)
    calls = {"n": 0}

    async def _executor(_task):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("fatal")
        return "done"

    runtime.set_task_executor(_executor)
    task_id = await runtime.enqueue(
        umo="webchat:FriendMessage:webchat!u!s",
        subagent_name="writer",
        handoff_tool_name="transfer_to_writer",
        payload={"tool_args": {"input": "manual-retry"}},
        tool_call_id="call_manual_retry",
    )

    processed = await runtime.process_once(batch_size=8)
    assert processed == 1
    assert db.tasks[task_id].status == "failed"

    retried = await runtime.retry_task(task_id)
    assert retried is True
    assert db.tasks[task_id].status == "retrying"
    assert db.tasks[task_id].attempt == 0

    db.tasks[task_id].next_run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    processed = await runtime.process_once(batch_size=8)
    assert processed == 1
    assert db.tasks[task_id].status == "succeeded"
    assert calls["n"] == 2


class _RaceDb(_FakeDb):
    def __init__(self):
        super().__init__()
        self._race_injected = False

    async def create_subagent_task(self, **kwargs) -> SubagentTask:
        if not self._race_injected:
            self._race_injected = True
            now = datetime.now(timezone.utc)
            winner = SubagentTask(
                task_id="winner_task",
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
            self.tasks[winner.task_id] = winner
            raise IntegrityError(
                statement="INSERT INTO subagent_tasks ...",
                params={},
                orig=Exception(
                    "UNIQUE constraint failed: subagent_tasks.idempotency_key"
                ),
            )
        return await super().create_subagent_task(**kwargs)


@pytest.mark.asyncio
async def test_runtime_enqueue_handles_idempotency_race_and_returns_existing_task():
    db = _RaceDb()
    runtime = SubagentRuntime(db)

    task_id = await runtime.enqueue(
        umo="webchat:FriendMessage:webchat!u!s",
        subagent_name="writer",
        handoff_tool_name="transfer_to_writer",
        payload={"tool_args": {"input": "race"}},
        tool_call_id="call_race",
    )

    assert task_id == "winner_task"


@pytest.mark.asyncio
async def test_runtime_process_once_logs_when_executor_is_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    db = _FakeDb()
    runtime = SubagentRuntime(db)
    warnings: list[str] = []

    def _fake_warning(message: str, *args) -> None:
        warnings.append(message % args if args else message)

    monkeypatch.setattr("astrbot.core.subagent.runtime.logger.warning", _fake_warning)
    processed = await runtime.process_once(batch_size=8)

    assert processed == 0
    assert any("task_executor is not set" in item for item in warnings)
