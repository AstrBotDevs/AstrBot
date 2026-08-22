"""Database engine and session lifecycle ownership."""

import abc
import asyncio
import threading
import typing as T
from contextlib import asynccontextmanager
from weakref import WeakSet

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_AIOSQLITE_JOIN_TIMEOUT_SEC = 1.0


def is_aiosqlite_worker_thread(thread: threading.Thread) -> bool:
    """Return whether a thread is an aiosqlite connection worker."""
    target = getattr(thread, "_target", None)
    return (
        getattr(target, "__name__", None) == "_connection_worker_thread"
        and getattr(target, "__module__", "") == "aiosqlite.core"
    )


def _aiosqlite_worker_thread(dbapi_connection: object) -> threading.Thread | None:
    raw = getattr(dbapi_connection, "_connection", None)
    thread = getattr(raw, "_thread", None)
    if isinstance(thread, threading.Thread):
        return thread
    return None


def track_aiosqlite_workers(engine: AsyncEngine) -> WeakSet[threading.Thread]:
    """Record aiosqlite worker threads created for an async engine."""
    workers: WeakSet[threading.Thread] = WeakSet()

    def _capture(dbapi_connection: object, *_args: object) -> None:
        thread = _aiosqlite_worker_thread(dbapi_connection)
        if thread is not None:
            workers.add(thread)

    event.listen(engine.sync_engine, "connect", _capture)
    event.listen(engine.sync_engine, "checkout", _capture)
    return workers


async def dispose_async_engine(
    engine: AsyncEngine,
    workers: WeakSet[threading.Thread] | None = None,
) -> None:
    """Dispose an async engine and join the aiosqlite workers it owned.

    aiosqlite completes ``close()`` after the stop sentinel is queued, but the
    worker thread can still be alive for a short interval. Tests and process
    shutdown treat that thread as leaked unless close waits for it to exit.
    """
    pending = [thread for thread in list(workers or ()) if thread.is_alive()]
    await engine.dispose()
    if not pending:
        return
    loop = asyncio.get_running_loop()
    await asyncio.gather(
        *(
            loop.run_in_executor(None, thread.join, _AIOSQLITE_JOIN_TIMEOUT_SEC)
            for thread in pending
            if thread.is_alive()
        )
    )


class BaseDatabase(abc.ABC):
    """Own the database engine, session factory, and their lifecycle."""

    DATABASE_URL = ""

    def __init__(self) -> None:
        # SQLite only supports a single writer at a time. Without a busy
        # timeout the driver raises "database is locked" instantly when a
        # second write is attempted. Setting timeout=30 tells SQLite to wait
        # up to 30 s for the lock, which is enough for brief write bursts.
        is_sqlite = "sqlite" in self.DATABASE_URL
        connect_args = {"timeout": 30} if is_sqlite else {}
        self.engine = create_async_engine(
            self.DATABASE_URL,
            echo=False,
            future=True,
            connect_args=connect_args,
        )
        self._aiosqlite_workers = track_aiosqlite_workers(self.engine)
        self.AsyncSessionLocal = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._active_sessions: WeakSet[AsyncSession] = WeakSet()
        self._init_lock = asyncio.Lock()
        self.inited = False

    @abc.abstractmethod
    async def initialize(self) -> None:
        """Initialize the database schema and connection settings."""

    @asynccontextmanager
    async def get_db(self) -> T.AsyncGenerator[AsyncSession]:
        """Yield a tracked database session."""
        if not self.inited:
            await self.initialize()
        session = self.AsyncSessionLocal()
        self._active_sessions.add(session)
        try:
            yield session
        finally:
            try:
                await session.close()
            finally:
                self._active_sessions.discard(session)

    async def close(self) -> None:
        """Close tracked sessions and dispose the database engine."""
        for session in list(self._active_sessions):
            try:
                await session.close()
            finally:
                self._active_sessions.discard(session)
        await dispose_async_engine(self.engine, self._aiosqlite_workers)
        self.inited = False
