"""Persistence, integrity and failure contracts for the original image store."""

import asyncio
import hashlib
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import text
from sqlmodel import select

from astrbot.core import image_asset_store as storage
from astrbot.core.db.po import (
    ConversationImageCheckpoint,
    ConversationImageRef,
    ConversationV2,
    ImageAsset,
)
from astrbot.core.db.sqlite import SQLiteDatabase


@pytest_asyncio.fixture
async def store_env(tmp_path, monkeypatch):
    monkeypatch.setattr(
        storage, "get_astrbot_data_path", lambda: str(tmp_path / "data")
    )
    db = SQLiteDatabase(str(tmp_path / "test.db"))
    await db.initialize()
    db.inited = True
    source = tmp_path / "input.png"
    Image.new("RGB", (32, 24), "red").save(source)
    store = storage.ImageAssetStore(db, max_pixels=1024 * 1024, max_frames=10)
    try:
        yield store, db, source
    finally:
        await db.engine.dispose()


async def associate(
    db, asset, *, conversation="conversation", owner="owner", platform="test"
):
    """Create test-only links; production lifecycle wiring is outside this module.

    Args:
        db: Isolated test database.
        asset: Asset whose bytes should become readable.
        conversation: Conversation identity.
        owner: Conversation owner.
        platform: Conversation platform.
    """
    async with db.get_db() as session:
        session.add(
            ConversationV2(
                conversation_id=conversation, platform_id=platform, user_id=owner
            )
        )
        session.add(
            ConversationImageCheckpoint(
                conversation_id=conversation,
                checkpoint_id="checkpoint",
                sequence=1,
                active=True,
            )
        )
        session.add(
            ConversationImageRef(
                conversation_id=conversation,
                occurrence_id="image",
                checkpoint_id="checkpoint",
                asset_id=asset.asset_id,
            )
        )
        await session.commit()


def access(**changes):
    return {
        "conversation_id": "conversation",
        "occurrence_id": "image",
        "user_id": "owner",
        "platform_id": "test",
        **changes,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["original", "legacy_model_input"])
async def test_persists_exact_bytes_and_reads_after_store_restart(store_env, kind):
    store, db, source = store_env
    original = source.read_bytes()
    asset = await store.import_file(source, source_kind=kind)
    assert asset.source_kind == kind
    assert asset.byte_size == len(original)
    assert asset.sha256 == hashlib.sha256(original).hexdigest()
    assert (asset.width, asset.height, asset.mime_type) == (32, 24, "image/png")
    assert not Path(asset.storage_key).is_absolute()
    assert source.read_bytes() == original
    assert (store.root / asset.storage_key).read_bytes() == original
    assert not list(store.root.glob("*.part"))
    await associate(db, asset)
    source.unlink()
    await db.engine.dispose()
    restarted_db = SQLiteDatabase(db.db_path)
    try:
        reopened = storage.ImageAssetStore(
            restarted_db, max_pixels=1024 * 1024, max_frames=10
        )
        async with reopened.open_image(**access()) as stream:
            assert stream.read() == original
        assert stream.closed
    finally:
        await restarted_db.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"user_id": "other"},
        {"platform_id": "other"},
        {"conversation_id": "other"},
        {"occurrence_id": "other"},
    ],
)
async def test_read_checks_real_owner_platform_and_association_without_foreign_keys(
    store_env, changes
):
    store, db, source = store_env
    asset = await store.import_file(source)
    await associate(db, asset)
    async with db.get_db() as session:
        assert (await session.execute(text("PRAGMA foreign_keys"))).scalar_one() == 0
    with pytest.raises(PermissionError):
        async with store.open_image(**access(**changes)):
            pytest.fail("Unauthorized read")


@pytest.mark.asyncio
async def test_asset_id_alone_and_orphan_association_do_not_authorize_reads(store_env):
    store, db, source = store_env
    asset = await store.import_file(source)
    async with db.get_db() as session:
        session.add(
            ConversationImageRef(
                conversation_id="conversation",
                occurrence_id="image",
                asset_id=asset.asset_id,
            )
        )
        await session.commit()
    with pytest.raises(PermissionError):
        async with store.open_image(**access()):
            pytest.fail("Orphan reference authorized a read")


@pytest.mark.asyncio
async def test_original_larger_than_64_mib_is_persisted(store_env):
    store, _, source = store_env
    with source.open("ab") as output:
        output.truncate(64 * 1024**2 + 1)

    asset = await store.import_file(source)

    assert asset.byte_size == 64 * 1024**2 + 1
    assert (store.root / asset.storage_key).stat().st_size == asset.byte_size
    assert not list(store.root.glob("*.part"))


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["pixels", "frames", "corrupt"])
async def test_rejects_invalid_or_over_limit_images(store_env, failure):
    store, db, source = store_env
    if failure == "pixels":
        store.max_pixels = 10
    elif failure == "frames":
        source = source.with_suffix(".gif")
        Image.new("RGB", (10, 10), "red").save(
            source, save_all=True, append_images=[Image.new("RGB", (10, 10), "blue")]
        )
        store.max_frames = 1
    else:
        source.write_bytes(b"not an image")
    with pytest.raises((ValueError, OSError)):
        await store.import_file(source)
    assert not list(store.root.glob("*.img"))
    assert not list(store.root.glob("*.part"))


@pytest.mark.asyncio
async def test_atomic_publish_failure_cleans_staging(store_env, monkeypatch):
    store, db, source = store_env

    def fail_publish(self, target):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(Path, "replace", fail_publish)
    with pytest.raises(OSError, match="simulated"):
        await store.import_file(source)
    assert not list(store.root.glob("*.part"))
    assert not list(store.root.glob("*.img"))
    async with db.get_db() as session:
        assert (await session.execute(select(ImageAsset))).first() is None


@pytest.mark.asyncio
async def test_commit_failure_leaves_published_orphan_for_reconciliation(
    store_env, monkeypatch
):
    store, db, source = store_env
    real_get_db = db.get_db

    @asynccontextmanager
    async def fail_commit():
        async with real_get_db() as session:
            session.commit = AsyncMock(side_effect=OSError("commit failed"))
            yield session

    monkeypatch.setattr(db, "get_db", fail_commit)
    with pytest.raises(OSError, match="commit failed"):
        await store.import_file(source)
    files = list(store.root.glob("*.img"))
    assert len(files) == 1
    assert files[0].read_bytes() == source.read_bytes()
    assert not list(store.root.glob("*.part"))
    monkeypatch.setattr(db, "get_db", real_get_db)
    async with db.get_db() as session:
        assert (await session.execute(select(ImageAsset))).first() is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "damage", ["missing", "same_size_corruption", "traversal", "unavailable"]
)
async def test_missing_corrupt_and_invalid_asset_paths_are_rejected(store_env, damage):
    store, db, source = store_env
    asset = await store.import_file(source)
    await associate(db, asset)
    path = store.root / asset.storage_key
    if damage == "missing":
        path.unlink()
    elif damage == "same_size_corruption":
        path.write_bytes(b"x" * asset.byte_size)
    else:
        async with db.get_db() as session:
            row = await session.get(ImageAsset, asset.asset_id)
            if damage == "traversal":
                row.storage_key = "../input.png"
            else:
                row.state = "unavailable"
            await session.commit()
    with pytest.raises(OSError):
        async with store.open_image(**access()):
            pytest.fail("Invalid stored asset returned")


@pytest.mark.asyncio
async def test_symlink_asset_and_source_are_rejected(store_env, require_symlink):
    store, db, source = store_env
    link = source.with_name("link.png")
    link.symlink_to(source)
    with pytest.raises(ValueError):
        await store.import_file(link)
    asset = await store.import_file(source)
    await associate(db, asset)
    path = store.root / asset.storage_key
    path.unlink()
    path.symlink_to(source)
    with pytest.raises(OSError):
        async with store.open_image(**access()):
            pytest.fail("Symlink followed")


@pytest.mark.asyncio
async def test_cancellation_drains_worker_before_releasing_lock(store_env, monkeypatch):
    store, db, source = store_env
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    original = store._capture

    def blocked_capture(path, kind, stop):
        entered.set()
        release.wait(timeout=5)
        try:
            return original(path, kind, stop)
        finally:
            finished.set()

    monkeypatch.setattr(store, "_capture", blocked_capture)
    task = asyncio.create_task(store.import_file(source))
    assert await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    second = storage.ImageAssetStore(db, max_pixels=1000, max_frames=10)
    waiting = asyncio.create_task(second.import_file(source))
    await asyncio.sleep(0)
    assert not waiting.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished.is_set()
    await waiting
    assert len(list(store.root.glob("*.img"))) == 1
    assert not list(store.root.glob("*.part"))


@pytest.mark.asyncio
async def test_open_reader_holds_store_lock_until_context_exit(store_env):
    store, db, source = store_env
    asset = await store.import_file(source)
    await associate(db, asset)
    async with store.open_image(**access()) as stream:
        contender = asyncio.create_task(store.import_file(source))
        await asyncio.sleep(0)
        assert not contender.done()
        assert stream.read(1)
    await contender


@pytest.mark.asyncio
async def test_fsync_failure_does_not_publish_asset(store_env, monkeypatch):
    store, db, source = store_env

    def fail_sync(_fd):
        raise OSError("simulated full disk")

    monkeypatch.setattr(storage.os, "fsync", fail_sync)
    with pytest.raises(OSError, match="full disk"):
        await store.import_file(source)
    assert not list(store.root.glob("*.part"))
    assert not list(store.root.glob("*.img"))
    async with db.get_db() as session:
        assert (await session.execute(select(ImageAsset))).first() is None


@pytest.mark.asyncio
async def test_uncertain_commit_never_deletes_committed_image(store_env, monkeypatch):
    store, db, source = store_env
    real_get_db = db.get_db

    @asynccontextmanager
    async def uncertain_commit():
        async with real_get_db() as session:
            commit = session.commit

            async def commit_then_fail():
                await commit()
                raise OSError("commit outcome uncertain")

            session.commit = commit_then_fail
            yield session

    monkeypatch.setattr(db, "get_db", uncertain_commit)
    with pytest.raises(OSError, match="outcome uncertain"):
        await store.import_file(source)
    monkeypatch.setattr(db, "get_db", real_get_db)
    async with db.get_db() as session:
        asset = (await session.execute(select(ImageAsset))).scalar_one()
    assert (store.root / asset.storage_key).read_bytes() == source.read_bytes()
    assert not list(store.root.glob("*.part"))


@pytest.mark.asyncio
async def test_source_change_during_capture_is_not_published(store_env, monkeypatch):
    store, db, source = store_env
    monkeypatch.setattr(storage, "COPY_CHUNK_BYTES", 16)
    original_hash = hashlib.sha256

    class GrowingHash:
        def __init__(self):
            self.digest = original_hash()
            self.grown = False

        def update(self, chunk):
            if not self.grown:
                with source.open("ab") as output:
                    output.write(b"x" * 100)
                self.grown = True
            self.digest.update(chunk)

        def hexdigest(self):
            return self.digest.hexdigest()

    monkeypatch.setattr(storage.hashlib, "sha256", GrowingHash)
    with pytest.raises(OSError, match="source changed during capture"):
        await store.import_file(source)
    assert not list(store.root.glob("*.part"))
    assert not list(store.root.glob("*.img"))


@pytest.mark.asyncio
async def test_same_task_can_use_reader_after_cancelled_read(store_env, monkeypatch):
    store, db, source = store_env
    asset = await store.import_file(source)
    await associate(db, asset)
    entered = threading.Event()
    release = threading.Event()
    original = store._verify_file

    def blocked_verify(stream, metadata, stop):
        entered.set()
        release.wait(timeout=5)
        return original(stream, metadata, stop)

    monkeypatch.setattr(store, "_verify_file", blocked_verify)

    async def read_image():
        async with store.open_image(**access()) as stream:
            return stream.read()

    task = asyncio.create_task(read_image())
    assert await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    monkeypatch.setattr(store, "_verify_file", original)
    async with store.open_image(**access()) as stream:
        assert stream.read() == source.read_bytes()


@pytest.mark.asyncio
@pytest.mark.parametrize("image_format", ["PNG", "JPEG", "BMP", "GIF", "TIFF", "WEBP"])
async def test_supported_formats_preserve_original_bytes(store_env, image_format):
    store, db, source = store_env
    Image.new("RGB", (64, 64), "red").save(source, format=image_format)
    original = source.read_bytes()
    asset = await store.import_file(source)
    assert (store.root / asset.storage_key).read_bytes() == original


@pytest.mark.asyncio
@pytest.mark.parametrize("image_format", ["JPEG", "BMP", "TIFF"])
@pytest.mark.parametrize("cut_bytes", [2, 30])
async def test_truncated_pixel_data_is_not_published(
    store_env, image_format, cut_bytes
):
    store, db, source = store_env
    Image.new("RGB", (64, 64), "red").save(source, format=image_format)
    source.write_bytes(source.read_bytes()[:-cut_bytes])
    with pytest.raises(OSError):
        await store.import_file(source)
    assert not list(store.root.glob("*.img"))
    assert not list(store.root.glob("*.part"))
    async with db.get_db() as session:
        assert not (await session.execute(select(ImageAsset))).all()
