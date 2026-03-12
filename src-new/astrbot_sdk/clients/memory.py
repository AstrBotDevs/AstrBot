from __future__ import annotations

from typing import Any

from ._proxy import CapabilityProxy


class MemoryClient:
    def __init__(self, proxy: CapabilityProxy) -> None:
        self._proxy = proxy

    async def search(self, query: str) -> list[dict[str, Any]]:
        output = await self._proxy.call("memory.search", {"query": query})
        return list(output.get("items", []))

    async def save(
        self,
        key: str,
        value: dict[str, Any] | None = None,
        **extra: Any,
    ) -> None:
        if value is not None and not isinstance(value, dict):
            raise TypeError("memory.save 的 value 必须是 dict")
        payload = dict(value or {})
        if extra:
            payload.update(extra)
        await self._proxy.call("memory.save", {"key": key, "value": payload})

    async def get(self, key: str) -> dict[str, Any] | None:
        """精确获取：通过唯一键获取单个记忆项。

        Args:
            key: 记忆项的唯一键

        Returns:
            记忆项内容，若不存在则返回 None
        """
        output = await self._proxy.call("memory.get", {"key": key})
        value = output.get("value")
        return value if isinstance(value, dict) else None

    async def delete(self, key: str) -> None:
        await self._proxy.call("memory.delete", {"key": key})
