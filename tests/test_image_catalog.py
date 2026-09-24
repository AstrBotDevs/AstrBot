"""Authorized catalog reads and conversation-scoped observation updates."""

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import event, text

from astrbot.core import image_asset_store as storage
from astrbot.core.db.po import (
    ConversationImageCheckpoint,
    ConversationImageRef,
    ImageAsset,
    ProviderStat,
)
from astrbot.core.db.sqlite import SQLiteDatabase


@pytest_asyncio.fixture
async def db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        storage, "get_astrbot_data_path", lambda: str(tmp_path / "data")
    )
    database = SQLiteDatabase(str(tmp_path / "catalog.db"))
    await database.initialize()
    database.inited = True
    async with database.get_db() as session, session.begin():
        session.add(
            ImageAsset(
                asset_id="asset",
                storage_key="asset.img",
                mime_type="image/png",
                byte_size=10,
                width=1,
                height=1,
                sha256="a" * 64,
            )
        )
    await database.create_conversation("owner", "platform", cid="parent")
    refs = [
        ConversationImageRef(
            conversation_id="parent",
            occurrence_id=f"image{i:02}",
            asset_id="asset",
            checkpoint_id="cp",
            image_index=i,
            source_message_id="source",
            description="100% observed" if i == 0 else "x" * 1000,
        )
        for i in range(25)
    ]
    history = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_ref",
                    "asset_id": "asset",
                    "occurrence_id": ref.occurrence_id,
                }
                for ref in refs
            ],
        },
        {"role": "_checkpoint", "content": {"id": "cp"}},
    ]
    await database.update_conversation("parent", content=history, image_refs=refs)
    yield database
    await database.engine.dispose()


AUTH = {"user_id": "owner", "platform_id": "platform"}


async def describe(db, **overrides):
    args = dict(
        **AUTH,
        expected_checkpoint_id="cp",
        expected_version=0,
        description="new observation",
        status="ready",
        provider="provider",
        model="model",
        representation="preview",
    )
    args.update(overrides)
    return await db.update_image_description("parent", "image00", **args)


@pytest.mark.asyncio
async def test_keyset_filters_and_metadata_only(db):
    statements = []

    def capture(conn, cursor, statement, parameters, context, many):
        statements.append(statement)

    event.listen(db.engine.sync_engine, "before_cursor_execute", capture)
    first, cursor = await db.list_conversation_images("parent", **AUTH)
    second, end = await db.list_conversation_images("parent", **AUTH, cursor=cursor)
    latest = await db.get_conversation_images("parent", ["image01"], **AUTH)
    event.remove(db.engine.sync_engine, "before_cursor_execute", capture)
    assert len(first) == 20 and len(second) == 5 and end is None
    assert len({row["occurrence_id"] for row in first + second}) == 25
    assert len(first[1]["description"]) == 512 and len(latest[0].description) == 1000
    assert all("conversations.content" not in statement for statement in statements)
    rows, _ = await db.list_conversation_images(
        "parent", **AUTH, query="%", source_message_id="source"
    )
    assert [row["occurrence_id"] for row in rows] == ["image00"]
    assert await db.list_conversation_images(
        "parent", **AUTH, source_message_id="missing"
    ) == ([], None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "auth",
    [
        {"user_id": "wrong", "platform_id": "platform"},
        {"user_id": "owner", "platform_id": "wrong"},
    ],
)
async def test_identity_rejected(db, auth):
    assert await db.list_conversation_images("parent", **auth) == ([], None)
    assert await db.get_conversation_images("parent", ["image00"], **auth) == []
    assert not await describe(db, **auth)
    assert not await db.update_image_annotation(
        "parent",
        "image00",
        **auth,
        expected_checkpoint_id="cp",
        expected_annotation="",
        annotation="correction",
    )


@pytest.mark.asyncio
async def test_cas_and_annotation_independent(db):
    results = await asyncio.gather(describe(db), describe(db, description="competitor"))
    assert sorted(results) == [False, True]
    assert not await describe(db, expected_version=1, status="failed", description="")
    assert await db.update_image_annotation(
        "parent",
        "image00",
        **AUTH,
        expected_checkpoint_id="cp",
        expected_annotation="",
        annotation="user correction",
    )
    assert not await db.update_image_annotation(
        "parent",
        "image00",
        **AUTH,
        expected_checkpoint_id="cp",
        expected_annotation="",
        annotation="late correction",
    )
    ref = (await db.get_conversation_images("parent", ["image00"], **AUTH))[0]
    assert ref.description_version == 1 and ref.user_annotation == "user correction"


@pytest.mark.asyncio
async def test_stale_save_and_branch_isolation(db):
    original = await db.get_conversation_by_id("parent")
    stale = await db.get_conversation_images("parent", ["image00"], **AUTH)
    assert await describe(db)
    await db.update_conversation("parent", content=original.content, image_refs=stale)
    await db.create_conversation(
        "child-owner",
        "platform",
        cid="child",
        content=original.content,
        image_branch_source=("parent", "owner", "platform", "cp"),
    )
    assert await describe(db, expected_version=1, description="parent only")
    child = await db.get_conversation_images(
        "child", ["image00"], user_id="child-owner", platform_id="platform"
    )
    parent = await db.get_conversation_images("parent", ["image00"], **AUTH)
    assert (
        child[0].description == "new observation"
        and parent[0].description == "parent only"
    )
    assert await db.get_conversation_images("child", ["image00"], **AUTH) == []
    await db.update_conversation("parent", content=[])
    assert len((await db.list_conversation_images("parent", **AUTH))[0]) == 20


@pytest.mark.asyncio
async def test_late_result_after_regeneration_and_delete(db):
    old = await db.get_conversation_by_id("parent")
    await db.update_conversation(
        "parent",
        content=[],
        expected_history=old.content,
        image_checkpoint_replacement=("cp", "new", ["image00"]),
    )
    assert not await describe(db)
    assert await describe(db, expected_checkpoint_id="new")
    await db.delete_conversation("parent")
    assert not await describe(db, expected_checkpoint_id="new", expected_version=1)
    assert await db.get_conversation_images("parent", ["image00"], **AUTH) == []


@pytest.mark.asyncio
async def test_inactive_turn_rejected_including_stream(db, tmp_path):
    async with db.get_db() as session, session.begin():
        checkpoint = await session.get(ConversationImageCheckpoint, ("parent", "cp"))
        checkpoint.active = False
    assert await db.list_conversation_images("parent", **AUTH) == ([], None)
    assert await db.get_conversation_images("parent", ["image00"], **AUTH) == []
    assert not await describe(db)
    with pytest.raises(PermissionError):
        async with storage.ImageAssetStore(
            db, max_pixels=20_000_000, max_frames=100
        ).open_image(conversation_id="parent", occurrence_id="image00", **AUTH):
            pytest.fail("Inactive image stream must not open")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs", [{"limit": 21}, {"limit": 0}, {"cursor": (0, "id")}, {"query": "x" * 257}]
)
async def test_catalog_bounds(db, kwargs):
    with pytest.raises(ValueError):
        await db.list_conversation_images("parent", **AUTH, **kwargs)


@pytest.mark.asyncio
async def test_update_and_lookup_bounds(db):
    with pytest.raises(ValueError):
        await db.get_conversation_images("parent", ["id"] * 101, **AUTH)
    for invalid in [
        {"description": "x" * 4097},
        {"provider": "x" * 257},
        {"expected_version": -1},
        {"status": "invalid"},
    ]:
        with pytest.raises(ValueError):
            await describe(db, **invalid)


@pytest.mark.asyncio
async def test_provider_details_old_schema_migration_and_roundtrip(db):
    old = await db.insert_provider_stat(
        umo="owner", provider_id="old", stats={"token_usage": {"output": 7}}
    )
    assert old.request_details == {}
    async with db.engine.begin() as connection:
        await connection.execute(
            text("ALTER TABLE provider_stats DROP COLUMN request_details")
        )
    await db.initialize()
    await db.initialize()
    details = {
        "purpose": "caption",
        "attempts": 2,
        "image_submissions": 4,
        "usage_unknown_calls": 1,
    }
    new = await db.insert_provider_stat(
        umo="owner",
        provider_id="caption",
        provider_model="vision",
        stats={"image_request": details, "token_usage": {"input_other": 12}},
    )
    async with db.get_db() as session:
        stored_old = await session.get(ProviderStat, old.id)
        stored_new = await session.get(ProviderStat, new.id)
    assert stored_old.request_details == {} and stored_old.token_output == 7
    assert stored_new.request_details == details and stored_new.token_input_other == 12
    assert stored_new.agent_type == "internal" and stored_new.provider_id == "caption"


@pytest.mark.asyncio
async def test_unsaved_registry_is_not_database_authority(db):
    ref = ConversationImageRef(
        conversation_id="parent",
        occurrence_id="unsaved",
        asset_id="asset",
        checkpoint_id="cp",
    )
    assert await db.get_conversation_images("parent", [ref.occurrence_id], **AUTH) == []
    assert not await db.update_image_description(
        "parent",
        ref.occurrence_id,
        **AUTH,
        expected_checkpoint_id="cp",
        expected_version=0,
        description="forged",
        status="ready",
        provider="p",
        model="m",
        representation="preview",
    )


@pytest.mark.asyncio
async def test_description_task_delayed_until_after_deletion(db):
    started, release = asyncio.Event(), asyncio.Event()

    async def delayed_caption():
        snapshot = (await db.get_conversation_images("parent", ["image00"], **AUTH))[0]
        started.set()
        await release.wait()
        return await describe(db, expected_version=snapshot.description_version)

    task = asyncio.create_task(delayed_caption())
    await started.wait()
    await db.delete_conversation("parent")
    release.set()
    assert not await task
