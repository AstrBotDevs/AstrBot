import asyncio
import os
import threading
from collections import defaultdict
from copy import deepcopy
from typing import Any, Literal, TypeVar, overload

from apscheduler.schedulers.background import BackgroundScheduler

from astrbot import logger
from astrbot.core.db.po import Preference
from astrbot.core.db.protocols import PreferenceStore

from .astrbot_path import get_astrbot_data_path

_VT = TypeVar("_VT")
_MISSING = object()
_WriteAction = Literal["put", "remove", "clear"]
_WriteOperation = tuple[
    _WriteAction,
    str,
    str,
    str | None,
    Any,
    asyncio.Future[None],
]


class SharedPreferences:
    """Persist scoped preferences through a runtime-owned async write queue."""

    def __init__(self, db_helper: PreferenceStore, json_storage_path=None) -> None:
        if json_storage_path is None:
            json_storage_path = os.path.join(
                get_astrbot_data_path(),
                "shared_preferences.json",
            )
        self.path = json_storage_path
        self.db_helper = db_helper
        self.temporary_cache: dict[str, dict[str, Any]] = defaultdict(dict)
        """Automatically cleared every 24 hours."""

        self._cache: dict[tuple[str, str, str], Any] = {}
        """Write overlay for read-after-write visibility; not a full table mirror."""
        self._cache_lock = threading.RLock()
        self._cache_initialized = False
        self._initialize_lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._write_queue: asyncio.Queue[_WriteOperation] | None = None
        self._writer_task: asyncio.Task[None] | None = None
        self._terminated = False

        self._scheduler = BackgroundScheduler()
        self._scheduler.add_job(
            self._clear_temporary_cache, "interval", hours=24, id="clear_sp_temp_cache"
        )
        self._scheduler.start()

    def _clear_temporary_cache(self) -> None:
        self.temporary_cache.clear()

    async def initialize(self) -> None:
        """Bind persistence to the active event loop without preloading preferences.

        The preferences table can be arbitrarily large, so reads miss the write
        overlay and fall back to point queries instead of a startup full scan.

        Raises:
            RuntimeError: If another running event loop already owns the store.
        """
        loop = asyncio.get_running_loop()
        async with self._initialize_lock:
            if self._cache_initialized:
                if self._loop is loop:
                    return
                if self._loop is not None and self._loop.is_running():
                    raise RuntimeError(
                        "SharedPreferences is already bound to another running event loop."
                    )
                self._loop = loop
                self._write_queue = asyncio.Queue()
                self._writer_task = None
                return

            with self._cache_lock:
                self._cache_initialized = True
            self._loop = loop
            self._write_queue = asyncio.Queue()

    def _apply_cache_operation(self, operation: _WriteOperation) -> None:
        """Apply a queued mutation to the in-memory write overlay."""
        action, scope, scope_id, key, value, _ = operation
        with self._cache_lock:
            if action == "put" and key is not None:
                self._cache[(scope, scope_id, key)] = deepcopy(value)
            elif action == "remove" and key is not None:
                self._cache.pop((scope, scope_id, key), None)
            elif action == "clear":
                stale_keys = [
                    cache_key
                    for cache_key in self._cache
                    if cache_key[:2] == (scope, scope_id)
                ]
                for cache_key in stale_keys:
                    self._cache.pop(cache_key, None)

    def _submit_write(self, operation: _WriteOperation) -> None:
        """Update the cache and enqueue its matching persistent mutation."""
        queue = self._write_queue
        loop = self._loop
        if queue is None or loop is None:
            raise RuntimeError("SharedPreferences has not been initialized.")
        if asyncio.get_running_loop() is not loop:
            raise RuntimeError(
                "SharedPreferences writes must run on their owning event loop."
            )

        self._apply_cache_operation(operation)
        queue.put_nowait(operation)
        if self._writer_task is None or self._writer_task.done():
            self._writer_task = loop.create_task(
                self._drain_write_queue(),
                name="shared_preferences_writer",
            )

    async def _drain_write_queue(self) -> None:
        """Persist queued preference mutations in FIFO order."""
        queue = self._write_queue
        if queue is None:
            return

        while True:
            try:
                operation = queue.get_nowait()
            except asyncio.QueueEmpty:
                return

            action, scope, scope_id, key, value, completion = operation
            try:
                if action == "put" and key is not None:
                    await self.db_helper.insert_preference_or_update(
                        scope, scope_id, key, {"val": value}
                    )
                elif action == "remove" and key is not None:
                    await self.db_helper.remove_preference(scope, scope_id, key)
                elif action == "clear":
                    await self.db_helper.clear_preferences(scope, scope_id)
                else:
                    raise ValueError(f"Unknown preference write operation: {action}")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "Failed to persist shared preference operation %s for %s/%s: %s",
                    action,
                    scope,
                    scope_id,
                    exc,
                    exc_info=True,
                )
                if not completion.done():
                    completion.set_exception(exc)
            else:
                if not completion.done():
                    completion.set_result(None)
            finally:
                queue.task_done()

    async def flush(self) -> None:
        """Wait for all currently queued writes to finish."""
        await self.initialize()
        queue = self._write_queue
        if queue is None:
            return
        if asyncio.get_running_loop() is not self._loop:
            raise RuntimeError(
                "SharedPreferences writes must be flushed on their owning event loop."
            )
        await queue.join()
        if self._writer_task is not None:
            await self._writer_task

    async def terminate(self) -> None:
        """Flush preference writes and stop the runtime-owned cache scheduler."""
        if self._terminated:
            return
        if self._cache_initialized:
            await self.flush()
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        self._terminated = True

    async def get_async(
        self,
        scope: str,
        scope_id: str,
        key: str,
        default: _VT = None,
    ) -> _VT:
        """Get one scoped preference from the write overlay or a point query."""
        await self.initialize()
        with self._cache_lock:
            value = self._cache.get((scope, scope_id, key), _MISSING)
            if value is not _MISSING:
                return deepcopy(value)
        preference = await self.db_helper.get_preference(scope, scope_id, key)
        if preference is None:
            return default
        stored = preference.value
        if not isinstance(stored, dict) or "val" not in stored:
            return default
        return deepcopy(stored["val"])

    async def range_get_async(
        self,
        scope: str,
        scope_id: str | None = None,
        key: str | None = None,
    ) -> list[Preference]:
        """Get preferences matching a scope, optional scope ID, and optional key."""
        await self.flush()
        return await self.db_helper.get_preferences(scope, scope_id, key)

    @overload
    async def session_get(self, umo: str, key: str, default: _VT = None) -> _VT: ...

    @overload
    async def session_get(
        self, umo: None, key: str, default: Any = None
    ) -> list[Preference]: ...

    @overload
    async def session_get(
        self, umo: str, key: None, default: Any = None
    ) -> list[Preference]: ...

    @overload
    async def session_get(
        self, umo: None, key: None, default: Any = None
    ) -> list[Preference]: ...

    async def session_get(
        self,
        umo: str | None,
        key: str | None = None,
        default: _VT = None,
    ) -> _VT | list[Preference]:
        """Get one session preference or list matching session preferences."""
        if umo is None or key is None:
            return await self.range_get_async("umo", umo, key)
        return await self.get_async("umo", umo, key, default)

    @overload
    async def global_get(self, key: None, default: Any = None) -> list[Preference]: ...

    @overload
    async def global_get(self, key: str, default: _VT = None) -> _VT: ...

    async def global_get(
        self, key: str | None, default: _VT = None
    ) -> _VT | list[Preference]:
        """Get one global preference or list global preferences."""
        if key is None:
            return await self.range_get_async("global", "global", key)
        return await self.get_async("global", "global", key, default)

    async def put_async(self, scope: str, scope_id: str, key: str, value: Any) -> None:
        """Store one preference and wait for durable persistence."""
        await self.initialize()
        completion = asyncio.get_running_loop().create_future()
        self._submit_write(("put", scope, scope_id, key, deepcopy(value), completion))
        await completion

    async def session_put(self, umo: str, key: str, value: Any) -> None:
        await self.put_async("umo", umo, key, value)

    async def global_put(self, key: str, value: Any) -> None:
        await self.put_async("global", "global", key, value)

    async def remove_async(self, scope: str, scope_id: str, key: str) -> None:
        """Remove one preference and wait for durable persistence."""
        await self.initialize()
        completion = asyncio.get_running_loop().create_future()
        self._submit_write(("remove", scope, scope_id, key, None, completion))
        await completion

    async def session_remove(self, umo: str, key: str) -> None:
        await self.remove_async("umo", umo, key)

    async def global_remove(self, key: str) -> None:
        await self.remove_async("global", "global", key)

    async def clear_async(self, scope: str, scope_id: str) -> None:
        """Clear one preference scope and wait for durable persistence."""
        await self.initialize()
        completion = asyncio.get_running_loop().create_future()
        self._submit_write(("clear", scope, scope_id, None, None, completion))
        await completion
