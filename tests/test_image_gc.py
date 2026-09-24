"""Conservative retirement, reader exclusion and explicit orphan maintenance."""

import asyncio
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from PIL import Image
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
async def gc_env(tmp_path, monkeypatch):
    monkeypatch.setattr(
        storage, "get_astrbot_data_path", lambda: str(tmp_path / "data")
    )
    db = SQLiteDatabase(str(tmp_path / "test.db"))
    await db.initialize()
    db.inited = True
    source = tmp_path / "input.png"
    Image.new("RGB", (20, 20), "red").save(source)
    store = storage.ImageAssetStore(db, max_pixels=1000, max_frames=1)
    asset = await store.import_file(source)
    try:
        yield db, store, asset
    finally:
        await db.engine.dispose()


@pytest.mark.asyncio
async def test_gc_keeps_never_linked_assets_and_orphan_files(gc_env):
    db, store, asset = gc_env
    orphan = store.root / f"{uuid.uuid4()}.img"
    partial = store.root / f"{uuid.uuid4()}.part"
    orphan.write_bytes(b"uncommitted")
    partial.write_bytes(b"interrupted")
    assert await storage.collect_pending_images(db) == 0
    assert orphan.exists() and partial.exists()
    assert (store.root / asset.storage_key).exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", [False, True])
async def test_gc_removes_only_pending_unreferenced_asset(gc_env, missing):
    db, store, asset = gc_env
    path = store.root / asset.storage_key
    if missing:
        path.unlink()
    async with db.get_db() as session:
        row = await session.get(ImageAsset, asset.asset_id)
        row.state = "pending_delete"
        await session.commit()
    assert await storage.collect_pending_images(db) == 1
    assert not path.exists()
    async with db.get_db() as session:
        assert await session.get(ImageAsset, asset.asset_id) is None
    assert await storage.collect_pending_images(db) == 0


@pytest.mark.asyncio
async def test_gc_failed_unlink_retries(gc_env, monkeypatch):
    db, store, asset = gc_env
    async with db.get_db() as session:
        row = await session.get(ImageAsset, asset.asset_id)
        row.state = "pending_delete"
        await session.commit()
    original = Path.unlink

    def fail(path, *args, **kwargs):
        if path.name == asset.storage_key:
            raise PermissionError("injected locked file")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail)
        assert await storage.collect_pending_images(db) == 0
    async with db.get_db() as session:
        assert (await session.get(ImageAsset, asset.asset_id)).state == "pending_delete"
    assert await storage.collect_pending_images(db) == 1


@pytest.mark.asyncio
async def test_gc_rechecks_references_even_if_asset_marked_pending(gc_env):
    db, store, asset = gc_env
    async with db.get_db() as session:
        session.add(ConversationV2(conversation_id="c", user_id="u", platform_id="p"))
        session.add(
            ConversationImageRef(
                conversation_id="c", occurrence_id="i", asset_id=asset.asset_id
            )
        )
        row = await session.get(ImageAsset, asset.asset_id)
        row.state = "pending_delete"
        await session.commit()
    assert await storage.collect_pending_images(db) == 0
    assert (store.root / asset.storage_key).exists()
    with pytest.raises(ValueError, match="referenced"):
        await storage.cleanup_image_orphans(db, [asset.storage_key])


@pytest.mark.asyncio
async def test_gc_waits_for_active_reader(gc_env):
    db, store, asset = gc_env
    async with db.get_db() as session:
        session.add(ConversationV2(conversation_id="c", user_id="u", platform_id="p"))
        session.add(
            ConversationImageCheckpoint(
                conversation_id="c", checkpoint_id="cp", sequence=1, active=True
            )
        )
        session.add(
            ConversationImageRef(
                conversation_id="c",
                occurrence_id="i",
                asset_id=asset.asset_id,
                checkpoint_id="cp",
            )
        )
        await session.commit()
    async with store.open_image(
        conversation_id="c", occurrence_id="i", user_id="u", platform_id="p"
    ) as stream:
        # Simulate a legacy/external deletion transaction; GC must still wait.
        async with db.get_db() as session:
            ref = await session.get(ConversationImageRef, ("c", "i"))
            await session.delete(ref)
            row = await session.get(ImageAsset, asset.asset_id)
            row.state = "pending_delete"
            await session.commit()
        pending = asyncio.create_task(storage.collect_pending_images(db))
        await asyncio.sleep(0.08)
        assert not pending.done()
        assert stream.read(8) == b"\x89PNG\r\n\x1a\n"
    assert await asyncio.wait_for(pending, 2) == 1
    assert not (store.root / asset.storage_key).exists()


@pytest.mark.asyncio
async def test_explicit_maintenance_removes_selected_orphans_only(gc_env):
    db, store, asset = gc_env
    selected = store.root / f"{uuid.uuid4()}.part"
    untouched = store.root / f"{uuid.uuid4()}.img"
    selected.write_bytes(b"partial")
    untouched.write_bytes(b"keep")
    assert (
        await storage.cleanup_image_orphans(db, [selected.name, asset.storage_key]) == 2
    )
    assert not selected.exists()
    assert not (store.root / asset.storage_key).exists()
    assert untouched.exists()
    async with db.get_db() as session:
        assert not (await session.execute(select(ImageAsset))).scalars().all()


@pytest.mark.asyncio
async def test_orphan_selection_is_validated_before_deletion(gc_env):
    db, store, asset = gc_env
    orphan = store.root / f"{uuid.uuid4()}.img"
    orphan.write_bytes(b"keep")
    with pytest.raises(ValueError):
        await storage.cleanup_image_orphans(db, [orphan.name, "../outside.img"])
    assert orphan.exists()


@pytest.mark.asyncio
async def test_pending_asset_symlink_never_deletes_target(gc_env, tmp_path):
    db, store, asset = gc_env
    path = store.root / asset.storage_key
    path.unlink()
    outside = tmp_path / "outside"
    outside.write_bytes(b"keep")
    path.symlink_to(outside)
    async with db.get_db() as session:
        row = await session.get(ImageAsset, asset.asset_id)
        row.state = "pending_delete"
        await session.commit()
    assert await storage.collect_pending_images(db) == 0
    assert outside.read_bytes() == b"keep"


@pytest.mark.asyncio
async def test_gc_commit_failure_can_recover_missing_file(gc_env, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession

    db, store, asset = gc_env
    async with db.get_db() as session:
        row = await session.get(ImageAsset, asset.asset_id)
        row.state = "pending_delete"
        await session.commit()

    async def fail_commit(session):
        raise RuntimeError("injected commit failure")

    with monkeypatch.context() as patch:
        patch.setattr(AsyncSession, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="commit failure"):
            await storage.collect_pending_images(db)
    assert not (store.root / asset.storage_key).exists()
    async with db.get_db() as session:
        assert (await session.get(ImageAsset, asset.asset_id)).state == "pending_delete"
    assert await storage.collect_pending_images(db) == 1


@pytest.mark.asyncio
async def test_parent_deletion_preserves_real_original_until_child_deleted(gc_env):
    db, store, asset = gc_env
    history = [
        {
            "role": "user",
            "content": [
                {"type": "image_ref", "asset_id": asset.asset_id, "occurrence_id": "i"}
            ],
        },
        {"role": "_checkpoint", "content": {"id": "turn"}},
    ]
    await db.create_conversation("parent-owner", "test", cid="parent")
    await db.update_conversation(
        "parent",
        content=history,
        image_refs=[
            ConversationImageRef(
                conversation_id="parent",
                occurrence_id="i",
                asset_id=asset.asset_id,
                checkpoint_id="turn",
            )
        ],
    )
    await db.create_conversation(
        "child-owner",
        "test",
        cid="child",
        content=history,
        image_branch_source=("parent", "parent-owner", "test", "turn"),
    )
    await db.delete_conversation("parent")
    assert (store.root / asset.storage_key).exists()
    async with store.open_image(
        conversation_id="child",
        occurrence_id="i",
        user_id="child-owner",
        platform_id="test",
    ) as stream:
        assert stream.read(8) == b"\x89PNG\r\n\x1a\n"
    await db.delete_conversations_by_user_id("child-owner")
    assert not (store.root / asset.storage_key).exists()
    async with db.get_db() as session:
        assert await session.get(ImageAsset, asset.asset_id) is None


@pytest.mark.asyncio
async def test_real_conversation_delete_waits_for_active_reader(gc_env):
    db, store, asset = gc_env
    await db.create_conversation(
        "owner",
        "test",
        cid="c",
        content=[{"role": "_checkpoint", "content": {"id": "turn"}}],
    )
    await db.update_conversation(
        "c",
        image_refs=[
            ConversationImageRef(
                conversation_id="c",
                occurrence_id="i",
                asset_id=asset.asset_id,
                checkpoint_id="turn",
            )
        ],
    )
    async with store.open_image(
        conversation_id="c", occurrence_id="i", user_id="owner", platform_id="test"
    ) as stream:
        deletion = asyncio.create_task(db.delete_conversation("c"))
        await asyncio.sleep(0.08)
        assert not deletion.done()
        assert stream.read(8) == b"\x89PNG\r\n\x1a\n"
    await asyncio.wait_for(deletion, 2)
    assert not (store.root / asset.storage_key).exists()
