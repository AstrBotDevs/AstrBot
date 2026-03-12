from __future__ import annotations

from typing import Any

from ._proxy import CapabilityProxy


class MemoryClient:
    def __init__(self, proxy: CapabilityProxy) -> None:
        self._proxy = proxy

    async def search(self, query: str) -> list[dict[str, Any]]:
        output = await self._proxy.call("memory.search", {"query": query})
        return list(output.get("items", []))

    async def save(self, key: str, value: dict[str, Any]) -> None:
        await self._proxy.call("memory.save", {"key": key, "value": value})

    async def delete(self, key: str) -> None:
        await self._proxy.call("memory.delete", {"key": key})
