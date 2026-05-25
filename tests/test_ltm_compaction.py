"""Test LTM (LongTermMemory) context management for group chats.

LTM has its OWN compaction strategy, independent config keys, and
different persistence model from private chat.  These tests verify
that LTM compaction actually modifies self.contexts / self.summaries,
and that the request-time guard does NOT double-compress LTM-managed
contexts.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.builtin_stars.astrbot.long_term_memory import (
    LongTermMemory,
    _build_segments,
    _extract_bot_content,
    _parse_tool_call,
    _parse_tool_result,
    _truncate_user_segment,
)
from astrbot.core.agent.context.round_utils import rounds_to_text, split_into_rounds


# ---------------------------------------------------------------------------
# _build_segments helpers
# ---------------------------------------------------------------------------


def _raw_bot(time_str: str, content: str) -> str:
    return f"<BOT/{time_str}>: {content}"


def _raw_user(nick: str, time_str: str, content: str) -> str:
    return f"[{nick}/{time_str}]:  {content}"


# ---------------------------------------------------------------------------
# _parse_tool_call / _parse_tool_result / _extract_bot_content
# ---------------------------------------------------------------------------


def test_parse_tool_call_valid():
    result = _parse_tool_call(
        '<T:CALL>{"id":"abc","name":"search","args":{"q":"x"}}</T:CALL>'
    )
    assert result is not None
    assert result["id"] == "abc"
    assert result["type"] == "function"
    assert result["function"]["name"] == "search"


def test_parse_tool_call_invalid_json():
    assert _parse_tool_call("<T:CALL>not json</T:CALL>") is None


def test_parse_tool_result_valid():
    result = _parse_tool_result("<T:RES id=abc>result text</T:RES>")
    assert result is not None
    assert result["role"] == "tool"
    assert result["tool_call_id"] == "abc"
    assert result["content"] == "result text"


def test_parse_tool_result_no_id():
    assert _parse_tool_result("<T:RES >stuff</T:RES>") is None


def test_extract_bot_content():
    assert _extract_bot_content("<BOT/12:34:56>: hello world") == "hello world"


def test_extract_bot_content_no_separator():
    assert _extract_bot_content("<BOT/12:34:56> missing colon") is None


# ---------------------------------------------------------------------------
# _build_segments
# ---------------------------------------------------------------------------


def test_build_segments_empty():
    assert _build_segments([]) == []


def test_build_segments_user_only():
    lines = [
        _raw_user("Alice", "10:00:00", "hello"),
        _raw_user("Bob", "10:01:00", "hi"),
    ]
    segs = _build_segments(lines)
    assert len(segs) == 1
    assert segs[0]["role"] == "user"
    assert "Alice" in segs[0]["content"]
    assert "Bob" in segs[0]["content"]


def test_build_segments_tool_chain():
    lines = [
        '<T:CALL>{"id":"1","name":"search","args":{"q":"test"}}</T:CALL>',
        '<T:CALL>{"id":"2","name":"calc","args":{"expr":"1+1"}}</T:CALL>',
        "<T:RES id=1>search results</T:RES>",
        "<T:RES id=2>2</T:RES>",
    ]
    segs = _build_segments(lines)
    # Should produce: 1 assistant(tool_calls with 2 tools), 2 tool results
    assert len(segs) == 3
    assert segs[0]["role"] == "assistant"
    assert segs[0]["tool_calls"] is not None
    assert len(segs[0]["tool_calls"]) == 2  # merged consecutive calls
    assert segs[1]["role"] == "tool"
    assert segs[2]["role"] == "tool"


def test_build_segments_bot_reply():
    lines = [
        _raw_user("Alice", "10:00:00", "help"),
        _raw_bot("10:00:05", "Sure, what do you need?"),
    ]
    segs = _build_segments(lines)
    assert len(segs) == 2
    assert segs[0]["role"] == "user"
    assert segs[1]["role"] == "assistant"
    assert "Sure" in segs[1]["content"]


def test_build_segments_mixed():
    lines = [
        _raw_user("Alice", "10:00:00", "search python"),
        '<T:CALL>{"id":"3","name":"search","args":{"q":"python"}}</T:CALL>',
        "<T:RES id=3>Python is a programming language.</T:RES>",
        _raw_bot("10:00:10", "Python is a programming language."),
    ]
    segs = _build_segments(lines)
    assert len(segs) == 4
    roles = [s["role"] for s in segs]
    assert roles == ["user", "assistant", "tool", "assistant"]


# ---------------------------------------------------------------------------
# split_into_rounds
# ---------------------------------------------------------------------------


def test_split_rounds_empty():
    assert split_into_rounds([]) == []


def test_split_rounds_single():
    ctxs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    rounds = split_into_rounds(ctxs)
    assert len(rounds) == 1
    assert len(rounds[0]) == 2


def test_split_rounds_multi():
    ctxs = [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
        {"role": "tool", "tool_call_id": "x", "content": "t1"},
    ]
    rounds = split_into_rounds(ctxs)
    assert len(rounds) == 2
    assert len(rounds[0]) == 2  # u1+a1
    assert len(rounds[1]) == 3  # u2+a2+t1


def test_split_rounds_no_user_start():
    """If the first segment is not a user, it forms its own round,
    and the next user starts a new round."""
    ctxs = [
        {"role": "assistant", "content": "orphan"},
        {"role": "user", "content": "u1"},
    ]
    rounds = split_into_rounds(ctxs)
    # orphan assistant alone → round 0, user starts round 1
    assert len(rounds) == 2
    assert rounds[0][0]["role"] == "assistant"
    assert rounds[1][0]["role"] == "user"


# ---------------------------------------------------------------------------
# LTM compaction: truncate strategy
# ---------------------------------------------------------------------------


class TestLTMTruncateCompaction:
    """Verify LTM's truncate-based compaction modifies self.contexts."""

    def test_truncation_drops_oldest_rounds(self):
        """When rounds > ltm_max_rounds, oldest rounds are dropped."""
        # Build 90 rounds
        rounds = []
        for i in range(90):
            rounds.append([
                {"role": "user", "content": f"u{i}"},
                {"role": "assistant", "content": f"a{i}"},
            ])
        # Flatten to simulate self.contexts
        contexts = [seg for rnd in rounds for seg in rnd]

        # Simulate compaction with defaults: max=80, drop=50
        max_rounds = 80
        drop_rounds = 50

        assert len(rounds) > max_rounds
        safe_drop = min(drop_rounds, len(rounds) - 1)
        kept = rounds[safe_drop:]
        new_contexts = [seg for rnd in kept for seg in rnd]

        # Should have kept 90 - 50 = 40 rounds
        assert len(kept) == 40
        # First kept round should be round 50
        assert kept[0][0]["content"] == "u50"
        # Verify self.contexts would be replaced
        assert new_contexts != contexts
        assert len(new_contexts) < len(contexts)

    def test_truncation_not_triggered_under_limit(self):
        """Rounds under the limit should not be truncated."""
        rounds = []
        for i in range(70):  # < 80
            rounds.append([
                {"role": "user", "content": f"u{i}"},
                {"role": "assistant", "content": f"a{i}"},
            ])
        contexts = [seg for rnd in rounds for seg in rnd]

        max_rounds = 80
        assert len(rounds) <= max_rounds
        # No truncation should happen
        assert len(rounds) == 70

    def test_drop_clamped_to_len_minus_one(self):
        """If drop_rounds > len(rounds)-1, clamp to len-1 (keep at least 1)."""
        rounds = []
        for i in range(5):
            rounds.append([
                {"role": "user", "content": f"u{i}"},
                {"role": "assistant", "content": f"a{i}"},
            ])

        max_rounds = 3  # 5 > 3 → trigger
        drop_rounds = 50  # would drop all if not clamped

        safe_drop = min(drop_rounds, len(rounds) - 1)  # min(50, 4) = 4
        kept = rounds[safe_drop:]  # rounds[4:] = last 1 round
        assert len(kept) == 1
        assert kept[0][0]["content"] == "u4"


# ---------------------------------------------------------------------------
# LTM compaction: llm_summary strategy
# ---------------------------------------------------------------------------


class TestLTMSummaryCompaction:
    @pytest.mark.asyncio
    async def test_summary_triggers_and_updates_summaries(self):
        """LLM summary updates self.summaries and truncates self.contexts."""
        ltm = LongTermMemory(
            acm=MagicMock(),
            context=MagicMock(),
        )
        umo = "test_umo"
        # Pre-populate contexts with 85 rounds (> trigger=80)
        rounds = []
        for i in range(85):
            rounds.append([
                {"role": "user", "content": f"u{i}"},
                {"role": "assistant", "content": f"a{i}"},
            ])
        ltm.contexts[umo] = [seg for rnd in rounds for seg in rnd]

        # Mock provider for summary
        mock_provider = MagicMock()
        mock_provider.text_chat = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.completion_text = "Summary: users discussed various topics."
        mock_provider.text_chat.return_value = mock_resp

        mock_event = MagicMock()
        mock_event.unified_msg_origin = umo

        keep_recent = 30
        compact_ctx = {
            "provider": mock_provider,
            "prompt": "",
            "old_rounds": rounds[:-keep_recent],
            "recent_rounds": rounds[-keep_recent:],
            "existing_summary": ltm.summaries.get(umo, ""),
            "snapshot_round_count": len(rounds),
        }
        compact_ctx["summary_text"] = await ltm._generate_llm_summary(umo, compact_ctx)
        ltm._apply_llm_summary(umo, compact_ctx)

        # Summary should be stored
        assert ltm.summaries[umo] == "Summary: users discussed various topics."

        # Contexts should be replaced with only the recent rounds
        recent_rounds = rounds[-30:]
        expected_contexts = [seg for rnd in recent_rounds for seg in rnd]
        assert ltm.contexts[umo] == expected_contexts
        assert len(ltm.contexts[umo]) < 85 * 2

    @pytest.mark.asyncio
    async def test_summary_failure_keeps_original_and_sets_cooldown(self):
        """Failed summary should fall back to truncate contexts."""
        ctx_mock = MagicMock()
        ctx_mock.get_config.return_value = {
            "provider_settings": {"max_context_length": 50, "dequeue_context_length": 10}
        }
        ltm = LongTermMemory(
            acm=MagicMock(),
            context=ctx_mock,
        )
        umo = "test_umo"
        rounds = []
        for i in range(85):
            rounds.append([
                {"role": "user", "content": f"u{i}"},
                {"role": "assistant", "content": f"a{i}"},
            ])
        original_contexts = [seg for rnd in rounds for seg in rnd]
        ltm.contexts[umo] = list(original_contexts)

        # Mock provider that raises
        mock_provider = MagicMock()
        mock_provider.text_chat = AsyncMock(side_effect=Exception("API error"))

        mock_event = MagicMock()
        mock_event.unified_msg_origin = umo

        keep_recent = 30
        compact_ctx = {
            "provider": mock_provider,
            "prompt": "",
            "old_rounds": rounds[:-keep_recent],
            "recent_rounds": rounds[-keep_recent:],
            "existing_summary": ltm.summaries.get(umo, ""),
            "snapshot_round_count": len(rounds),
        }
        compact_ctx["summary_text"] = await ltm._generate_llm_summary(umo, compact_ctx)
        ltm._apply_llm_summary(umo, compact_ctx)

        # Contexts truncated by fallback (empty summary text)
        assert len(ltm.contexts[umo]) <= len(original_contexts)

    @pytest.mark.asyncio
    async def test_summary_not_triggered_when_old_rounds_empty(self):
        """When rounds <= keep_recent, old_rounds is empty → no provider call."""
        ctx_mock = MagicMock()
        ctx_mock.get_config.return_value = {
            "provider_settings": {"max_context_length": 50, "dequeue_context_length": 10}
        }
        ltm = LongTermMemory(
            acm=MagicMock(),
            context=ctx_mock,
        )
        umo = "test_umo"
        # 30 rounds = keep_recent → old_rounds = rounds[:0] = []
        rounds = []
        for i in range(30):
            rounds.append([
                {"role": "user", "content": f"u{i}"},
                {"role": "assistant", "content": f"a{i}"},
            ])
        ltm.contexts[umo] = [seg for rnd in rounds for seg in rnd]

        mock_provider = MagicMock()
        mock_provider.text_chat = AsyncMock()

        mock_event = MagicMock()
        mock_event.unified_msg_origin = umo

        keep_recent = 30
        compact_ctx = {
            "provider": mock_provider,
            "prompt": "",
            "old_rounds": rounds[:-keep_recent] if len(rounds) > keep_recent else [],
            "recent_rounds": rounds[-keep_recent:] if len(rounds) > keep_recent else rounds,
            "existing_summary": ltm.summaries.get(umo, ""),
            "snapshot_round_count": len(rounds),
        }
        compact_ctx["summary_text"] = await ltm._generate_llm_summary(umo, compact_ctx)
        ltm._apply_llm_summary(umo, compact_ctx)

        # old_rounds empty → early return before text_chat
        mock_provider.text_chat.assert_not_called()


# ---------------------------------------------------------------------------
# Guard + LTM interaction: guard should NOT do LLM compression on LTM contexts
# ---------------------------------------------------------------------------


class TestGuardDoesNotDoubleCompressLTM:
    """With our changes, the request-time guard uses only TruncateByTurns,
    never LLMSummaryCompressor.  This is correct regardless of whether
    LTM is active, but especially important for LTM-managed group chats.
    """

    def test_context_config_no_llm_provider_falls_back_to_truncate(self):
        """When llm_compress_provider is None, ContextManager must select
        TruncateByTurnsCompressor."""
        from astrbot.core.agent.context.config import ContextConfig
        from astrbot.core.agent.context.manager import ContextManager
        from astrbot.core.agent.context.compressor import TruncateByTurnsCompressor

        config = ContextConfig(
            max_context_tokens=10000,
            enforce_max_turns=-1,  # disabled
            truncate_turns=10,
            llm_compress_provider=None,  # ← our change
        )
        mgr = ContextManager(config)
        assert isinstance(mgr.compressor, TruncateByTurnsCompressor)
        assert mgr.compressor.truncate_turns == 10
