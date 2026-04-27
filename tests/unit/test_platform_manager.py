import asyncio

import pytest

from astrbot.core.platform.manager import PlatformManager, PlatformTasks


class _PlatformThatNeedsTaskStopped:
    def __init__(self) -> None:
        self.client_self_id = "dummy-client"
        self.run_task_cancelled = asyncio.Event()

    async def terminate(self) -> None:
        await asyncio.wait_for(self.run_task_cancelled.wait(), timeout=1)


async def _run_until_cancelled(cancelled: asyncio.Event) -> None:
    try:
        await asyncio.sleep(3600)
    except asyncio.CancelledError:
        cancelled.set()
        raise


@pytest.mark.asyncio
async def test_terminate_stops_platform_tasks_before_adapter_shutdown() -> None:
    manager = PlatformManager({"platform": [], "platform_settings": {}}, asyncio.Queue())
    inst = _PlatformThatNeedsTaskStopped()

    run_task = asyncio.create_task(_run_until_cancelled(inst.run_task_cancelled))
    wrapper_task = asyncio.create_task(asyncio.sleep(3600))
    manager._platform_tasks[inst.client_self_id] = PlatformTasks(
        run=run_task,
        wrapper=wrapper_task,
    )

    await asyncio.wait_for(manager._terminate_inst_and_tasks(inst), timeout=1)

    assert inst.run_task_cancelled.is_set()
    assert run_task.cancelled()
    assert wrapper_task.cancelled()
