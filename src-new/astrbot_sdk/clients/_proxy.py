from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from ..errors import AstrBotError


class CapabilityProxy:
    def __init__(self, peer) -> None:
        self._peer = peer

    def _get_descriptor(self, name: str):
        return self._peer.remote_capability_map.get(name)

    def _ensure_available(self, name: str, *, stream: bool) -> None:
        descriptor = self._get_descriptor(name)
        if descriptor is None:
            if self._peer.remote_capability_map:
                raise AstrBotError.capability_not_found(name)
            return
        if stream and not descriptor.supports_stream:
            raise AstrBotError.invalid_input(f"{name} 不支持 stream=true")
        if not stream and descriptor.supports_stream is False:
            return

    async def call(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._ensure_available(name, stream=False)
        return await self._peer.invoke(name, payload, stream=False)

    async def stream(
        self,
        name: str,
        payload: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        self._ensure_available(name, stream=True)
        event_stream = await self._peer.invoke_stream(name, payload)
        async for event in event_stream:
            if event.phase == "delta":
                yield event.data
