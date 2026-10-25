import pytest
import pytest_asyncio

from astrbot.core.db.sqlite import SQLiteDatabase


@pytest_asyncio.fixture
async def database(tmp_path):
    database = SQLiteDatabase(str(tmp_path / "umo-alias.db"))
    await database.initialize()
    try:
        yield database
    finally:
        await database.engine.dispose()


@pytest.mark.asyncio
async def test_delete_umo_alias_removes_matching_row(database):
    await database.upsert_umo_alias(
        "default:GroupMessage:123456",
        "sender-1",
        "Example group",
        "My group",
    )

    assert await database.delete_umo_alias("default:GroupMessage:123456") is True
    assert await database.get_umo_alias("default:GroupMessage:123456") is None


@pytest.mark.asyncio
async def test_delete_umo_alias_returns_false_for_missing_row(database):
    assert await database.delete_umo_alias("default:GroupMessage:missing") is False
