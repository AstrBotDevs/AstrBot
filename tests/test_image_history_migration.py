"""Safety and lifecycle tests for bounded legacy image migration."""

import base64
import errno

import pytest
import pytest_asyncio
from PIL import Image
from sqlmodel import select

from astrbot.core import image_asset_store
from astrbot.core import image_history_migration as migration
from astrbot.core.db.po import (
    ConversationImageCheckpoint,
    ConversationImageRef,
    ImageAsset,
)
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.image_history_migration import (
    ImageHistoryMigrationError,
    migrate_legacy_image_history,
)


@pytest_asyncio.fixture
async def migration_env(tmp_path, monkeypatch):
    """Create an isolated database, managed store, and AstrBot temp directory."""
    data_root = tmp_path / "data"
    temp_root = data_root / "temp"
    temp_root.mkdir(parents=True)
    monkeypatch.setattr(
        image_asset_store, "get_astrbot_data_path", lambda: str(data_root)
    )
    monkeypatch.setattr(
        "astrbot.core.image_history_migration.get_astrbot_temp_path",
        lambda: str(temp_root),
    )
    db = SQLiteDatabase(str(tmp_path / "migration.db"))
    await db.initialize()
    db.inited = True
    await db.create_conversation("owner", "platform", cid="conversation")
    try:
        yield db, data_root, temp_root
    finally:
        await db.engine.dispose()


def image_data_uri(color="red"):
    """Return a small valid PNG data URI for migration tests.

    Args:
        color: Pillow-compatible fill color.

    Returns:
        A base64-encoded PNG data URI.
    """
    from io import BytesIO

    image = Image.new("RGB", (12, 9), color)
    stream = BytesIO()
    image.save(stream, format="PNG")
    return "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode()


def inline_image(url):
    """Build the historical nested image block used by provider contexts.

    Args:
        url: Data URI or local image reference.

    Returns:
        A persisted image_url mapping.
    """
    return {"type": "image_url", "image_url": {"url": url}}


async def db_rows(db, model):
    async with db.get_db() as session:
        return list((await session.execute(select(model))).scalars())


async def migrate(db, history):
    return await migrate_legacy_image_history(
        db,
        "conversation",
        history,
        user_id="owner",
        platform_id="platform",
    )


@pytest.mark.asyncio
async def test_migrates_inline_data_into_pending_conversation_reference(migration_env):
    db, data_root, _ = migration_env
    history = [
        {"role": "user", "content": [inline_image(image_data_uri())]},
        {"role": "assistant", "content": "It is a red square."},
    ]
    await db.update_conversation("conversation", content=history)

    result = await migrate(db, history)

    assert result.migrated_images == 1
    ref_part = result.history[0]["content"][0]
    assert ref_part["type"] == "image_ref"
    assert ref_part["description"] == ""
    assert ref_part["description_status"] == "pending"
    checkpoint_id = result.history[-1]["content"]["id"]
    refs = await db_rows(db, ConversationImageRef)
    checkpoints = await db_rows(db, ConversationImageCheckpoint)
    assets = await db_rows(db, ImageAsset)
    assert len(refs) == len(checkpoints) == len(assets) == 1
    assert refs[0].checkpoint_id == checkpoint_id
    assert refs[0].occurrence_id == ref_part["occurrence_id"]
    assert refs[0].asset_id == ref_part["asset_id"]
    assert assets[0].source_kind == "legacy_model_input"
    assert (data_root / "image_assets" / assets[0].storage_key).read_bytes()
    stored = await db.get_conversation_by_id("conversation")
    assert stored.content == result.history


@pytest.mark.asyncio
async def test_adds_separate_checkpoints_for_unmarked_user_turns(migration_env):
    db, _, _ = migration_env
    history = [
        {"role": "user", "content": [inline_image(image_data_uri("red"))]},
        {"role": "assistant", "content": "first"},
        {"role": "user", "content": [inline_image(image_data_uri("blue"))]},
        {"role": "assistant", "content": "second"},
    ]
    await db.update_conversation("conversation", content=history)

    result = await migrate(db, history)

    checkpoint_rows = await db_rows(db, ConversationImageCheckpoint)
    refs = await db_rows(db, ConversationImageRef)
    assert len(checkpoint_rows) == len(refs) == 2
    assert len({ref.checkpoint_id for ref in refs}) == 2
    assert result.history[0]["content"][0]["type"] == "image_ref"
    second_user = next(
        item
        for item in result.history
        if item.get("role") == "user"
        and item["content"][0].get("type") == "image_ref"
        and item["content"][0]["asset_id"]
        != result.history[0]["content"][0]["asset_id"]
    )
    assert second_user["content"][0]["type"] == "image_ref"
    assert len([item for item in result.history if item["role"] == "_checkpoint"]) == 2
    assert all(row.active for row in checkpoint_rows)


@pytest.mark.asyncio
async def test_preserves_existing_checkpoint_and_binds_inline_image(migration_env):
    db, _, _ = migration_env
    history = [
        {"role": "user", "content": [inline_image(image_data_uri())]},
        {"role": "assistant", "content": "answer"},
        {"role": "_checkpoint", "content": {"id": "existing-checkpoint"}},
    ]
    await db.update_conversation("conversation", content=history)

    result = await migrate(db, history)

    assert result.history[-1] == history[-1]
    ref = (await db_rows(db, ConversationImageRef))[0]
    assert ref.checkpoint_id == "existing-checkpoint"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url,reason",
    [
        ("https://127.0.0.1:1/image.png", "unavailable"),
        ("data:image/png;base64,not-base64!", "invalid_image"),
        ("file:///definitely/missing/image.png", "unavailable"),
    ],
)
async def test_unavailable_or_corrupt_source_keeps_history_and_catalog_unchanged(
    migration_env, url, reason
):
    db, _, _ = migration_env
    valid_history = [{"role": "user", "content": "original"}]
    await db.update_conversation("conversation", content=valid_history)
    history = [
        {"role": "user", "content": [inline_image(url)]},
        {"role": "assistant", "content": "answer"},
    ]

    with pytest.raises(ImageHistoryMigrationError) as error:
        await migrate(db, history)

    assert error.value.reason == reason
    stored = await db.get_conversation_by_id("conversation")
    assert stored.content == valid_history
    assert await db_rows(db, ImageAsset) == []
    assert await db_rows(db, ConversationImageRef) == []
    assert await db_rows(db, ConversationImageCheckpoint) == []


@pytest.mark.asyncio
async def test_rejects_path_outside_temp_without_reading_it(migration_env, tmp_path):
    db, _, _ = migration_env
    outside = tmp_path / "outside.png"
    Image.new("RGB", (12, 9)).save(outside)
    history = [{"role": "user", "content": [inline_image(str(outside))]}]
    await db.update_conversation("conversation", content=history)

    with pytest.raises(ImageHistoryMigrationError) as error:
        await migrate(db, history)

    assert error.value.reason == "unavailable"
    assert await db_rows(db, ImageAsset) == []


@pytest.mark.asyncio
async def test_accepts_regular_file_in_temp_and_rejects_symlink(migration_env):
    db, _, temp_root = migration_env
    source = temp_root / "cached.png"
    Image.new("RGB", (12, 9), "green").save(source)
    history = [{"role": "user", "content": [inline_image(source.as_uri())]}]
    await db.update_conversation("conversation", content=history)
    result = await migrate(db, history)
    assert result.migrated_images == 1

    await db.create_conversation("owner", "platform", cid="symlink-case")
    linked = temp_root / "linked.png"
    linked.symlink_to(source)
    symlink_history = [{"role": "user", "content": [inline_image(linked.as_uri())]}]
    await db.update_conversation("symlink-case", content=symlink_history)
    with pytest.raises(ImageHistoryMigrationError) as error:
        await migrate_legacy_image_history(
            db,
            "symlink-case",
            symlink_history,
            user_id="owner",
            platform_id="platform",
        )
    assert error.value.reason == "unavailable"


@pytest.mark.asyncio
async def test_unknown_image_shaped_part_is_not_migrated(migration_env):
    db, _, _ = migration_env
    history = [
        {
            "role": "user",
            "content": [{"type": "image", "url": "data:image/png;base64,xx"}],
        }
    ]

    result = await migrate(db, history)

    assert result.migrated_images == 0
    assert result.history == history
    assert await db_rows(db, ImageAsset) == []


@pytest.mark.asyncio
async def test_cas_failure_does_not_overwrite_concurrent_history(migration_env):
    db, _, _ = migration_env
    history = [{"role": "user", "content": [inline_image(image_data_uri())]}]
    concurrent_history = [{"role": "user", "content": "newer message"}]
    await db.update_conversation("conversation", content=history)
    original_update = db.update_conversation

    async def race_update(*args, **kwargs):
        await original_update("conversation", content=concurrent_history)
        return await original_update(*args, **kwargs)

    db.update_conversation = race_update
    with pytest.raises(ImageHistoryMigrationError) as error:
        await migrate(db, history)

    assert error.value.reason == "history_changed"
    stored = await db.get_conversation_by_id("conversation")
    assert stored.content == concurrent_history
    assert await db_rows(db, ConversationImageRef) == []
    # Failed CAS can leave an unassociated file/row for explicit M3 maintenance.
    assert len(await db_rows(db, ImageAsset)) == 1


@pytest.mark.asyncio
async def test_wrong_conversation_identity_fails_before_import(migration_env):
    db, _, _ = migration_env
    history = [{"role": "user", "content": [inline_image(image_data_uri())]}]
    await db.update_conversation("conversation", content=history)

    with pytest.raises(ImageHistoryMigrationError) as error:
        await migrate_legacy_image_history(
            db,
            "conversation",
            history,
            user_id="different-owner",
            platform_id="platform",
        )

    assert error.value.reason == "history_changed"
    assert await db_rows(db, ImageAsset) == []


@pytest.mark.asyncio
async def test_data_uri_staging_cleans_partial_file_and_propagates_resource_errors(
    migration_env, monkeypatch
):
    _, _, temp_root = migration_env
    uri = image_data_uri()

    def resource_failure(_descriptor):
        raise OSError(errno.ENOMEM, "out of memory")

    monkeypatch.setattr(migration.os, "fsync", resource_failure)
    with pytest.raises(OSError) as error:
        migration._stage_data_uri(uri, temp_root)

    assert error.value.errno == errno.ENOMEM
    assert list(temp_root.glob("image-history-migration-*.img")) == []


@pytest.mark.asyncio
async def test_migration_rolls_back_if_references_expand_past_online_limit(
    migration_env, monkeypatch
):
    from astrbot.core import conversation_history_limits as limits
    from astrbot.core.db.po import ConversationV2

    db, _, _ = migration_env
    history = [{"role": "user", "content": [inline_image(image_data_uri())]}]
    await db.update_conversation("conversation", content=history)
    async with db.get_db() as session:
        original_size = await session.scalar(
            select(limits.history_size_bytes(ConversationV2.content)).where(
                ConversationV2.conversation_id == "conversation"
            )
        )
    monkeypatch.setattr(limits, "MAX_ONLINE_HISTORY_BYTES", original_size)

    with pytest.raises(limits.HistoryTooLargeError):
        await migrate(db, history)

    stored = await db.get_conversation_by_id("conversation")
    assert stored.content == history
    assert await db_rows(db, ConversationImageRef) == []
    assert await db_rows(db, ConversationImageCheckpoint) == []
