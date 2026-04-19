import pytest

from astrbot.core.agent.message import (
    CheckpointData,
    CheckpointMessageSegment,
    Message,
    get_checkpoint_id,
    merge_existing_checkpoint_messages,
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


def test_merge_existing_checkpoint_messages_restores_boundaries():
    existing = [
        {"role": "user", "content": "old user"},
        {"role": "assistant", "content": "old bot"},
        {"role": "_checkpoint", "content": {"id": "cp-1"}},
    ]
    provider_messages = [
        {"role": "user", "content": "new user"},
        {"role": "assistant", "content": "new bot"},
        {"role": "user", "content": "next user"},
    ]

    assert merge_existing_checkpoint_messages(existing, provider_messages) == [
        {"role": "user", "content": "new user"},
        {"role": "assistant", "content": "new bot"},
        {"role": "_checkpoint", "content": {"id": "cp-1"}},
        {"role": "user", "content": "next user"},
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
