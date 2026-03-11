from __future__ import annotations

import asyncio
import math
from typing import TYPE_CHECKING

from astrbot import logger

from .constants import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_ERROR_RETRY_MAX_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    MIN_BATCH_SIZE,
    MIN_POLL_INTERVAL,
)
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
        error_retry_max_interval: float = DEFAULT_ERROR_RETRY_MAX_INTERVAL,
    ) -> None:
        self._runtime = runtime
        self._poll_interval = max(MIN_POLL_INTERVAL, float(poll_interval))
        self._batch_size = max(MIN_BATCH_SIZE, int(batch_size))
        self._error_retry_max_interval = max(
            self._poll_interval,
            float(error_retry_max_interval),
        )
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    def start(self) -> asyncio.Task[None]:
        if self._task and not self._task.done():
            return self._task
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop(), name="subagent_worker")
        return self._task

    def _compute_error_backoff(self, consecutive_errors: int) -> float:
        base = max(self._poll_interval, MIN_POLL_INTERVAL)
        capped_max = max(base, self._error_retry_max_interval)
        exponent = max(0, consecutive_errors - 1)
        return min(base * math.pow(2, exponent), capped_max)

    def configure(
        self,
        *,
        poll_interval: float,
        batch_size: int,
        error_retry_max_interval: float,
    ) -> None:
        self._poll_interval = max(MIN_POLL_INTERVAL, float(poll_interval))
        self._batch_size = max(MIN_BATCH_SIZE, int(batch_size))
        self._error_retry_max_interval = max(
            self._poll_interval,
            float(error_retry_max_interval),
        )

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
        consecutive_errors = 0
        while not self._stop_event.is_set():
            try:
                processed = await self._runtime.process_once(
                    batch_size=self._batch_size
                )
                consecutive_errors = 0
                if processed <= 0:
                    await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                consecutive_errors += 1
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
                await asyncio.sleep(self._compute_error_backoff(consecutive_errors))
        logger.info("Subagent worker stopped.")
