from __future__ import annotations

from typing import Protocol

from astrbot.core.computer.booters.base import ComputerBooter
from astrbot.core.star.context import Context


class SandboxProvider(Protocol):
    provider_id: str

    def build_create_config(self, context: Context, session_id: str) -> dict: ...

    async def create_booter(
        self,
        context: Context,
        session_id: str,
        sandbox_id: str,
        config: dict,
    ) -> ComputerBooter: ...

    async def destroy_booter(self, booter: ComputerBooter, record: dict) -> None: ...
