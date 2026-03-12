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
    - 值类型为 dict，支持结构化数据
    - 支持前缀查询键列表

TODO:
    - 缺少批量操作支持 (set_many, get_many)
    - 缺少数据变更事件通知
"""

from __future__ import annotations

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

    async def get(self, key: str) -> dict[str, Any] | None:
        """获取指定键的值。

        Args:
            key: 数据键名

        Returns:
            存储的字典值，若键不存在或值非 dict 则返回 None

        示例:
            data = await ctx.db.get("user_settings")
            if data:
                print(data["theme"])
        """
        output = await self._proxy.call("db.get", {"key": key})
        value = output.get("value")
        return value if isinstance(value, dict) else None

    async def set(self, key: str, value: dict[str, Any]) -> None:
        """设置键值对。

        Args:
            key: 数据键名
            value: 要存储的字典值

        示例:
            await ctx.db.set("user_settings", {"theme": "dark", "lang": "zh"})
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
        return [str(item) for item in output.get("keys", [])]
