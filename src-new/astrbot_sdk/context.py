"""v4 原生运行时上下文。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from loguru import logger as base_logger

from .clients import DBClient, LLMClient, MemoryClient, PlatformClient
from .clients._proxy import CapabilityProxy


@dataclass(slots=True)
class CancelToken:
    _cancelled: asyncio.Event

    def __init__(self) -> None:
        self._cancelled = asyncio.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    async def wait(self) -> None:
        await self._cancelled.wait()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise asyncio.CancelledError


class Context:
    def __init__(
        self,
        *,
        peer,
        plugin_id: str,
        cancel_token: CancelToken | None = None,
        logger: Any | None = None,
    ) -> None:
        proxy = CapabilityProxy(peer)
        self.llm = LLMClient(proxy)
        self.memory = MemoryClient(proxy)
        self.db = DBClient(proxy)
        self.platform = PlatformClient(proxy)
        self.plugin_id = plugin_id
        self.logger = logger or base_logger.bind(plugin_id=plugin_id)
        self.cancel_token = cancel_token or CancelToken()
