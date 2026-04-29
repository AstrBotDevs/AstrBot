"""Unit tests for astrbot.core.agent.message: Message, CheckpointData, CheckpointMessageSegment."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from astrbot.core.agent.message import (
    AssistantMessageSegment,
    CheckpointData,
    CheckpointMessageSegment,
    ContentPart,
    ImageURLPart,
    Message,
    SystemMessageSegment,
    TextPart,
    ThinkPart,
    ToolCall,
    ToolCallMessageSegment,
    UserMessageSegment,
    bind_checkpoint_messages,
    dump_messages_with_checkpoints,
    get_checkpoint_id,
    is_checkpoint_message,
    strip_checkpoint_messages,
)


class TestMessageConstruction:
    """Message base model construction and validation."""

    def test_minimal_user_message(self):
        """A user message requires role and content."""
        msg = Message(role="user", content="hello")
        assert msg.role == "user"
        assert msg.content == "hello"
        assert msg.tool_calls is None
        assert msg.tool_call_id is None

    def test_assistant_message_with_content(self):
        """An assistant message with text content."""
        msg = Message(role="assistant", content="I am an assistant")
        assert msg.role == "assistant"
        assert msg.content == "I am an assistant"

    def test_assistant_message_with_tool_calls_no_content(self):
        """Assistant messages with tool_calls may have content=None."""
        tc = ToolCall(id="call_1", function=ToolCall.FunctionBody(name="f", arguments="{}"))
        msg = Message(role="assistant", content=None, tool_calls=[tc])
        assert msg.role == "assistant"
        assert msg.content is None
        assert len(msg.tool_calls or []) == 1

    def test_tool_message(self):
        """A tool message with role='tool'."""
        msg = Message(role="tool", content="tool result", tool_call_id="call_1")
        assert msg.role == "tool"
        assert msg.tool_call_id == "call_1"

    def test_system_message(self):
        """A system message."""
        msg = Message(role="system", content="You are a helpful assistant")
        assert msg.role == "system"

    def test_missing_content_raises_for_user(self):
        """User/System/Tool messages must have content."""
        with pytest.raises(ValidationError, match="content is required"):
            Message(role="user", content=None)

    def test_missing_content_raises_for_system(self):
        """System messages must have content."""
        with pytest.raises(ValidationError, match="content is required"):
            Message(role="system", content=None)

    def test_invalid_role_raises(self):
        """An invalid role is rejected."""
        with pytest.raises(ValidationError):
            Message(role="invalid_role", content="hi")


class TestCheckpointMessage:
    """CheckpointData and role='_checkpoint' messages."""

    def test_checkpoint_data_construction(self):
        """CheckpointData can be constructed with an id."""
        cp = CheckpointData(id="cp_1")
        assert cp.id == "cp_1"

    def test_checkpoint_message_valid(self):
        """A valid checkpoint message has role _checkpoint and CheckpointData content."""
        cp = CheckpointData(id="cp_1")
        msg = Message(role="_checkpoint", content=cp)
        assert msg.role == "_checkpoint"
        assert isinstance(msg.content, CheckpointData)

    def test_checkpoint_message_string_content_raises(self):
        """Checkpoint messages must use CheckpointData, not plain strings."""
        with pytest.raises(ValidationError):
            Message(role="_checkpoint", content="not a checkpoint")

    def test_checkpoint_data_in_non_checkpoint_role_raises(self):
        """CheckpointData in a non-checkpoint role is rejected."""
        cp = CheckpointData(id="cp_1")
        with pytest.raises(ValidationError, match="CheckpointData is only allowed"):
            Message(role="user", content=cp)

    def test_is_checkpoint_message_detection(self):
        """is_checkpoint_message correctly identifies checkpoint messages."""
        cp = CheckpointData(id="cp_1")
        msg = Message(role="_checkpoint", content=cp)
        assert is_checkpoint_message(msg) is True
        assert is_checkpoint_message(Message(role="user", content="hi")) is False

    def test_is_checkpoint_message_dict(self):
        """is_checkpoint_message works with dicts."""
        assert is_checkpoint_message({"role": "_checkpoint"}) is True
        assert is_checkpoint_message({"role": "user"}) is False

    def test_get_checkpoint_id(self):
        """get_checkpoint_id returns the id from a checkpoint message."""
        cp = CheckpointData(id="cp_42")
        msg = Message(role="_checkpoint", content=cp)
        assert get_checkpoint_id(msg) == "cp_42"

    def test_get_checkpoint_id_none_for_non_checkpoint(self):
        """get_checkpoint_id returns None for non-checkpoint messages."""
        msg = Message(role="user", content="hi")
        assert get_checkpoint_id(msg) is None

    def test_strip_checkpoint_messages(self):
        """strip_checkpoint_messages removes checkpoint entries."""
        history = [
            {"role": "user", "content": "hi"},
            {"role": "_checkpoint", "content": {"id": "cp_1"}},
            {"role": "assistant", "content": "hello"},
        ]
        cleaned = strip_checkpoint_messages(history)
        assert len(cleaned) == 2
        assert all(m["role"] != "_checkpoint" for m in cleaned)

    def test_bind_and_dump_checkpoints(self):
        """dump_messages_with_checkpoints reinserts bound checkpoints after dump."""
        cp = CheckpointData(id="cp_99")
        msg = Message(role="assistant", content="hi")
        msg._checkpoint_after = cp
        dumped = dump_messages_with_checkpoints([msg])
        assert len(dumped) == 2
        assert dumped[0]["role"] == "assistant"
        assert dumped[1]["role"] == "_checkpoint"
        assert dumped[1]["content"]["id"] == "cp_99"

    def test_bind_checkpoint_messages_roundtrip(self):
        """bind_checkpoint_messages binds checkpoints to prior messages."""
        history = [
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "a"},
            {"role": "_checkpoint", "content": {"id": "cp_1"}},
        ]
        messages = bind_checkpoint_messages(history)
        assert len(messages) == 2
        assert messages[1]._checkpoint_after is not None
        assert messages[1]._checkpoint_after.id == "cp_1"


class TestMessageSegments:
    """Typed message segment subclasses."""

    def test_assistant_message_segment(self):
        """AssistantMessageSegment has role fixed to 'assistant'."""
        msg = AssistantMessageSegment(content="hello")
        assert msg.role == "assistant"

    def test_user_message_segment(self):
        """UserMessageSegment has role fixed to 'user'."""
        msg = UserMessageSegment(content="hello")
        assert msg.role == "user"

    def test_system_message_segment(self):
        """SystemMessageSegment has role fixed to 'system'."""
        msg = SystemMessageSegment(content="beep")
        assert msg.role == "system"

    def test_tool_call_message_segment(self):
        """ToolCallMessageSegment has role fixed to 'tool'."""
        msg = ToolCallMessageSegment(content="result", tool_call_id="c1")
        assert msg.role == "tool"

    def test_checkpoint_message_segment(self):
        """CheckpointMessageSegment has role fixed to '_checkpoint' and optional CheckpointData content."""
        cp = CheckpointData(id="cp_1")
        msg = CheckpointMessageSegment(content=cp)
        assert msg.role == "_checkpoint"
        assert msg.content.id == "cp_1"


class TestContentParts:
    """Content part subclasses."""

    def test_text_part(self):
        """TextPart holds text content."""
        tp = TextPart(text="Hello, world!")
        assert tp.type == "text"
        assert tp.text == "Hello, world!"

    def test_think_part(self):
        """ThinkPart holds think content."""
        tp = ThinkPart(think="I need to think about this.")
        assert tp.type == "think"
        assert tp.think == "I need to think about this."
        assert tp.encrypted is None

    def test_think_part_merge(self):
        """merge_in_place appends think content."""
        t1 = ThinkPart(think="First ")
        t2 = ThinkPart(think="Second")
        assert t1.merge_in_place(t2) is True
        assert t1.think == "First Second"

    def test_think_part_merge_non_think_returns_false(self):
        """merge_in_place returns False when other is not a ThinkPart."""
        t1 = ThinkPart(think="A")
        assert t1.merge_in_place("not a think part") is False

    def test_think_part_merge_encrypted_returns_false(self):
        """merge_in_place returns False when self is encrypted."""
        t1 = ThinkPart(think="A", encrypted="sig1")
        t2 = ThinkPart(think="B")
        assert t1.merge_in_place(t2) is False

    def test_image_url_part(self):
        """ImageURLPart holds an image URL."""
        part = ImageURLPart(image_url=ImageURLPart.ImageURL(url="http://example.com/img.jpg"))
        assert part.type == "image_url"
        assert part.image_url.url == "http://example.com/img.jpg"

    def test_image_url_with_id(self):
        """ImageURLPart can include an id."""
        part = ImageURLPart(
            image_url=ImageURLPart.ImageURL(url="http://example.com/img.jpg", id="img_1")
        )
        assert part.image_url.id == "img_1"


class TestToolCall:
    """ToolCall construction and serialization."""

    def test_tool_call_minimal(self):
        """ToolCall with id and function body."""
        tc = ToolCall(id="call_1", function=ToolCall.FunctionBody(name="f", arguments="{}"))
        assert tc.id == "call_1"
        assert tc.function.name == "f"
        assert tc.function.arguments == "{}"

    def test_tool_call_extra_content(self):
        """ToolCall with extra_content is serialized."""
        tc = ToolCall(
            id="call_2",
            function=ToolCall.FunctionBody(name="g", arguments='{"x": 1}'),
            extra_content={"meta": "data"},
        )
        dumped = tc.model_dump()
        assert dumped["extra_content"] == {"meta": "data"}

    def test_tool_call_extra_content_none_omitted(self):
        """ToolCall with extra_content=None omits the field in serialization."""
        tc = ToolCall(id="call_3", function=ToolCall.FunctionBody(name="h", arguments="{}"))
        dumped = tc.model_dump()
        assert "extra_content" not in dumped

    def test_message_serialization_omits_tool_calls_when_none(self):
        """Message.model_dump omits tool_calls when None."""
        msg = Message(role="assistant", content="hi")
        dumped = msg.model_dump()
        assert "tool_calls" not in dumped

    def test_message_serialization_omits_tool_call_id_when_none(self):
        """Message.model_dump omits tool_call_id when None."""
        msg = Message(role="user", content="hi")
        dumped = msg.model_dump()
        assert "tool_call_id" not in dumped
