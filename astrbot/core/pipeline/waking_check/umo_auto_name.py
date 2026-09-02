from __future__ import annotations

import asyncio
from collections import OrderedDict
from typing import TYPE_CHECKING

from astrbot import logger
from astrbot.core.umo_alias import get_event_auto_name
from astrbot.core.utils.task_utils import create_tracked_task

if TYPE_CHECKING:
    from astrbot.core.db.protocols import UmoAliasStore
    from astrbot.core.platform.astr_message_event import AstrMessageEvent

MAX_UMO_AUTO_NAME_CACHE_SIZE = 10_000


class UmoAutoNameRecorder:
    """Persist changed UMO names without blocking the waking stage."""

    def __init__(
        self,
        store: UmoAliasStore | None,
        config_id: str,
        background_tasks: set[asyncio.Task] | None = None,
    ) -> None:
        """Initialize the bounded cache and background writer state.

        Args:
            store: Persistence used to write automatic names.
            config_id: Pipeline configuration identifier used in the task name.
            background_tasks: Lifecycle-owned task set. Local set is used in tests.
        """
        self.store = store
        self.config_id = config_id
        self._background_tasks = (
            background_tasks if background_tasks is not None else set()
        )
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._pending: OrderedDict[str, tuple[str, str]] = OrderedDict()
        self._writer_task: asyncio.Task[None] | None = None

    def schedule(self, event: AstrMessageEvent) -> None:
        """Queue a changed automatic name from an awakened event.

        Args:
            event: Awakened event containing the UMO and display metadata.
        """
        if self.store is None:
            return

        umo = event.unified_msg_origin
        auto_name = get_event_auto_name(event, fallback_to_id=False)
        if not auto_name:
            return
        if self._cache.get(umo) == auto_name:
            self._cache.move_to_end(umo)
            if self._pending:
                self._ensure_writer()
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

        self._ensure_writer()

    def _ensure_writer(self) -> None:
        """Start a background writer when none is running."""
        if self.store is None:
            return
        current = asyncio.current_task()
        if current is not None and current.cancelling():
            return
        if self._writer_task is None or self._writer_task.done():
            self._writer_task = create_tracked_task(
                self._background_tasks,
                self._flush(),
                name=f"umo_auto_name_writer:{self.config_id}",
            )

    async def _flush(self) -> None:
        """Persist queued names sequentially, coalescing changes per UMO."""
        if self.store is None:
            return

        try:
            while self._pending:
                umo, (creator_sender_id, auto_name) = self._pending.popitem(last=False)
                try:
                    await self.store.upsert_umo_auto_name(
                        umo=umo,
                        creator_sender_id=creator_sender_id,
                        auto_name=auto_name,
                    )
                except asyncio.CancelledError:
                    if umo not in self._pending and self._cache.get(umo) == auto_name:
                        self._cache.pop(umo, None)
                    raise
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
            if self._pending:
                self._ensure_writer()
