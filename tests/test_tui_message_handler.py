"""Tests for TUI message handler module."""

import pytest

from astrbot.tui.message_handler import (
    ChatResponse,
    MessageType,
    ParsedMessage,
    SSEMessageParser,
)


class TestMessageType:
    """Tests for MessageType enum."""

    def test_all_message_types_exist(self):
        """Test all expected message types are defined."""
        assert MessageType.SESSION_ID.value == "session_id"
        assert MessageType.PLAIN.value == "plain"
        assert MessageType.IMAGE.value == "image"
        assert MessageType.RECORD.value == "record"
        assert MessageType.FILE.value == "file"
        assert MessageType.TOOL_CALL.value == "tool_call"
        assert MessageType.TOOL_CALL_RESULT.value == "tool_call_result"
        assert MessageType.REASONING.value == "reasoning"
        assert MessageType.AGENT_STATS.value == "agent_stats"
        assert MessageType.AUDIO_CHUNK.value == "audio_chunk"
        assert MessageType.COMPLETE.value == "complete"
        assert MessageType.END.value == "end"
        assert MessageType.MESSAGE_SAVED.value == "message_saved"
        assert MessageType.ERROR.value == "error"


class TestSSEMessageParser:
    """Tests for SSE message parser."""

    def test_parse_plain_message(self):
        """Test parsing a plain text message."""
        parser = SSEMessageParser()
        line = 'data: {"type": "plain", "data": "Hello world"}'

        result = parser.parse_line(line)

        assert result is not None
        assert result.type == MessageType.PLAIN
        assert result.data == "Hello world"
        assert result.streaming is False

    def test_parse_streaming_message(self):
        """Test parsing a streaming message."""
        parser = SSEMessageParser()
        line = 'data: {"type": "plain", "data": "Part 1", "streaming": true}'

        result = parser.parse_line(line)

        assert result is not None
        assert result.type == MessageType.PLAIN
        assert result.streaming is True

    def test_parse_tool_call(self):
        """Test parsing a tool call message."""
        parser = SSEMessageParser()
        # Properly formatted SSE line with escaped JSON inside data field
        line = 'data: {"type": "tool_call", "data": "{\\"name\\": \\"search\\"}"}'

        result = parser.parse_line(line)

        assert result is not None
        assert result.type == MessageType.TOOL_CALL

    def test_parse_reasoning(self):
        """Test parsing a reasoning message."""
        parser = SSEMessageParser()
        line = 'data: {"type": "reasoning", "data": "Let me think..."}'

        result = parser.parse_line(line)

        assert result is not None
        assert result.type == MessageType.REASONING
        assert result.data == "Let me think..."

    def test_parse_complete(self):
        """Test parsing a complete message."""
        parser = SSEMessageParser()
        line = 'data: {"type": "complete", "data": ""}'

        result = parser.parse_line(line)

        assert result is not None
        assert result.type == MessageType.COMPLETE

    def test_parse_invalid_line_returns_none(self):
        """Test that invalid lines return None."""
        parser = SSEMessageParser()

        assert parser.parse_line("not a data line") is None
        assert parser.parse_line("data: ") is None
        assert parser.parse_line("") is None

    def test_parse_invalid_json_returns_none(self):
        """Test that invalid JSON returns None."""
        parser = SSEMessageParser()
        line = "data: {invalid json}"

        assert parser.parse_line(line) is None

    def test_parse_session_id(self):
        """Test parsing session_id message."""
        parser = SSEMessageParser()
        line = 'data: {"type": "session_id", "session_id": "abc123"}'

        result = parser.parse_line(line)

        assert result is not None
        assert result.type == MessageType.SESSION_ID
        assert result.raw.get("session_id") == "abc123"

    def test_parse_image(self):
        """Test parsing image message."""
        parser = SSEMessageParser()
        line = 'data: {"type": "image", "data": "[IMAGE]file.jpg"}'

        result = parser.parse_line(line)

        assert result is not None
        assert result.type == MessageType.IMAGE
        assert result.data == "[IMAGE]file.jpg"

    def test_parse_record(self):
        """Test parsing record message."""
        parser = SSEMessageParser()
        line = 'data: {"type": "record", "data": "[RECORD]audio.wav"}'

        result = parser.parse_line(line)

        assert result is not None
        assert result.type == MessageType.RECORD

    def test_parse_file(self):
        """Test parsing file message."""
        parser = SSEMessageParser()
        line = 'data: {"type": "file", "data": "[FILE]doc.pdf"}'

        result = parser.parse_line(line)

        assert result is not None
        assert result.type == MessageType.FILE


class TestSSEMessageParserProcess:
    """Tests for processing parsed messages."""

    def test_process_plain_text_accumulates(self):
        """Test that streaming plain text accumulates."""
        parser = SSEMessageParser()

        msg1 = ParsedMessage(
            type=MessageType.PLAIN,
            data="Hello ",
            streaming=True,
        )
        msg2 = ParsedMessage(
            type=MessageType.PLAIN,
            data="world!",
            streaming=True,
        )

        response1, _ = parser.process_message(msg1)
        response2, _ = parser.process_message(msg2)

        assert response1.text == "Hello "
        assert response2.text == "Hello world!"

    def test_process_reasoning_accumulates(self):
        """Test that reasoning text accumulates."""
        parser = SSEMessageParser()

        msg1 = ParsedMessage(type=MessageType.REASONING, data="Step 1. ")
        msg2 = ParsedMessage(type=MessageType.REASONING, data="Step 2.")

        response1, _ = parser.process_message(msg1)
        response2, _ = parser.process_message(msg2)

        assert response1.reasoning == "Step 1. "
        assert response2.reasoning == "Step 1. Step 2."

    def test_process_complete_resets(self):
        """Test that complete message resets parser state."""
        parser = SSEMessageParser()

        # Send some messages
        parser.process_message(
            ParsedMessage(type=MessageType.PLAIN, data="Hi", streaming=True)
        )
        parser.process_message(
            ParsedMessage(type=MessageType.REASONING, data="Thinking...")
        )

        # Send complete
        response, is_complete = parser.process_message(
            ParsedMessage(type=MessageType.COMPLETE, data="")
        )

        assert is_complete is True
        assert response.complete is True
        assert response.text == "Hi"

    def test_process_end_flags_complete(self):
        """Test that end message flags completion."""
        parser = SSEMessageParser()

        response, is_complete = parser.process_message(
            ParsedMessage(type=MessageType.END, data="")
        )

        assert is_complete is True

    def test_reset_clears_state(self):
        """Test that reset clears all accumulated state."""
        parser = SSEMessageParser()

        parser.process_message(
            ParsedMessage(type=MessageType.PLAIN, data="Hello", streaming=True)
        )
        parser.process_message(
            ParsedMessage(type=MessageType.REASONING, data="Thinking...")
        )
        parser._tool_calls["tc1"] = object()  # type: ignore

        parser.reset()

        assert parser._accumulated_text == ""
        assert parser._accumulated_reasoning == ""
        assert parser._tool_calls == {}
        assert parser._accumulated_parts == []


class TestChatResponse:
    """Tests for ChatResponse dataclass."""

    def test_defaults(self):
        """Test ChatResponse default values."""
        response = ChatResponse()

        assert response.text == ""
        assert response.reasoning == ""
        assert response.tool_calls == {}
        assert response.agent_stats == {}
        assert response.complete is False
        assert response.session_id is None

    def test_get_display_text(self):
        """Test get_display_text method."""
        response = ChatResponse(text="Hello world")
        assert response.get_display_text() == "Hello world"

    def test_get_reasoning_display_empty(self):
        """Test get_reasoning_display when empty."""
        response = ChatResponse()
        assert response.get_reasoning_display() == ""

    def test_get_reasoning_display_with_content(self):
        """Test get_reasoning_display with content."""
        response = ChatResponse(reasoning="Step 1\nStep 2")
        result = response.get_reasoning_display()
        assert "[Reasoning]" in result
        assert "Step 1" in result


class TestParsedMessage:
    """Tests for ParsedMessage dataclass."""

    def test_defaults(self):
        """Test ParsedMessage default values."""
        msg = ParsedMessage(type=MessageType.PLAIN, data="test")

        assert msg.type == MessageType.PLAIN
        assert msg.data == "test"
        assert msg.raw == {}
        assert msg.chain_type is None
        assert msg.streaming is False
        assert msg.message_id is None
