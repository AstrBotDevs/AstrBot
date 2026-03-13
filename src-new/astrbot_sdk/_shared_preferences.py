"""旧版 ``sp`` 共享偏好存储的轻量兼容实现。

当前实现是进程内存级别的 KV 存储，主要目标是让旧插件的导入和常见读写流程
继续工作，而不是完整复刻旧 core 的数据库持久化语义。
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, TypeVar

_VT = TypeVar("_VT")


@dataclass(slots=True)
class PreferenceRecord:
    scope: str
    scope_id: str
    key: str
    value: dict[str, Any]


class SharedPreferences:
    def __init__(self) -> None:
        self._store: dict[str, dict[str, dict[str, Any]]] = defaultdict(
            lambda: defaultdict(dict)
        )
        self.temporary_cache: dict[str, dict[str, Any]] = defaultdict(dict)

    async def get_async(
        self,
        scope: str,
        scope_id: str,
        key: str,
        default: _VT = None,
    ) -> _VT:
        return self._store.get(scope, {}).get(scope_id, {}).get(key, default)

    async def range_get_async(
        self,
        scope: str,
        scope_id: str | None = None,
        key: str | None = None,
    ) -> list[PreferenceRecord]:
        records: list[PreferenceRecord] = []
        scope_store = self._store.get(scope, {})
        for current_scope_id, values in scope_store.items():
            if scope_id is not None and current_scope_id != scope_id:
                continue
            for current_key, current_value in values.items():
                if key is not None and current_key != key:
                    continue
                records.append(
                    PreferenceRecord(
                        scope=scope,
                        scope_id=current_scope_id,
                        key=current_key,
                        value={"val": current_value},
                    )
                )
        return records

    async def session_get(
        self,
        umo: str | None,
        key: str | None = None,
        default: _VT = None,
    ) -> _VT | list[PreferenceRecord]:
        if umo is None or key is None:
            return await self.range_get_async("umo", umo, key)
        return await self.get_async("umo", umo, key, default)

    async def global_get(
        self,
        key: str | None,
        default: _VT = None,
    ) -> _VT | list[PreferenceRecord]:
        if key is None:
            return await self.range_get_async("global", "global", key)
        return await self.get_async("global", "global", key, default)

    async def put_async(self, scope: str, scope_id: str, key: str, value: Any) -> None:
        self._store[scope][scope_id][key] = value

    async def session_put(self, umo: str, key: str, value: Any) -> None:
        await self.put_async("umo", umo, key, value)

    async def global_put(self, key: str, value: Any) -> None:
        await self.put_async("global", "global", key, value)

    async def remove_async(self, scope: str, scope_id: str, key: str) -> None:
        scope_store = self._store.get(scope)
        if not scope_store:
            return
        values = scope_store.get(scope_id)
        if not values:
            return
        values.pop(key, None)
        if not values:
            scope_store.pop(scope_id, None)

    async def session_remove(self, umo: str, key: str) -> None:
        await self.remove_async("umo", umo, key)

    async def global_remove(self, key: str) -> None:
        await self.remove_async("global", "global", key)

    async def clear_async(self, scope: str, scope_id: str) -> None:
        scope_store = self._store.get(scope)
        if scope_store is None:
            return
        scope_store.pop(scope_id, None)

    def _run_sync(self, coro):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        raise RuntimeError(
            "sp 的同步接口不能在运行中的事件循环内调用，请改用 async 版本"
        )

    def get(
        self,
        key: str,
        default: _VT = None,
        scope: str | None = None,
        scope_id: str | None = "",
    ) -> _VT:
        return self._run_sync(
            self.get_async(scope or "unknown", scope_id or "unknown", key, default)
        )

    def range_get(
        self,
        scope: str,
        scope_id: str | None = None,
        key: str | None = None,
    ) -> list[PreferenceRecord]:
        return self._run_sync(self.range_get_async(scope, scope_id, key))

    def put(
        self,
        key: str,
        value: Any,
        scope: str | None = None,
        scope_id: str | None = None,
    ) -> None:
        self._run_sync(
            self.put_async(scope or "unknown", scope_id or "unknown", key, value)
        )

    def remove(
        self,
        key: str,
        scope: str | None = None,
        scope_id: str | None = None,
    ) -> None:
        self._run_sync(
            self.remove_async(scope or "unknown", scope_id or "unknown", key)
        )

    def clear(self, scope: str | None = None, scope_id: str | None = None) -> None:
        self._run_sync(self.clear_async(scope or "unknown", scope_id or "unknown"))


sp = SharedPreferences()

__all__ = ["PreferenceRecord", "SharedPreferences", "sp"]
