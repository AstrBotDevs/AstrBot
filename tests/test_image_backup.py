"""Image snapshot integrity, restore isolation and bounded media copy contracts."""

import asyncio
import json
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import select, text

from astrbot.core import image_asset_store as storage
from astrbot.core.backup import exporter as export_module
from astrbot.core.backup import importer as import_module
from astrbot.core.backup.constants import IMAGE_MEDIA_PREFIX
from astrbot.core.backup.exporter import AstrBotExporter
from astrbot.core.backup.importer import AstrBotImporter
from astrbot.core.config.default import VERSION
from astrbot.core.db.po import (
    ConversationImageCheckpoint,
    ConversationImageRef,
    ConversationV2,
    ImageAsset,
)
from astrbot.core.db.sqlite import SQLiteDatabase


@pytest_asyncio.fixture
async def image_backup_env(tmp_path, monkeypatch):
    root = tmp_path / "source"
    root.mkdir()
    for module in (storage, export_module, import_module):
        monkeypatch.setattr(module, "get_astrbot_data_path", lambda: str(root))
    monkeypatch.setattr(export_module, "get_backup_directories", dict)
    monkeypatch.setattr(import_module, "get_backup_directories", dict)
    db = SQLiteDatabase(str(tmp_path / "source.db"))
    await db.initialize()
    db.inited = True
    source = tmp_path / "input.png"
    Image.new("RGB", (20, 10), "red").save(source)
    store = storage.ImageAssetStore(db, max_pixels=1000, max_frames=1)
    asset = await store.import_file(source)
    async with db.get_db() as session:
        session.add(
            ConversationV2(
                conversation_id="c",
                platform_id="p",
                user_id="u",
                content=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_ref",
                                "occurrence_id": "o",
                                "asset_id": asset.asset_id,
                            }
                        ],
                    },
                    {"role": "_checkpoint", "content": {"id": "turn"}},
                ],
            )
        )
        await session.flush()
        session.add(
            ConversationImageCheckpoint(
                conversation_id="c", checkpoint_id="turn", sequence=1
            )
        )
        session.add(
            ConversationImageRef(
                conversation_id="c",
                occurrence_id="o",
                asset_id=asset.asset_id,
                checkpoint_id="turn",
                description="red",
                description_status="ready",
            )
        )
        await session.commit()
    exporter = AstrBotExporter(db, config_path=str(tmp_path / "absent.json"))
    archive = await exporter.export_all(str(tmp_path / "backups"))
    try:
        yield db, store, asset, Path(archive), monkeypatch, tmp_path
    finally:
        await db.engine.dispose()


def rewrite_archive(source, target, mutate):
    """Rewrite a small fixture archive with intentional corruption.

    Args:
        source: Original valid archive.
        target: Corrupt archive destination.
        mutate: Callable modifying metadata and archive entries.
    """
    with zipfile.ZipFile(source) as zf:
        files = {name: zf.read(name) for name in zf.namelist()}
    data = json.loads(files["databases/main_db.json"])
    mutate(data, files)
    files["databases/main_db.json"] = json.dumps(data).encode()
    with zipfile.ZipFile(target, "w") as zf:
        for name, value in files.items():
            zf.writestr(name, value)


@pytest.mark.asyncio
async def test_cross_root_restore_authorized_read_and_foreign_keys(image_backup_env):
    db, store, asset, archive, monkeypatch, tmp_path = image_backup_env
    new_root = tmp_path / "destination"
    for module in (storage, export_module, import_module):
        monkeypatch.setattr(module, "get_astrbot_data_path", lambda: str(new_root))
    destination = SQLiteDatabase(str(tmp_path / "restored.db"))
    await destination.initialize()
    destination.inited = True
    try:
        async with destination.get_db() as session:
            await session.execute(text("PRAGMA foreign_keys=ON"))
        result = await AstrBotImporter(destination).import_all(str(archive))
        assert result.success, result.errors
        restored = storage.ImageAssetStore(destination, max_pixels=1000, max_frames=1)
        async with restored.open_image(
            conversation_id="c", occurrence_id="o", user_id="u", platform_id="p"
        ) as stream:
            assert stream.read() == (store.root / asset.storage_key).read_bytes()
        async with destination.get_db() as session:
            ref = (await session.execute(select(ConversationImageRef))).scalar_one()
            assert ref.description == "red"
            checkpoint = (
                await session.execute(select(ConversationImageCheckpoint))
            ).scalar_one()
            assert checkpoint.sequence == 1 and checkpoint.active
        # Replacing a populated database also clears image children before parents.
        again = await AstrBotImporter(destination).import_all(str(archive))
        assert again.success, again.errors
        assert (restored.root / ".store.lock").exists()
    finally:
        await destination.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "missing",
        "checksum",
        "path",
        "asset",
        "association",
        "ledger",
        "inactive",
        "duplicate_sequence",
        "size_mismatch",
        "unexpected",
        "wrong_turn",
        "history_order",
    ],
)
async def test_invalid_media_rejected_before_clear(image_backup_env, failure):
    db, store, asset, archive, monkeypatch, tmp_path = image_backup_env
    corrupt = tmp_path / f"{failure}.zip"

    def mutate(data, files):
        media = IMAGE_MEDIA_PREFIX + asset.storage_key
        if failure == "missing":
            files.pop(media)
        elif failure == "checksum":
            files[media] = b"x" * asset.byte_size
        elif failure == "path":
            data["image_assets"][0]["storage_key"] = "../escape.img"
        elif failure == "asset":
            data["conversation_image_refs"][0]["asset_id"] = "unknown"
        elif failure == "association":
            data["conversation_image_refs"] = []
        elif failure == "ledger":
            data["conversation_image_checkpoints"] = []
        elif failure == "inactive":
            data["conversation_image_checkpoints"][0]["active"] = False
        elif failure == "duplicate_sequence":
            row = dict(data["conversation_image_checkpoints"][0], checkpoint_id="other")
            data["conversation_image_checkpoints"].append(row)
        elif failure == "size_mismatch":
            data["image_assets"][0]["byte_size"] += 1
        elif failure == "wrong_turn":
            data["conversations"][0]["content"][-1]["content"]["id"] = "other"
            data["conversation_image_checkpoints"].append(
                {
                    "conversation_id": "c",
                    "checkpoint_id": "other",
                    "sequence": 2,
                    "active": True,
                }
            )
        elif failure == "history_order":
            data["conversation_image_checkpoints"].append(
                {
                    "conversation_id": "c",
                    "checkpoint_id": "other",
                    "sequence": 2,
                    "active": True,
                }
            )
            data["conversations"][0]["content"].insert(
                0, {"role": "_checkpoint", "content": {"id": "other"}}
            )
        elif failure == "unexpected":
            files[IMAGE_MEDIA_PREFIX + "../../escape"] = b"x"

    rewrite_archive(archive, corrupt, mutate)
    importer = AstrBotImporter(db)
    importer._clear_main_db = AsyncMock()
    result = await importer.import_all(str(corrupt))
    assert not result.success
    importer._clear_main_db.assert_not_awaited()
    assert (store.root / asset.storage_key).exists()


@pytest.mark.asyncio
async def test_conflicting_existing_identity_is_never_overwritten(image_backup_env):
    db, store, asset, archive, monkeypatch, tmp_path = image_backup_env
    path = store.root / asset.storage_key
    conflict = b"x" * asset.byte_size
    path.write_bytes(conflict)
    importer = AstrBotImporter(db)
    importer._clear_main_db = AsyncMock()
    result = await importer.import_all(str(archive))
    assert not result.success
    importer._clear_main_db.assert_not_awaited()
    assert path.read_bytes() == conflict


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_missing_original_makes_export_fail(image_backup_env):
    db, store, asset, archive, monkeypatch, tmp_path = image_backup_env
    (store.root / asset.storage_key).unlink()
    with pytest.raises(FileNotFoundError):
        await AstrBotExporter(db).export_all(str(tmp_path / "failed"))
    assert not list((tmp_path / "failed").glob("*.zip"))


@pytest.mark.asyncio
async def test_restore_failure_keeps_published_orphans_and_old_database(
    image_backup_env,
):
    db, store, asset, archive, monkeypatch, tmp_path = image_backup_env
    new_root = tmp_path / "new"
    for module in (storage, import_module):
        monkeypatch.setattr(module, "get_astrbot_data_path", lambda: str(new_root))
    importer = AstrBotImporter(db)
    importer._clear_main_db = AsyncMock(side_effect=RuntimeError("clear failed"))
    result = await importer.import_all(str(archive))
    assert not result.success
    assert (new_root / "image_assets" / asset.storage_key).read_bytes() == (
        store.root / asset.storage_key
    ).read_bytes()
    async with db.get_db() as session:
        assert (
            await session.execute(select(ImageAsset))
        ).scalar_one().asset_id == asset.asset_id


@pytest.mark.asyncio
async def test_backup_lock_excludes_store_operations(image_backup_env):
    db, store, asset, archive, monkeypatch, tmp_path = image_backup_env
    entered = asyncio.Event()
    release = asyncio.Event()
    exporter = AstrBotExporter(db)
    original = exporter._export_main_database

    async def paused():
        entered.set()
        await release.wait()
        return await original()

    exporter._export_main_database = paused
    task = asyncio.create_task(exporter.export_all(str(tmp_path / "locked")))
    await entered.wait()
    competing = asyncio.create_task(storage.collect_pending_images(db))
    await asyncio.sleep(0.08)
    assert not competing.done()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await asyncio.wait_for(competing, 2) == 0
    assert not list((tmp_path / "locked").glob("*.zip"))


@pytest.mark.asyncio
async def test_old_backup_without_image_tables_restores(image_backup_env):
    db, store, asset, archive, monkeypatch, tmp_path = image_backup_env
    old = tmp_path / "old.zip"
    with zipfile.ZipFile(old, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"astrbot_version": VERSION}))
        zf.writestr("databases/main_db.json", json.dumps({"conversations": []}))
    result = await AstrBotImporter(db).import_all(str(old))
    assert result.success, result.errors
    async with db.get_db() as session:
        assert not (await session.execute(select(ImageAsset))).scalars().all()
    # Old files remain safe, charged orphans instead of destructive directory moves.
    assert (store.root / asset.storage_key).exists()


@pytest.mark.asyncio
async def test_image_zip_reads_are_bounded_and_restore_cancellation_cleans_part(
    image_backup_env, monkeypatch
):
    db, store, asset, archive, _, tmp_path = image_backup_env
    root = tmp_path / "cancelled"
    for module in (storage, import_module):
        monkeypatch.setattr(module, "get_astrbot_data_path", lambda: str(root))
    original_read = zipfile.ZipExtFile.read
    reads = 0

    def bounded_read(stream, n=-1):
        nonlocal reads
        if stream.name.startswith(IMAGE_MEDIA_PREFIX):
            assert 0 < n <= storage.COPY_CHUNK_BYTES
            reads += 1
            # Validation reads data and EOF, publication then reads its first chunk.
            if reads == 3:
                asyncio.current_task().cancel()
        return original_read(stream, n)

    monkeypatch.setattr(zipfile.ZipExtFile, "read", bounded_read)
    importer = AstrBotImporter(db)
    importer._clear_main_db = AsyncMock()
    with pytest.raises(asyncio.CancelledError):
        await importer.import_all(str(archive))
    importer._clear_main_db.assert_not_awaited()
    assert not list((root / "image_assets").glob("*.part"))
    assert not list((root / "image_assets").glob("*.img"))
    async with storage.image_store_lock():
        pass


@pytest.mark.asyncio
async def test_image_lookalike_in_tool_arguments_is_not_an_asset_reference(
    image_backup_env,
):
    db, store, asset, archive, monkeypatch, tmp_path = image_backup_env
    adjusted = tmp_path / "arguments.zip"

    def mutate(data, files):
        data["conversations"][0]["content"].append(
            {
                "role": "assistant",
                "content": "ok",
                "tool_calls": [
                    {
                        "arguments": {
                            "type": "image_ref",
                            "asset_id": "ordinary_user_json",
                        }
                    }
                ],
            }
        )

    rewrite_archive(archive, adjusted, mutate)
    result = await AstrBotImporter(db).import_all(str(adjusted))
    assert result.success, result.errors


@pytest.mark.asyncio
async def test_legacy_empty_backup_does_not_inspect_unrelated_image_orphans(
    image_backup_env,
):
    db, store, asset, archive, monkeypatch, tmp_path = image_backup_env
    (store.root / "unexpected_directory").mkdir()
    old = tmp_path / "old_empty.zip"
    with zipfile.ZipFile(old, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"astrbot_version": VERSION}))
        zf.writestr("databases/main_db.json", json.dumps({"conversations": []}))
    result = await AstrBotImporter(db).import_all(str(old))
    assert result.success, result.errors


@pytest.mark.asyncio
async def test_directory_fsync_failure_precedes_clear_and_retains_orphan(
    image_backup_env,
):
    import os
    import stat

    if os.name == "nt":
        pytest.skip("Directory fsync is POSIX-only")
    db, store, asset, archive, monkeypatch, tmp_path = image_backup_env
    root = tmp_path / "fsync"
    for module in (storage, import_module):
        monkeypatch.setattr(module, "get_astrbot_data_path", lambda: str(root))
    original = os.fsync

    def failed_directory_sync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("directory sync failed")
        original(fd)

    monkeypatch.setattr(import_module.os, "fsync", failed_directory_sync)
    importer = AstrBotImporter(db)
    importer._clear_main_db = AsyncMock()
    result = await importer.import_all(str(archive))
    assert not result.success
    importer._clear_main_db.assert_not_awaited()
    assert (root / "image_assets" / asset.storage_key).exists()
    assert not list((root / "image_assets").glob("*.part"))


@pytest.mark.asyncio
@pytest.mark.parametrize("checkpoints", [("b", "a"), ("a", "b", "a")])
async def test_legacy_text_checkpoint_edits_remain_backup_compatible(
    image_backup_env, checkpoints
):
    db, store, asset, archive, monkeypatch, tmp_path = image_backup_env
    original = [{"role": "_checkpoint", "content": {"id": cp}} for cp in ("a", "b")]
    edited = [{"role": "_checkpoint", "content": {"id": cp}} for cp in checkpoints]
    await db.create_conversation("text-user", "p", cid="text", content=original)
    await db.update_conversation(
        "text", content=edited, expected_history=original, prune_image_refs=True
    )
    exported = await AstrBotExporter(
        db, config_path=str(tmp_path / "absent.json")
    ).export_all(str(tmp_path / "text-backup"))
    result = await AstrBotImporter(db).import_all(exported)
    assert result.success, result.to_dict()
    assert (await db.get_conversation_by_id("text")).content == edited
