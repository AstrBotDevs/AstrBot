from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from astrbot.core.platform.astr_message_event import AstrMessageEvent

if TYPE_CHECKING:
    from .chain_config import ChainConfig


@dataclass
class WaitState:
    chain_config: ChainConfig
    node_uuid: str

    def is_valid(self, current_chain_config: ChainConfig | None) -> bool:
        """检查 WaitState 是否仍然有效"""
        if current_chain_config is None:
            return False

        if current_chain_config != self.chain_config:
            return False

        return True


def build_wait_key(event: AstrMessageEvent) -> str:
    """Build a stable wait key that is independent of preprocessing."""
    return (
        f"{event.get_platform_id()}:"
        f"{event.get_message_type().value}:"
        f"{event.get_sender_id()}:"
        f"{event.get_group_id()}"
    )


class WaitRegistry:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._by_key: dict[str, WaitState] = {}

    async def set(self, key: str, state: WaitState) -> None:
        async with self._lock:
            self._by_key[key] = state

    async def pop(self, key: str) -> WaitState | None:
        async with self._lock:
            return self._by_key.pop(key, None)


wait_registry = WaitRegistry()
