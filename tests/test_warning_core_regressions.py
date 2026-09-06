import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path

import numpy as np
import pytest
import pytest_asyncio
from sqlmodel import text

from astrbot.api.web import PluginMultiDict
from astrbot.core.db.po import PlatformMessageHistory
from astrbot.core.db.sqlite import SQLiteDatabase, _run_legacy_query
from astrbot.core.db.vec_db.faiss_impl.embedding_storage import EmbeddingStorage
from astrbot.core.utils.migra_helper import (
    _get_effective_provider_map,
    _get_provider_runner_type,
)


@pytest.mark.parametrize("value", [None, "last"])
def test_multidict_lookup_preserves_nullable_last_value(value: str | None) -> None:
    data = PluginMultiDict[str | None]([("key", "first"), ("key", value)])
    assert data["key"] == value
    assert data.getlist("key") == ["first", value]
    with pytest.raises(KeyError, match="missing"):
        _ = data["missing"]


@pytest.mark.parametrize("value", [None, [], "invalid", {1: "invalid key"}])
def test_legacy_provider_migration_rejects_non_mapping_inputs(value: object) -> None:
    assert _get_effective_provider_map(value) == {}
    assert _get_provider_runner_type(value) is None


def test_legacy_provider_migration_preserves_source_and_provider_fields() -> None:
    source = {"id": "source", "type": "dify", "dify_api_key": "original"}
    provider = {"id": "provider", "provider_source_id": "source", "timeout": 30}
    effective = _get_effective_provider_map(
        {"provider_sources": [source], "provider": [provider]}
    )["provider"]
    assert effective["dify_api_key"] == "original"
    assert effective["timeout"] == 30
    assert _get_provider_runner_type(effective) == "dify"
    effective["dify_api_key"] = "changed"
    assert source["dify_api_key"] == "original"


@pytest_asyncio.fixture
async def history_db(tmp_path: Path) -> AsyncIterator[SQLiteDatabase]:
    db = SQLiteDatabase(str(tmp_path / "history.db"))
    try:
        yield db
    finally:
        await db.engine.dispose()


@pytest.mark.asyncio
async def test_history_idempotency_lookup_and_delete_count(
    history_db: SQLiteDatabase,
) -> None:
    async with history_db.get_db() as session:
        session.add_all(
            [
                PlatformMessageHistory(
                    platform_id="test",
                    user_id=group,
                    content={"message": []},
                    idempotency_key="shared-key",
                )
                for group in ("group-a", "group-b")
            ]
        )
        await session.commit()
    record = await history_db.find_platform_message_history_by_idempotency_key(
        "test", "group-a", "shared-key"
    )
    assert record is not None and record.user_id == "group-a"
    assert (
        await history_db.find_platform_message_history_by_idempotency_key(
            "test", "other", "shared-key"
        )
        is None
    )
    assert await history_db.delete_all_platform_message_history("test", "group-a") == 1
    assert await history_db.delete_all_platform_message_history("test", "group-a") == 0


@pytest.mark.asyncio
async def test_history_schema_upgrade_adds_nullable_idempotency_key(
    tmp_path: Path,
) -> None:
    path = tmp_path / "legacy-history.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE platform_message_history ("
            "id INTEGER PRIMARY KEY, platform_id TEXT NOT NULL, user_id TEXT NOT NULL, "
            "sender_id TEXT, sender_name TEXT, content JSON NOT NULL, "
            "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
        )
        conn.execute(
            "INSERT INTO platform_message_history "
            "(id, platform_id, user_id, content, created_at, updated_at) VALUES "
            "(1, 'test', 'legacy', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
    db = SQLiteDatabase(str(path))
    try:
        async with db.get_db() as session:
            record = await session.get(PlatformMessageHistory, 1)
            assert record is not None and record.idempotency_key is None
            columns = await session.execute(
                text("PRAGMA table_info(platform_message_history)")
            )
            assert "idempotency_key" in {row[1] for row in columns}
    finally:
        await db.engine.dispose()


@pytest.mark.parametrize("fail", [False, True])
def test_legacy_query_propagates_results_and_failures(fail: bool) -> None:
    async def query() -> int:
        if fail:
            raise ValueError("query failed")
        return 7

    if fail:
        with pytest.raises(ValueError, match="query failed"):
            _run_legacy_query(query)
    else:
        assert _run_legacy_query(query) == 7


@pytest.mark.asyncio
async def test_faiss_delete_accepts_typed_selector_and_is_idempotent() -> None:
    storage = EmbeddingStorage(dimension=2)
    await storage.insert(np.array([1.0, 2.0], dtype=np.float32), 7)
    await storage.delete([7])
    await storage.delete([7])
    await storage.delete([])
    assert storage.index is not None and storage.index.ntotal == 0
