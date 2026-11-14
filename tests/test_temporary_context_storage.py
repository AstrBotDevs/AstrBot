"""Raw temporary content is stored once and filtered consistently on recovery."""

import pytest

from astrbot.core.agent.conversation_events import ConversationEventWriter
from astrbot.core.db.conversation import persistent_messages
from astrbot.core.db.po import ConversationEvent, ConversationV3


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["create", "append", "direct", "rebase"])
async def test_raw_bodies_are_stored_once_and_filtered_on_every_projection(
    database, path
):
    store = database.conversation_store
    raw = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "visible-text"},
                {"type": "text", "text": "hidden-part", "_no_save": True},
            ],
        },
        {"role": "assistant", "content": "hidden-message", "_no_save": True},
    ]
    expected = persistent_messages(raw)
    conv = await store.create(
        umo="owner",
        platform_id="p",
        content=raw
        if path == "create"
        else [{"role": "user", "content": "old"}]
        if path == "rebase"
        else None,
    )
    before = await store.read(conv.conversation_id)
    if path != "create":
        writer = ConversationEventWriter(store, before)
        if path == "direct":
            for index, message in enumerate(raw):
                await writer.append_message(message, event_id=f"message-{index}")
                await writer.append_message(message, event_id=f"message-{index}")
        writer.stage_history(raw)
        writer.stage_history(raw)
        await writer.save_history(raw)
        assert writer.get_messages() == expected
        # Reading/staging the same working history must not produce another copy.
        seq = writer.head_seq
        await writer.save_history(raw)
        assert writer.head_seq == seq
    stored = await store.events(conv.conversation_id)
    bodies = [
        message
        for event in stored
        if event.payload
        for message in (
            [event.payload["message"]]
            if event.type == "message.appended"
            else [entry["message"] for entry in event.payload["messages"]]
            if event.type == "context.rebased"
            else []
        )
    ]
    assert bodies.count(raw[0]) == bodies.count(raw[1]) == 1
    if path in {"append", "direct"}:
        assert bodies == raw
    assert expected[0] not in bodies
    assert all(
        "include_in_context" not in event.payload for event in stored if event.payload
    )
    recovered = await store.read(conv.conversation_id)
    assert recovered.messages == expected
    assert ConversationEventWriter(store, recovered).get_messages() == expected
    fork = await store.create(
        umo="owner",
        platform_id="p",
        source_event_id=recovered.revision.leaf_event_id,
    )
    assert (await store.read(fork.conversation_id)).messages == expected
    for keyword in ["hidden-part", "hidden-message"]:
        assert (await database.get_filtered_conversations(search_query=keyword))[1] == 0
    assert (await database.get_filtered_conversations(search_query="visible-text"))[
        1
    ] == 2


@pytest.mark.asyncio
async def test_legacy_double_records_remain_readable_and_retryable(database):
    store = database.conversation_store
    conv = await store.create(umo="owner", platform_id="p")
    raw = {
        "role": "user",
        "content": [
            {"type": "text", "text": "keep"},
            {"type": "text", "text": "temporary", "_no_save": True},
        ],
    }
    visible = persistent_messages([raw])[0]
    legacy_payload = {"message": raw, "include_in_context": False}
    async with database.get_db() as session:
        session.add_all(
            [
                ConversationEvent(
                    conversation_ref=conv.id,
                    seq=2,
                    event_id="raw-old",
                    type="message.appended",
                    payload=legacy_payload,
                ),
                ConversationEvent(
                    conversation_ref=conv.id,
                    seq=3,
                    event_id="filtered-old",
                    type="message.appended",
                    payload={"message": visible},
                ),
            ]
        )
        metadata = await session.get(ConversationV3, conv.id)
        await session.commit()
    snapshot = await store.read(conv.conversation_id)
    assert snapshot.messages == [visible]
    retry = await store.append(
        conv.conversation_id,
        [
            {
                "type": "message.appended",
                "event_id": "raw-old",
                "payload": legacy_payload,
            }
        ],
    )
    assert retry.replayed
    writer = ConversationEventWriter(store, snapshot)
    await writer.append_message({"role": "assistant", "content": "reply"})
    assert (
        writer.get_messages()
        == (await store.read(conv.conversation_id)).messages
        == [visible, {"role": "assistant", "content": "reply"}]
    )
    with pytest.raises(ValueError, match="_no_save"):
        await store.append(
            conv.conversation_id,
            [{"type": "message.appended", "payload": legacy_payload}],
        )
