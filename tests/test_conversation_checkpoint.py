import pytest

from astrbot.core.agent.message import (
    CheckpointData,
    CheckpointMessageSegment,
    Message,
    bind_checkpoint_messages,
    dump_messages_with_checkpoints,
    get_checkpoint_id,
    strip_checkpoint_messages,
)
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
