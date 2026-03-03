from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.db.migration.migra_subagent_tasks import migrate_subagent_tasks
from astrbot.core.db.sqlite import SQLiteDatabase


class _FakeMigrationConn:
    async def run_sync(self, _fn):
        return None

    async def execute(self, _stmt):
        return SimpleNamespace(fetchone=lambda: ("subagent_tasks",))


class _FakeMigrationEngine:
    class _BeginCtx:
        async def __aenter__(self):
            return _FakeMigrationConn()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    def begin(self):
        return _FakeMigrationEngine._BeginCtx()


class _FakeMigrationDb:
    def __init__(self):
        self.marker_done = False
        self.engine = _FakeMigrationEngine()

    async def get_preference(self, _scope, _scope_id, _key):
        return self.marker_done


@pytest.mark.asyncio
async def test_subagent_migration_is_idempotent(monkeypatch: pytest.MonkeyPatch):
    db = _FakeMigrationDb()
    put_async = AsyncMock(
        side_effect=lambda *_args, **_kwargs: setattr(db, "marker_done", True)
    )
    monkeypatch.setattr(
        "astrbot.core.db.migration.migra_subagent_tasks.sp.put_async", put_async
    )

    await migrate_subagent_tasks(db)
    await migrate_subagent_tasks(db)

    put_async.assert_awaited_once()


@pytest.mark.asyncio
async def test_sqlite_subagent_task_status_transitions(tmp_path: Path):
    db_path = tmp_path / "subagent_tasks.db"
    db = SQLiteDatabase(str(db_path))
    await db.initialize()

    now = datetime.now(timezone.utc)
    task = await db.create_subagent_task(
        task_id="task_1",
        idempotency_key="idem_1",
        umo="umo:1",
        subagent_name="writer",
        handoff_tool_name="transfer_to_writer",
        payload_json='{"input":"hello"}',
        max_attempts=3,
    )
    claimed = await db.claim_due_subagent_tasks(
        now=now + timedelta(seconds=1), limit=10
    )
    assert any(row.task_id == task.task_id for row in claimed)

    running = await db.mark_subagent_task_running(task.task_id)
    assert running is not None
    assert running.status == "running"
    assert running.attempt == 1

    retried = await db.mark_subagent_task_retrying(
        task_id=task.task_id,
        next_run_at=now - timedelta(seconds=1),
        error_class="transient",
        last_error="timeout",
    )
    assert retried is True

    running_again = await db.mark_subagent_task_running(task.task_id)
    assert running_again is not None
    assert running_again.status == "running"
    assert running_again.attempt == 2

    succeeded = await db.mark_subagent_task_succeeded(task.task_id, result_text="done")
    assert succeeded is True

    failed_task = await db.create_subagent_task(
        task_id="task_2",
        idempotency_key="idem_2",
        umo="umo:2",
        subagent_name="writer",
        handoff_tool_name="transfer_to_writer",
        payload_json='{"input":"boom"}',
        max_attempts=3,
    )
    running_failed = await db.mark_subagent_task_running(failed_task.task_id)
    assert running_failed is not None
    failed = await db.mark_subagent_task_failed(
        task_id=failed_task.task_id,
        error_class="fatal",
        last_error="bad input",
    )
    assert failed is True
    retried_failed = await db.reschedule_subagent_task(
        task_id=failed_task.task_id,
        next_run_at=now - timedelta(seconds=1),
        error_class="manual",
        last_error="manual retry requested",
    )
    assert retried_failed is True
    retried_rows = await db.list_subagent_tasks(status="retrying", limit=10)
    retried_row = next(row for row in retried_rows if row.task_id == failed_task.task_id)
    assert retried_row.attempt == 0
    running_failed_retry = await db.mark_subagent_task_running(failed_task.task_id)
    assert running_failed_retry is not None
    assert running_failed_retry.attempt == 1
    succeeded_after_retry = await db.mark_subagent_task_succeeded(
        failed_task.task_id, result_text="done_after_manual_retry"
    )
    assert succeeded_after_retry is True

    canceled_task = await db.create_subagent_task(
        task_id="task_3",
        idempotency_key="idem_3",
        umo="umo:3",
        subagent_name="writer",
        handoff_tool_name="transfer_to_writer",
        payload_json='{"input":"cancel"}',
        max_attempts=3,
    )
    canceled = await db.cancel_subagent_task(canceled_task.task_id)
    assert canceled is True

    canceled_running_task = await db.create_subagent_task(
        task_id="task_4",
        idempotency_key="idem_4",
        umo="umo:4",
        subagent_name="writer",
        handoff_tool_name="transfer_to_writer",
        payload_json='{"input":"cancel_running"}',
        max_attempts=3,
    )
    running_canceled = await db.mark_subagent_task_running(canceled_running_task.task_id)
    assert running_canceled is not None
    canceled_running = await db.cancel_subagent_task(canceled_running_task.task_id)
    assert canceled_running is True
    failed_after_cancel = await db.mark_subagent_task_failed(
        task_id=canceled_running_task.task_id,
        error_class="fatal",
        last_error="should_not_override_cancel",
    )
    assert failed_after_cancel is False

    succeeded_rows = await db.list_subagent_tasks(status="succeeded", limit=10)
    failed_rows = await db.list_subagent_tasks(status="failed", limit=10)
    canceled_rows = await db.list_subagent_tasks(status="canceled", limit=10)
    assert any(row.task_id == "task_1" for row in succeeded_rows)
    assert not any(row.task_id == "task_2" for row in failed_rows)
    assert any(row.task_id == "task_2" for row in succeeded_rows)
    assert any(row.task_id == "task_3" for row in canceled_rows)
    assert any(row.task_id == "task_4" for row in canceled_rows)
