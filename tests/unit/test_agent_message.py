"""Message validation, typed content, and current history serialization."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from astrbot.core.agent.message import (
    AssistantMessageSegment,
    AudioURLPart,
    ImageURLPart,
    Message,
    SystemMessageSegment,
    TextPart,
    ThinkPart,
    ToolCall,
    ToolCallMessageSegment,
    UserMessageSegment,
    dump_messages,
    load_messages,
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
        tc = ToolCall(
            id="call_1", function=ToolCall.FunctionBody(name="f", arguments="{}")
        )
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
            Message.model_validate({"role": "invalid_role", "content": "hi"})


class TestMessageSerialization:
    """Context and event-journal serialization preserve distinct temporary markers."""

    @pytest.mark.parametrize("role", ["system", "user", "assistant", "tool"])
    def test_supported_message_roles_round_trip(self, role):
        message = Message(role=role, content="preserved")
        history = dump_messages([message])
        assert history == [{"role": role, "content": "preserved"}]
        assert load_messages(history) == [message]

    @pytest.mark.parametrize(
        "raw",
        [
            {"role": "_checkpoint", "content": {"id": "old-checkpoint"}},
            {"role": "user", "content": None},
            {"role": "tool", "content": None},
            {"role": "system", "content": {"id": "not-content"}},
        ],
    )
    def test_invalid_history_is_rejected(self, raw):
        with pytest.raises(ValidationError):
            load_messages([raw])

    def test_temporary_part_marker_round_trips_only_in_journal(self):
        temporary = TextPart(text="temporary")
        assert temporary.mark_as_temp() is temporary
        message = Message(role="user", content=[TextPart(text="kept"), temporary])
        context = dump_messages([message])
        journal = dump_messages([message], include_temporary=True)
        assert context == [
            {"role": "user", "content": [{"type": "text", "text": "kept"}]}
        ]
        assert journal == [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "kept"},
                    {"type": "text", "text": "temporary", "_no_save": True},
                ],
            }
        ]
        restored = load_messages(journal)
        assert restored[0].content[1]._no_save
        assert dump_messages(restored) == context
        assert message.content[1] is temporary

    def test_message_marker_is_private_on_wire_and_preserved_in_journal(self):
        message = Message(role="assistant", content="interrupted")
        message._no_save = True
        assert "_no_save" not in message.model_dump()
        journal = dump_messages([message], include_temporary=True)
        assert journal == [
            {"role": "assistant", "content": "interrupted", "_no_save": True}
        ]
        assert load_messages(journal)[0]._no_save is True

    def test_tool_call_metadata_and_result_identity_round_trip(self):
        call = ToolCall(
            id="call-1",
            function=ToolCall.FunctionBody(name="probe", arguments='{"value": 3}'),
            extra_content={"signature": "token"},
        )
        messages = [
            Message(role="assistant", tool_calls=[call]),
            Message(role="tool", content="result", tool_call_id="call-1"),
        ]
        dumped = dump_messages(messages, include_temporary=True)
        restored = load_messages(dumped)
        assert dump_messages(restored, include_temporary=True) == dumped
        assert dumped[0]["tool_calls"][0]["extra_content"] == {"signature": "token"}
        assert dumped[1]["tool_call_id"] == "call-1"

    def test_restored_messages_do_not_mutate_input_history(self):
        history = [
            {
                "role": "user",
                "content": [{"type": "text", "text": "before", "_no_save": True}],
            }
        ]
        message = load_messages(history)[0]
        message.content[0].text = "after"
        assert history[0]["content"][0]["text"] == "before"
        assert history[0]["content"][0]["_no_save"] is True


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
        part = ImageURLPart(
            image_url=ImageURLPart.ImageURL(url="http://example.com/img.jpg")
        )
        assert part.type == "image_url"
        assert part.image_url.url == "http://example.com/img.jpg"

    def test_image_url_with_id(self):
        """ImageURLPart can include an id."""
        part = ImageURLPart(
            image_url=ImageURLPart.ImageURL(
                url="http://example.com/img.jpg", id="img_1"
            )
        )
        assert part.image_url.id == "img_1"


class TestToolCall:
    """ToolCall construction and serialization."""

    def test_tool_call_minimal(self):
        """ToolCall with id and function body."""
        tc = ToolCall(
            id="call_1", function=ToolCall.FunctionBody(name="f", arguments="{}")
        )
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
        tc = ToolCall(
            id="call_3", function=ToolCall.FunctionBody(name="h", arguments="{}")
        )
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


def test_audio_url_part_retains_id_and_serializes_as_content():
    part = AudioURLPart(
        audio_url=AudioURLPart.AudioURL(url="data:audio/aac;base64,YQ==", id="audio-1")
    )
    message = Message(role="user", content=[part])
    assert dump_messages(load_messages(dump_messages([message]))) == dump_messages(
        [message]
    )
    assert message.content[0].audio_url.id == "audio-1"
