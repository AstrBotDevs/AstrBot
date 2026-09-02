import pytest

from astrbot.core.db.sqlite import SQLiteDatabase


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
