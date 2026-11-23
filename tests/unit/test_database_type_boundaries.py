"""Runtime contracts at typed database, message, and vector-storage boundaries."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlmodel import select

from astrbot.core.agent.message import TextPart
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.db.po import (
    ConversationEvent,
    Persona,
    PlatformMessageHistory,
    Preference,
)
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.db.webchat_projection import project_webchat_event_links


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("plain", "plain"),
        ([{"type": "text", "text": "raw"}], [{"type": "text", "text": "raw"}]),
        ([TextPart(text="model")], [{"type": "text", "text": "model"}]),
        (
            [
                TextPart(text="visible"),
                {"type": "text", "text": "temporary", "_no_save": True},
            ],
            [{"type": "text", "text": "visible"}],
        ),
    ],
    ids=["text", "dictionary-part", "model-part", "mixed-temporary-part"],
)
async def test_manager_validates_raw_and_model_content_without_mutating_input(
    database: SQLiteDatabase, content, expected
) -> None:
    conv = await database.conversation_store.create(umo="owner", platform_id="test")
    original = deepcopy(content)
    await ConversationManager(database).append_message(
        content, cid=conv.conversation_id
    )
    snapshot = await database.conversation_store.read(conv.conversation_id)
    assert snapshot is not None
    assert snapshot.messages[-1]["content"] == expected
    assert content == original


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [123, [{"type": "text"}]])
async def test_invalid_plugin_content_does_not_append_an_event(
    database: SQLiteDatabase, content
) -> None:
    store = database.conversation_store
    conv = await store.create(umo="owner", platform_id="test")
    before = await store.events(conv.conversation_id)
    with pytest.raises(ValueError):
        await ConversationManager(database).append_message(
            content, cid=conv.conversation_id
        )
    assert [event.event_id for event in await store.events(conv.conversation_id)] == [
        event.event_id for event in before
    ]


class _SerializedDictionary(dict):
    def model_dump(self) -> dict:
        return {**self, "content": "serialized content"}


@pytest.mark.asyncio
async def test_message_pair_preserves_dictionary_serialization_hook(
    database: SQLiteDatabase,
) -> None:
    conv = await database.conversation_store.create(umo="owner", platform_id="test")
    await ConversationManager(database).add_message_pair(
        conv.conversation_id,
        _SerializedDictionary(role="user", content="raw content"),
        {"role": "assistant", "content": "reply"},
    )
    snapshot = await database.conversation_store.read(conv.conversation_id)
    assert snapshot is not None
    assert [message["content"] for message in snapshot.messages] == [
        "serialized content",
        "reply",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind", ["message.appended", "context.rebased", "turn.finished"]
)
async def test_display_projection_requires_payload_only_for_context_events(
    database: SQLiteDatabase, kind: str
) -> None:
    event = ConversationEvent(conversation_ref=1, seq=1, type=kind, payload=None)
    async with database.get_db() as session:
        if kind == "turn.finished":
            await project_webchat_event_links(session, [event])
        else:
            with pytest.raises(ValueError, match="must have a payload"):
                await project_webchat_event_links(session, [event])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "expected_deleted", "remaining_offsets"),
    [
        ("delete_platform_message_before", 1, [0, 1]),
        ("delete_platform_message_after", 1, [-1, 0]),
        ("delete_all_platform_message_history", 3, []),
    ],
)
async def test_history_delete_counts_keep_time_and_identity_boundaries(
    database: SQLiteDatabase,
    method: str,
    expected_deleted: int,
    remaining_offsets: list[int],
) -> None:
    boundary = datetime(2026, 1, 1, tzinfo=UTC)
    identities = [("p", "u", offset) for offset in (-1, 0, 1)] + [
        ("other-platform", "u", -1),
        ("p", "other-user", 1),
    ]
    async with database.get_db() as session, session.begin():
        session.add_all(
            PlatformMessageHistory(
                platform_id=platform,
                user_id=user,
                content={"offset": offset},
                created_at=boundary + timedelta(days=offset),
            )
            for platform, user, offset in identities
        )
    delete = getattr(database, method)
    args = (
        ("p", "u")
        if method == "delete_all_platform_message_history"
        else ("p", "u", boundary)
    )
    assert await delete(*args) == expected_deleted
    assert await delete(*args) == 0
    async with database.get_db() as session:
        records = (
            (await session.execute(select(PlatformMessageHistory))).scalars().all()
        )
    assert sorted(
        (row.platform_id, row.user_id, row.content["offset"]) for row in records
    ) == sorted([("p", "u", offset) for offset in remaining_offsets] + identities[-2:])


@pytest.mark.asyncio
async def test_session_projection_preserves_nullable_project_and_owner_filter(
    database: SQLiteDatabase,
) -> None:
    plain = await database.create_platform_session("owner", session_id="plain")
    linked = await database.create_platform_session("owner", session_id="linked")
    await database.create_platform_session("other-owner", session_id="foreign")
    project = await database.create_chatui_project("owner", "work", emoji=None)
    await database.add_session_to_project(linked.session_id, project.project_id)
    rows, total = await database.get_platform_sessions_by_creator_paginated("owner")
    assert total == 2
    by_session = {row["session"].session_id: row for row in rows}
    assert set(by_session) == {plain.session_id, linked.session_id}
    assert by_session[plain.session_id]["project_id"] is None
    assert by_session[plain.session_id]["project_title"] is None
    assert by_session[plain.session_id]["project_emoji"] is None
    assert by_session[linked.session_id]["project_title"] == "work"
    assert by_session[linked.session_id]["project_emoji"] == project.emoji
    filtered, total = await database.get_platform_sessions_by_creator_paginated(
        "owner", exclude_project_sessions=True
    )
    assert total == 1
    assert [row["session"].session_id for row in filtered] == [plain.session_id]


@pytest.mark.asyncio
async def test_selected_conversation_projection_keeps_five_columns_and_matching_count(
    database: SQLiteDatabase,
) -> None:
    first = await database.conversation_store.create(
        umo="chat:a", platform_id="p", title="first", persona_id="helper"
    )
    second = await database.conversation_store.create(
        umo="chat:b", platform_id="p", title="second"
    )
    async with database.get_db() as session, session.begin():
        session.add(Persona(persona_id="helper", system_prompt="instructions"))
        session.add_all(
            Preference(scope="umo", scope_id=umo, key="sel_conv_id", value={"val": cid})
            for umo, cid in (
                ("chat:a", first.conversation_id),
                ("chat:b", second.conversation_id),
                ("other:c", "missing"),
            )
        )
    rows, total = await database.get_session_conversations(
        platform="chat", page=1, page_size=1
    )
    assert total == 2
    assert rows == [
        {
            "session_id": "chat:a",
            "conversation_id": first.conversation_id,
            "persona_id": "helper",
            "title": "first",
            "persona_name": "helper",
        }
    ]
    page, total = await database.get_session_conversations(
        platform="chat", page=2, page_size=1
    )
    assert total == 2
    assert [row["session_id"] for row in page] == ["chat:b"]
    filtered, total = await database.get_session_conversations(
        platform="chat", search_query="second"
    )
    assert total == 1
    assert filtered == page
    dangling, total = await database.get_session_conversations(platform="other")
    assert total == 1
    assert dangling == [
        {
            "session_id": "other:c",
            "conversation_id": "missing",
            "persona_id": None,
            "title": None,
            "persona_name": None,
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("index_kind", ["id-map", "ivf-hash-map"])
@pytest.mark.parametrize("ids", [[], [999], [11, 11], [11, 33]])
async def test_faiss_delete_matches_array_wrapper_and_persists(
    tmp_path: Path, index_kind: str, ids: list[int]
) -> None:
    faiss = pytest.importorskip("faiss")
    import numpy as np

    from astrbot.core.db.vec_db.faiss_impl.embedding_storage import EmbeddingStorage

    path = tmp_path / "index.faiss"
    vectors = np.array([[0.1, 0], [0, 0.2], [0.3, 0.4]], dtype=np.float32)
    if index_kind == "ivf-hash-map":
        index = faiss.IndexIVFFlat(faiss.IndexFlatL2(2), 2, 1)
        index.train(np.tile(vectors, (32, 1)))
        index.set_direct_map_type(faiss.DirectMap.Hashtable)
        faiss.write_index(index, str(path))
    storage = EmbeddingStorage(2, str(path))
    await storage.insert_batch(vectors, [11, 22, 33])
    reference = faiss.clone_index(storage.index)
    reference.remove_ids(np.array(ids, dtype=np.int64))
    await storage.delete(ids)
    restored = EmbeddingStorage(2, str(path))
    assert restored.index.ntotal == storage.index.ntotal == reference.ntotal
    expected_distances, expected_ids = reference.search(vectors[:1], 3)
    actual_distances, actual_ids = restored.index.search(vectors[:1], 3)
    np.testing.assert_array_equal(actual_ids, expected_ids)
    np.testing.assert_array_equal(actual_distances, expected_distances)
    await storage.delete(ids)
    assert storage.index.ntotal == reference.ntotal
