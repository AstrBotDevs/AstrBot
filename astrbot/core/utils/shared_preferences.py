from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import Preference
import threading
import asyncio
import os
from typing import TypeVar, Any, overload
from .astrbot_path import get_astrbot_data_path


_VT = TypeVar("_VT")


class SharedPreferences:
    def __init__(self, db_helper: BaseDatabase, json_storage_path=None):
        if json_storage_path is None:
            json_storage_path = os.path.join(
                get_astrbot_data_path(), "shared_preferences.json"
            )
        self.path = json_storage_path
        self.db_helper = db_helper

        self._sync_loop = asyncio.new_event_loop()
        t = threading.Thread(target=self._sync_loop.run_forever, daemon=True)
        t.start()

    async def get_async(
        self,
        scope: str,
        scope_id: str,
        key: str,
        default: _VT = None,
    ) -> _VT:
        """获取指定范围和键的偏好设置"""
        if scope_id is not None and key is not None:
            result = await self.db_helper.get_preference(scope, scope_id, key)
            if result:
                ret = result.value["val"]
            else:
                ret = default
            return ret
        else:
            raise ValueError(
                "scope_id and key cannot be None when getting a specific preference."
            )

    async def range_get_async(
        self, scope: str, scope_id: str | None = None, key: str | None = None
    ) -> list[Preference]:
        """获取指定范围的偏好设置
        Note: 返回 Preference 列表，其中的 value 属性是一个 dict，value["val"] 为值。scope_id 和 key 可以为 None，这时返回该范围下所有的偏好设置。
        """
        ret = await self.db_helper.get_preferences(scope, scope_id, key)
        return ret

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
        self, umo: str | None, key: str | None = None, default: _VT = None
    ) -> _VT | list[Preference]:
        """获取会话范围的偏好设置

        Note: 当 scope_id 或者 key 为 None，时，返回 Preference 列表，其中的 value 属性是一个 dict，value["val"] 为值。
        """
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
        """获取全局范围的偏好设置

        Note: 当 scope_id 或者 key 为 None，时，返回 Preference 列表，其中的 value 属性是一个 dict，value["val"] 为值。
        """
        if key is None:
            return await self.range_get_async("global", "global", key)
        return await self.get_async("global", "global", key, default)

    async def put_async(self, scope: str, scope_id: str, key: str, value: Any):
        """设置指定范围和键的偏好设置"""
        await self.db_helper.insert_preference_or_update(
            scope, scope_id, key, {"val": value}
        )

    async def session_put(self, umo: str, key: str, value: Any):
        await self.put_async("umo", umo, key, value)

    async def global_put(self, key: str, value: Any):
        await self.put_async("global", "global", key, value)

    async def remove_async(self, scope: str, scope_id: str, key: str):
        """删除指定范围和键的偏好设置"""
        await self.db_helper.remove_preference(scope, scope_id, key)

    async def session_remove(self, umo: str, key: str):
        await self.remove_async("umo", umo, key)

    async def global_remove(self, key: str):
        """删除全局偏好设置"""
        await self.remove_async("global", "global", key)

    async def clear_async(self, scope: str, scope_id: str):
        """清空指定范围的所有偏好设置"""
        await self.db_helper.clear_preferences(scope, scope_id)

    # ====
    # DEPRECATED METHODS
    # ====

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
                "scope_id and key cannot be None when getting a specific preference."
            )
        result = asyncio.run_coroutine_threadsafe(
            self.get_async(scope or "unknown", scope_id or "unknown", key, default),
            self._sync_loop,
        ).result()

        return result if result is not None else default

    def range_get(
        self, scope: str, scope_id: str | None = None, key: str | None = None
    ) -> list[Preference]:
        """获取指定范围的偏好设置（已弃用）"""
        result = asyncio.run_coroutine_threadsafe(
            self.range_get_async(scope, scope_id, key), self._sync_loop
        ).result()

        return result

    def put(self, key, value, scope: str | None = None, scope_id: str | None = None):
        """设置偏好设置（已弃用）"""
        asyncio.run_coroutine_threadsafe(
            self.put_async(scope or "unknown", scope_id or "unknown", key, value),
            self._sync_loop,
        ).result()

    def remove(self, key, scope: str | None = None, scope_id: str | None = None):
        """删除偏好设置（已弃用）"""
        asyncio.run_coroutine_threadsafe(
            self.remove_async(scope or "unknown", scope_id or "unknown", key),
            self._sync_loop,
        ).result()

    def clear(self, scope: str | None = None, scope_id: str | None = None):
        """清空偏好设置（已弃用）"""
        asyncio.run_coroutine_threadsafe(
            self.clear_async(scope or "unknown", scope_id or "unknown"),
            self._sync_loop,
        ).result()
