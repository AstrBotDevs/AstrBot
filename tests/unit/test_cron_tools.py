"""Tests for cron tool metadata."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.tools.cron_tools import FutureTaskTool


def _context(
    cron_mgr,
    *,
    umo: str = "test:group:shared",
    sender_id: str = "user-1",
    tz_name: str | None = "Asia/Shanghai",
):
    return SimpleNamespace(
        context=SimpleNamespace(
            context=SimpleNamespace(
                cron_manager=cron_mgr,
                get_config=lambda umo=None: {"timezone": tz_name},
            ),
            event=SimpleNamespace(
                unified_msg_origin=umo,
                get_sender_id=lambda: sender_id,
            ),
        )
    )


def _job(job_id: str, *, umo: str = "test:group:shared", sender_id: str = "user-1"):
    return SimpleNamespace(
        job_id=job_id,
        name=f"name-{job_id}",
        job_type="active_agent",
        run_once=False,
        cron_expression="0 8 * * *",
        enabled=True,
        next_run_time=None,
        payload={
            "session": umo,
            "sender_id": sender_id,
            "note": f"note-{job_id}",
            "origin": "tool",
        },
    )


def test_future_task_schema_has_action_and_create_cron_guidance():
    """The merged tool should expose action routing and unambiguous cron guidance."""
    tool = FutureTaskTool()

    assert tool.name == "future_task"
    assert tool.parameters["required"] == ["action"]
    assert tool.parameters["properties"]["action"]["enum"] == [
        "create",
        "edit",
        "delete",
        "list",
    ]

    description = tool.parameters["properties"]["cron_expression"]["description"]

    assert "mon-fri" in description
    assert "sat,sun" in description
    assert "1-5" in description
    assert "Prefer named weekdays" in description


def test_future_task_schema_has_no_job_type_and_delete_job_id():
    """The merged tool should remove job_type and document delete requirements."""
    tool = FutureTaskTool()

    assert "job_type" not in tool.parameters["properties"]
    action_description = tool.parameters["properties"]["action"]["description"]
    job_id_description = tool.parameters["properties"]["job_id"]["description"]

    assert "'edit' requires 'job_id'" in action_description
    assert "Required for 'delete' and 'edit'" in job_id_description


@pytest.mark.asyncio
async def test_future_task_edit_requires_job_id():
    """Edit mode should require job_id."""
    tool = FutureTaskTool()
    cron_mgr = SimpleNamespace()
    context = SimpleNamespace(
        context=SimpleNamespace(
            context=SimpleNamespace(cron_manager=cron_mgr),
            event=SimpleNamespace(
                unified_msg_origin="test:private:session",
                get_sender_id=lambda: "user-1",
            ),
        )
    )

    result = await tool.call(context, action="edit")

    assert result == "error: job_id is required when action=edit."


@pytest.mark.asyncio
async def test_future_task_edit_updates_existing_job():
    """Edit mode should update note and one-time scheduling fields."""
    tool = FutureTaskTool()
    existing_job = SimpleNamespace(
        job_id="job-1",
        name="old name",
        job_type="active_agent",
        run_once=False,
        cron_expression="0 8 * * *",
        payload={
            "session": "test:private:session",
            "sender_id": "user-1",
            "note": "old note",
            "origin": "tool",
        },
    )
    updated_job = SimpleNamespace(
        job_id="job-1",
        name="new name",
        run_once=True,
        cron_expression=None,
        next_run_time=None,
    )
    cron_mgr = SimpleNamespace(
        db=SimpleNamespace(get_cron_job=AsyncMock(return_value=existing_job)),
        update_job=AsyncMock(return_value=updated_job),
    )
    context = SimpleNamespace(
        context=SimpleNamespace(
            context=SimpleNamespace(cron_manager=cron_mgr),
            event=SimpleNamespace(
                unified_msg_origin="test:private:session",
                get_sender_id=lambda: "user-1",
            ),
        )
    )

    result = await tool.call(
        context,
        action="edit",
        job_id="job-1",
        name="new name",
        note="new note",
        run_once=True,
        run_at="2026-02-02T08:00:00+08:00",
    )

    cron_mgr.update_job.assert_awaited_once_with(
        "job-1",
        name="new name",
        description="new note",
        run_once=True,
        cron_expression=None,
        payload={
            "session": "test:private:session",
            "sender_id": "user-1",
            "note": "new note",
            "origin": "tool",
            "run_at": "2026-02-02T08:00:00+08:00",
        },
    )
    assert result == "Updated future task job-1 (new name)."


@pytest.mark.asyncio
async def test_future_task_edit_rejects_same_umo_different_sender():
    """Same-session users should not edit another sender's task."""
    tool = FutureTaskTool()
    existing_job = _job("job-1", sender_id="admin-user")
    cron_mgr = SimpleNamespace(
        db=SimpleNamespace(get_cron_job=AsyncMock(return_value=existing_job)),
        update_job=AsyncMock(),
    )

    result = await tool.call(
        _context(cron_mgr, sender_id="attacker-user"),
        action="edit",
        job_id="job-1",
        note="attacker note",
    )

    assert result == "error: you can only edit your own future tasks."
    cron_mgr.update_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_future_task_delete_rejects_same_umo_different_sender():
    """Same-session users should not delete another sender's task."""
    tool = FutureTaskTool()
    existing_job = _job("job-1", sender_id="admin-user")
    cron_mgr = SimpleNamespace(
        db=SimpleNamespace(get_cron_job=AsyncMock(return_value=existing_job)),
        delete_job=AsyncMock(),
    )

    result = await tool.call(
        _context(cron_mgr, sender_id="attacker-user"),
        action="delete",
        job_id="job-1",
    )

    assert result == "error: you can only delete your own future tasks."
    cron_mgr.delete_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_future_task_list_filters_by_umo_and_sender():
    """List mode should show only tasks owned by the current sender."""
    tool = FutureTaskTool()
    own_job = _job("own-job", sender_id="user-1")
    same_umo_other_sender = _job("other-sender-job", sender_id="user-2")
    different_umo_same_sender = _job(
        "other-umo-job",
        umo="test:group:other",
        sender_id="user-1",
    )
    cron_mgr = SimpleNamespace(
        list_jobs=AsyncMock(
            return_value=[own_job, same_umo_other_sender, different_umo_same_sender]
        )
    )

    result = await tool.call(
        _context(cron_mgr, sender_id="user-1"),
        action="list",
    )

    assert "own-job" in result
    assert "other-sender-job" not in result
    assert "other-umo-job" not in result


@pytest.mark.asyncio
async def test_future_task_list_localizes_naive_utc_next_run_time_to_shanghai():
    """List mode should treat a naive DB next_run_time as UTC and convert it.

    SQLite has no tz-aware datetime column, so the real DB layer always
    returns next_run_time without tzinfo even though the stored instant is
    UTC. This must not be misread as "already in the display timezone".
    """
    tool = FutureTaskTool()
    job = _job("job-1")
    job.next_run_time = datetime(2026, 1, 1, 0, 0)
    cron_mgr = SimpleNamespace(list_jobs=AsyncMock(return_value=[job]))

    result = await tool.call(
        _context(cron_mgr, tz_name="Asia/Shanghai"),
        action="list",
    )

    assert "2026-01-01 08:00:00+08:00" in result


@pytest.mark.asyncio
async def test_future_task_list_localizes_naive_utc_next_run_time_to_new_york():
    """List mode should honor a differently configured IANA timezone."""
    tool = FutureTaskTool()
    job = _job("job-1")
    job.next_run_time = datetime(2026, 1, 1, 0, 0)
    cron_mgr = SimpleNamespace(list_jobs=AsyncMock(return_value=[job]))

    result = await tool.call(
        _context(cron_mgr, tz_name="America/New_York"),
        action="list",
    )

    assert "2025-12-31 19:00:00-05:00" in result


@pytest.mark.asyncio
async def test_future_task_list_falls_back_when_timezone_invalid():
    """An invalid configured timezone should not crash the tool."""
    tool = FutureTaskTool()
    job = _job("job-1")
    job.next_run_time = datetime(2026, 1, 1, 0, 0)
    cron_mgr = SimpleNamespace(list_jobs=AsyncMock(return_value=[job]))

    result = await tool.call(
        _context(cron_mgr, tz_name="Not/AZone"),
        action="list",
    )

    assert "job-1" in result


@pytest.mark.asyncio
async def test_future_task_create_passes_config_timezone_to_scheduler():
    """Create mode should forward the configured timezone so recurring jobs don't
    silently use the server's local timezone."""
    tool = FutureTaskTool()
    created_job = SimpleNamespace(
        job_id="job-1",
        name="active_agent_task",
        next_run_time=None,
    )
    cron_mgr = SimpleNamespace(
        add_active_job=AsyncMock(return_value=created_job),
        get_next_run_time=MagicMock(return_value=datetime(2026, 1, 1, 0, 0)),
    )

    result = await tool.call(
        _context(cron_mgr, tz_name="Asia/Shanghai"),
        action="create",
        cron_expression="0 8 * * *",
        note="daily reminder",
    )

    cron_mgr.add_active_job.assert_awaited_once()
    _, call_kwargs = cron_mgr.add_active_job.call_args
    assert call_kwargs["timezone"] == "Asia/Shanghai"
    cron_mgr.get_next_run_time.assert_called_once_with("job-1")
    assert "2026-01-01 08:00:00+08:00" in result


@pytest.mark.asyncio
async def test_future_task_create_localizes_next_run_for_new_york():
    """Create mode's reported next-run time should reflect a non-Shanghai tz too."""
    tool = FutureTaskTool()
    created_job = SimpleNamespace(
        job_id="job-1",
        name="active_agent_task",
        next_run_time=None,
    )
    cron_mgr = SimpleNamespace(
        add_active_job=AsyncMock(return_value=created_job),
        get_next_run_time=MagicMock(return_value=datetime(2026, 1, 1, 0, 0)),
    )

    result = await tool.call(
        _context(cron_mgr, tz_name="America/New_York"),
        action="create",
        cron_expression="0 8 * * *",
        note="daily reminder",
    )

    _, call_kwargs = cron_mgr.add_active_job.call_args
    assert call_kwargs["timezone"] == "America/New_York"
    assert "2025-12-31 19:00:00-05:00" in result


@pytest.mark.asyncio
async def test_future_task_create_falls_back_to_run_at_when_scheduler_has_no_time():
    """If the scheduler has not registered a next-run time yet (e.g. run_once
    scheduled far in the future), create mode should fall back to displaying
    the user-supplied run_at instead of the literal string 'None'."""
    tool = FutureTaskTool()
    created_job = SimpleNamespace(
        job_id="job-1",
        name="active_agent_task",
        next_run_time=None,
    )
    cron_mgr = SimpleNamespace(
        add_active_job=AsyncMock(return_value=created_job),
        get_next_run_time=MagicMock(return_value=None),
    )

    result = await tool.call(
        _context(cron_mgr, tz_name="Asia/Shanghai"),
        action="create",
        run_once=True,
        run_at="2026-02-02T08:00:00+08:00",
        note="one-time reminder",
    )

    assert "2026-02-02 08:00:00+08:00" in result
