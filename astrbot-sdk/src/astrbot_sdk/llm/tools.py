from __future__ import annotations

from typing import TYPE_CHECKING

from .entities import LLMToolSpec

if TYPE_CHECKING:
    from ..clients._proxy import CapabilityProxy


class LLMToolManager:
    def __init__(self, proxy: CapabilityProxy) -> None:
        self._proxy = proxy

    async def list_registered(self) -> list[LLMToolSpec]:
        output = await self._proxy.call("llm_tool.manager.get", {})
        items = output.get("registered")
        if not isinstance(items, list):
            return []
        return [
            LLMToolSpec.from_payload(item) for item in items if isinstance(item, dict)
        ]

    async def list_active(self) -> list[LLMToolSpec]:
        output = await self._proxy.call("llm_tool.manager.get", {})
        items = output.get("active")
        if not isinstance(items, list):
            return []
        return [
            LLMToolSpec.from_payload(item) for item in items if isinstance(item, dict)
        ]

    async def activate(self, name: str) -> bool:
        output = await self._proxy.call("llm_tool.manager.activate", {"name": name})
        return bool(output.get("activated", False))

    async def deactivate(self, name: str) -> bool:
        output = await self._proxy.call("llm_tool.manager.deactivate", {"name": name})
        return bool(output.get("deactivated", False))

    async def add(self, *tools: LLMToolSpec) -> list[str]:
        output = await self._proxy.call(
            "llm_tool.manager.add",
            {"tools": [tool.to_payload() for tool in tools]},
        )
        result = output.get("names")
        if not isinstance(result, list):
            return []
        return [str(item) for item in result]

    async def remove(self, name: str) -> bool:
        output = await self._proxy.call("llm_tool.manager.remove", {"name": name})
        return bool(output.get("removed", False))

    async def get(self, name: str) -> LLMToolSpec | None:
        for tool in await self.list_registered():
            if tool.name == name:
                return tool
        return None
