from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from astrbot import logger

from .constants import DEFAULT_BATCH_SIZE, DEFAULT_POLL_INTERVAL
from .runtime import SubagentRuntime

if TYPE_CHECKING:
    pass


class SubagentWorker:
    def __init__(
        self,
        runtime: SubagentRuntime,
        *,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        self._runtime = runtime
        self._poll_interval = max(0.1, float(poll_interval))
        self._batch_size = max(1, int(batch_size))
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    def start(self) -> asyncio.Task[None]:
        if self._task and not self._task.done():
            return self._task
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop(), name="subagent_worker")
        return self._task

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run_loop(self) -> None:
        logger.info("Subagent worker started.")
        while not self._stop_event.is_set():
            try:
                processed = await self._runtime.process_once(
                    batch_size=self._batch_size
                )
                if processed <= 0:
                    await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                exc_type = type(exc).__name__
                exc_module = type(exc).__module__
                full_exc_name = (
                    exc_type if exc_module == "builtins" else f"{exc_module}.{exc_type}"
                )
                logger.error(
                    "Subagent worker loop error (type=%s): %s",
                    full_exc_name,
                    exc,
                    exc_info=True,
                )
                await asyncio.sleep(self._poll_interval)
        logger.info("Subagent worker stopped.")
