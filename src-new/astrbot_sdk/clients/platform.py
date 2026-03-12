from __future__ import annotations

from typing import Any

from ._proxy import CapabilityProxy


class PlatformClient:
    def __init__(self, proxy: CapabilityProxy) -> None:
        self._proxy = proxy

    async def send(self, session: str, text: str) -> dict[str, Any]:
        return await self._proxy.call(
            "platform.send",
            {"session": session, "text": text},
        )

    async def send_image(self, session: str, image_url: str) -> dict[str, Any]:
        return await self._proxy.call(
            "platform.send_image",
            {"session": session, "image_url": image_url},
        )

    async def get_members(self, session: str) -> list[dict[str, Any]]:
        output = await self._proxy.call("platform.get_members", {"session": session})
        return list(output.get("members", []))
