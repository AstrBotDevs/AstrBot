from __future__ import annotations

import asyncio
from collections import OrderedDict
from typing import TYPE_CHECKING

from astrbot import logger
from astrbot.core.umo_alias import get_event_auto_name, normalize_umo_name

if TYPE_CHECKING:
    from astrbot.core.db import BaseDatabase
    from astrbot.core.platform.astr_message_event import AstrMessageEvent

MAX_UMO_AUTO_NAME_CACHE_SIZE = 10_000


class UmoAutoNameRecorder:
    """Persist changed session and sender names without blocking waking."""

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
        self._sender_cache: OrderedDict[tuple[str, str], str] = OrderedDict()
        self._sender_pending: OrderedDict[tuple[str, str], tuple[str, str]] = (
            OrderedDict()
        )
        self._writer_task: asyncio.Task[None] | None = None

    def schedule(self, event: AstrMessageEvent) -> None:
        """Queue changed session and sender names from an awakened event.

        Args:
            event: Awakened event containing the UMO and display metadata.
        """
        if self.db_helper is None:
            return

        umo = event.unified_msg_origin
        auto_name = get_event_auto_name(event, fallback_to_id=False)
        sender_id = str(event.get_sender_id() or "")
        sender_name = normalize_umo_name(event.get_sender_name())
        # Sender changes must be recorded even when the group name is unchanged.
        for key, name, cache, pending in (
            (umo, auto_name, self._cache, self._pending),
            ((umo, sender_id), sender_name, self._sender_cache, self._sender_pending),
        ):
            is_sender = isinstance(key, tuple)
            if (is_sender and not sender_id) or (not is_sender and not name):
                continue
            cached_name = cache.get(key)
            if cached_name == name or (not name and cached_name):
                cache.move_to_end(key)
                continue

            cache[key] = name
            cache.move_to_end(key)
            if len(cache) > MAX_UMO_AUTO_NAME_CACHE_SIZE:
                cache.popitem(last=False)

            pending[key] = (sender_id, name)
            pending.move_to_end(key)
            if len(pending) > MAX_UMO_AUTO_NAME_CACHE_SIZE:
                dropped_key, (_, dropped_name) = pending.popitem(last=False)
                if cache.get(dropped_key) == dropped_name:
                    cache.pop(dropped_key, None)

        if (self._pending or self._sender_pending) and (
            self._writer_task is None or self._writer_task.done()
        ):
            task = asyncio.create_task(
                self._flush(),
                name=f"umo_auto_name_writer:{self.config_id}",
            )
            self._writer_task = task
            task.add_done_callback(self._on_writer_done)

    async def _flush(self) -> None:
        """Persist queued names sequentially, coalescing changes per identity."""
        if self.db_helper is None:
            return

        try:
            while self._pending or self._sender_pending:
                is_sender = not self._pending
                pending = self._sender_pending if is_sender else self._pending
                cache = self._sender_cache if is_sender else self._cache
                key, (sender_id, name) = pending.popitem(last=False)
                umo = key[0] if is_sender else key
                try:
                    if is_sender:
                        await self.db_helper.upsert_umo_sender(
                            umo=umo, sender_id=sender_id, sender_name=name
                        )
                    else:
                        await self.db_helper.upsert_umo_auto_name(
                            umo=umo, creator_sender_id=sender_id, auto_name=name
                        )
                except Exception as exc:
                    logger.warning(
                        "Failed to persist session or sender name for %s: %s",
                        key,
                        exc,
                    )
                    if key not in pending and cache.get(key) == name:
                        cache.pop(key, None)
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
