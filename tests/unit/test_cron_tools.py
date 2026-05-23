"""Tests for cron tool metadata."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.tools.cron_tools import (
    CreateActiveCronTool,
    DeleteCronJobTool,
    ListCronJobsTool,
)


def _make_context(cron_manager: object | None = None) -> ContextWrapper:
    return ContextWrapper(
        context=SimpleNamespace(
            context=SimpleNamespace(cron_manager=cron_manager),
            event=SimpleNamespace(
                unified_msg_origin="test:private:session",
                get_sender_id=lambda: "user-1",
            ),
        )
    )


def test_create_future_task_tool_has_correct_name():
    """The create tool should have correct name."""
    tool = CreateActiveCronTool()

    assert tool.name == "create_future_task"


def test_create_future_task_tool_requires_note():
    """The create tool should require note field."""
    tool = CreateActiveCronTool()

    assert "note" in tool.parameters["required"]


def test_create_future_task_tool_has_cron_guidance():
    """The create tool should have cron guidance in description."""
    tool = CreateActiveCronTool()

    description = tool.parameters["properties"]["cron_expression"]["description"]

    assert "mon-fri" in description
    assert "sat,sun" in description


def test_delete_future_task_tool_has_job_id_required():
    """The delete tool should require job_id."""
    tool = DeleteCronJobTool()

    assert tool.name == "delete_future_task"
    assert "job_id" in tool.parameters["required"]


def test_list_future_tasks_tool_name():
    """The list tool should have correct name."""
    tool = ListCronJobsTool()

    assert tool.name == "list_future_tasks"


@pytest.mark.asyncio
async def test_delete_future_task_requires_job_id():
    """Delete should require job_id."""
    tool = DeleteCronJobTool()
    context = _make_context(SimpleNamespace())

    result = await tool.call(context, job_id=None)

    assert "job_id is required" in result


@pytest.mark.asyncio
async def test_delete_future_task_verifies_ownership():
    """Delete should verify the job belongs to current umo."""
    tool = DeleteCronJobTool()
    cron_mgr = SimpleNamespace(
        db=SimpleNamespace(
            get_cron_job=AsyncMock(
                return_value=SimpleNamespace(
                    job_id="job-1",
                    name="test job",
                    payload={"session": "other:private:session"},
                )
            )
        ),
    )
    context = _make_context(cron_mgr)

    result = await tool.call(context, job_id="job-1")

    assert "only delete" in result


@pytest.mark.asyncio
async def test_delete_future_task_success():
    """Delete should successfully delete job and return message."""
    tool = DeleteCronJobTool()
    cron_mgr = SimpleNamespace(
        db=SimpleNamespace(
            get_cron_job=AsyncMock(
                return_value=SimpleNamespace(
                    job_id="job-1",
                    name="test job",
                    payload={"session": "test:private:session"},
                )
            )
        ),
        delete_job=AsyncMock(return_value=True),
    )
    context = _make_context(cron_mgr)

    result = await tool.call(context, job_id="job-1")

    cron_mgr.delete_job.assert_awaited_once_with("job-1")
    assert "Deleted cron job job-1" in result


@pytest.mark.asyncio
async def test_list_future_tasks_returns_jobs():
    """List should return formatted job list."""
    tool = ListCronJobsTool()
    cron_mgr = SimpleNamespace(
        list_jobs=AsyncMock(
            return_value=[
                SimpleNamespace(
                    job_id="job-1",
                    name="test job",
                    job_type="active_agent",
                    run_once=False,
                    enabled=True,
                    next_run_time="2026-04-16T08:00:00",
                    payload={"session": "test:private:session"},
                ),
            ]
        ),
    )
    context = _make_context(cron_mgr)

    result = await tool.call(context)

    assert "job-1" in result
    assert "test job" in result


@pytest.mark.asyncio
async def test_list_future_tasks_empty():
    """List should return message when no jobs."""
    tool = ListCronJobsTool()
    cron_mgr = SimpleNamespace(
        list_jobs=AsyncMock(return_value=[]),
    )
    context = _make_context(cron_mgr)

    result = await tool.call(context)

    assert "No cron jobs found" in result
