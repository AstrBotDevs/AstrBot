from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._proxy import CapabilityProxy


@dataclass(slots=True)
class FileRegistration:
    token: str
    url: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> FileRegistration:
        return cls(
            token=str(payload.get("token", "")),
            url=str(payload.get("url", "")),
        )


class FileServiceClient:
    def __init__(self, proxy: CapabilityProxy) -> None:
        self._proxy = proxy

    async def register_file(
        self,
        path: str,
        timeout: float | None = None,
    ) -> str:
        output = await self._proxy.call(
            "system.file.register",
            {"path": str(path), "timeout": timeout},
        )
        return FileRegistration.from_payload(output).token

    async def handle_file(self, token: str) -> str:
        output = await self._proxy.call(
            "system.file.handle",
            {"token": str(token)},
        )
        return str(output.get("path", ""))

    async def _register_file_url(
        self,
        path: str,
        timeout: float | None = None,
    ) -> str:
        output = await self._proxy.call(
            "system.file.register",
            {"path": str(path), "timeout": timeout},
        )
        return FileRegistration.from_payload(output).url
