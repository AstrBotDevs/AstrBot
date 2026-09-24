"""Stable image imports and durable offline migration task state."""

import hashlib
import uuid
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from PIL import Image
from sqlmodel import select

from astrbot.core import image_asset_store as storage
from astrbot.core.db.po import ImageAsset, ImageHistoryMigrationTask
from astrbot.core.db.sqlite import SQLiteDatabase


@pytest_asyncio.fixture
async def maintenance_env(tmp_path, monkeypatch):
    monkeypatch.setattr(
        storage, "get_astrbot_data_path", lambda: str(tmp_path / "data")
    )
    db = SQLiteDatabase(str(tmp_path / "maintenance.db"))
    await db.initialize()
    db.inited = True
    source = tmp_path / "source.png"
    Image.new("RGB", (24, 18), "red").save(source)
    store = storage.ImageAssetStore(db, max_pixels=1024 * 1024, max_frames=10)
    try:
        yield store, db, source
    finally:
        await db.engine.dispose()


@pytest.mark.asyncio
async def test_stable_import_reuses_asset_without_recharging_full_quota(
    maintenance_env,
):
    store, db, source = maintenance_env
    stable_id = str(uuid.uuid4())
    source_bytes = source.read_bytes()
    store.max_total_bytes = len(source_bytes)

    first = await store.import_file(
        source, source_kind="legacy_model_input", asset_id=stable_id
    )
    second = await store.import_file(
        source, source_kind="legacy_model_input", asset_id=stable_id
    )

    assert first.asset_id == second.asset_id == stable_id
    assert first.sha256 == hashlib.sha256(source_bytes).hexdigest()
    assert (store.root / f"{stable_id}.img").read_bytes() == source_bytes
    assert sorted(path.name for path in store.root.glob("*.img")) == [
        f"{stable_id}.img"
    ]
    async with db.get_db() as session:
        rows = (await session.execute(select(ImageAsset))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_stable_import_recovers_published_file_without_asset_row(maintenance_env):
    store, db, source = maintenance_env
    stable_id = str(uuid.uuid4())
    source_bytes = source.read_bytes()
    store.max_total_bytes = len(source_bytes)
    published = await store.import_file(
        source, source_kind="legacy_model_input", asset_id=stable_id
    )
    async with db.get_db() as session:
        await session.delete(await session.get(ImageAsset, stable_id))
        await session.commit()

    recovered = await store.import_file(
        source, source_kind="legacy_model_input", asset_id=stable_id
    )

    assert recovered.asset_id == published.asset_id == stable_id
    assert recovered.sha256 == hashlib.sha256(source_bytes).hexdigest()
    assert (store.root / f"{stable_id}.img").read_bytes() == source_bytes
    assert not list(store.root.glob("*.part"))
    async with db.get_db() as session:
        rows = (await session.execute(select(ImageAsset))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_stable_import_retry_recovers_uncertain_metadata_commit(
    maintenance_env, monkeypatch
):
    store, db, source = maintenance_env
    stable_id = str(uuid.uuid4())
    store.max_total_bytes = source.stat().st_size
    real_get_db = db.get_db

    @asynccontextmanager
    async def committed_but_unreported():
        async with real_get_db() as session:
            commit = session.commit

            async def commit_then_fail():
                await commit()
                raise OSError("simulated lost commit response")

            session.commit = commit_then_fail
            yield session

    monkeypatch.setattr(db, "get_db", committed_but_unreported)
    with pytest.raises(OSError, match="lost commit response"):
        await store.import_file(source, asset_id=stable_id)

    monkeypatch.setattr(db, "get_db", real_get_db)
    recovered = await store.import_file(source, asset_id=stable_id)
    async with db.get_db() as session:
        rows = (await session.execute(select(ImageAsset))).scalars().all()
    assert recovered.asset_id == stable_id
    assert len(rows) == 1
    assert len(list(store.root.glob("*.img"))) == 1


@pytest.mark.asyncio
async def test_stable_import_rejects_changed_input_without_overwriting(maintenance_env):
    store, db, source = maintenance_env
    stable_id = str(uuid.uuid4())
    original = source.read_bytes()
    await store.import_file(source, asset_id=stable_id)
    Image.new("RGB", (24, 18), "blue").save(source)

    with pytest.raises(storage.ImageAssetImportConflictError):
        await store.import_file(source, asset_id=stable_id)

    assert (store.root / f"{stable_id}.img").read_bytes() == original
    async with db.get_db() as session:
        rows = (await session.execute(select(ImageAsset))).scalars().all()
    assert len(rows) == 1
    assert rows[0].sha256 == hashlib.sha256(original).hexdigest()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("sha256", "0" * 64),
        ("byte_size", 1),
        ("mime_type", "image/jpeg"),
        ("source_kind", "original"),
        ("width", 1),
        ("height", 1),
        ("state", "pending_delete"),
        ("storage_key", "other.img"),
    ],
)
async def test_stable_import_rejects_mismatched_asset_metadata(
    maintenance_env, field, replacement
):
    store, db, source = maintenance_env
    stable_id = str(uuid.uuid4())
    original = source.read_bytes()
    await store.import_file(
        source, source_kind="legacy_model_input", asset_id=stable_id
    )
    async with db.get_db() as session:
        row = await session.get(ImageAsset, stable_id)
        setattr(row, field, replacement)
        await session.commit()

    with pytest.raises(storage.ImageAssetImportConflictError):
        await store.import_file(
            source, source_kind="legacy_model_input", asset_id=stable_id
        )

    assert (store.root / f"{stable_id}.img").read_bytes() == original


@pytest.mark.asyncio
async def test_orphan_file_conflict_is_not_overwritten(maintenance_env):
    store, db, source = maintenance_env
    stable_id = str(uuid.uuid4())
    original = source.read_bytes()
    await store.import_file(source, asset_id=stable_id)
    async with db.get_db() as session:
        await session.delete(await session.get(ImageAsset, stable_id))
        await session.commit()
    Image.new("RGB", (24, 18), "blue").save(source)

    with pytest.raises(storage.ImageAssetImportConflictError):
        await store.import_file(source, asset_id=stable_id)

    assert (store.root / f"{stable_id}.img").read_bytes() == original
    async with db.get_db() as session:
        assert await session.get(ImageAsset, stable_id) is None


@pytest.mark.asyncio
async def test_stale_stable_part_is_removed_before_quota_check(maintenance_env):
    store, _, source = maintenance_env
    stable_id = str(uuid.uuid4())
    source_size = source.stat().st_size
    store.max_total_bytes = source_size
    stale_part = store.root / f"{stable_id}.part"
    stale_part.write_bytes(b"partial write that must not count as a completed asset")

    asset = await store.import_file(
        source, source_kind="legacy_model_input", asset_id=stable_id
    )

    assert asset.asset_id == stable_id
    assert not stale_part.exists()
    assert (store.root / f"{stable_id}.img").stat().st_size == source_size


@pytest.mark.asyncio
async def test_random_imports_keep_existing_non_idempotent_default(maintenance_env):
    store, _, source = maintenance_env

    first = await store.import_file(source)
    second = await store.import_file(source)

    assert first.asset_id != second.asset_id


@pytest.mark.asyncio
async def test_migration_task_has_persistent_state_without_conversation_foreign_key(
    maintenance_env,
):
    _, db, _ = maintenance_env
    task_id = str(uuid.uuid4())
    task = ImageHistoryMigrationTask(
        task_id=task_id,
        conversation_id="conversation-removed-later",
        user_id="owner",
        platform_id="test",
        source_row_id=4,
        source_created_at="2026-09-23 12:00:00.000000",
        source_sha256="a" * 64,
        source_byte_size=100,
    )
    assert not ImageHistoryMigrationTask.__table__.foreign_keys

    async with db.get_db() as session:
        session.add(task)
        await session.commit()
        stored = await session.get(ImageHistoryMigrationTask, task_id)
        assert stored is not None
        assert stored.state == "prepared"
        stored.state = "committed"
        stored.output_sha256 = "b" * 64
        stored.output_byte_size = 42
        await session.commit()

    async with db.get_db() as session:
        stored = await session.get(ImageHistoryMigrationTask, task_id)
    assert stored is not None
    assert stored.state == "committed"
    assert stored.output_sha256 == "b" * 64
    assert stored.output_byte_size == 42
