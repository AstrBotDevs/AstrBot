"""数据库客户端模块。

提供键值存储能力，用于持久化插件数据。

与旧版对比：
    旧版 (src/astrbot_sdk/api/star/context.py):
        Context.put_kv_data(key, value)
        Context.get_kv_data(key)
        Context.delete_kv_data(key)

    新版:
        Context.db.set(key, value)
        Context.db.get(key)
        Context.db.delete(key)
        Context.db.list(prefix)  # 新增：列出键

功能说明：
    - 数据永久存储，除非用户显式删除
    - 值类型支持任意 JSON 数据
    - 支持前缀查询键列表
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

from ._proxy import CapabilityProxy


class DBClient:
    """键值数据库客户端。

    提供插件数据的持久化存储能力，数据永久保存直到显式删除。

    Attributes:
        _proxy: CapabilityProxy 实例，用于远程能力调用
    """

    def __init__(self, proxy: CapabilityProxy) -> None:
        """初始化数据库客户端。

        Args:
            proxy: CapabilityProxy 实例
        """
        self._proxy = proxy

    async def get(self, key: str) -> Any | None:
        """获取指定键的值。

        Args:
            key: 数据键名

        Returns:
            存储的值，若键不存在则返回 None

        示例:
            data = await ctx.db.get("user_settings")
            if data:
                print(data["theme"])
        """
        output = await self._proxy.call("db.get", {"key": key})
        return output.get("value")

    async def set(self, key: str, value: Any) -> None:
        """设置键值对。

        Args:
            key: 数据键名
            value: 要存储的 JSON 值

        示例:
            await ctx.db.set("user_settings", {"theme": "dark", "lang": "zh"})
            await ctx.db.set("greeted", True)
        """
        await self._proxy.call("db.set", {"key": key, "value": value})

    async def delete(self, key: str) -> None:
        """删除指定键的数据。

        Args:
            key: 要删除的数据键名

        示例:
            await ctx.db.delete("user_settings")
        """
        await self._proxy.call("db.delete", {"key": key})

    async def list(self, prefix: str | None = None) -> list[str]:
        """列出匹配前缀的所有键。

        Args:
            prefix: 键前缀过滤，None 表示列出所有键

        Returns:
            匹配的键名列表

        示例:
            # 列出所有用户设置相关的键
            keys = await ctx.db.list("user_")
            # ["user_settings", "user_profile", "user_history"]
        """
        output = await self._proxy.call("db.list", {"prefix": prefix})
        keys = output.get("keys")
        if not isinstance(keys, (list, tuple)):
            return []
        return [str(item) for item in keys]

    async def get_many(self, keys: Sequence[str]) -> dict[str, Any | None]:
        """批量获取多个键的值。

        Args:
            keys: 要读取的键列表

        Returns:
            一个 dict，key 为键名，value 为对应值（不存在则为 None）

        示例:
            values = await ctx.db.get_many(["user:1", "user:2"])
            if values["user:1"] is None:
                print("user:1 missing")
        """
        output = await self._proxy.call("db.get_many", {"keys": list(keys)})
        items = output.get("items")
        if not isinstance(items, (list, tuple)):
            return {}
        result: dict[str, Any | None] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            key = item.get("key")
            if not isinstance(key, str):
                continue
            result[key] = item.get("value")
        return result

    async def set_many(
        self, items: Mapping[str, Any] | Sequence[tuple[str, Any]]
    ) -> None:
        """批量写入多个键值对。

        Args:
            items: 键值对集合（dict 或二元组序列）

        示例:
            await ctx.db.set_many({"user:1": {"name": "a"}, "user:2": {"name": "b"}})
        """
        if isinstance(items, Mapping):
            pairs = list(items.items())
        else:
            pairs = list(items)

        payload_items: list[dict[str, Any]] = [
            {"key": str(key), "value": value} for key, value in pairs
        ]
        await self._proxy.call("db.set_many", {"items": payload_items})

    def watch(self, prefix: str | None = None) -> AsyncIterator[dict[str, Any]]:
        """订阅 KV 变更事件（流式）。

        Args:
            prefix: 键前缀过滤；None 表示订阅所有键

        Yields:
            变更事件 dict：{"op": "set"|"delete", "key": str, "value": Any|None}

        示例:
            async for event in ctx.db.watch("user:"):
                print(event["op"], event["key"])
        """
        return self._proxy.stream("db.watch", {"prefix": prefix})
