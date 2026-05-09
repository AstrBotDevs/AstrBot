from __future__ import annotations

from typing import Protocol

from astrbot.core.computer.booters.base import ComputerBooter
from astrbot.core.star.context import Context


class SandboxProvider(Protocol):
    provider_id: str
    capabilities: set[str]
    tool_names: set[str]

    def build_create_config(self, context: Context, session_id: str) -> dict: ...

    def build_connect_info(self, sandbox_name: str, config: dict) -> dict: ...

    def update_connect_info(self, record: dict, *, sandbox_name: str) -> dict: ...

    def get_idle_timeout(self, context: Context, session_id: str) -> float: ...

    async def create_booter(
        self,
        context: Context,
        session_id: str,
        sandbox_id: str,
        config: dict,
    ) -> ComputerBooter: ...

    async def destroy_booter(self, booter: ComputerBooter, record: dict) -> None: ...
