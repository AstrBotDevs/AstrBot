"""Structured instance-scoped background task ownership."""

from __future__ import annotations

import asyncio
import contextvars
import logging
from collections.abc import Coroutine
from typing import Any, TypeVar

from .errors import AstrBotSDKError

_T = TypeVar("_T")
_logger = logging.getLogger("astrbot_sdk.tasks")


class TaskGroup:
    """Own plugin background tasks and local completion writes across shutdown."""

    def __init__(self) -> None:
        self._closing = False
        self._cancellable: set[asyncio.Task[Any]] = set()
        self._committed: set[asyncio.Task[Any]] = set()
        self._failure: str | None = None

    @property
    def is_shutdown(self) -> bool:
        """Whether shutdown has started."""
        return self._closing

    def spawn(self, name: str, coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        """Spawn a background task automatically cancelled when the plugin shuts down.

        Args:
            name: Diagnostic task label.
            coro: Coroutine to run.

        Returns:
            Created asyncio Task.

        Raises:
            AstrBotSDKError: The plugin is already shutting down.
        """
        if self._closing:
            coro.close()
            raise AstrBotSDKError("plugin is stopping; background task rejected")
        ctx_copy = contextvars.copy_context()

        def _create_detached() -> asyncio.Task[Any]:
            from .context import (
                _ACTIVE_INVOCATION_CTX,
                _AMBIENT_CALL_ID,
                _AMBIENT_EVENT,
                _AMBIENT_UMO,
            )

            _ACTIVE_INVOCATION_CTX.set(None)
            _AMBIENT_CALL_ID.set(None)
            _AMBIENT_EVENT.set(None)
            _AMBIENT_UMO.set(None)
            return asyncio.create_task(coro, name=name)

        task: asyncio.Task[Any] = ctx_copy.run(_create_detached)
        self._cancellable.add(task)

        def _done(done_task: asyncio.Task[Any]) -> None:
            self._cancellable.discard(done_task)
            if not done_task.cancelled():
                exc = done_task.exception()
                if exc is not None:
                    _logger.error("background task %s failed: %s", name, exc)
                    self._failure = f"task {name} failed: {exc}"

        task.add_done_callback(_done)
        return task

    async def run_to_completion(
        self,
        name: str,
        coro: Coroutine[Any, Any, _T],
    ) -> _T | None:
        """Run a local write/commit task immune to caller cancellation until shutdown.

        Args:
            name: Diagnostic task label.
            coro: Coroutine to finish cleanly.

        Returns:
            Coroutine result, or None if shutdown already began.
        """
        if self._closing:
            coro.close()
            return None
        task: asyncio.Task[_T] = asyncio.create_task(coro, name=name)
        self._committed.add(task)
        task.add_done_callback(lambda t: self._committed.discard(t))
        return await asyncio.shield(task)

    def check_health(self) -> None:
        """Raise if an uncaught background task failure was recorded."""
        if self._failure is not None:
            raise AstrBotSDKError(self._failure)

    async def shutdown(self) -> None:
        """Cancel cancellable tasks and wait for committed tasks to drain."""
        self._closing = True
        for task in list(self._cancellable):
            if not task.done():
                task.cancel()
        pending = [*self._cancellable, *self._committed]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self._cancellable.clear()
        self._committed.clear()
