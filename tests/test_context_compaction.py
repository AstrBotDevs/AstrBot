"""Test that persistent context compaction is actually effective —
the compressed result is saved to the conversation layer, not discarded
on a temporary copy.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.agent.message import Message
from astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal import (
    _count_conversation_turns,
    _has_valid_summary_message,
    _history_exceeds_turn_limit,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_message(role: str, content: str = "test") -> Message:
    return Message(role=role, content=content)


def _build_turns(n: int) -> list[Message]:
    """Build *n* user+assistant pairs."""
    msgs: list[Message] = []
    for i in range(n):
        msgs.append(_make_message("user", f"user_msg_{i}"))
        msgs.append(_make_message("assistant", f"assistant_msg_{i}"))
    return msgs


# ---------------------------------------------------------------------------
# _count_conversation_turns
# ---------------------------------------------------------------------------


def test_count_turns_empty():
    assert _count_conversation_turns([]) == 0


def test_count_turns_only_user():
    msgs = [_make_message("user", "hi"), _make_message("user", "hey")]
    assert _count_conversation_turns(msgs) == 2


def test_count_turns_mixed():
    msgs = [
        _make_message("system", "sys"),
        _make_message("user", "u1"),
        _make_message("assistant", "a1"),
        _make_message("user", "u2"),
        _make_message("assistant", "a2"),
        _make_message("tool", "t1"),
    ]
    assert _count_conversation_turns(msgs) == 2  # only user=u1,u2


# ---------------------------------------------------------------------------
# _history_exceeds_turn_limit
# ---------------------------------------------------------------------------


def test_exceeds_disabled():
    msgs = _build_turns(100)
    assert _history_exceeds_turn_limit(msgs, -1) is False


def test_exceeds_zero_or_negative():
    msgs = _build_turns(10)
    assert _history_exceeds_turn_limit(msgs, 0) is False
    assert _history_exceeds_turn_limit(msgs, -5) is False


def test_exceeds_under_limit():
    msgs = _build_turns(25)
    assert _history_exceeds_turn_limit(msgs, 25) is False  # 25 is not > 25


def test_exceeds_over_limit():
    msgs = _build_turns(26)
    assert _history_exceeds_turn_limit(msgs, 25) is True


# ---------------------------------------------------------------------------
# _has_valid_summary_message
# ---------------------------------------------------------------------------


def test_valid_summary_detected():
    msgs = [
        Message(
            role="user",
            content="Our previous history conversation summary: the user asked about weather.",
        ),
        Message(role="assistant", content="Acknowledged."),
    ]
    assert _has_valid_summary_message(msgs) is True


def test_empty_summary_not_detected():
    msgs = [
        Message(
            role="user",
            content="Our previous history conversation summary: ",
        ),
    ]
    assert _has_valid_summary_message(msgs) is False


def test_no_summary_prefix():
    msgs = [Message(role="user", content="regular message")]
    assert _has_valid_summary_message(msgs) is False


# ---------------------------------------------------------------------------
# end-to-end: _save_to_history truncation fallback
# ---------------------------------------------------------------------------


class TestSaveToHistoryCompaction:
    """Simulate the _save_to_history compaction path without a real LLM.

    We mock the LLM compression provider away so the fallback_truncate
    path is exercised.  This proves that messages_to_save is *replaced*
    with the truncated version before calling update_conversation.
    """

    @pytest.mark.asyncio
    async def test_truncation_replaces_messages_to_save(self):
        from astrbot.core.agent.context.truncator import ContextTruncator

        # Build 30 turns (60 messages) + 1 extra → 31 user messages
        messages = _build_turns(31)
        # The _save_to_history skips the very first system message, so we
        # don't add one here — just the history + current user.
        truncator = ContextTruncator()
        truncated = truncator.truncate_by_turns(
            messages,
            keep_most_recent_turns=25,
            drop_turns=10,
        )
        # After truncation, should have ~16 turns (high-water 25, low-water 16)
        user_count = _count_conversation_turns(truncated)
        assert user_count <= 25
        # With 25-10+1=16 turns → at most 16 user messages
        assert user_count >= 1
        # Verify the oldest messages are gone
        first_user_content = next(
            m.content for m in truncated if m.role == "user"
        )
        assert isinstance(first_user_content, str)
        # Should NOT be "user_msg_0" (that was in the first dropped turn)
        assert "user_msg_0" not in str(first_user_content)

    @pytest.mark.asyncio
    async def test_truncation_persists_to_conversation(self):
        """Verify that after truncation, the conversation is updated with
        the *truncated* messages, not the originals.
        """
        from unittest.mock import AsyncMock, MagicMock

        from astrbot.core.agent.response import AgentStats
        from astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal import (
            InternalAgentSubStage,
        )
        from astrbot.core.provider.entities import LLMResponse

        # Build a mock InternalAgentSubStage
        stage = InternalAgentSubStage()
        # Inject config values
        stage.max_context_length = 25
        stage.dequeue_context_length = 10
        stage.context_limit_reached_strategy = "truncate_by_turns"  # force truncation path
        stage.llm_compress_provider_id = ""
        stage.llm_compress_keep_recent = 6
        stage.llm_compress_instruction = ""

        # Mock conversation manager
        mock_conv = MagicMock()
        mock_conv.cid = "test-cid-123"
        stage.conv_manager = AsyncMock()

        # Build a ProviderRequest with conversation
        from astrbot.core.provider.entities import ProviderRequest

        req = ProviderRequest(conversation=mock_conv, prompt="hello")

        # Build 30 turns of history → 30 user messages, > 25
        all_messages = _build_turns(30)
        # Add the current user message and assistant response
        all_messages.append(_make_message("user", "current_user_msg"))
        all_messages.append(_make_message("assistant", "current_assistant_msg"))
        # total: 31 user messages → exceeds 25

        llm_resp = LLMResponse(
            role="assistant", completion_text="I'm here to help!"
        )

        # Mock event
        mock_event = MagicMock()

        await stage._save_to_history(
            event=mock_event,
            req=req,
            llm_response=llm_resp,
            all_messages=all_messages,
            runner_stats=AgentStats(),
        )

        # Verify update_conversation was called
        stage.conv_manager.update_conversation.assert_called_once()

        call_args = stage.conv_manager.update_conversation.call_args
        saved_history = call_args.kwargs["history"]

        # The saved history should have FEWER messages than the original
        original_msg_count = len(all_messages) - 1  # minus first system skip
        assert len(saved_history) < original_msg_count, (
            f"Expected truncated history ({len(saved_history)}) "
            f"to be smaller than original ({original_msg_count})"
        )

        # The saved history should NOT contain the oldest messages
        saved_contents = [
            m.get("content", "") if isinstance(m, dict) else str(m)
            for m in saved_history
        ]
        joined = " ".join(saved_contents)
        assert "user_msg_0" not in joined, (
            "Oldest user message should have been truncated"
        )

    @pytest.mark.asyncio
    async def test_next_round_loads_compressed_history(self):
        """Simulate a full cycle: compress → save → load → verify compressed
        version is what the next round sees.
        """
        from astrbot.core.agent.context.truncator import ContextTruncator

        # Round N: 30 turns
        original = _build_turns(30)
        original.append(_make_message("user", "round_N_user"))
        original.append(_make_message("assistant", "round_N_assistant"))

        # Compress
        truncator = ContextTruncator()
        compressed = truncator.truncate_by_turns(
            original,
            keep_most_recent_turns=25,
            drop_turns=10,
        )

        # "Save" to a mock DB
        saved = [m.model_dump() for m in compressed]

        # Round N+1: "load" from DB
        loaded = [Message.model_validate(m) for m in saved]
        loaded.append(_make_message("user", "round_N+1_user"))

        # The loaded context should start from the compressed version
        user_msgs = [m for m in loaded if m.role == "user"]
        contents = [m.content for m in user_msgs if isinstance(m.content, str)]

        # "round_N_user" should be present (it was recent enough)
        assert any("round_N_user" in c for c in contents), (
            "Recent user message should survive compression"
        )
        # "round_N+1_user" is the new message
        assert any("round_N+1_user" in c for c in contents)

        # Verify the round count stays under threshold
        turn_count = _count_conversation_turns(loaded)
        # After compression (16 turns) + 1 new = 17 turns, well under 25
        assert turn_count < 25, (
            f"Next round should stay under limit, got {turn_count}"
        )
