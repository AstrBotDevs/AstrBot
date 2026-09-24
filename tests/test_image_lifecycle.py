"""Conversation-local image grants, turn order and explicit removal contracts."""

import asyncio
import copy
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
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
async def db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        storage, "get_astrbot_data_path", lambda: str(tmp_path / "data")
    )
    monkeypatch.setattr(storage, "collect_pending_images", AsyncMock(return_value=0))
    database = SQLiteDatabase(str(tmp_path / "test.db"))
    await database.initialize()
    database.inited = True
    yield database
    await database.engine.dispose()


def turn(cp, occurrence=None, asset="asset", role="user"):
    content = (
        [{"type": "image_ref", "asset_id": asset, "occurrence_id": occurrence}]
        if occurrence
        else "text"
    )
    return [
        {"role": role, "content": content},
        {"role": "_checkpoint", "content": {"id": cp}},
    ]


async def seed(db, *, cid="parent", occurrence="image", cp="cp1", asset="asset"):
    async with db.get_db() as session, session.begin():
        if await session.get(ImageAsset, asset) is None:
            session.add(
                ImageAsset(
                    asset_id=asset,
                    storage_key=f"{asset}.img",
                    mime_type="image/png",
                    byte_size=10,
                    width=1,
                    height=1,
                    sha256="a" * 64,
                )
            )
    await db.create_conversation("owner", "test", cid=cid)
    await db.update_conversation(
        cid,
        content=turn(cp, occurrence, asset),
        image_refs=[
            ConversationImageRef(
                conversation_id=cid,
                occurrence_id=occurrence,
                asset_id=asset,
                checkpoint_id=cp,
                description="original",
            )
        ],
    )


async def rows(db, model):
    async with db.get_db() as session:
        return list((await session.execute(select(model))).scalars())


@pytest.mark.asyncio
async def test_compression_branch_inherits_catalog_before_boundary_only(db):
    await seed(db)
    history = turn("cp1", "image") + turn("cp2")
    await db.update_conversation("parent", content=history)
    async with db.get_db() as session, session.begin():
        session.add(
            ImageAsset(
                asset_id="later",
                storage_key="later.img",
                mime_type="image/png",
                byte_size=5,
                width=1,
                height=1,
                sha256="b" * 64,
            )
        )
    await db.update_conversation(
        "parent",
        content=history + turn("cp3", "later", "later"),
        image_refs=[
            ConversationImageRef(
                conversation_id="parent",
                occurrence_id="later",
                asset_id="later",
                checkpoint_id="cp3",
            )
        ],
    )
    compressed = turn("cp2") + turn("cp3", "later", "later")
    await db.update_conversation("parent", content=compressed)
    await db.create_conversation(
        "child-owner",
        "test",
        cid="child",
        content=turn("cp2"),
        image_branch_source=("parent", "owner", "test", "cp2"),
    )
    refs = await rows(db, ConversationImageRef)
    assert {(r.conversation_id, r.occurrence_id) for r in refs} == {
        ("parent", "image"),
        ("parent", "later"),
        ("child", "image"),
    }
    async with db.get_db() as session, session.begin():
        child = await session.get(ConversationImageRef, ("child", "image"))
        child.description = "child correction"
    await db.delete_conversation("parent")
    remaining = await rows(db, ConversationImageRef)
    assert len(remaining) == 1 and remaining[0].description == "child correction"
    assets = {a.asset_id: a.state for a in await rows(db, ImageAsset)}
    assert assets == {"asset": "available", "later": "pending_delete"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source",
    [
        ("parent", "intruder", "test", "cp1"),
        ("parent", "owner", "other", "cp1"),
        ("parent", "owner", "test", "missing"),
    ],
)
async def test_branch_authorization_failure_is_atomic(db, source):
    await seed(db)
    with pytest.raises((ValueError, PermissionError)):
        await db.create_conversation(
            "child",
            "test",
            cid="child",
            content=turn("cp1", "image"),
            image_branch_source=source,
        )
    assert [c.conversation_id for c in await rows(db, ConversationV2)] == ["parent"]


@pytest.mark.asyncio
async def test_branch_cannot_inherit_future_checkpoint(db):
    await seed(db)
    await db.update_conversation("parent", content=turn("cp1", "image") + turn("cp2"))
    with pytest.raises(PermissionError):
        await db.create_conversation(
            "child",
            "test",
            content=turn("cp2"),
            image_branch_source=("parent", "owner", "test", "cp1"),
        )


@pytest.mark.asyncio
async def test_plain_json_cannot_grant_or_reassign_image(db):
    await seed(db)
    await db.create_conversation("owner", "test", cid="other")
    with pytest.raises(PermissionError):
        await db.update_conversation("other", content=turn("cp1", "image"))
    with pytest.raises(PermissionError):
        await db.update_conversation("parent", content=turn("cp1", "image", "unknown"))
    assert len(await rows(db, ConversationImageCheckpoint)) == 1


@pytest.mark.asyncio
async def test_explicit_edit_retires_turn_and_preserves_compressed_catalog(db):
    await seed(db)
    await db.update_conversation(
        "parent",
        content=turn("cp2", "new"),
        image_refs=[
            ConversationImageRef(
                conversation_id="parent",
                occurrence_id="new",
                asset_id="asset",
                checkpoint_id="cp2",
            )
        ],
    )
    old = turn("cp2", "new")
    await db.update_conversation(
        "parent", content=[], expected_history=old, prune_image_refs=True
    )
    refs = await rows(db, ConversationImageRef)
    assert [r.occurrence_id for r in refs] == ["image"]
    assert {
        r.checkpoint_id: r.active for r in await rows(db, ConversationImageCheckpoint)
    } == {"cp1": True, "cp2": False}


@pytest.mark.asyncio
async def test_regeneration_rebinds_user_images_and_removes_tool_output(db):
    await seed(db)
    old = [
        {
            "role": "user",
            "content": [
                {"type": "image_ref", "asset_id": "asset", "occurrence_id": "image"}
            ],
        },
        {
            "role": "tool",
            "content": [
                {"type": "image_ref", "asset_id": "asset", "occurrence_id": "tool"}
            ],
        },
        {"role": "_checkpoint", "content": {"id": "cp1"}},
    ]
    await db.update_conversation(
        "parent",
        content=old,
        image_refs=[
            ConversationImageRef(
                conversation_id="parent",
                occurrence_id="tool",
                asset_id="asset",
                checkpoint_id="cp1",
            )
        ],
    )
    await db.update_conversation(
        "parent",
        content=[],
        expected_history=old,
        image_checkpoint_replacement=("cp1", "new", ["image"]),
    )
    refs = await rows(db, ConversationImageRef)
    assert [(r.occurrence_id, r.checkpoint_id) for r in refs] == [("image", "new")]
    await db.update_conversation("parent", content=turn("new", "image"))
    assert {
        r.checkpoint_id: (r.sequence, r.active)
        for r in await rows(db, ConversationImageCheckpoint)
    } == {"cp1": (1, False), "new": (2, True)}


@pytest.mark.asyncio
async def test_stale_edit_cannot_delete_new_data(db):
    await seed(db)
    original = turn("cp1", "image")
    await db.update_conversation("parent", content=original + turn("cp2"))
    with pytest.raises(ValueError, match="changed"):
        await db.update_conversation(
            "parent", content=[], expected_history=original, prune_image_refs=True
        )
    assert len(await rows(db, ConversationImageRef)) == 1
    assert len(await rows(db, ConversationImageCheckpoint)) == 2


@pytest.mark.asyncio
async def test_delete_owner_preserves_other_owner_and_unlinked_assets(db):
    await seed(db)
    await db.create_conversation("other", "test", cid="other")
    async with db.get_db() as session, session.begin():
        session.add(
            ImageAsset(
                asset_id="orphan",
                storage_key="orphan.img",
                mime_type="image/png",
                byte_size=10,
                width=1,
                height=1,
                sha256="c" * 64,
            )
        )
    await db.delete_conversations_by_user_id("owner")
    assert not await rows(db, ConversationImageRef)
    assert not await rows(db, ConversationImageCheckpoint)
    assert [c.conversation_id for c in await rows(db, ConversationV2)] == ["other"]
    assert {a.asset_id: a.state for a in await rows(db, ImageAsset)} == {
        "asset": "pending_delete",
        "orphan": "available",
    }


@pytest.mark.asyncio
async def test_invalid_trusted_association_rolls_back_history(db):
    await seed(db)
    original = copy.deepcopy((await rows(db, ConversationV2))[0].content)
    with pytest.raises(PermissionError):
        await db.update_conversation(
            "parent",
            content=original + turn("cp2", "bad"),
            image_refs=[
                ConversationImageRef(
                    conversation_id="other",
                    occurrence_id="bad",
                    asset_id="asset",
                    checkpoint_id="cp2",
                )
            ],
        )
    assert (await rows(db, ConversationV2))[0].content == original
    assert len(await rows(db, ConversationImageCheckpoint)) == 1


@pytest.mark.asyncio
async def test_cleanup_failure_does_not_rollback_delete(db, monkeypatch):
    await seed(db)
    monkeypatch.setattr(
        storage, "collect_pending_images", AsyncMock(side_effect=OSError("busy"))
    )
    await db.delete_conversation("parent")
    assert not await rows(db, ConversationV2)
    assert (await rows(db, ImageAsset))[0].state == "pending_delete"


@pytest.mark.asyncio
async def test_metadata_update_preserves_return_without_image_synchronization(
    db, monkeypatch
):
    await seed(db)
    monkeypatch.setattr(
        db,
        "_sync_image_history",
        AsyncMock(side_effect=AssertionError("unexpected history read")),
    )
    updated = await db.update_conversation("parent", title="new title")
    assert updated.title == "new title"
    await db.update_conversation("missing", title="ignored")
    assert (await rows(db, ConversationV2))[0].title == "new title"


@pytest.mark.asyncio
async def test_concurrent_edits_use_expected_history(db):
    await seed(db)
    old = turn("cp1", "image")
    results = await asyncio.gather(
        db.update_conversation(
            "parent", content=[], expected_history=old, prune_image_refs=True
        ),
        db.update_conversation(
            "parent", content=[], expected_history=old, prune_image_refs=True
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(result, ValueError) for result in results) == 1
    assert not await rows(db, ConversationImageRef)


@pytest.mark.asyncio
async def test_large_catalog_delete_uses_subqueries(db):
    await db.create_conversation("owner", "test", cid="large", content=turn("cp"))
    async with db.get_db() as session, session.begin():
        for index in range(1200):
            asset_id = f"asset-{index}"
            session.add(
                ImageAsset(
                    asset_id=asset_id,
                    storage_key=f"{asset_id}.img",
                    mime_type="image/png",
                    byte_size=1,
                    width=1,
                    height=1,
                    sha256="d" * 64,
                )
            )
            session.add(
                ConversationImageRef(
                    conversation_id="large",
                    occurrence_id=str(index),
                    asset_id=asset_id,
                    checkpoint_id="cp",
                )
            )
    await db.delete_conversation("large")
    assert not await rows(db, ConversationImageRef)
    assert all(asset.state == "pending_delete" for asset in await rows(db, ImageAsset))


@pytest.mark.asyncio
async def test_authorized_image_cannot_move_to_another_turn(db):
    await seed(db)
    original = turn("cp1", "image") + turn("cp2")
    await db.update_conversation("parent", content=original)
    with pytest.raises(PermissionError, match="between turns"):
        await db.update_conversation(
            "parent",
            content=turn("cp1") + turn("cp2", "image"),
            expected_history=original,
            prune_image_refs=True,
        )
    assert (await rows(db, ConversationV2))[0].content == original


@pytest.mark.asyncio
async def test_later_image_cannot_be_edited_before_branch_boundary(db):
    await seed(db, cp="cp3")
    # Use a separate conversation with no-image turns preceding the image turn.
    await db.create_conversation(
        "owner", "test", cid="ordered", content=turn("cp1") + turn("cp2")
    )
    original = turn("cp1") + turn("cp2") + turn("cp3", "future")
    await db.update_conversation(
        "ordered",
        content=original,
        image_refs=[
            ConversationImageRef(
                conversation_id="ordered",
                occurrence_id="future",
                asset_id="asset",
                checkpoint_id="cp3",
            )
        ],
    )
    with pytest.raises(PermissionError, match="between turns"):
        await db.update_conversation(
            "ordered",
            content=turn("cp1", "future") + turn("cp2") + turn("cp3"),
            expected_history=original,
            prune_image_refs=True,
        )
    async with db.get_db() as session:
        conversation = (
            await session.execute(
                select(ConversationV2).where(
                    ConversationV2.conversation_id == "ordered"
                )
            )
        ).scalar_one()
        assert conversation.content == original


@pytest.mark.asyncio
async def test_text_reorder_then_first_image_normalizes_checkpoint_order(db):
    await seed(db, cid="source")
    original = turn("a") + turn("b")
    edited = turn("b") + turn("a")
    await db.create_conversation("owner", "test", cid="text", content=original)
    await db.update_conversation(
        "text", content=edited, expected_history=original, prune_image_refs=True
    )
    await db.update_conversation(
        "text",
        content=edited + turn("c", "new"),
        image_refs=[
            ConversationImageRef(
                conversation_id="text",
                occurrence_id="new",
                asset_id="asset",
                checkpoint_id="c",
            )
        ],
    )
    ledger = sorted(
        (row.sequence, row.checkpoint_id)
        for row in await rows(db, ConversationImageCheckpoint)
        if row.conversation_id == "text"
    )
    assert ledger == [(1, "b"), (2, "a"), (3, "c")]
    await db.update_conversation("text", content=edited + turn("c", "new"))


@pytest.mark.asyncio
async def test_first_image_normalizes_preexisting_text_ledger(db):
    await seed(db, cid="source")
    original = turn("a") + turn("b")
    edited = turn("b") + turn("a")
    await db.create_conversation("owner", "test", cid="text", content=original)
    # A legacy caller may replace plain text without an explicit edit flag.
    await db.update_conversation("text", content=edited)
    await db.update_conversation(
        "text",
        content=edited + turn("c", "new"),
        image_refs=[
            ConversationImageRef(
                conversation_id="text",
                occurrence_id="new",
                asset_id="asset",
                checkpoint_id="c",
            )
        ],
    )
    assert (await db.get_conversation_by_id("text")).content == edited + turn(
        "c", "new"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["branch", "regenerate"])
async def test_legacy_reordered_text_supports_branch_and_regeneration(db, operation):
    original = turn("a") + turn("b")
    edited = turn("b") + turn("a")
    await db.create_conversation("owner", "test", cid="text", content=original)
    # Emulate a pre-fix ledger restored from an older text-only snapshot.
    async with db.get_db() as session, session.begin():
        conversation = (
            await session.execute(
                select(ConversationV2).where(ConversationV2.conversation_id == "text")
            )
        ).scalar_one()
        conversation.content = edited
    if operation == "branch":
        await db.create_conversation(
            "child",
            "test",
            cid="child",
            content=edited,
            image_branch_source=("text", "owner", "test", "a"),
        )
        assert (await db.get_conversation_by_id("child")).content == edited
    else:
        await db.update_conversation(
            "text",
            content=turn("b"),
            expected_history=edited,
            image_checkpoint_replacement=("a", "new", []),
        )
        ledger = {
            row.checkpoint_id: row
            for row in await rows(db, ConversationImageCheckpoint)
        }
        assert not ledger["a"].active
        assert ledger["new"].sequence > ledger["a"].sequence > ledger["b"].sequence
