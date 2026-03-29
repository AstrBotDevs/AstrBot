"""文件服务客户端。

提供文件令牌注册和令牌反查能力，封装 `system.file.*` capabilities。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._proxy import CapabilityProxy


@dataclass(slots=True)
class FileRegistration:
    """文件注册结果。"""

    token: str
    url: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> FileRegistration:
        return cls(
            token=str(payload.get("token", "")),
            url=str(payload.get("url", "")),
        )


class FileServiceClient:
    """文件服务能力客户端。"""

    def __init__(self, proxy: CapabilityProxy) -> None:
        self._proxy = proxy

    async def _register(
        self,
        path: str,
        *,
        timeout: float | None,
    ) -> FileRegistration:
        output = await self._proxy.call(
            "system.file.register",
            {"path": str(path), "timeout": timeout},
        )
        return FileRegistration.from_payload(output)

    async def register_file(
        self,
        path: str,
        timeout: float | None = None,
    ) -> str:
        """注册本地文件并返回文件令牌。"""

        return (await self._register(path, timeout=timeout)).token

    async def register_file_url(
        self,
        path: str,
        timeout: float | None = None,
    ) -> str:
        """注册本地文件并返回公开访问 URL。"""

        return (await self._register(path, timeout=timeout)).url

    async def handle_file(self, token: str) -> str:
        """将文件令牌解析回本地文件路径。"""

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
        return await self.register_file_url(path, timeout=timeout)
