"""Tests for bounded SQLite image-history maintenance storage operations."""

import hashlib
import json
import sqlite3
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from astrbot.core import conversation_history_limits, image_asset_store
from astrbot.core.db.po import (
    ConversationImageCheckpoint,
    ConversationImageRef,
    ConversationV2,
    ImageAsset,
    ImageHistoryMigrationTask,
)
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.image_history_maintenance_storage import (
    ConversationSourceError,
    SourceFingerprint,
    commit_migrated_history,
    create_database_snapshot,
    fingerprint_conversation,
    open_fingerprinted_conversation_history,
)


@pytest_asyncio.fixture
async def maintenance_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Create a file-backed test database and isolate the image store lock."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    monkeypatch.setattr(
        image_asset_store,
        "get_astrbot_data_path",
        lambda: str(data_root),
    )

    @asynccontextmanager
    async def no_store_lock():
        yield

    monkeypatch.setattr(image_asset_store, "image_store_lock", no_store_lock)
    db = SQLiteDatabase(str(tmp_path / "maintenance.sqlite"))
    await db.initialize()
    db.inited = True
    await db.create_conversation(
        "user-1",
        "platform-1",
        cid="conversation-1",
    )
    try:
        yield db
    finally:
        await db.engine.dispose()


def _write_raw_history(database_path: Path, value: str) -> None:
    """Replace a history with raw JSON without passing it through the ORM."""
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE conversations SET content = ? WHERE conversation_id = ?",
            (value, "conversation-1"),
        )


async def _create_prepared_task(db, fingerprint: SourceFingerprint) -> str:
    task_id = str(uuid.uuid4())
    async with db.get_db() as session, session.begin():
        session.add(
            ImageHistoryMigrationTask(
                task_id=task_id,
                conversation_id=fingerprint.conversation_id,
                user_id=fingerprint.user_id,
                platform_id=fingerprint.platform_id,
                source_row_id=fingerprint.source_row_id,
                source_created_at=fingerprint.source_created_at,
                source_sha256=fingerprint.source_sha256,
                source_byte_size=fingerprint.source_byte_size,
            )
        )
    return task_id


async def _get_task(db, task_id: str) -> ImageHistoryMigrationTask:
    async with db.get_db() as session:
        return await session.get(ImageHistoryMigrationTask, task_id)


@pytest.mark.asyncio
async def test_fingerprint_reads_and_hashes_large_text_in_bounded_chunks(
    maintenance_db,
):
    db = maintenance_db
    body = json.dumps(
        [{"role": "user", "content": "图片前缀 " + "x" * (17 * 1024 * 1024)}],
        ensure_ascii=False,
    )
    _write_raw_history(Path(db.db_path), body)

    fingerprint = fingerprint_conversation(
        Path(db.db_path),
        "conversation-1",
        chunk_bytes=31 * 1024,
    )

    assert fingerprint.user_id == "user-1"
    assert fingerprint.platform_id == "platform-1"
    assert fingerprint.source_row_id > 0
    assert fingerprint.source_byte_size == len(body.encode("utf-8"))
    assert fingerprint.source_sha256 == hashlib.sha256(body.encode()).hexdigest()
    with pytest.raises(conversation_history_limits.HistoryTooLargeError):
        await maintenance_db.get_conversation_by_id("conversation-1")


@pytest.mark.asyncio
async def test_fingerprinted_blob_is_seekable_and_rejects_changed_snapshot(
    maintenance_db,
):
    db = maintenance_db
    original = json.dumps([{"role": "user", "content": "原图"}], ensure_ascii=False)
    _write_raw_history(Path(db.db_path), original)
    fingerprint = fingerprint_conversation(Path(db.db_path), "conversation-1")

    with open_fingerprinted_conversation_history(Path(db.db_path), fingerprint) as blob:
        assert blob.read(20) == original.encode("utf-8")[:20]
        blob.seek(0)
        assert blob.read() == original.encode("utf-8")

    changed = json.dumps([{"role": "user", "content": "新图"}], ensure_ascii=False)
    _write_raw_history(Path(db.db_path), changed)
    with pytest.raises(ConversationSourceError, match="changed"):
        with open_fingerprinted_conversation_history(Path(db.db_path), fingerprint):
            pytest.fail("A changed source must not be yielded")


def test_database_snapshot_includes_committed_wal_pages(tmp_path):
    source = tmp_path / "live.sqlite"
    snapshot = tmp_path / "snapshot.sqlite"
    connection = sqlite3.connect(source)
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute(
        "CREATE TABLE conversations ("
        "inner_conversation_id INTEGER PRIMARY KEY, conversation_id TEXT UNIQUE, "
        "user_id TEXT, platform_id TEXT, created_at TEXT, content TEXT)"
    )
    value = json.dumps([{"role": "user", "content": "WAL 数据"}], ensure_ascii=False)
    connection.execute(
        "INSERT INTO conversations VALUES (1, 'cid', 'u', 'p', 'created', ?)",
        (value,),
    )
    connection.commit()
    try:
        assert create_database_snapshot(source, snapshot) == snapshot
        assert fingerprint_conversation(snapshot, "cid") == fingerprint_conversation(
            source, "cid"
        )
        assert not Path(f"{snapshot}-wal").exists()
        with pytest.raises(FileExistsError):
            create_database_snapshot(source, snapshot)
        assert not list(tmp_path.glob(".snapshot.sqlite.*.partial"))
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_commit_history_and_task_state_are_atomic_and_idempotent(
    maintenance_db,
    monkeypatch,
):
    db = maintenance_db
    monkeypatch.setattr(
        conversation_history_limits,
        "MAX_ONLINE_HISTORY_BYTES",
        64 * 1024,
    )
    original = json.dumps(
        [{"role": "user", "content": "x" * (128 * 1024)}],
        ensure_ascii=False,
    )
    _write_raw_history(Path(db.db_path), original)
    fingerprint = fingerprint_conversation(Path(db.db_path), "conversation-1")
    task_id = await _create_prepared_task(db, fingerprint)
    new_history = [{"role": "user", "content": [{"type": "text", "text": "已迁移"}]}]
    original_load = db._conversation_without_history

    async def load_with_bounded_native_cache(session, cid):
        assert await session.scalar(text("PRAGMA cache_size")) == -2048
        assert await session.scalar(text("PRAGMA mmap_size")) == 0
        assert await session.scalar(text("PRAGMA temp_store")) == 1
        return await original_load(session, cid)

    monkeypatch.setattr(
        db, "_conversation_without_history", load_with_bounded_native_cache
    )

    result = await commit_migrated_history(
        db,
        task_id,
        fingerprint,
        previous_projection=[],
        new_history=new_history,
        image_refs=[],
    )

    stored = await db.get_conversation_by_id("conversation-1")
    task = await _get_task(db, task_id)
    stored_bytes = json.dumps(stored.content).encode()
    assert stored.content == new_history
    assert task.state == "committed"
    assert task.output_sha256 == hashlib.sha256(stored_bytes).hexdigest()
    assert task.output_byte_size == len(stored_bytes)
    assert result.status == "committed"

    replay = await commit_migrated_history(
        db,
        task_id,
        fingerprint,
        previous_projection=[],
        new_history=new_history,
        image_refs=[],
    )
    assert replay.status == "already_committed"
    assert replay.output_sha256 == result.output_sha256

    tampered = json.dumps([{"role": "assistant", "content": "external edit"}])
    _write_raw_history(Path(db.db_path), tampered)
    with pytest.raises(ConversationSourceError, match="output changed"):
        await commit_migrated_history(
            db,
            task_id,
            fingerprint,
            previous_projection=[],
            new_history=new_history,
            image_refs=[],
        )
    async with db.get_db() as session:
        stored = await session.execute(
            select(ConversationV2.content).where(
                ConversationV2.conversation_id == "conversation-1"
            )
        )
        assert stored.scalar_one() == json.loads(tampered)


@pytest.mark.asyncio
async def test_commit_rejects_source_change_without_overwriting_it(maintenance_db):
    db = maintenance_db
    original = json.dumps([{"role": "user", "content": "x" * (128 * 1024)}])
    _write_raw_history(Path(db.db_path), original)
    fingerprint = fingerprint_conversation(Path(db.db_path), "conversation-1")
    task_id = await _create_prepared_task(db, fingerprint)
    changed = json.dumps([{"role": "user", "content": "new source"}])
    _write_raw_history(Path(db.db_path), changed)

    with pytest.raises(ConversationSourceError, match="changed"):
        await commit_migrated_history(
            db,
            task_id,
            fingerprint,
            previous_projection=[],
            new_history=[{"role": "assistant", "content": "replacement"}],
            image_refs=[],
        )

    assert (
        fingerprint_conversation(Path(db.db_path), "conversation-1").source_sha256
        == hashlib.sha256(changed.encode()).hexdigest()
    )
    task = await _get_task(db, task_id)
    assert task.state == "prepared"
    async with db.get_db() as session:
        row = await session.execute(
            select(ConversationV2.content).where(
                ConversationV2.conversation_id == "conversation-1"
            )
        )
        assert row.scalar_one() == json.loads(changed)


@pytest.mark.asyncio
async def test_over_limit_output_rolls_back_history_refs_checkpoints_and_task(
    maintenance_db,
    monkeypatch,
):
    db = maintenance_db
    original = json.dumps([{"role": "user", "content": "x" * 128_000}])
    _write_raw_history(Path(db.db_path), original)
    fingerprint = fingerprint_conversation(Path(db.db_path), "conversation-1")
    task_id = await _create_prepared_task(db, fingerprint)
    monkeypatch.setattr(conversation_history_limits, "MAX_ONLINE_HISTORY_BYTES", 96)

    asset_id = str(uuid.uuid4())
    occurrence_id = str(uuid.uuid4())
    checkpoint_id = str(uuid.uuid4())
    async with db.get_db() as session, session.begin():
        session.add(
            ImageAsset(
                asset_id=asset_id,
                storage_key=f"{asset_id}.img",
                mime_type="image/png",
                byte_size=8,
                width=1,
                height=1,
                sha256=hashlib.sha256(b"image").hexdigest(),
                source_kind="legacy_model_input",
            )
        )
    history = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_ref",
                    "schema_version": 1,
                    "occurrence_id": occurrence_id,
                    "asset_id": asset_id,
                    "description": "",
                    "description_status": "pending",
                    "description_version": 0,
                }
            ],
        },
        {"role": "_checkpoint", "content": {"id": checkpoint_id}},
        {"role": "assistant", "content": "y" * 300},
    ]
    refs = [
        ConversationImageRef(
            conversation_id="conversation-1",
            occurrence_id=occurrence_id,
            asset_id=asset_id,
            checkpoint_id=checkpoint_id,
            image_index=0,
        )
    ]

    with pytest.raises(conversation_history_limits.HistoryTooLargeError):
        await commit_migrated_history(
            db,
            task_id,
            fingerprint,
            previous_projection=[],
            new_history=history,
            image_refs=refs,
        )

    task = await _get_task(db, task_id)
    assert task.state == "prepared"
    async with db.get_db() as session:
        assert (
            not (
                await session.execute(
                    select(ConversationImageRef).where(
                        ConversationImageRef.conversation_id == "conversation-1"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert (
            not (
                await session.execute(
                    select(ConversationImageCheckpoint).where(
                        ConversationImageCheckpoint.conversation_id == "conversation-1"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert fingerprint_conversation(Path(db.db_path), "conversation-1") == fingerprint
