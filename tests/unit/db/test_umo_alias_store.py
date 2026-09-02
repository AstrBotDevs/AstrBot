import asyncio
import contextvars
from typing import Literal
from unittest.mock import patch

import pytest
from sqlalchemy.dialects.sqlite import Insert as SQLiteInsert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from astrbot.core.db.sqlite import SQLiteDatabase


def _is_umo_alias_insert(statement: object) -> bool:
    table = getattr(statement, "table", None)
    return (
        isinstance(statement, SQLiteInsert)
        and getattr(table, "name", None) == "umo_aliases"
    )


@pytest.mark.asyncio
async def test_upsert_umo_alias_updates_existing_row_and_filtered_reads(
    temp_db: SQLiteDatabase,
):
    created = await temp_db.upsert_umo_alias(
        "umo-1",
        "sender-1",
        "Auto One",
        "Alias One",
    )
    updated = await temp_db.upsert_umo_alias(
        "umo-1",
        "sender-2",
        None,
        "Alias Two",
    )
    await temp_db.upsert_umo_alias(
        "umo-2",
        "sender-3",
        "Auto Two",
        None,
    )

    assert created.umo == "umo-1"
    assert updated.umo == "umo-1"
    assert updated.creator_sender_id == "sender-2"
    assert updated.auto_name is None
    assert updated.user_alias == "Alias Two"

    filtered = await temp_db.get_umo_aliases(["umo-2"])
    assert [alias.umo for alias in filtered] == ["umo-2"]
    assert await temp_db.get_umo_aliases([]) == []


@pytest.mark.asyncio
async def test_upsert_umo_auto_name_does_not_overwrite_manual_alias(
    temp_db: SQLiteDatabase,
):
    await temp_db.upsert_umo_alias(
        "umo-1",
        "admin-1",
        "Auto One",
        "Alias One",
    )
    await temp_db.upsert_umo_auto_name("umo-1", "sender-9", "Auto Two")

    alias = await temp_db.get_umo_alias("umo-1")
    assert alias is not None
    assert alias.auto_name == "Auto Two"
    assert alias.user_alias == "Alias One"
    assert alias.creator_sender_id == "admin-1"


async def _run_raced_umo_upserts(
    temp_db: SQLiteDatabase,
    umo: str,
    leading: Literal["manual", "auto"] | None,
) -> list[object]:
    """Start both upserts together and optionally let one INSERT finish first."""
    barrier = asyncio.Barrier(2)
    leading_insert_done = asyncio.Event()
    op_name: contextvars.ContextVar[str] = contextvars.ContextVar("umo_upsert_op")
    original_execute = AsyncSession.execute

    async def gated_execute(
        self: AsyncSession,
        statement: object,
        *args: object,
        **kwargs: object,
    ) -> object:
        if _is_umo_alias_insert(statement):
            await barrier.wait()
            if leading is not None and op_name.get() != leading:
                await leading_insert_done.wait()
            result = await original_execute(self, statement, *args, **kwargs)
            if leading is not None and op_name.get() == leading:
                leading_insert_done.set()
            return result
        return await original_execute(self, statement, *args, **kwargs)

    async def run_manual() -> object:
        token = op_name.set("manual")
        try:
            return await temp_db.upsert_umo_alias(
                umo,
                "admin-1",
                "Auto Name",
                "Manual Alias",
            )
        finally:
            op_name.reset(token)

    async def run_auto() -> None:
        token = op_name.set("auto")
        try:
            await temp_db.upsert_umo_auto_name(umo, "sender-9", "Auto Name")
        finally:
            op_name.reset(token)

    with patch.object(AsyncSession, "execute", new=gated_execute):
        return await asyncio.wait_for(
            asyncio.gather(run_manual(), run_auto(), return_exceptions=True),
            timeout=10,
        )


def _assert_no_integrity_error_and_manual_alias(
    results: list[object],
) -> None:
    integrity_errors = [item for item in results if isinstance(item, IntegrityError)]
    assert integrity_errors == []
    for item in results:
        if isinstance(item, BaseException):
            raise item


@pytest.mark.asyncio
@pytest.mark.parametrize("leading", ["manual", "auto"])
async def test_concurrent_manual_and_auto_name_upserts_preserve_manual_alias(
    temp_db: SQLiteDatabase,
    leading: Literal["manual", "auto"],
):
    """Race the first insert for one UMO in both winner orders."""
    umo = f"umo-race-{leading}"
    assert await temp_db.get_umo_alias(umo) is None

    results = await _run_raced_umo_upserts(temp_db, umo, leading)
    _assert_no_integrity_error_and_manual_alias(results)

    alias = await temp_db.get_umo_alias(umo)
    assert alias is not None
    assert alias.user_alias == "Manual Alias"
    assert alias.auto_name == "Auto Name"


@pytest.mark.asyncio
async def test_simultaneous_manual_and_auto_name_inserts_do_not_raise(
    temp_db: SQLiteDatabase,
):
    """Both INSERTs enter execute together; ON CONFLICT must absorb the loser."""
    umo = "umo-race-simultaneous"
    assert await temp_db.get_umo_alias(umo) is None

    results = await _run_raced_umo_upserts(temp_db, umo, leading=None)
    _assert_no_integrity_error_and_manual_alias(results)

    alias = await temp_db.get_umo_alias(umo)
    assert alias is not None
    assert alias.user_alias == "Manual Alias"
    assert alias.auto_name == "Auto Name"
