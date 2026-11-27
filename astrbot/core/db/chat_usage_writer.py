"""Batch chat request statistics without making model calls wait for SQLite."""

from __future__ import annotations

import asyncio
from contextvars import Context
from time import monotonic
from typing import TYPE_CHECKING

from sqlalchemy import insert

from astrbot import logger
from astrbot.core.db.po import ChatRequestStat

if TYPE_CHECKING:
    from astrbot.core.db import BaseDatabase

QUEUE_CAPACITY = 1024
BATCH_SIZE = 64


class ChatUsageWriter:
    """Persist request statistics in bounded batches on the database's event loop."""

    def __init__(self, db: BaseDatabase) -> None:
        self._db = db
        self._queue: asyncio.Queue[ChatRequestStat] = asyncio.Queue(QUEUE_CAPACITY)
        self._task: asyncio.Task[None] | None = None
        self._closed = False
        self._warn_after = 0.0

    def enqueue(self, record: ChatRequestStat) -> None:
        """Queue a completed request without waiting for database capacity.

        Args:
            record: Usage and attribution captured by the provider wrapper.
        """
        if self._closed:
            return
        try:
            self._queue.put_nowait(record)
        except asyncio.QueueFull:
            now = monotonic()
            if now >= self._warn_after:
                self._warn_after = now + 30
                logger.warning("Chat usage queue is full. Dropping new records.")
            return
        if self._task is None or self._task.done():
            self._task = Context().run(
                asyncio.create_task, self._write_batches(), name="chat_usage_writer"
            )

    async def _write_batches(self) -> None:
        """Commit batches and exit when the queue is empty."""
        while not self._queue.empty():
            batch = [
                self._queue.get_nowait()
                for _ in range(min(BATCH_SIZE, self._queue.qsize()))
            ]
            try:
                async with self._db.get_db() as session, session.begin():
                    await session.execute(
                        insert(ChatRequestStat.__table__),
                        [record.model_dump(exclude={"id"}) for record in batch],
                    )
            except Exception:
                logger.warning(
                    "Could not persist %d chat usage records.",
                    len(batch),
                    exc_info=True,
                )
            finally:
                for _ in batch:
                    self._queue.task_done()

    async def flush(self) -> None:
        """Wait for queued writes before deleting their database rows."""
        await self._queue.join()

    async def close(self) -> None:
        """Stop accepting records and finish any queued transactions."""
        self._closed = True
        if self._task is not None:
            await asyncio.shield(self._task)
