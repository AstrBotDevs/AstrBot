"""记忆客户端模块。

提供 AI 记忆存储能力，用于存储和检索对话记忆、用户偏好等上下文数据。

设计说明：
    MemoryClient 与 DBClient 的区别：
    - DBClient: 简单的键值存储，精确匹配
    - MemoryClient: 支持基于当前 bridge 行为的记忆检索，适合 AI 上下文管理

    记忆系统可用于：
    - 存储用户偏好和设置
    - 记录对话摘要
    - 缓存 AI 推理结果
"""

from __future__ import annotations

from typing import Any, Literal

from .._internal.memory_utils import join_memory_namespace
from ._proxy import CapabilityProxy


def _normalize_search_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    normalized = dict(item)
    value = normalized.get("value")
    if isinstance(value, dict):
        for key, payload_value in value.items():
            normalized.setdefault(str(key), payload_value)
    return normalized


class MemoryClient:
    """记忆客户端。

    提供 AI 记忆的存储和检索能力。

    Attributes:
        _proxy: CapabilityProxy 实例，用于远程能力调用
    """

    def __init__(
        self,
        proxy: CapabilityProxy,
        *,
        namespace: str | None = None,
    ) -> None:
        """初始化记忆客户端。

        Args:
            proxy: CapabilityProxy 实例
        """
        self._proxy = proxy
        self._namespace = join_memory_namespace(namespace)

    def namespace(self, *parts: Any) -> MemoryClient:
        """Create a derived client that operates inside a child namespace."""

        return MemoryClient(
            self._proxy,
            namespace=join_memory_namespace(self._namespace, *parts),
        )

    def _resolve_exact_namespace(self, namespace: str | None) -> str:
        if namespace is None:
            return self._namespace
        return join_memory_namespace(self._namespace, namespace)

    def _resolve_scope_namespace(self, namespace: str | None) -> tuple[bool, str]:
        if namespace is None:
            if self._namespace:
                return True, self._namespace
            return False, ""
        return True, join_memory_namespace(self._namespace, namespace)

    async def search(
        self,
        query: str,
        *,
        mode: Literal["auto", "keyword", "vector", "hybrid"] = "auto",
        limit: int | None = None,
        min_score: float | None = None,
        provider_id: str | None = None,
        namespace: str | None = None,
        include_descendants: bool = True,
    ) -> list[dict[str, Any]]:
        """搜索记忆项。

        默认会在有 embedding provider 时执行 hybrid 检索，
        否则退化为关键词检索。返回结果包含 `score` 与 `match_type` 字段。

        Args:
            query: 搜索查询文本
            mode: 搜索模式，支持 auto/keyword/vector/hybrid
            limit: 最大返回条数
            min_score: 最低分数阈值
            provider_id: 指定 embedding provider，默认使用当前激活的 provider

        Returns:
            匹配的记忆项列表，按相关度排序

        示例:
            results = await ctx.memory.search(
                "用户喜欢什么颜色",
                mode="hybrid",
                limit=5,
            )
            for item in results:
                print(item["key"], item["score"], item["match_type"])
        """
        payload: dict[str, Any] = {"query": query, "mode": mode}
        if limit is not None:
            payload["limit"] = limit
        if min_score is not None:
            payload["min_score"] = min_score
        if provider_id is not None:
            payload["provider_id"] = provider_id
        has_namespace, resolved_namespace = self._resolve_scope_namespace(namespace)
        if has_namespace:
            payload["namespace"] = resolved_namespace
        payload["include_descendants"] = bool(include_descendants)
        output = await self._proxy.call("memory.search", payload)
        items = output.get("items")
        if not isinstance(items, (list, tuple)):
            return []
        normalized_items: list[dict[str, Any]] = []
        for item in items:
            normalized = _normalize_search_item(item)
            if normalized is not None:
                normalized_items.append(normalized)
        return normalized_items

    async def save(
        self,
        key: str,
        value: dict[str, Any] | None = None,
        namespace: str | None = None,
        **extra: Any,
    ) -> None:
        """保存记忆项。

        将数据存储到记忆系统，可通过 search() 检索或 get() 精确获取。

        Args:
            key: 记忆项的唯一标识键
            value: 要存储的数据字典
            **extra: 额外的键值对，会合并到 value 中
        Raises:
            TypeError: 如果 value 不是 dict 类型
        示例:
            保存用户偏好
            await ctx.memory.save("user_pref", {"theme": "dark", "lang": "zh"})

            使用关键字参数
            await ctx.memory.save("note", None, content="重要笔记", tags=["work"])

            使用 embedding_text 显式指定检索文本
            await ctx.memory.save(
                "profile",
                {"name": "alice", "embedding_text": "Alice 喜欢蓝色和海边"},
            )
        """
        if value is not None and not isinstance(value, dict):
            raise TypeError("memory.save 的 value 必须是 dict")
        payload = dict(value or {})
        if extra:
            payload.update(extra)
        request: dict[str, Any] = {"key": key, "value": payload}
        request["namespace"] = self._resolve_exact_namespace(namespace)
        await self._proxy.call("memory.save", request)

    async def get(
        self,
        key: str,
        *,
        namespace: str | None = None,
    ) -> dict[str, Any] | None:
        """精确获取单个记忆项。

        通过唯一键精确获取记忆内容，不经过搜索匹配。

        Args:
            key: 记忆项的唯一键

        Returns:
            记忆项内容字典，若不存在则返回 None

        示例:
            pref = await ctx.memory.get("user_pref")
            if pref:
                print(f"用户偏好主题: {pref.get('theme')}")
        """
        payload: dict[str, Any] = {"key": key}
        payload["namespace"] = self._resolve_exact_namespace(namespace)
        output = await self._proxy.call("memory.get", payload)
        value = output.get("value")
        return value if isinstance(value, dict) else None

    async def delete(
        self,
        key: str,
        *,
        namespace: str | None = None,
    ) -> None:
        """删除记忆项。

        Args:
            key: 要删除的记忆项键名

        示例:
            await ctx.memory.delete("old_note")
        """
        payload: dict[str, Any] = {"key": key}
        payload["namespace"] = self._resolve_exact_namespace(namespace)
        await self._proxy.call("memory.delete", payload)

    async def save_with_ttl(
        self,
        key: str,
        value: dict[str, Any],
        ttl_seconds: int,
        *,
        namespace: str | None = None,
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
        payload: dict[str, Any] = {
            "key": key,
            "value": value,
            "ttl_seconds": ttl_seconds,
        }
        payload["namespace"] = self._resolve_exact_namespace(namespace)
        await self._proxy.call("memory.save_with_ttl", payload)

    async def get_many(
        self,
        keys: list[str],
        *,
        namespace: str | None = None,
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
        payload: dict[str, Any] = {"keys": keys}
        payload["namespace"] = self._resolve_exact_namespace(namespace)
        output = await self._proxy.call("memory.get_many", payload)
        items = output.get("items")
        if not isinstance(items, (list, tuple)):
            return []
        return [dict(item) for item in items if isinstance(item, dict)]

    async def delete_many(
        self,
        keys: list[str],
        *,
        namespace: str | None = None,
    ) -> int:
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
        payload: dict[str, Any] = {"keys": keys}
        payload["namespace"] = self._resolve_exact_namespace(namespace)
        output = await self._proxy.call("memory.delete_many", payload)
        return int(output.get("deleted_count", 0))

    async def stats(
        self,
        *,
        namespace: str | None = None,
        include_descendants: bool = True,
    ) -> dict[str, Any]:
        """获取记忆系统统计信息。

        返回记忆系统的当前状态，包括条目数、索引状态和脏索引数量。

        Returns:
            统计信息字典，包含：
            - total_items: 总记忆条目数
            - total_bytes: 总占用字节数（可选）
            - ttl_entries: 带过期时间的条目数（可选）
            - indexed_items: 已建立检索索引的条目数（可选）
            - embedded_items: 已生成向量的条目数（可选）
            - dirty_items: 等待重建索引的条目数（可选）

        示例:
            stats = await ctx.memory.stats()
            print(f"记忆库共有 {stats['total_items']} 条记录")
            if "embedded_items" in stats:
                print(f"其中 {stats['embedded_items']} 条已经向量化")
        """
        payload: dict[str, Any] = {
            "include_descendants": bool(include_descendants),
        }
        has_namespace, resolved_namespace = self._resolve_scope_namespace(namespace)
        if has_namespace:
            payload["namespace"] = resolved_namespace
        output = await self._proxy.call("memory.stats", payload)
        stats = {
            "total_items": output.get("total_items", 0),
            "total_bytes": output.get("total_bytes"),
        }
        if "namespace" in output:
            stats["namespace"] = output.get("namespace")
        if "namespace_count" in output:
            stats["namespace_count"] = output.get("namespace_count")
        if "fts_enabled" in output:
            stats["fts_enabled"] = output.get("fts_enabled")
        if "vector_backend" in output:
            stats["vector_backend"] = output.get("vector_backend")
        if "vector_indexes" in output:
            stats["vector_indexes"] = output.get("vector_indexes")
        if "plugin_id" in output:
            stats["plugin_id"] = output.get("plugin_id")
        if "ttl_entries" in output:
            stats["ttl_entries"] = output.get("ttl_entries")
        if "indexed_items" in output:
            stats["indexed_items"] = output.get("indexed_items")
        if "embedded_items" in output:
            stats["embedded_items"] = output.get("embedded_items")
        if "dirty_items" in output:
            stats["dirty_items"] = output.get("dirty_items")
        return stats
