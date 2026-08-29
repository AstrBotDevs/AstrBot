from contextlib import AbstractAsyncContextManager
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from astrbot.core.db.protocols import DatabaseSessionStore


class DatabaseStoreMixin:
    """Runtime mixin host. Session access is typed through ``store_session``."""


def store_session(store: object) -> AbstractAsyncContextManager[AsyncSession]:
    """Return the host database session context manager."""
    return cast(DatabaseSessionStore, store).get_db()
