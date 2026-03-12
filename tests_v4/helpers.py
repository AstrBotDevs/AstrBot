from __future__ import annotations

import asyncio
from pathlib import Path

from astrbot_sdk.runtime.transport import Transport


class MemoryTransport(Transport):
    def __init__(self) -> None:
        super().__init__()
        self.partner: "MemoryTransport | None" = None

    async def start(self) -> None:
        self._closed.clear()

    async def stop(self) -> None:
        self._closed.set()

    async def send(self, payload: str) -> None:
        if self.partner is None:
            raise RuntimeError("MemoryTransport 未连接 partner")
        await self.partner._dispatch(payload)


def make_transport_pair() -> tuple[MemoryTransport, MemoryTransport]:
    left = MemoryTransport()
    right = MemoryTransport()
    left.partner = right
    right.partner = left
    return left, right


class FakeEnvManager:
    def prepare_environment(self, _plugin) -> Path:
        return Path(__import__("sys").executable)


async def drain_loop() -> None:
    await asyncio.sleep(0.05)
