from __future__ import annotations

from typing import Any

from ._proxy import CapabilityProxy


class DBClient:
    def __init__(self, proxy: CapabilityProxy) -> None:
        self._proxy = proxy

    async def get(self, key: str) -> dict[str, Any] | None:
        output = await self._proxy.call("db.get", {"key": key})
        value = output.get("value")
        return value if isinstance(value, dict) else None

    async def set(self, key: str, value: dict[str, Any]) -> None:
        await self._proxy.call("db.set", {"key": key, "value": value})

    async def delete(self, key: str) -> None:
        await self._proxy.call("db.delete", {"key": key})

    async def list(self, prefix: str | None = None) -> list[str]:
        output = await self._proxy.call("db.list", {"prefix": prefix})
        return [str(item) for item in output.get("keys", [])]
