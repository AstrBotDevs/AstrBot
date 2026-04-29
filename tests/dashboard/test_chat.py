"""Unit tests for standalone functions/classes in astrbot/dashboard/routes/chat.py.

Tests cover BotMessageAccumulator, extract_reasoning_from_message_parts,
collect_plain_text_from_message_parts, _sanitize_upload_filename, and
track_conversation.  No Quart app fixture required.
"""

import pytest

from astrbot.dashboard.routes.chat import (
    BotMessageAccumulator,
    _sanitize_upload_filename,
    collect_plain_text_from_message_parts,
    extract_reasoning_from_message_parts,
    track_conversation,
)

# ---------------------------------------------------------------------------
# extract_reasoning_from_message_parts
# ---------------------------------------------------------------------------


class TestExtractReasoningFromMessageParts:
    def test_empty_list_returns_empty(self):
        assert extract_reasoning_from_message_parts([]) == ""

    def test_no_think_parts_returns_empty(self):
        parts = [{"type": "plain", "text": "hello"}]
        assert extract_reasoning_from_message_parts(parts) == ""

    def test_single_think_part(self):
        parts = [{"type": "think", "think": "deep reasoning"}]
        assert extract_reasoning_from_message_parts(parts) == "deep reasoning"

    def test_multiple_think_parts_concatenated(self):
        parts = [
            {"type": "think", "think": "first "},
            {"type": "plain", "text": "skip"},
            {"type": "think", "think": "second"},
        ]
        assert extract_reasoning_from_message_parts(parts) == "first second"

    def test_non_string_think_value_skipped(self):
        parts = [
            {"type": "think", "think": 42},
            {"type": "think", "think": "valid"},
        ]
        assert extract_reasoning_from_message_parts(parts) == "valid"


# ---------------------------------------------------------------------------
# collect_plain_text_from_message_parts
# ---------------------------------------------------------------------------


class TestCollectPlainTextFromMessageParts:
    def test_empty_list_returns_empty(self):
        assert collect_plain_text_from_message_parts([]) == ""

    def test_no_plain_parts_returns_empty(self):
        parts = [{"type": "think", "think": "hidden"}]
        assert collect_plain_text_from_message_parts(parts) == ""

    def test_single_plain_part(self):
        parts = [{"type": "plain", "text": "hello world"}]
        assert collect_plain_text_from_message_parts(parts) == "hello world"

    def test_multiple_plain_parts_concatenated(self):
        parts = [
            {"type": "plain", "text": "hello "},
            {"type": "think", "think": "hidden"},
            {"type": "plain", "text": "world"},
        ]
        assert collect_plain_text_from_message_parts(parts) == "hello world"

    def test_non_string_text_field_skipped(self):
        parts = [{"type": "plain", "text": 99}]
        assert collect_plain_text_from_message_parts(parts) == ""


# ---------------------------------------------------------------------------
# _sanitize_upload_filename
# ---------------------------------------------------------------------------


class TestSanitizeUploadFilename:
    def test_empty_returns_random_hex(self):
        result = _sanitize_upload_filename("")
        assert isinstance(result, str)
        assert len(result) == 16
        assert all(c in "0123456789abcdef" for c in result)

    def test_null_bytes_removed(self):
        assert _sanitize_upload_filename("file\x00name.txt") == "filename.txt"

    def test_path_traversal_stripped(self):
        assert _sanitize_upload_filename("../../etc/passwd") == "passwd"

    def test_windows_fakepath_stripped(self):
        assert _sanitize_upload_filename("C:\\fakepath\\doc.pdf") == "doc.pdf"

    def test_windows_fakepath_lowercase_drive(self):
        assert _sanitize_upload_filename("c:\\fakepath\\photo.png") == "photo.png"

    def test_backslash_converted(self):
        assert _sanitize_upload_filename("folder\\sub\\file.txt") == "file.txt"

    def test_normal_filename_preserved(self):
        assert _sanitize_upload_filename("report.pdf") == "report.pdf"

    def test_dot_returns_random(self):
        result = _sanitize_upload_filename(".")
        assert isinstance(result, str) and len(result) == 16

    def test_trailing_slash_stripped(self):
        assert _sanitize_upload_filename("dir/") == "dir"


# ---------------------------------------------------------------------------
# track_conversation  (async context manager)
# ---------------------------------------------------------------------------


class TestTrackConversation:
    @pytest.mark.asyncio
    async def test_adds_and_removes_key(self):
        convs: dict = {}
        async with track_conversation(convs, "test-id"):
            assert convs.get("test-id") is True
        assert "test-id" not in convs

    @pytest.mark.asyncio
    async def test_cleans_up_on_exception(self):
        convs: dict = {}
        with pytest.raises(RuntimeError):
            async with track_conversation(convs, "test-id"):
                raise RuntimeError("boom")
        assert "test-id" not in convs


# ---------------------------------------------------------------------------
# BotMessageAccumulator
# ---------------------------------------------------------------------------


class TestBotMessageAccumulatorInit:
    def test_initial_state(self):
        acc = BotMessageAccumulator()
        assert acc.parts == []
        assert acc.pending_text == ""
        assert acc.pending_tool_calls == {}
        assert acc.has_content() is False

    def test_has_content_true_with_pending_text(self):
        acc = BotMessageAccumulator()
        acc.pending_text = "x"
        assert acc.has_content() is True

    def test_has_content_true_with_parts(self):
        acc = BotMessageAccumulator()
        acc.parts.append({"type": "plain", "text": "x"})
        assert acc.has_content() is True

    def test_has_content_true_with_pending_tool_calls(self):
        acc = BotMessageAccumulator()
        acc.pending_tool_calls["c1"] = {"id": "c1"}
        assert acc.has_content() is True


class TestBotMessageAccumulatorAddPlain:
    def test_streaming_appends_to_pending(self):
        acc = BotMessageAccumulator()
        acc.add_plain("Hello ", chain_type=None, streaming=True)
        acc.add_plain("World", chain_type=None, streaming=True)
        assert acc.pending_text == "Hello World"

    def test_non_streaming_replaces_pending(self):
        acc = BotMessageAccumulator()
        acc.add_plain("Hello", chain_type=None, streaming=True)
        acc.add_plain("World", chain_type=None, streaming=False)
        assert acc.pending_text == "World"

    def test_reasoning_chain_flushes_and_stores_think(self):
        acc = BotMessageAccumulator()
        acc.add_plain("visible", chain_type=None, streaming=True)
        acc.add_plain("hidden", chain_type="reasoning", streaming=False)
        assert acc.pending_text == ""
        assert acc.reasoning_text() == "hidden"
        assert acc.plain_text() == "visible"

    def test_tool_call_stores_pending_call(self):
        acc = BotMessageAccumulator()
        acc.add_plain(
            '{"id": "c1", "name": "search"}',
            chain_type="tool_call",
            streaming=False,
        )
        assert "c1" in acc.pending_tool_calls

    def test_tool_call_result_creates_part(self):
        acc = BotMessageAccumulator()
        acc._store_tool_call('{"id": "c1", "name": "search"}')
        acc._store_tool_call_result(
            '{"id": "c1", "result": "data", "ts": 1}'
        )
        assert "c1" not in acc.pending_tool_calls
        assert len(acc.parts) == 1
        assert acc.parts[0]["tool_calls"][0]["result"] == "data"

    def test_tool_call_invalid_json_ignored(self):
        acc = BotMessageAccumulator()
        acc.add_plain("not-json", chain_type="tool_call", streaming=False)
        assert acc.pending_tool_calls == {}


class TestBotMessageAccumulatorAddAttachment:
    def test_none_ignored(self):
        acc = BotMessageAccumulator()
        acc.add_attachment(None)
        assert acc.parts == []

    def test_valid_part_appended(self):
        acc = BotMessageAccumulator()
        acc.add_attachment({"type": "image", "url": "test.jpg"})
        assert len(acc.parts) == 1
        assert acc.parts[0]["url"] == "test.jpg"

    def test_flushes_pending_text_before_append(self):
        acc = BotMessageAccumulator()
        acc.add_plain("text", chain_type=None, streaming=True)
        acc.add_attachment({"type": "image"})
        assert acc.pending_text == ""
        assert acc.parts[0]["type"] == "plain"


class TestBotMessageAccumulatorBuildMessageParts:
    def test_flushes_pending_text(self):
        acc = BotMessageAccumulator()
        acc.add_plain("hello", chain_type=None, streaming=True)
        parts = acc.build_message_parts()
        assert len(parts) == 1
        assert parts[0] == {"type": "plain", "text": "hello"}

    def test_includes_pending_tool_calls_when_requested(self):
        acc = BotMessageAccumulator()
        acc.pending_tool_calls["c1"] = {"id": "c1", "name": "search"}
        parts = acc.build_message_parts(include_pending_tool_calls=True)
        assert len(parts) == 1
        assert parts[0]["type"] == "tool_call"

    def test_skips_pending_tool_calls_by_default(self):
        acc = BotMessageAccumulator()
        acc.pending_tool_calls["c1"] = {"id": "c1"}
        parts = acc.build_message_parts(include_pending_tool_calls=False)
        assert parts == []


class TestBotMessageAccumulatorInternalFlushAndThink:
    def test_flush_creates_new_plain_part(self):
        acc = BotMessageAccumulator()
        acc.pending_text = "hello"
        acc._flush_pending_text()
        assert acc.parts == [{"type": "plain", "text": "hello"}]
        assert acc.pending_text == ""

    def test_flush_appends_to_existing_plain_part(self):
        acc = BotMessageAccumulator()
        acc.parts.append({"type": "plain", "text": "Hello"})
        acc.pending_text = " World"
        acc._flush_pending_text()
        assert acc.parts == [{"type": "plain", "text": "Hello World"}]

    def test_append_think_creates_new_part(self):
        acc = BotMessageAccumulator()
        acc._append_think_part("step 1")
        assert acc.parts == [{"type": "think", "think": "step 1"}]

    def test_append_think_appends_to_existing(self):
        acc = BotMessageAccumulator()
        acc._append_think_part("step 1")
        acc._append_think_part(" step 2")
        assert acc.parts == [{"type": "think", "think": "step 1 step 2"}]

    def test_append_think_empty_ignored(self):
        acc = BotMessageAccumulator()
        acc._append_think_part("")
        assert acc.parts == []


class TestBotMessageAccumulatorParseJsonObject:
    def test_valid_dict(self):
        assert BotMessageAccumulator._parse_json_object(
            '{"a": 1}'
        ) == {"a": 1}

    def test_valid_list_returns_none(self):
        assert BotMessageAccumulator._parse_json_object("[1,2]") is None

    def test_invalid_json_returns_none(self):
        assert BotMessageAccumulator._parse_json_object("not json") is None
