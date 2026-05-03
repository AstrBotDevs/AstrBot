import pytest

from astrbot.core.agent.message import (
    CheckpointData,
    CheckpointMessageSegment,
    Message,
    TextPart,
    bind_checkpoint_messages,
    dump_messages_with_checkpoints,
    get_checkpoint_id,
    strip_checkpoint_messages,
)
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.provider.provider import Provider
from astrbot.dashboard.routes.chat import ChatRoute


def test_checkpoint_message_segment_round_trip():
    message = CheckpointMessageSegment(content=CheckpointData(id="cp-1"))

    dumped = message.model_dump()

    assert dumped == {"role": "_checkpoint", "content": {"id": "cp-1"}}
    assert get_checkpoint_id(dumped) == "cp-1"
    assert Message.model_validate(dumped).content == CheckpointData(id="cp-1")


def test_checkpoint_requires_checkpoint_data():
    with pytest.raises(ValueError, match="checkpoint message content"):
        Message(role="_checkpoint", content="cp-1")


def test_checkpoint_data_is_only_allowed_for_checkpoint_role():
    with pytest.raises(ValueError, match="CheckpointData is only allowed"):
        Message(role="user", content=CheckpointData(id="cp-1"))


def test_strip_checkpoint_messages():
    history = [
        {"role": "user", "content": "hello"},
        {"role": "_checkpoint", "content": {"id": "cp-1"}},
        {"role": "assistant", "content": "world"},
    ]

    assert strip_checkpoint_messages(history) == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]


def test_bind_and_dump_checkpoint_messages_preserves_boundaries():
    history = [
        {"role": "user", "content": "old user"},
        {"role": "assistant", "content": "old bot"},
        {"role": "_checkpoint", "content": {"id": "cp-1"}},
        {"role": "user", "content": "next user"},
    ]

    messages = bind_checkpoint_messages(history)

    assert len(messages) == 3
    assert messages[1]._checkpoint_after == CheckpointData(id="cp-1")
    assert dump_messages_with_checkpoints(messages) == [
        {"role": "user", "content": "old user"},
        {"role": "assistant", "content": "old bot"},
        {"role": "_checkpoint", "content": {"id": "cp-1"}},
        {"role": "user", "content": "next user"},
    ]


def test_dump_checkpoint_messages_drops_checkpoint_when_message_is_dropped():
    history = [
        {"role": "user", "content": "old user"},
        {"role": "assistant", "content": "old bot"},
        {"role": "_checkpoint", "content": {"id": "cp-1"}},
        {"role": "user", "content": "latest user"},
    ]

    messages = bind_checkpoint_messages(history)

    assert dump_messages_with_checkpoints(messages[2:]) == [
        {"role": "user", "content": "latest user"},
    ]


def test_dump_messages_filters_temp_content_parts():
    messages = [
        Message(
            role="user",
            content=[
                TextPart(text="persisted"),
                TextPart(text="temporary").mark_as_temp(),
            ],
        ),
        Message(role="assistant", content="ok"),
    ]

    assert dump_messages_with_checkpoints(messages) == [
        {"role": "user", "content": [{"type": "text", "text": "persisted"}]},
        {"role": "assistant", "content": "ok"},
    ]


def test_content_part_no_save_round_trip_from_dict():
    message = Message.model_validate(
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "persisted"},
                {"type": "text", "text": "temporary", "_no_save": True},
            ],
        }
    )

    assert isinstance(message.content, list)
    assert message.content[0]._no_save is False
    assert message.content[1]._no_save is True
    assert dump_messages_with_checkpoints([message]) == [
        {"role": "user", "content": [{"type": "text", "text": "persisted"}]},
    ]


@pytest.mark.asyncio
async def test_provider_request_assemble_context_preserves_temp_content_part_marker():
    request = ProviderRequest(
        prompt="hello",
        extra_user_content_parts=[TextPart(text="temporary").mark_as_temp()],
    )

    message = Message.model_validate(await request.assemble_context())

    assert isinstance(message.content, list)
    assert message.content[1].text == "temporary"
    assert message.content[1]._no_save is True
    assert dump_messages_with_checkpoints([message]) == [
        {"role": "user", "content": [{"type": "text", "text": "hello"}]},
    ]


def test_provider_ensure_message_to_dicts_skips_checkpoints():
    messages = [
        Message(role="user", content="hello"),
        CheckpointMessageSegment(content=CheckpointData(id="cp-1")),
        {"role": "assistant", "content": "world"},
        {"role": "_checkpoint", "content": {"id": "cp-2"}},
    ]

    assert Provider._ensure_message_to_dicts(object(), messages) == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]


def test_chat_route_find_turn_range():
    route = ChatRoute.__new__(ChatRoute)
    history = [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
        {"role": "_checkpoint", "content": {"id": "cp-1"}},
        {"role": "user", "content": "c"},
        {"role": "assistant", "content": "d"},
        {"role": "_checkpoint", "content": {"id": "cp-2"}},
    ]

    assert route._find_turn_range(history, "cp-2") == (3, 5)
    assert route._find_turn_range(history, "missing") is None
