"""记忆客户端模块。

提供 AI 记忆存储能力，用于存储和检索对话记忆、用户偏好等语义数据。

与旧版对比：
    旧版: 无独立记忆模块，KV 存储用于简单数据持久化

    新版: 新增 MemoryClient，提供语义搜索能力
        - search(): 语义搜索记忆项
        - save(): 保存记忆项
        - save_with_ttl(): 保存带过期时间的记忆项
        - get(): 精确获取单个记忆项
        - get_many(): 批量获取多个记忆项
        - delete(): 删除记忆项
        - delete_many(): 批量删除多个记忆项
        - stats(): 获取记忆统计信息

设计说明：
    MemoryClient 与 DBClient 的区别：
    - DBClient: 简单的键值存储，精确匹配
    - MemoryClient: 支持语义搜索的智能存储，适合 AI 上下文管理

    记忆系统可用于：
    - 存储用户偏好和设置
    - 记录对话摘要
    - 缓存 AI 推理结果
"""

from __future__ import annotations

from typing import Any

from ._proxy import CapabilityProxy


class MemoryClient:
    """记忆客户端。

    提供 AI 记忆的存储和检索能力，支持语义搜索。

    Attributes:
        _proxy: CapabilityProxy 实例，用于远程能力调用
    """

    def __init__(self, proxy: CapabilityProxy) -> None:
        """初始化记忆客户端。

        Args:
            proxy: CapabilityProxy 实例
        """
        self._proxy = proxy

    async def search(self, query: str) -> list[dict[str, Any]]:
        """语义搜索记忆项。

        使用自然语言查询检索相关记忆，返回匹配的记忆项列表。
        与精确匹配的 get() 不同，search() 使用向量相似度进行语义匹配。

        Args:
            query: 搜索查询文本

        Returns:
            匹配的记忆项列表，按相关度排序

        示例:
            # 搜索用户偏好相关的记忆
            results = await ctx.memory.search("用户喜欢什么颜色")
            for item in results:
                print(item["key"], item["content"])
        """
        output = await self._proxy.call("memory.search", {"query": query})
        items = output.get("items")
        if not isinstance(items, (list, tuple)):
            return []
        return list(items)

    async def save(
        self,
        key: str,
        value: dict[str, Any] | None = None,
        **extra: Any,
    ) -> None:
        """保存记忆项。

        将数据存储到记忆系统，可通过 search() 进行语义搜索或 get() 精确获取。

        Args:
            key: 记忆项的唯一标识键
            value: 要存储的数据字典
            **extra: 额外的键值对，会合并到 value 中

        Raises:
            TypeError: 如果 value 不是 dict 类型

        示例:
            # 保存用户偏好
            await ctx.memory.save("user_pref", {"theme": "dark", "lang": "zh"})

            # 使用关键字参数
            await ctx.memory.save("note", None, content="重要笔记", tags=["work"])
        """
        if value is not None and not isinstance(value, dict):
            raise TypeError("memory.save 的 value 必须是 dict")
        payload = dict(value or {})
        if extra:
            payload.update(extra)
        await self._proxy.call("memory.save", {"key": key, "value": payload})

    async def get(self, key: str) -> dict[str, Any] | None:
        """精确获取单个记忆项。

        通过唯一键精确获取记忆内容，不使用语义搜索。

        Args:
            key: 记忆项的唯一键

        Returns:
            记忆项内容字典，若不存在则返回 None

        示例:
            pref = await ctx.memory.get("user_pref")
            if pref:
                print(f"用户偏好主题: {pref.get('theme')}")
        """
        output = await self._proxy.call("memory.get", {"key": key})
        value = output.get("value")
        return value if isinstance(value, dict) else None

    async def delete(self, key: str) -> None:
        """删除记忆项。

        Args:
            key: 要删除的记忆项键名

        示例:
            await ctx.memory.delete("old_note")
        """
        await self._proxy.call("memory.delete", {"key": key})

    async def save_with_ttl(
        self,
        key: str,
        value: dict[str, Any],
        ttl_seconds: int,
    ) -> None:
        """保存带过期时间的记忆项。

        与 save() 不同，此方法允许设置记忆项的存活时间（TTL），
        过期后记忆项将自动删除。

        Args:
            key: 记忆项的唯一标识键
            value: 要存储的数据字典
            ttl_seconds: 存活时间（秒），必须大于 0

        Raises:
            TypeError: 如果 value 不是 dict 类型
            ValueError: 如果 ttl_seconds 小于 1

        示例:
            # 保存临时会话状态，1小时后过期
            await ctx.memory.save_with_ttl(
                "session_temp",
                {"state": "waiting"},
                ttl_seconds=3600,
            )
        """
        if not isinstance(value, dict):
            raise TypeError("memory.save_with_ttl 的 value 必须是 dict")
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds 必须大于 0")
        await self._proxy.call(
            "memory.save_with_ttl",
            {"key": key, "value": value, "ttl_seconds": ttl_seconds},
        )

    async def get_many(
        self,
        keys: list[str],
    ) -> list[dict[str, Any]]:
        """批量获取多个记忆项。

        一次性获取多个键对应的记忆内容，比多次调用 get() 更高效。

        Args:
            keys: 记忆项键名列表

        Returns:
            记忆项列表，每项包含 key 和 value 字段，
            不存在的键返回 value 为 None

        示例:
            items = await ctx.memory.get_many(["pref1", "pref2", "pref3"])
            for item in items:
                if item["value"]:
                    print(f"{item['key']}: {item['value']}")
        """
        output = await self._proxy.call("memory.get_many", {"keys": keys})
        items = output.get("items")
        if not isinstance(items, (list, tuple)):
            return []
        return [dict(item) for item in items]

    async def delete_many(self, keys: list[str]) -> int:
        """批量删除多个记忆项。

        一次性删除多个键对应的记忆项，返回实际删除的数量。

        Args:
            keys: 要删除的记忆项键名列表

        Returns:
            实际删除的记忆项数量

        示例:
            deleted = await ctx.memory.delete_many(["old1", "old2", "old3"])
            print(f"删除了 {deleted} 条记忆")
        """
        output = await self._proxy.call("memory.delete_many", {"keys": keys})
        return int(output.get("deleted_count", 0))

    async def stats(self) -> dict[str, Any]:
        """获取记忆系统统计信息。

        返回记忆系统的当前状态，包括总条目数等统计信息。

        Returns:
            统计信息字典，包含：
            - total_items: 总记忆条目数
            - total_bytes: 总占用字节数（可选）

        示例:
            stats = await ctx.memory.stats()
            print(f"记忆库共有 {stats['total_items']} 条记录")
        """
        output = await self._proxy.call("memory.stats", {})
        stats = {
            "total_items": output.get("total_items", 0),
            "total_bytes": output.get("total_bytes"),
        }
        if "plugin_id" in output:
            stats["plugin_id"] = output.get("plugin_id")
        if "ttl_entries" in output:
            stats["ttl_entries"] = output.get("ttl_entries")
        return stats
