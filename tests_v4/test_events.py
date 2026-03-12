"""
Unit tests for Events module.
"""

from __future__ import annotations

import pytest

from astrbot_sdk.events import MessageEvent, PlainTextResult


class TestMessageEvent:
    """Tests for MessageEvent."""

    def test_from_payload_creates_event(self):
        """from_payload() should create a MessageEvent from dict."""
        payload = {
            "text": "hello world",
            "session_id": "session-1",
            "user_id": "user-1",
            "platform": "test",
        }
        event = MessageEvent.from_payload(payload)

        assert event.text == "hello world"
        assert event.session_id == "session-1"
        assert event.user_id == "user-1"
        assert event.platform == "test"

    def test_from_payload_handles_missing_fields(self):
        """from_payload() should handle missing optional fields."""
        payload = {"text": "test"}
        event = MessageEvent.from_payload(payload)

        assert event.text == "test"
        assert event.session_id == ""  # Falls back to empty string
        assert event.user_id is None  # Optional field

    def test_from_payload_preserves_raw_payload(self):
        """from_payload() should preserve raw payload."""
        payload = {
            "text": "test",
            "extra_field": "extra_value",
        }
        event = MessageEvent.from_payload(payload)

        assert event.raw == payload
        assert event.raw["extra_field"] == "extra_value"

    def test_from_payload_reads_target_shape(self):
        """from_payload() should derive session/platform from structured target payload."""
        event = MessageEvent.from_payload(
            {
                "text": "hello",
                "target": {
                    "conversation_id": "session-1",
                    "platform": "test-platform",
                },
            }
        )

        assert event.session_id == "session-1"
        assert event.platform == "test-platform"

    @pytest.mark.asyncio
    async def test_bind_reply_handler(self):
        """bind_reply_handler() should enable reply functionality."""
        event = MessageEvent(text="hello", session_id="s1")
        replies = []

        async def capture_reply(text: str) -> None:
            replies.append(text)

        event.bind_reply_handler(capture_reply)
        await event.reply("response")

        assert replies == ["response"]

    @pytest.mark.asyncio
    async def test_reply_without_handler_raises(self):
        """reply() without bound handler should raise."""
        event = MessageEvent(text="hello", session_id="s1")

        with pytest.raises(RuntimeError, match="未绑定 reply handler"):
            await event.reply("response")

    def test_to_payload(self):
        """to_payload() should serialize event to dict."""
        event = MessageEvent(
            text="hello",
            session_id="session-1",
            user_id="user-1",
            platform="test",
        )
        payload = event.to_payload()

        assert payload["text"] == "hello"
        assert payload["session_id"] == "session-1"
        assert payload["user_id"] == "user-1"
        assert payload["platform"] == "test"
        assert payload["target"]["conversation_id"] == "session-1"

    def test_to_payload_preserves_extra_raw_fields(self):
        """to_payload() should preserve unmodeled raw fields during round-trip."""
        event = MessageEvent.from_payload(
            {
                "text": "hello",
                "session_id": "session-1",
                "trace_id": "trace-123",
            }
        )
        event.text = "updated"

        payload = event.to_payload()

        assert payload["trace_id"] == "trace-123"
        assert payload["text"] == "updated"

    def test_plain_result_createsPlainTextResult(self):
        """plain_result() should create PlainTextResult."""
        event = MessageEvent(text="hello", session_id="s1")
        result = event.plain_result("test output")

        assert isinstance(result, PlainTextResult)
        assert result.text == "test output"


class TestPlainTextResult:
    """Tests for PlainTextResult."""

    def test_create_plain_text_result(self):
        """Should create PlainTextResult."""
        result = PlainTextResult(text="hello")
        assert result.text == "hello"

    def test_plain_text_result_is_dataclass(self):
        """PlainTextResult should be a dataclass with slots."""
        result = PlainTextResult(text="test")
        # It's a dataclass, check attribute access works
        assert result.text == "test"
