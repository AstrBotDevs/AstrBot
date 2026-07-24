import asyncio

import mcp
import pytest

from astrbot.core.agent.job_manager import AgentJobManager
from astrbot.core.agent.tool import ToolOutcome


async def _wait_for_terminal(
    manager: AgentJobManager, job_id: str, timeout: float = 2.0
):
    """Wait until one test job reaches a terminal state.

    Args:
        manager: Job manager under test.
        job_id: Submitted job identifier.
        timeout: Maximum test wait.

    Returns:
        The terminal job record.

    Raises:
        TimeoutError: If the job does not terminate within the test deadline.
    """

    async with asyncio.timeout(timeout):
        while True:
            job = manager.get(job_id)
            if job and job.status in manager.TERMINAL_STATUSES:
                return job
            await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_job_manager_persists_success_without_raw_arguments(tmp_path):
    manager = AgentJobManager(tmp_path / "jobs.db")

    async def runner() -> ToolOutcome:
        return ToolOutcome(
            status="success",
            result=mcp.types.CallToolResult(
                content=[mcp.types.TextContent(type="text", text="finished")]
            ),
        )

    job = await manager.submit(
        tool_name="read_document",
        requester_id="qq:10001",
        umo="group:20002",
        arguments={"secret": "must-not-be-persisted"},
        runner=runner,
    )
    completed = await _wait_for_terminal(manager, job.job_id)

    assert completed.status == "succeeded"
    assert completed.result == "finished"
    assert completed.args_hash
    assert "must-not-be-persisted" not in (tmp_path / "jobs.db").read_bytes().decode(
        "utf-8", errors="ignore"
    )


@pytest.mark.asyncio
async def test_job_manager_normalizes_empty_result_as_failure(tmp_path):
    manager = AgentJobManager(tmp_path / "jobs.db")

    async def runner() -> ToolOutcome:
        return ToolOutcome(status="empty", retryable=True)

    job = await manager.submit(
        tool_name="empty_tool",
        requester_id="qq:10001",
        umo="private:10001",
        arguments={},
        runner=runner,
    )
    completed = await _wait_for_terminal(manager, job.job_id)

    assert completed.status == "failed"
    assert completed.error_code == "empty_result"


@pytest.mark.asyncio
async def test_job_manager_cancel_is_requester_scoped(tmp_path):
    manager = AgentJobManager(tmp_path / "jobs.db")
    started = asyncio.Event()

    async def runner() -> ToolOutcome:
        started.set()
        await asyncio.Event().wait()
        return ToolOutcome(status="success")

    job = await manager.submit(
        tool_name="long_read",
        requester_id="qq:10001",
        umo="group:20002",
        arguments={},
        runner=runner,
        cancellable=True,
    )
    await asyncio.wait_for(started.wait(), timeout=1)

    denied, _ = await manager.cancel(job.job_id, requester_id="qq:other")
    cancelled, _ = await manager.cancel(job.job_id, requester_id="qq:10001")

    assert denied is False
    assert cancelled is True
    assert manager.get(job.job_id).status == "cancelled"


@pytest.mark.asyncio
async def test_job_manager_recovery_marks_inflight_job_interrupted(tmp_path):
    database_path = tmp_path / "jobs.db"
    first = AgentJobManager(database_path)
    started = asyncio.Event()

    async def runner() -> ToolOutcome:
        started.set()
        await asyncio.Event().wait()
        return ToolOutcome(status="success")

    job = await first.submit(
        tool_name="long_read",
        requester_id="qq:10001",
        umo="group:20002",
        arguments={},
        runner=runner,
    )
    await asyncio.wait_for(started.wait(), timeout=1)

    recovered = AgentJobManager(database_path)

    assert recovered.get(job.job_id).status == "interrupted"
    await first.shutdown()
