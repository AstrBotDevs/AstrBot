"""Offline migration integration, recovery, and command-line safety."""

import base64
import json
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import text
from sqlmodel import select

from astrbot.core import image_asset_store as storage
from astrbot.core import image_history_maintenance as maintenance
from astrbot.core import image_history_migration as ordinary
from astrbot.core.db.po import (
    ConversationImageRef,
    ImageAsset,
    ImageHistoryMigrationTask,
)
from astrbot.core.db.sqlite import SQLiteDatabase


@pytest_asyncio.fixture
async def maintenance_env(tmp_path, monkeypatch):
    root = tmp_path / "data"
    (root / "temp").mkdir(parents=True)
    monkeypatch.setattr(storage, "get_astrbot_data_path", lambda: str(root))
    monkeypatch.setattr(maintenance, "get_astrbot_data_path", lambda: str(root))
    monkeypatch.setattr(ordinary, "get_astrbot_temp_path", lambda: str(root / "temp"))
    db = SQLiteDatabase(str(root / "data_v4.db"))
    await db.initialize()
    db.inited = True
    await db.create_conversation("owner", "platform", cid="legacy")
    try:
        yield db, root
    finally:
        await db.engine.dispose()


def image_url(tmp_path, color="red", padded_bytes=0):
    source = tmp_path / f"{color}.png"
    Image.new("RGB", (12, 8), color).save(source)
    if padded_bytes:
        with source.open("ab") as stream:
            stream.truncate(padded_bytes)
    return "data:image/png;base64," + base64.b64encode(source.read_bytes()).decode(
        "ascii"
    )


async def store_history(db, history):
    # Direct binding can seed an oversized legacy source without online readers.
    async with db.get_db() as session, session.begin():
        await session.execute(
            text(
                "UPDATE conversations SET content=:value WHERE conversation_id='legacy'"
            ),
            {"value": json.dumps(history)},
        )


async def rows(db, model):
    async with db.get_db() as session:
        return list((await session.execute(select(model))).scalars())


@pytest.mark.asyncio
async def test_preflight_then_apply_preserves_text_and_is_idempotent(
    maintenance_env, tmp_path
):
    db, root = maintenance_env
    original = [
        {
            "role": "user",
            "extra": {"keep": '中文\\"'},
            "content": [
                {"type": "text", "text": "original note"},
                {"image_url": {"url": image_url(tmp_path)}, "type": "image_url"},
            ],
        },
        {"role": "assistant", "content": "answer"},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": image_url(tmp_path, "blue")}
            ],
        },
    ]
    await store_history(db, original)
    result = await maintenance.run_image_history_maintenance(db, "legacy")
    assert result["status"] == "prepared"
    assert result["image_count"] == 2
    assert (await db.get_conversation_by_id("legacy")).content == original
    assert await rows(db, ImageAsset) == []
    assert Path(result["backup_directory"]).joinpath("database.sqlite").is_file()

    done = await maintenance.run_image_history_maintenance(db, "legacy", apply=True)
    assert done["status"] == "committed"
    stored = (await db.get_conversation_by_id("legacy")).content
    assert stored[0]["extra"] == original[0]["extra"]
    assert stored[0]["content"][0] == original[0]["content"][0]
    assert stored[0]["content"][1]["type"] == "image_ref"
    assert stored[3]["content"][0]["type"] == "image_ref"
    assert (
        len(await rows(db, ImageAsset))
        == len(await rows(db, ConversationImageRef))
        == 2
    )
    assert all(
        item.source_kind == "legacy_model_input" for item in await rows(db, ImageAsset)
    )
    assert (await rows(db, ImageHistoryMigrationTask))[0].state == "committed"
    ids = {item.asset_id for item in await rows(db, ImageAsset)}
    again = await maintenance.run_image_history_maintenance(db, "legacy", apply=True)
    assert again["status"] == "already_committed"
    assert {item.asset_id for item in await rows(db, ImageAsset)} == ids
    assert len(list((root / "image_assets").glob("*.img"))) == 2


@pytest.mark.asyncio
async def test_migrates_actual_oversized_base64_history(maintenance_env, tmp_path):
    db, _ = maintenance_env
    original = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image_url(tmp_path, padded_bytes=13 * 1024 * 1024)
                    },
                }
            ],
        }
    ]
    await store_history(db, original)
    assert len(json.dumps(original)) > 16 * 1024 * 1024
    result = await maintenance.run_image_history_maintenance(db, "legacy", apply=True)
    assert result["status"] == "committed"
    assert result["source_bytes"] > 16 * 1024 * 1024
    assert result["output_bytes"] < 1024
    assert (await db.get_conversation_by_id("legacy")).content[0]["content"][0][
        "type"
    ] == "image_ref"


@pytest.mark.asyncio
async def test_resume_after_asset_commit_does_not_publish_duplicate(
    maintenance_env, tmp_path
):
    db, root = maintenance_env
    original = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_url(tmp_path)}},
                {
                    "type": "image_url",
                    "image_url": {"url": image_url(tmp_path, "blue")},
                },
            ],
        }
    ]
    await store_history(db, original)
    actual_import = storage.ImageAssetStore.import_file

    async def interrupt_after_publish(self, *args, **kwargs):
        await actual_import(self, *args, **kwargs)
        raise RuntimeError("simulated lost response after asset commit")

    with patch.object(storage.ImageAssetStore, "import_file", interrupt_after_publish):
        with pytest.raises(RuntimeError, match="lost response"):
            await maintenance.run_image_history_maintenance(db, "legacy", apply=True)
    assert (await db.get_conversation_by_id("legacy")).content == original
    assert len(await rows(db, ImageAsset)) == 1
    published = (await rows(db, ImageAsset))[0].asset_id
    done = await maintenance.run_image_history_maintenance(db, "legacy", apply=True)
    assert done["status"] == "committed"
    assert len(await rows(db, ImageAsset)) == 2
    assert published in {item.asset_id for item in await rows(db, ImageAsset)}
    assert len(list((root / "image_assets").glob("*.img"))) == 2


@pytest.mark.asyncio
async def test_resume_after_history_commit_reports_already_done(
    maintenance_env, tmp_path
):
    db, _ = maintenance_env
    await store_history(
        db,
        [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url(tmp_path)}}
                ],
            }
        ],
    )
    actual_commit = maintenance.commit_migrated_history

    async def lose_response(*args, **kwargs):
        await actual_commit(*args, **kwargs)
        raise RuntimeError("simulated lost response after history commit")

    with patch.object(maintenance, "commit_migrated_history", lose_response):
        with pytest.raises(RuntimeError, match="lost response"):
            await maintenance.run_image_history_maintenance(db, "legacy", apply=True)
    assert (await rows(db, ImageHistoryMigrationTask))[0].state == "committed"
    assert (await maintenance.run_image_history_maintenance(db, "legacy", apply=True))[
        "status"
    ] == "already_committed"
    assert len(await rows(db, ImageAsset)) == 1


@pytest.mark.asyncio
async def test_changed_source_during_import_is_not_overwritten(
    maintenance_env, tmp_path
):
    db, _ = maintenance_env
    await store_history(
        db,
        [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url(tmp_path)}}
                ],
            }
        ],
    )
    actual_commit = maintenance.commit_migrated_history
    changed = [{"role": "user", "content": "new source"}]

    async def change_before_commit(*args, **kwargs):
        await store_history(db, changed)
        return await actual_commit(*args, **kwargs)

    with patch.object(maintenance, "commit_migrated_history", change_before_commit):
        with pytest.raises(Exception, match="changed"):
            await maintenance.run_image_history_maintenance(db, "legacy", apply=True)
    assert (await db.get_conversation_by_id("legacy")).content == changed
    assert await rows(db, ConversationImageRef) == []
    assert (await rows(db, ImageHistoryMigrationTask))[0].state == "prepared"


@pytest.mark.asyncio
async def test_damaged_backup_is_rejected_before_image_publication(
    maintenance_env, tmp_path
):
    db, _ = maintenance_env
    original = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_url(tmp_path)}}
            ],
        }
    ]
    await store_history(db, original)
    result = await maintenance.run_image_history_maintenance(db, "legacy")
    backup = Path(result["backup_directory"]) / "database.sqlite"
    with backup.open("ab") as stream:
        stream.write(b"damaged")
    with pytest.raises(maintenance.ImageHistoryMaintenanceError, match="integrity"):
        await maintenance.run_image_history_maintenance(db, "legacy", apply=True)
    assert (await db.get_conversation_by_id("legacy")).content == original
    assert await rows(db, ImageAsset) == []


@pytest.mark.asyncio
async def test_large_text_is_preserved_when_output_cannot_fit(maintenance_env):
    db, root = maintenance_env
    original = [{"role": "user", "content": "x" * (16 * 1024 * 1024)}]
    await store_history(db, original)
    before = maintenance.fingerprint_conversation(Path(db.db_path), "legacy")
    with pytest.raises(ValueError):
        await maintenance.run_image_history_maintenance(db, "legacy", apply=True)
    after = maintenance.fingerprint_conversation(Path(db.db_path), "legacy")
    assert before == after
    assert await rows(db, ImageAsset) == []
    assert not list((root / "image_assets").glob("*.img"))


@pytest.mark.asyncio
async def test_retry_reclaims_only_owned_partial_images_before_capacity_check(
    maintenance_env, tmp_path, monkeypatch
):
    import uuid

    db, root = maintenance_env
    original = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": image_url(tmp_path)},
                {"type": "image_url", "image_url": image_url(tmp_path, "blue")},
            ],
        }
    ]
    await store_history(db, original)
    prepared = await maintenance.run_image_history_maintenance(db, "legacy")
    namespace = uuid.UUID(prepared["task_id"])
    own = []
    for index in range(2):
        part = (
            root / "image_assets" / f"{uuid.uuid5(namespace, f'asset:0:{index}')}.part"
        )
        part.write_bytes(b"unfinished" * 30)
        own.append(part)
    unrelated = root / "image_assets" / f"{uuid.uuid4()}.part"
    unrelated.write_bytes(b"unrelated" * 20)
    monkeypatch.setattr(
        maintenance,
        "DEFAULT_MAX_TOTAL_BYTES",
        prepared["additional_image_bytes"] + unrelated.stat().st_size,
    )
    again = await maintenance.run_image_history_maintenance(db, "legacy")
    assert again["reclaimable_staging_bytes"] == 600
    assert all(path.exists() for path in own)
    done = await maintenance.run_image_history_maintenance(db, "legacy", apply=True)
    assert done["status"] == "committed"
    assert all(not path.exists() for path in own)
    assert unrelated.read_bytes() == b"unrelated" * 20
    assert len(await rows(db, ImageAsset)) == 2


@pytest.mark.asyncio
async def test_incomplete_backup_rechecks_disk_before_resuming_gallery_copy(
    maintenance_env, tmp_path, monkeypatch
):
    import uuid
    from types import SimpleNamespace

    db, root = maintenance_env
    await store_history(db, [{"role": "user", "content": "keep"}])
    fingerprint = maintenance.fingerprint_conversation(Path(db.db_path), "legacy")
    job = root / "job"
    (job / "backup").mkdir(parents=True)
    maintenance.create_database_snapshot(
        Path(db.db_path), job / "backup" / "database.sqlite"
    )
    gallery = root / "image_assets"
    gallery.mkdir(exist_ok=True)
    (gallery / f"{uuid.uuid4()}.img").write_bytes(b"existing bytes")
    monkeypatch.setattr(
        maintenance.shutil, "disk_usage", lambda _: SimpleNamespace(free=0)
    )
    with pytest.raises(maintenance.ImageHistoryMaintenanceError, match="disk space"):
        maintenance._prepare_backup(Path(db.db_path), job, fingerprint, gallery)
    assert not (job / "backup" / "ready.json").exists()
    assert not list((job / "backup" / "image_assets").iterdir())


@pytest.mark.asyncio
async def test_completed_backup_still_requires_streaming_staging_space(
    maintenance_env, monkeypatch
):
    from types import SimpleNamespace

    db, _ = maintenance_env
    original = [{"role": "user", "content": "keep"}]
    await store_history(db, original)
    await maintenance.run_image_history_maintenance(db, "legacy")
    monkeypatch.setattr(
        maintenance.shutil, "disk_usage", lambda _: SimpleNamespace(free=0)
    )
    with pytest.raises(maintenance.ImageHistoryMaintenanceError, match="staging"):
        await maintenance.run_image_history_maintenance(db, "legacy", apply=True)
    assert (await db.get_conversation_by_id("legacy")).content == original
