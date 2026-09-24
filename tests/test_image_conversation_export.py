"""Contracts for the single-conversation portable image archive."""

import json
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import delete
from sqlmodel import select

from astrbot.core import image_asset_store as storage
from astrbot.core.conversation_history_limits import HistoryTooLargeError
from astrbot.core.db.po import (
    ConversationImageCheckpoint,
    ConversationImageRef,
    ConversationV2,
    ImageAsset,
)
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.image_conversation_export import (
    ImageConversationExportError,
    build_image_conversation_export,
)


@pytest_asyncio.fixture
async def export_env(tmp_path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setattr(storage, "get_astrbot_data_path", lambda: str(root))
    monkeypatch.setattr(
        "astrbot.core.image_conversation_export.get_astrbot_temp_path",
        lambda: str(root / "temp"),
    )
    db = SQLiteDatabase(str(tmp_path / "test.db"))
    await db.initialize()
    db.inited = True
    store = storage.ImageAssetStore(db, max_pixels=1000, max_frames=10)

    assets = []
    for index, color in enumerate(("red", "blue")):
        source = tmp_path / f"image-{index}.png"
        Image.new("RGB", (8, 6), color).save(source)
        assets.append(await store.import_file(source))

    history = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_ref",
                    "schema_version": 1,
                    "occurrence_id": "shown-in-history",
                    "asset_id": assets[0].asset_id,
                    "description": "old description snapshot",
                    "description_status": "ready",
                    "description_version": 0,
                }
            ],
        },
        {"role": "_checkpoint", "content": {"id": "turn-1"}},
    ]
    async with db.get_db() as session:
        session.add(
            ConversationV2(
                conversation_id="conversation-1",
                user_id="u",
                platform_id="p",
                title="Portable test",
                content=history,
            )
        )
        await session.flush()
        session.add_all(
            [
                ConversationImageCheckpoint(
                    conversation_id="conversation-1",
                    checkpoint_id="turn-1",
                    sequence=1,
                ),
                ConversationImageCheckpoint(
                    conversation_id="conversation-1",
                    checkpoint_id="turn-2",
                    sequence=2,
                ),
            ]
        )
        session.add_all(
            [
                ConversationImageRef(
                    conversation_id="conversation-1",
                    occurrence_id="shown-in-history",
                    asset_id=assets[0].asset_id,
                    checkpoint_id="turn-1",
                    description="current description",
                    description_status="ready",
                    description_version=3,
                    user_annotation="user correction",
                ),
                ConversationImageRef(
                    conversation_id="conversation-1",
                    occurrence_id="compressed-out",
                    asset_id=assets[1].asset_id,
                    checkpoint_id="turn-2",
                    description="kept in active image memory",
                    description_status="pending",
                    user_annotation="",
                ),
                ConversationImageRef(
                    conversation_id="conversation-1",
                    occurrence_id="duplicate-asset",
                    asset_id=assets[0].asset_id,
                    checkpoint_id="turn-2",
                    description="same bytes, distinct occurrence",
                    description_status="ready",
                ),
            ]
        )
        await session.commit()

    try:
        yield db, store, assets, root, history
    finally:
        await db.engine.dispose()


@pytest.mark.asyncio
async def test_export_includes_active_images_missing_from_compressed_history(
    export_env,
):
    db, _, assets, root, history = export_env

    archive_path = await build_image_conversation_export(
        db, "conversation-1", user_id="u", platform_id="p"
    )
    try:
        assert archive_path.parent == root / "temp"
        with zipfile.ZipFile(archive_path) as archive:
            assert archive.testzip() is None
            manifest = json.loads(archive.read("manifest.json"))
            history_record = json.loads(archive.read("conversation.jsonl"))
            image_refs = [
                json.loads(line)
                for line in archive.read("image_refs.jsonl").decode().splitlines()
            ]

            assert manifest["format"] == "astrbot-image-conversation"
            assert manifest["version"] == 1
            assert manifest["imports_into_astrbot"] is False
            assert history_record["content"] == history
            assert {item["occurrence_id"] for item in image_refs} == {
                "shown-in-history",
                "compressed-out",
                "duplicate-asset",
            }
            current = next(
                item
                for item in image_refs
                if item["occurrence_id"] == "shown-in-history"
            )
            compressed = next(
                item for item in image_refs if item["occurrence_id"] == "compressed-out"
            )
            assert current["description"] == "current description"
            assert current["user_annotation"] == "user correction"
            assert compressed["checkpoint_sequence"] == 2
            assert compressed["media_path"] in archive.namelist()

            image_members = [
                name for name in archive.namelist() if name.startswith("media/")
            ]
            assert len(image_members) == 2
            for asset in assets:
                member = next(name for name in image_members if asset.asset_id in name)
                with archive.open(member) as packed_image:
                    assert packed_image.read() == (
                        Path(root / "image_assets" / asset.storage_key).read_bytes()
                    )
    finally:
        archive_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_export_rejects_another_owner_and_platform(export_env):
    db, *_ = export_env

    with pytest.raises(ImageConversationExportError):
        await build_image_conversation_export(
            db, "conversation-1", user_id="other", platform_id="p"
        )
    with pytest.raises(ImageConversationExportError):
        await build_image_conversation_export(
            db, "conversation-1", user_id="u", platform_id="other"
        )


@pytest.mark.asyncio
async def test_export_checks_history_size_before_loading_json(export_env, monkeypatch):
    db, _, _, root, _ = export_env
    monkeypatch.setattr(
        "astrbot.core.image_conversation_export.MAX_ONLINE_HISTORY_BYTES", 1
    )

    with pytest.raises(HistoryTooLargeError):
        await build_image_conversation_export(
            db, "conversation-1", user_id="u", platform_id="p"
        )
    assert not list((root / "temp").glob("astrbot_image_conversation_*.zip"))


@pytest.mark.asyncio
async def test_export_aborts_and_removes_partial_archive_when_image_is_corrupt(
    export_env,
):
    db, _, assets, root, _ = export_env
    image_path = root / "image_assets" / assets[0].storage_key
    image_path.write_bytes(b"corrupt")

    with pytest.raises(OSError):
        await build_image_conversation_export(
            db, "conversation-1", user_id="u", platform_id="p"
        )
    assert not list((root / "temp").glob("astrbot_image_conversation_*.zip"))


@pytest.mark.asyncio
async def test_export_rejects_unavailable_active_asset(export_env):
    db, _, assets, root, _ = export_env
    async with db.get_db() as session:
        asset = await session.get(ImageAsset, assets[0].asset_id)
        asset.state = "unavailable"
        await session.commit()

    with pytest.raises(ImageConversationExportError):
        await build_image_conversation_export(
            db, "conversation-1", user_id="u", platform_id="p"
        )
    assert not list((root / "temp").glob("astrbot_image_conversation_*.zip"))


@pytest.mark.asyncio
async def test_export_does_not_include_inactive_image_refs(export_env):
    db, _, assets, root, _ = export_env
    async with db.get_db() as session:
        session.add(
            ConversationImageCheckpoint(
                conversation_id="conversation-1",
                checkpoint_id="inactive-turn",
                sequence=3,
                active=False,
            )
        )
        session.add(
            ConversationImageRef(
                conversation_id="conversation-1",
                occurrence_id="inactive-ref",
                asset_id=assets[1].asset_id,
                checkpoint_id="inactive-turn",
                description="retired",
            )
        )
        await session.commit()

    archive_path = await build_image_conversation_export(
        db, "conversation-1", user_id="u", platform_id="p"
    )
    try:
        with zipfile.ZipFile(archive_path) as archive:
            image_refs = [
                json.loads(line)
                for line in archive.read("image_refs.jsonl").decode().splitlines()
            ]
        assert "inactive-ref" not in {item["occurrence_id"] for item in image_refs}
    finally:
        archive_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_export_uses_one_sqlite_snapshot_across_metadata_pages(
    export_env, monkeypatch
):
    db, _, _, root, _ = export_env
    monkeypatch.setattr("astrbot.core.image_conversation_export.EXPORT_PAGE_SIZE", 1)
    original_open = storage.ImageAssetStore.open_image
    updated = False

    @asynccontextmanager
    async def update_after_first_file_copy(self, **kwargs):
        nonlocal updated
        async with original_open(self, **kwargs) as source:
            yield source
        if not updated:
            updated = True
            async with db.get_db() as session:
                reference = await session.scalar(
                    select(ConversationImageRef).where(
                        ConversationImageRef.occurrence_id == "compressed-out"
                    )
                )
                reference.description = "changed during export"
                await session.commit()

    monkeypatch.setattr(
        storage.ImageAssetStore, "open_image", update_after_first_file_copy
    )

    archive_path = await build_image_conversation_export(
        db, "conversation-1", user_id="u", platform_id="p"
    )
    try:
        with zipfile.ZipFile(archive_path) as archive:
            image_refs = [
                json.loads(line)
                for line in archive.read("image_refs.jsonl").decode().splitlines()
            ]
        compressed = next(
            item for item in image_refs if item["occurrence_id"] == "compressed-out"
        )
        assert compressed["description"] == "kept in active image memory"
    finally:
        archive_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_export_aborts_when_reference_is_revoked_mid_export(
    export_env, monkeypatch
):
    db, _, assets, root, _ = export_env
    monkeypatch.setattr("astrbot.core.image_conversation_export.EXPORT_PAGE_SIZE", 1)
    original_open = storage.ImageAssetStore.open_image
    revoked = False
    asset_for_occurrence = {
        "shown-in-history": assets[0].asset_id,
        "duplicate-asset": assets[0].asset_id,
        "compressed-out": assets[1].asset_id,
    }

    @asynccontextmanager
    async def revoke_another_asset_after_first_copy(self, **kwargs):
        nonlocal revoked
        async with original_open(self, **kwargs) as source:
            yield source
        if not revoked:
            revoked = True
            copied_asset_id = asset_for_occurrence[kwargs["occurrence_id"]]
            target_asset_id = next(
                asset.asset_id for asset in assets if asset.asset_id != copied_asset_id
            )
            async with db.get_db() as session:
                await session.execute(
                    delete(ConversationImageRef).where(
                        ConversationImageRef.asset_id == target_asset_id
                    )
                )
                await session.commit()

    monkeypatch.setattr(
        storage.ImageAssetStore,
        "open_image",
        revoke_another_asset_after_first_copy,
    )

    with pytest.raises(PermissionError):
        await build_image_conversation_export(
            db, "conversation-1", user_id="u", platform_id="p"
        )
    assert not list((root / "temp").glob("astrbot_image_conversation_*.zip"))


@pytest.mark.asyncio
async def test_export_fails_when_active_reference_has_missing_asset_row(export_env):
    db, _, assets, root, _ = export_env
    async with db.get_db() as session, session.begin():
        await session.execute(
            delete(ImageAsset).where(ImageAsset.asset_id == assets[1].asset_id)
        )
    with pytest.raises(ImageConversationExportError, match="no asset metadata"):
        await build_image_conversation_export(
            db, "conversation-1", user_id="u", platform_id="p"
        )
    assert list((root / "temp").glob("astrbot_image_conversation_*.zip")) == []
