from __future__ import annotations

import asyncio
from collections import OrderedDict
from typing import TYPE_CHECKING

from astrbot import logger
from astrbot.core.umo_alias import get_event_auto_name

if TYPE_CHECKING:
    from astrbot.core.db import BaseDatabase
    from astrbot.core.platform.astr_message_event import AstrMessageEvent

MAX_UMO_AUTO_NAME_CACHE_SIZE = 10_000


class UmoAutoNameRecorder:
    """Persist changed UMO names without blocking the waking stage."""

    def __init__(
        self,
        db_helper: BaseDatabase | None,
        config_id: str,
    ) -> None:
        """Initialize the bounded cache and background writer state.

        Args:
            db_helper: Database used to persist automatic names.
            config_id: Pipeline configuration identifier used in the task name.
        """
        self.db_helper = db_helper
        self.config_id = config_id
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._pending: OrderedDict[str, tuple[str, str]] = OrderedDict()
        self._writer_task: asyncio.Task[None] | None = None

    def schedule(self, event: AstrMessageEvent) -> None:
        """Queue a changed automatic name from an awakened event.

        Args:
            event: Awakened event containing the UMO and display metadata.
        """
        if self.db_helper is None:
            return

        umo = event.unified_msg_origin
        auto_name = get_event_auto_name(event, fallback_to_id=False)
        if not auto_name:
            return
        if self._cache.get(umo) == auto_name:
            self._cache.move_to_end(umo)
            return

        self._cache[umo] = auto_name
        self._cache.move_to_end(umo)
        if len(self._cache) > MAX_UMO_AUTO_NAME_CACHE_SIZE:
            self._cache.popitem(last=False)

        self._pending[umo] = (str(event.get_sender_id() or ""), auto_name)
        self._pending.move_to_end(umo)
        if len(self._pending) > MAX_UMO_AUTO_NAME_CACHE_SIZE:
            dropped_umo, (_, dropped_name) = self._pending.popitem(last=False)
            if self._cache.get(dropped_umo) == dropped_name:
                self._cache.pop(dropped_umo, None)

        if self._writer_task is None or self._writer_task.done():
            task = asyncio.create_task(
                self._flush(),
                name=f"umo_auto_name_writer:{self.config_id}",
            )
            self._writer_task = task
            task.add_done_callback(self._on_writer_done)

    async def _flush(self) -> None:
        """Persist queued names sequentially, coalescing changes per UMO."""
        if self.db_helper is None:
            return

        try:
            while self._pending:
                umo, (creator_sender_id, auto_name) = self._pending.popitem(last=False)
                try:
                    await self.db_helper.upsert_umo_auto_name(
                        umo=umo,
                        creator_sender_id=creator_sender_id,
                        auto_name=auto_name,
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to persist automatic UMO name for %s: %s",
                        umo,
                        exc,
                    )
                    if umo not in self._pending and self._cache.get(umo) == auto_name:
                        self._cache.pop(umo, None)
        finally:
            self._writer_task = None

    @staticmethod
    def _on_writer_done(task: asyncio.Task[None]) -> None:
        """Expose unexpected writer failures.

        Args:
            task: Completed automatic-name writer task.
        """
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("UMO automatic-name writer failed.", exc_info=exc)
