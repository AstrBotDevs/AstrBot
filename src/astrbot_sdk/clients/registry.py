"""只读 handler 注册表客户端。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ._proxy import CapabilityProxy


@dataclass(slots=True)
class HandlerMetadata:
    plugin_name: str
    handler_full_name: str
    trigger_type: str
    event_types: list[str] = field(default_factory=list)
    enabled: bool = True
    group_path: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HandlerMetadata:
        return cls(
            plugin_name=str(data.get("plugin_name", "")),
            handler_full_name=str(data.get("handler_full_name", "")),
            trigger_type=str(data.get("trigger_type", "")),
            event_types=[
                str(item)
                for item in data.get("event_types", [])
                if isinstance(item, str)
            ],
            enabled=bool(data.get("enabled", True)),
            group_path=[
                str(item)
                for item in data.get("group_path", [])
                if isinstance(item, str)
            ],
        )


class RegistryClient:
    def __init__(self, proxy: CapabilityProxy) -> None:
        self._proxy = proxy

    async def get_handlers_by_event_type(
        self,
        event_type: str,
    ) -> list[HandlerMetadata]:
        output = await self._proxy.call(
            "registry.get_handlers_by_event_type",
            {"event_type": event_type},
        )
        return [
            HandlerMetadata.from_dict(item)
            for item in output.get("handlers", [])
            if isinstance(item, dict)
        ]

    async def get_handler_by_full_name(
        self,
        full_name: str,
    ) -> HandlerMetadata | None:
        output = await self._proxy.call(
            "registry.get_handler_by_full_name",
            {"full_name": full_name},
        )
        handler = output.get("handler")
        if not isinstance(handler, dict):
            return None
        return HandlerMetadata.from_dict(handler)

    async def set_handler_whitelist(
        self,
        plugin_names: list[str] | set[str] | None,
    ) -> list[str] | None:
        names = None
        if plugin_names is not None:
            names = sorted({str(item) for item in plugin_names if str(item).strip()})
        output = await self._proxy.call(
            "system.event.handler_whitelist.set",
            {"plugin_names": names},
        )
        result = output.get("plugin_names")
        if not isinstance(result, list):
            return None
        return [str(item) for item in result]

    async def get_handler_whitelist(self) -> list[str] | None:
        output = await self._proxy.call("system.event.handler_whitelist.get", {})
        result = output.get("plugin_names")
        if not isinstance(result, list):
            return None
        return [str(item) for item in result]

    async def clear_handler_whitelist(self) -> None:
        await self._proxy.call(
            "system.event.handler_whitelist.set",
            {"plugin_names": None},
        )


__all__ = ["HandlerMetadata", "RegistryClient"]
