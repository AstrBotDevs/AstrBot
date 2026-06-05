from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import OperationalError

from astrbot.core.db.po import ConversationV2, PlatformMessageHistory
from astrbot.core.db.sqlite import SQLiteDatabase


def _operational_error(message: str) -> OperationalError:
    return OperationalError("update conversations", {}, Exception(message))


@pytest.mark.asyncio
async def test_run_in_tx_retries_sqlite_database_locked(monkeypatch, tmp_path):
    db = SQLiteDatabase(str(tmp_path / "retry.db"))
    attempts = 0
    sleep_delays = []

    async def record_sleep(attempt: int) -> None:
        sleep_delays.append(attempt)

    monkeypatch.setattr(db, "_sleep_before_locked_retry", record_sleep)

    async def op(session):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _operational_error("database is locked")
        return "ok"

    assert await db._run_in_tx(op) == "ok"
    assert attempts == 2
    assert sleep_delays == [0]

    await db.engine.dispose()


@pytest.mark.asyncio
async def test_update_conversation_noop_returns_none_without_retrying_tx(
    monkeypatch,
    tmp_path,
):
    db = SQLiteDatabase(str(tmp_path / "noop-update-conversation.db"))
    run_in_tx = AsyncMock()
    get_conversation_by_id = AsyncMock()

    monkeypatch.setattr(db, "_run_in_tx", run_in_tx)
    monkeypatch.setattr(db, "get_conversation_by_id", get_conversation_by_id)

    assert await db.update_conversation("conv-1") is None
    run_in_tx.assert_not_awaited()
    get_conversation_by_id.assert_not_awaited()

    await db.engine.dispose()


@pytest.mark.asyncio
async def test_insert_platform_message_history_uses_retrying_transaction(
    monkeypatch,
    tmp_path,
):
    db = SQLiteDatabase(str(tmp_path / "platform-message-history.db"))
    history = PlatformMessageHistory(
        id=1,
        platform_id="webchat",
        user_id="webchat-user",
        content={"type": "text", "text": "hello"},
    )
    run_in_tx = AsyncMock(return_value=history)

    monkeypatch.setattr(db, "_run_in_tx", run_in_tx)

    result = await db.insert_platform_message_history(
        platform_id="webchat",
        user_id="webchat-user",
        content={"type": "text", "text": "hello"},
    )

    assert result is history
    run_in_tx.assert_awaited_once()

    await db.engine.dispose()


@pytest.mark.asyncio
async def test_update_platform_message_history_uses_retrying_transaction(
    monkeypatch,
    tmp_path,
):
    db = SQLiteDatabase(str(tmp_path / "update-platform-message-history.db"))
    run_in_tx = AsyncMock(return_value=None)

    monkeypatch.setattr(db, "_run_in_tx", run_in_tx)

    await db.update_platform_message_history(
        1,
        content={"type": "text", "text": "updated"},
    )

    run_in_tx.assert_awaited_once()

    await db.engine.dispose()


@pytest.mark.asyncio
async def test_run_in_tx_retries_sqlite_database_table_locked(monkeypatch, tmp_path):
    db = SQLiteDatabase(str(tmp_path / "retry-table.db"))
    attempts = 0

    async def no_sleep(attempt: int) -> None:
        return None

    monkeypatch.setattr(db, "_sleep_before_locked_retry", no_sleep)

    async def op(session):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _operational_error("database table is locked")
        return SimpleNamespace(value="ok")

    result = await db._run_in_tx(op)

    assert result.value == "ok"
    assert attempts == 2

    await db.engine.dispose()


@pytest.mark.asyncio
async def test_run_in_tx_reraises_after_sqlite_locked_retries_exhausted(
    monkeypatch,
    tmp_path,
):
    db = SQLiteDatabase(str(tmp_path / "retry-exhausted.db"))
    attempts = 0
    sleep_delays = []

    async def record_sleep(attempt: int) -> None:
        sleep_delays.append(attempt)

    monkeypatch.setattr(db, "_sleep_before_locked_retry", record_sleep)

    async def op(session):
        nonlocal attempts
        attempts += 1
        raise _operational_error("database is locked")

    with pytest.raises(OperationalError):
        await db._run_in_tx(op)

    assert attempts == 2
    assert sleep_delays == [0]

    await db.engine.dispose()


@pytest.mark.asyncio
async def test_run_in_tx_does_not_retry_other_operational_errors(
    monkeypatch,
    tmp_path,
):
    db = SQLiteDatabase(str(tmp_path / "no-retry.db"))
    attempts = 0

    async def fail_on_sleep(attempt: int) -> None:
        raise AssertionError("sleep should not be called")

    monkeypatch.setattr(db, "_sleep_before_locked_retry", fail_on_sleep)

    async def op(session):
        nonlocal attempts
        attempts += 1
        raise _operational_error("no such table: conversations")

    with pytest.raises(OperationalError):
        await db._run_in_tx(op)

    assert attempts == 1

    await db.engine.dispose()


@pytest.mark.asyncio
async def test_update_conversation_uses_retrying_transaction(monkeypatch, tmp_path):
    db = SQLiteDatabase(str(tmp_path / "update-conversation.db"))
    conversation = ConversationV2(
        conversation_id="conv-1",
        platform_id="webchat",
        user_id="webchat:FriendMessage:user-1",
        content=[{"role": "user", "content": "old"}],
    )
    run_in_tx = AsyncMock(return_value=conversation)

    monkeypatch.setattr(db, "_run_in_tx", run_in_tx)

    result = await db.update_conversation(
        "conv-1",
        content=[{"role": "user", "content": "new"}],
        token_usage=12,
    )

    assert result is conversation
    run_in_tx.assert_awaited_once()

    await db.engine.dispose()
