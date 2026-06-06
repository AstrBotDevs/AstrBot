from collections.abc import Sequence

import pytest
from sqlalchemy.exc import OperationalError

from astrbot.core.db import sqlite
from astrbot.core.db.po import Preference


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def all(self):
        return self.value


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _LockedOnceSession:
    def __init__(self, value, message: str = "database is locked"):
        self.value = value
        self.message = message
        self.attempts = 0

    async def execute(self, query):
        self.attempts += 1
        if self.attempts == 1:
            raise OperationalError(
                "select from preferences", {}, Exception(self.message)
            )
        return _ScalarResult(self.value)


@pytest.mark.asyncio
async def test_get_preference_retries_sqlite_database_lock(
    temp_db,
    monkeypatch: pytest.MonkeyPatch,
):
    preference = Preference(
        scope="global",
        scope_id="global",
        key="migration_done",
        value={"val": True},
    )
    session = _LockedOnceSession(preference)
    sleep_delays = []

    async def record_sleep(delay: float) -> None:
        sleep_delays.append(delay)

    monkeypatch.setattr(temp_db, "get_db", lambda: _SessionContext(session))
    monkeypatch.setattr(sqlite.asyncio, "sleep", record_sleep)

    result = await temp_db.get_preference("global", "global", "migration_done")

    assert result == preference
    assert session.attempts == 2
    assert sleep_delays == [sqlite.SQLITE_LOCK_RETRY_BASE_DELAY]


@pytest.mark.asyncio
async def test_get_preferences_retries_sqlite_database_lock(
    temp_db,
    monkeypatch: pytest.MonkeyPatch,
):
    preferences: Sequence[Preference] = [
        Preference(
            scope="global",
            scope_id="global",
            key="migration_done",
            value={"val": True},
        ),
    ]
    session = _LockedOnceSession(preferences, "database table is locked")

    async def no_sleep(delay: float) -> None:
        return None

    monkeypatch.setattr(temp_db, "get_db", lambda: _SessionContext(session))
    monkeypatch.setattr(sqlite.asyncio, "sleep", no_sleep)

    result = await temp_db.get_preferences("global")

    assert result == preferences
    assert session.attempts == 2


@pytest.mark.asyncio
async def test_get_preference_does_not_retry_other_operational_errors(
    temp_db,
    monkeypatch: pytest.MonkeyPatch,
):
    session = _LockedOnceSession(None, "no such table: preferences")
    sleep_delays = []

    async def record_sleep(delay: float) -> None:
        sleep_delays.append(delay)

    monkeypatch.setattr(temp_db, "get_db", lambda: _SessionContext(session))
    monkeypatch.setattr(sqlite.asyncio, "sleep", record_sleep)

    with pytest.raises(OperationalError):
        await temp_db.get_preference("global", "global", "migration_done")

    assert session.attempts == 1
    assert sleep_delays == []
