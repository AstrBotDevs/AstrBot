import asyncio
import os
import threading
from collections import defaultdict
from copy import deepcopy
from typing import Any, TypeVar, overload

from apscheduler.schedulers.background import BackgroundScheduler
from deprecated import deprecated

from astrbot import logger
from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import Preference

from .astrbot_path import get_astrbot_data_path

_VT = TypeVar("_VT")
_MISSING = object()
_WriteOperation = tuple[
    str,
    str,
    str,
    str | None,
    Any,
    asyncio.Future[None] | None,
]


class SharedPreferences:
    def __init__(self, db_helper: BaseDatabase, json_storage_path=None) -> None:
        if json_storage_path is None:
            json_storage_path = os.path.join(
                get_astrbot_data_path(),
                "shared_preferences.json",
            )
        self.path = json_storage_path
        self.db_helper = db_helper
        self.temporary_cache: dict[str, dict[str, Any]] = defaultdict(dict)
        """automatically clear per 24 hours. Might be helpful in some cases XD"""

        # In-memory overlay of preferences written through this process. It gives
        # read-after-write visibility for both sync and async APIs while writes
        # are asynchronously persisted through the FIFO write queue.
        #
        # This is intentionally NOT a full mirror of the preferences table: the
        # table can hold gigabytes of plugin KV data, so preloading it at startup
        # (as PR #9649 did) can OOM the process. Reads that miss the overlay fall
        # back to point queries against the database: async reads await the async
        # engine, while deprecated synchronous reads use a dedicated sync SQLite
        # connection so they never block on (or deadlock against) the async pool.
        # See https://github.com/AstrBotDevs/AstrBot/pull/9649 for the original
        # deadlock scenario and design rationale.
        self._cache: dict[tuple[str, str, str], Any] = {}
        self._cache_lock = threading.RLock()
        self._cache_initialized = False
        self._initializing = False
        self._initialize_lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._write_queue: asyncio.Queue[_WriteOperation] | None = None
        self._writer_task: asyncio.Task[None] | None = None
        self._pending_writes: list[_WriteOperation] = []
        self._warned_sync_read_unsupported = False
        self._warned_sync_range_read_unsupported = False

        self._scheduler = BackgroundScheduler()
        self._scheduler.add_job(
            self._clear_temporary_cache, "interval", hours=24, id="clear_sp_temp_cache"
        )
        self._scheduler.start()

    def _clear_temporary_cache(self) -> None:
        self.temporary_cache.clear()

    def _apply_cache_operation(self, operation: _WriteOperation) -> None:
        """Apply one preference mutation to the in-memory cache.

        Args:
            operation: Queued write operation to reflect in memory.
        """
        action, scope, scope_id, key, value, _ = operation
        with self._cache_lock:
            if action == "put" and key is not None:
                self._cache[(scope, scope_id, key)] = deepcopy(value)
            elif action == "remove" and key is not None:
                self._cache.pop((scope, scope_id, key), None)
            elif action == "clear":
                keys = [
                    cache_key
                    for cache_key in self._cache
                    if cache_key[0] == scope and cache_key[1] == scope_id
                ]
                for cache_key in keys:
                    self._cache.pop(cache_key, None)

    def _schedule_write(self, operation: _WriteOperation) -> None:
        """Schedule a preference write on the owning event loop.

        Args:
            operation: Preference mutation to persist.
        """
        loop = self._loop
        queue = self._write_queue
        if loop is None or queue is None or not loop.is_running() or self._initializing:
            with self._cache_lock:
                self._pending_writes.append(operation)
            return

        def enqueue() -> None:
            queue.put_nowait(operation)
            if self._writer_task is None or self._writer_task.done():
                self._writer_task = loop.create_task(
                    self._drain_write_queue(),
                    name="shared_preferences_writer",
                )

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is loop:
            enqueue()
        else:
            try:
                loop.call_soon_threadsafe(enqueue)
            except RuntimeError:
                with self._cache_lock:
                    self._pending_writes.append(operation)

    def _submit_write(self, operation: _WriteOperation) -> None:
        """Update the cache and schedule persistence in the same order.

        Args:
            operation: Preference mutation to apply and persist.
        """
        with self._cache_lock:
            self._apply_cache_operation(operation)
            self._schedule_write(operation)

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
                        scope,
                        scope_id,
                        key,
                        {"val": value},
                    )
                elif action == "remove" and key is not None:
                    await self.db_helper.remove_preference(scope, scope_id, key)
                elif action == "clear":
                    await self.db_helper.clear_preferences(scope, scope_id)
                else:
                    raise ValueError(f"Unknown preference write operation: {action}")
            except Exception as exc:
                logger.error(
                    "Failed to persist shared preference operation %s for %s/%s: %s",
                    action,
                    scope,
                    scope_id,
                    exc,
                    exc_info=True,
                )
                if completion is not None and not completion.done():
                    completion.set_exception(exc)
            else:
                if completion is not None and not completion.done():
                    completion.set_result(None)
            finally:
                queue.task_done()

    async def initialize(self) -> None:
        """Bind writes to the current event loop and replay pending writes.

        The preferences table is intentionally NOT preloaded here: it can be
        arbitrarily large, and reads fall back to point queries instead.

        Raises:
            RuntimeError: If another running event loop already owns the store.
        """
        loop = asyncio.get_running_loop()
        async with self._initialize_lock:
            if self._loop is loop and self._cache_initialized:
                return
            with self._cache_lock:
                self._initializing = True
            try:
                if self._loop is not None and self._loop is not loop:
                    if self._loop.is_running():
                        raise RuntimeError(
                            "SharedPreferences is already bound to another running "
                            "event loop."
                        )
                    old_queue = self._write_queue
                    if old_queue is not None:
                        with self._cache_lock:
                            while True:
                                try:
                                    operation = old_queue.get_nowait()
                                    self._pending_writes.append((*operation[:-1], None))
                                    old_queue.task_done()
                                except asyncio.QueueEmpty:
                                    break

                self._loop = loop
                self._write_queue = asyncio.Queue()
                self._writer_task = None

                with self._cache_lock:
                    pending_writes = list(self._pending_writes)
                    self._pending_writes.clear()
                    for operation in pending_writes:
                        self._apply_cache_operation(operation)
                    self._cache_initialized = True
                    self._initializing = False
            except BaseException:
                with self._cache_lock:
                    self._initializing = False
                raise

            for operation in pending_writes:
                self._schedule_write(operation)
            await self.flush()

    async def flush(self) -> None:
        """Wait until all queued synchronous preference writes are persisted.

        Raises:
            RuntimeError: If called from a different running event loop.
        """
        if self._loop is None or self._write_queue is None:
            with self._cache_lock:
                has_pending_writes = bool(self._pending_writes)
            if has_pending_writes:
                await self.initialize()
            return
        loop = asyncio.get_running_loop()
        if loop is not self._loop:
            if self._loop.is_running():
                raise RuntimeError(
                    "SharedPreferences writes must be flushed on their owning "
                    "event loop."
                )
            await self.initialize()
            return
        await asyncio.sleep(0)
        await self._write_queue.join()
        if self._writer_task is not None:
            await self._writer_task

    async def close(self) -> None:
        """Flush pending writes and stop the temporary-cache scheduler."""
        await self.flush()
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    async def get_async(
        self,
        scope: str,
        scope_id: str,
        key: str,
        default: _VT = None,
    ) -> _VT:
        """获取指定范围和键的偏好设置"""
        await self.initialize()
        if scope_id is None or key is None:
            return default
        with self._cache_lock:
            value = self._cache.get((scope, scope_id, key), _MISSING)
            if value is not _MISSING:
                return deepcopy(value)
        preference = await self.db_helper.get_preference(scope, scope_id, key)
        if preference is None:
            return default
        return deepcopy(preference.value["val"])

    async def range_get_async(
        self,
        scope: str,
        scope_id: str | None = None,
        key: str | None = None,
    ) -> list[Preference]:
        """获取指定范围的偏好设置
        Note: 返回 Preference 列表，其中的 value 属性是一个 dict，value["val"] 为值。scope_id 和 key 可以为 None，这时返回该范围下所有的偏好设置。
        """
        await self.initialize()
        await self.flush()
        ret = await self.db_helper.get_preferences(scope, scope_id, key)
        return ret

    @overload
    async def session_get(
        self,
        umo: str,
        key: str,
        default: _VT = None,
    ) -> _VT: ...

    @overload
    async def session_get(
        self,
        umo: None,
        key: str,
        default: Any = None,
    ) -> list[Preference]: ...

    @overload
    async def session_get(
        self,
        umo: str,
        key: None,
        default: Any = None,
    ) -> list[Preference]: ...

    @overload
    async def session_get(
        self,
        umo: None,
        key: None,
        default: Any = None,
    ) -> list[Preference]: ...

    async def session_get(
        self,
        umo: str | None,
        key: str | None = None,
        default: _VT = None,
    ) -> _VT | list[Preference]:
        """获取会话范围的偏好设置

        Note: 当 umo 或者 key 为 None，时，返回 Preference 列表，其中的 value 属性是一个 dict，value["val"] 为值。
        """
        if umo is None or key is None:
            return await self.range_get_async("umo", umo, key)
        return await self.get_async("umo", umo, key, default)

    @overload
    async def global_get(self, key: None, default: Any = None) -> list[Preference]: ...

    @overload
    async def global_get(self, key: str, default: _VT = None) -> _VT: ...

    async def global_get(
        self,
        key: str | None,
        default: _VT = None,
    ) -> _VT | list[Preference]:
        """获取全局范围的偏好设置

        Note: 当 scope_id 或者 key 为 None，时，返回 Preference 列表，其中的 value 属性是一个 dict，value["val"] 为值。
        """
        if key is None:
            return await self.range_get_async("global", "global", key)
        return await self.get_async("global", "global", key, default)

    async def put_async(self, scope: str, scope_id: str, key: str, value: Any) -> None:
        """设置指定范围和键的偏好设置"""
        await self.initialize()
        completion = asyncio.get_running_loop().create_future()
        operation: _WriteOperation = (
            "put",
            scope,
            scope_id,
            key,
            deepcopy(value),
            completion,
        )
        self._submit_write(operation)
        await completion

    async def session_put(self, umo: str, key: str, value: Any) -> None:
        await self.put_async("umo", umo, key, value)

    async def global_put(self, key: str, value: Any) -> None:
        await self.put_async("global", "global", key, value)

    async def remove_async(self, scope: str, scope_id: str, key: str) -> None:
        """删除指定范围和键的偏好设置"""
        await self.initialize()
        completion = asyncio.get_running_loop().create_future()
        operation: _WriteOperation = (
            "remove",
            scope,
            scope_id,
            key,
            None,
            completion,
        )
        self._submit_write(operation)
        await completion

    async def session_remove(self, umo: str, key: str) -> None:
        await self.remove_async("umo", umo, key)

    async def global_remove(self, key: str) -> None:
        """删除全局偏好设置"""
        await self.remove_async("global", "global", key)

    async def clear_async(self, scope: str, scope_id: str) -> None:
        """清空指定范围的所有偏好设置"""
        await self.initialize()
        completion = asyncio.get_running_loop().create_future()
        operation: _WriteOperation = (
            "clear",
            scope,
            scope_id,
            None,
            None,
            completion,
        )
        self._submit_write(operation)
        await completion

    # ====
    # DEPRECATED METHODS
    # ====

    @deprecated(
        version="4.0.0",
        reason="Use get_async() instead. Plugins: use PluginKVStoreMixin.get_kv_data().",
    )
    def get(
        self,
        key: str,
        default: _VT = None,
        scope: str | None = None,
        scope_id: str | None = "",
    ) -> _VT:
        """获取偏好设置（已弃用）"""
        if scope_id == "":
            scope_id = "unknown"
        if scope_id is None or key is None:
            # result = asyncio.run(self.range_get_async(scope, scope_id, key))
            raise ValueError(
                "scope_id and key cannot be None when getting a specific preference.",
            )
        resolved_scope = scope or "unknown"
        resolved_scope_id = scope_id or "unknown"
        with self._cache_lock:
            value = self._cache.get((resolved_scope, resolved_scope_id, key), _MISSING)
            if value is not _MISSING:
                return default if value is None else deepcopy(value)
        # Overlay miss: fall back to a point query through a dedicated
        # synchronous database connection. This briefly blocks the calling
        # thread (unavoidable for a synchronous API), but never touches the
        # async connection pool, so it cannot deadlock the event loop.
        get_sync = getattr(self.db_helper, "get_preference_sync", None)
        if get_sync is None:
            if not self._warned_sync_read_unsupported:
                self._warned_sync_read_unsupported = True
                logger.warning(
                    "SharedPreferences sync get() is not supported by database "
                    "backend %s; returning the default. Use get_async() instead.",
                    type(self.db_helper).__name__,
                )
            return default
        try:
            stored = get_sync(resolved_scope, resolved_scope_id, key)
        except Exception as exc:
            logger.warning(
                "SharedPreferences sync get() failed for %s/%s/%s: %s",
                resolved_scope,
                resolved_scope_id,
                key,
                exc,
            )
            return default
        if stored is None:
            return default
        value = stored.get("val")
        return default if value is None else deepcopy(value)

    @deprecated(version="4.0.0", reason="Use range_get_async() instead.")
    def range_get(
        self,
        scope: str,
        scope_id: str | None = None,
        key: str | None = None,
    ) -> list[Preference]:
        """Synchronously get preferences matching the supplied range.

        Historical values are loaded on demand through a dedicated synchronous
        database connection, then values written by this process are overlaid to
        preserve immediate read-after-write visibility without startup preload.

        Args:
            scope: Preference scope to query.
            scope_id: Optional identifier within the scope.
            key: Optional preference key.

        Returns:
            Preferences matching the supplied filters.
        """
        get_sync = getattr(self.db_helper, "get_preferences_sync", None)
        if get_sync is None:
            if not self._warned_sync_range_read_unsupported:
                self._warned_sync_range_read_unsupported = True
                logger.warning(
                    "SharedPreferences sync range_get() is not supported by "
                    "database backend %s; returning process-local values only. "
                    "Use range_get_async() instead.",
                    type(self.db_helper).__name__,
                )
            persisted: list[Preference] = []
        else:
            try:
                persisted = get_sync(scope, scope_id, key)
            except Exception as exc:
                logger.warning(
                    "SharedPreferences sync range_get() failed for %s/%s/%s: %s",
                    scope,
                    scope_id,
                    key,
                    exc,
                )
                persisted = []

        values = {
            (preference.scope, preference.scope_id, preference.key): preference
            for preference in persisted
        }
        with self._cache_lock:
            for (cache_scope, cache_scope_id, cache_key), value in self._cache.items():
                if (
                    cache_scope == scope
                    and (scope_id is None or cache_scope_id == scope_id)
                    and (key is None or cache_key == key)
                ):
                    values[(cache_scope, cache_scope_id, cache_key)] = Preference(
                        scope=cache_scope,
                        scope_id=cache_scope_id,
                        key=cache_key,
                        value={"val": deepcopy(value)},
                    )
        return list(values.values())

    @deprecated(
        version="4.0.0",
        reason="Use put_async() instead. Plugins: use PluginKVStoreMixin.put_kv_data().",
    )
    def put(
        self, key, value, scope: str | None = None, scope_id: str | None = None
    ) -> None:
        """设置偏好设置（已弃用）"""
        operation: _WriteOperation = (
            "put",
            scope or "unknown",
            scope_id or "unknown",
            key,
            deepcopy(value),
            None,
        )
        self._submit_write(operation)

    @deprecated(
        version="4.0.0",
        reason="Use remove_async() instead. Plugins: use PluginKVStoreMixin.delete_kv_data().",
    )
    def remove(
        self, key, scope: str | None = None, scope_id: str | None = None
    ) -> None:
        """删除偏好设置（已弃用）"""
        operation: _WriteOperation = (
            "remove",
            scope or "unknown",
            scope_id or "unknown",
            key,
            None,
            None,
        )
        self._submit_write(operation)

    @deprecated(version="4.0.0", reason="Use clear_async() instead.")
    def clear(self, scope: str | None = None, scope_id: str | None = None) -> None:
        """清空偏好设置（已弃用）"""
        operation: _WriteOperation = (
            "clear",
            scope or "unknown",
            scope_id or "unknown",
            None,
            None,
            None,
        )
        self._submit_write(operation)
