import pytest

from astrbot.core.db.sqlite import SQLiteDatabase


@pytest.mark.asyncio
async def test_preference_upsert_filter_remove_and_clear_paths(temp_db: SQLiteDatabase):
    created = await temp_db.insert_preference_or_update(
        "umo",
        "session-a",
        "sel_conv_id",
        {"val": "conv-a"},
    )
    updated = await temp_db.insert_preference_or_update(
        "umo",
        "session-a",
        "sel_conv_id",
        {"val": "conv-b"},
    )
    await temp_db.insert_preference_or_update(
        "umo",
        "session-a",
        "theme",
        {"val": "dark"},
    )
    await temp_db.insert_preference_or_update(
        "umo",
        "session-b",
        "sel_conv_id",
        {"val": "conv-c"},
    )

    assert created.scope_id == "session-a"
    assert updated.value == {"val": "conv-b"}
    assert (await temp_db.get_preference("umo", "session-a", "sel_conv_id")).value == {
        "val": "conv-b"
    }
    assert len(await temp_db.get_preferences("umo")) == 3
    assert [
        item.key for item in await temp_db.get_preferences("umo", scope_id="session-a")
    ] == ["sel_conv_id", "theme"]
    assert [
        item.scope_id
        for item in await temp_db.get_preferences("umo", key="sel_conv_id")
    ] == ["session-a", "session-b"]

    await temp_db.remove_preference("umo", "session-a", "sel_conv_id")
    assert await temp_db.get_preference("umo", "session-a", "sel_conv_id") is None

    await temp_db.clear_preferences("umo", "session-a")
    assert await temp_db.get_preferences("umo", scope_id="session-a") == []
    remaining = await temp_db.get_preferences("umo")
    assert [(item.scope_id, item.key) for item in remaining] == [
        ("session-b", "sel_conv_id")
    ]


@pytest.mark.asyncio
async def test_get_preferences_combines_scope_and_key_filters_and_returns_empty_for_miss(
    temp_db: SQLiteDatabase,
):
    await temp_db.insert_preference_or_update(
        "umo",
        "session-a",
        "sel_conv_id",
        {"val": "conv-a"},
    )
    await temp_db.insert_preference_or_update(
        "umo",
        "session-a",
        "theme",
        {"val": "dark"},
    )
    await temp_db.insert_preference_or_update(
        "umo",
        "session-b",
        "sel_conv_id",
        {"val": "conv-b"},
    )

    scoped_key = await temp_db.get_preferences(
        "umo",
        scope_id="session-a",
        key="sel_conv_id",
    )
    missing = await temp_db.get_preferences(
        "umo",
        scope_id="session-c",
        key="sel_conv_id",
    )

    assert [(item.scope_id, item.key) for item in scoped_key] == [
        ("session-a", "sel_conv_id")
    ]
    assert missing == []
