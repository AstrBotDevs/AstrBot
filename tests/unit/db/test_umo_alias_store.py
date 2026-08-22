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
