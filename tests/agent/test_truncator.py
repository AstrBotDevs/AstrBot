"""Tests for ContextTruncator."""

import pytest

from astrbot.core.agent.context.truncator import ContextTruncator
from astrbot.core.agent.message import Message, ToolCall, load_messages


class TestContextTruncator:
    """Test suite for ContextTruncator."""

    def create_message(self, role: str, content: str = "test content") -> Message:
        """Helper to create a simple test message."""
        return Message(role=role, content=content)

    def create_messages(
        self, count: int, include_system: bool = False
    ) -> list[Message]:
        """Helper to create alternating user/assistant messages.

        Args:
            count: Number of messages to create
            include_system: Whether to include a system message at the start

        Returns:
            List of messages
        """
        messages = []
        if include_system:
            messages.append(self.create_message("system", "System prompt"))

        for i in range(count):
            role = "user" if i % 2 == 0 else "assistant"
            messages.append(self.create_message(role, f"Message {i}"))
        return messages

    def create_tool_turn(self, tool_calls: int, prefix: str = "task") -> list[Message]:
        """Create one complete user turn with paired tool calls and results.

        Args:
            tool_calls: Number of sequential tool calls in the turn.
            prefix: Unique prefix for message contents and tool call IDs.

        Returns:
            The user request, tool chain and final assistant reply.
        """
        messages = [self.create_message("user", f"{prefix} request")]
        for i in range(tool_calls):
            call_id = f"{prefix}-{i}"
            messages.extend(
                [
                    Message(
                        role="assistant",
                        tool_calls=[
                            ToolCall(
                                id=call_id,
                                function=ToolCall.FunctionBody(
                                    name="read", arguments="{}"
                                ),
                            )
                        ],
                    ),
                    Message(role="tool", tool_call_id=call_id, content=f"result {i}"),
                ]
            )
        messages.append(self.create_message("assistant", f"{prefix} done"))
        return messages

    @pytest.mark.parametrize("tool_calls", [22, 100])
    @pytest.mark.parametrize("with_follow_up", [False, True])
    @pytest.mark.parametrize("limit", [-1, 2, 20])
    def test_long_tool_turn_does_not_consume_extra_turns(
        self, tool_calls, with_follow_up, limit
    ):
        """Count a tool-heavy task as one turn, including its final reply."""
        messages = [self.create_message("system", "Persona")]
        messages.extend(self.create_tool_turn(tool_calls))
        if with_follow_up:
            messages.append(self.create_message("user", "Continue"))
        before = [message.model_dump() for message in messages]

        result = ContextTruncator().truncate_by_turns(
            messages, keep_most_recent_turns=limit
        )

        assert result is messages
        assert [message.model_dump() for message in messages] == before

    @pytest.mark.parametrize("limit, drop_turns, retained", [(2, 1, 2), (3, 2, 2)])
    def test_turn_limit_keeps_complete_recent_tool_turns(
        self, limit, drop_turns, retained
    ):
        """Remove complete oldest turns while retaining both tool calls and results."""
        systems = [
            self.create_message("system", "Persona"),
            self.create_message("system", "Memo"),
        ]
        turns = [
            self.create_tool_turn(count, f"task-{i}")
            for i, count in enumerate([1, 22, 3, 2])
        ]
        messages = systems + [message for turn in turns for message in turn]
        before = [message.model_dump() for message in messages]

        result = ContextTruncator().truncate_by_turns(messages, limit, drop_turns)

        assert result == systems + [
            message for turn in turns[-retained:] for message in turn
        ]
        assert [message.model_dump() for message in messages] == before

    def test_in_progress_user_counts_towards_turn_limit(self):
        """An unanswered user input starts a new turn at the exact boundary."""
        messages = self.create_messages(4) + [self.create_message("user", "Current")]

        result = ContextTruncator().truncate_by_turns(
            messages, keep_most_recent_turns=2
        )

        assert result == messages[2:]

    @pytest.mark.parametrize("drop_turns", [1, 2, 20])
    def test_drop_oldest_removes_complete_tool_turns(self, drop_turns):
        """Dropping turns never splits a tool chain or removes the latest turn."""
        systems = [
            self.create_message("system", "Persona"),
            self.create_message("system", "Memo"),
        ]
        turns = [
            self.create_tool_turn(count, f"task-{i}")
            for i, count in enumerate([22, 3, 2])
        ]
        messages = systems + [message for turn in turns for message in turn]
        before = [message.model_dump() for message in messages]

        result = ContextTruncator().truncate_by_dropping_oldest_turns(
            messages, drop_turns
        )

        assert result == systems + [
            message for turn in turns[min(drop_turns, 2) :] for message in turn
        ]
        assert [message.model_dump() for message in messages] == before

    def test_dropping_sole_tool_turn_preserves_entire_turn(self):
        """Keep the current task intact when there is no older turn to remove."""
        messages = [
            self.create_message("system", "Persona"),
            *self.create_tool_turn(22),
        ]

        result = ContextTruncator().truncate_by_dropping_oldest_turns(messages, 10)

        assert result == messages

    @pytest.mark.parametrize("limit, drop_turns", [(0, 1), (1, 10)])
    def test_nonpositive_retention_keeps_latest_complete_turn(self, limit, drop_turns):
        """Always retain the latest turn instead of reinserting an unrelated old user."""
        older = self.create_tool_turn(1, "old")
        latest = self.create_tool_turn(3, "current")

        result = ContextTruncator().truncate_by_turns(older + latest, limit, drop_turns)

        assert result == latest

    @pytest.mark.parametrize(
        "method", ["truncate_by_turns", "truncate_by_dropping_oldest_turns"]
    )
    @pytest.mark.parametrize("system_count", [0, 1, 3])
    def test_round_truncation_preserves_empty_and_system_only_context(
        self, method, system_count
    ):
        """Do not count or delete a leading system-only context as a turn."""
        messages = [
            self.create_message("system", f"System {i}") for i in range(system_count)
        ]
        truncator = ContextTruncator()
        if method == "truncate_by_turns":
            result = truncator.truncate_by_turns(messages, keep_most_recent_turns=0)
        else:
            result = truncator.truncate_by_dropping_oldest_turns(
                messages, drop_turns=10
            )

        assert result == messages

    @pytest.mark.parametrize("drop_turns", [0, 1, 2])
    def test_turn_limit_ignores_pre_user_fragment(self, drop_turns):
        """Do not count an assistant/tool prelude or retain it after truncation."""
        systems = [self.create_message("system", "Persona")]
        prelude = self.create_tool_turn(1, "prelude")[1:]
        turns = [self.create_tool_turn(1, f"task-{i}") for i in range(3)]
        messages = systems + prelude + [msg for turn in turns for msg in turn]
        truncator = ContextTruncator()

        assert truncator.truncate_by_turns(messages, 3) is messages
        result = truncator.truncate_by_turns(messages, 2, drop_turns)

        retained = max(1, 3 - drop_turns)
        assert result == systems + [msg for turn in turns[-retained:] for msg in turn]
        assert result[len(systems)].role == "user"

    @pytest.mark.parametrize("drop_turns", [1, 2, 10])
    def test_drop_oldest_does_not_count_pre_user_fragment(self, drop_turns):
        """A pre-user fragment never uses up a requested whole-turn drop."""
        systems = [self.create_message("system", "Persona")]
        prelude = self.create_tool_turn(1, "prelude")[1:]
        turns = [self.create_tool_turn(1, f"task-{i}") for i in range(3)]
        messages = systems + prelude + [msg for turn in turns for msg in turn]

        result = ContextTruncator().truncate_by_dropping_oldest_turns(
            messages, drop_turns
        )

        assert result == systems + [
            msg for turn in turns[min(drop_turns, 2) :] for msg in turn
        ]

    @pytest.mark.parametrize("method", ["limit", "drop"])
    def test_internal_user_messages_stay_with_their_originating_turn(self, method):
        """Keep and drop persisted internal user messages with the actual request."""
        current = load_messages(
            [
                {"role": "user", "content": "Inspect the output"},
                {"role": "assistant", "content": "Working"},
                {"role": "user", "content": "Tool image", "_turn_continuation": True},
                {"role": "assistant", "content": "Image reviewed"},
                {"role": "user", "content": "Step limit", "_turn_continuation": True},
            ]
        )
        older = self.create_tool_turn(1, "old")
        messages = older + current
        truncator = ContextTruncator()

        if method == "limit":
            assert truncator.truncate_by_turns(messages, 2) is messages
            assert truncator.truncate_by_turns(messages, 1) == current
        else:
            assert truncator.truncate_by_dropping_oldest_turns(messages, 1) == current

        next_turn = self.create_tool_turn(1, "next")
        assert (
            truncator.truncate_by_dropping_oldest_turns(current + next_turn, 1)
            == next_turn
        )

    # ==================== fix_messages Tests ====================

    def test_fix_messages_empty_list(self):
        """Test fix_messages with an empty list."""
        truncator = ContextTruncator()
        result = truncator.fix_messages([])
        assert result == []

    def test_fix_messages_normal_messages(self):
        """Test fix_messages with normal user/assistant messages."""
        truncator = ContextTruncator()
        messages = [
            self.create_message("user", "Hello"),
            self.create_message("assistant", "Hi"),
            self.create_message("user", "How are you?"),
        ]
        result = truncator.fix_messages(messages)
        assert len(result) == 3
        assert result == messages

    def test_fix_messages_tool_without_context(self):
        """Test fix_messages with tool message without enough context."""
        truncator = ContextTruncator()
        messages = [
            self.create_message("tool", "Tool result"),
        ]
        result = truncator.fix_messages(messages)
        # Tool message without context should be removed
        assert len(result) == 0

    # ==================== truncate_by_turns Tests ====================

    def test_truncate_by_turns_no_limit(self):
        """Test truncate_by_turns with -1 (no limit)."""
        truncator = ContextTruncator()
        messages = self.create_messages(20)
        result = truncator.truncate_by_turns(messages, keep_most_recent_turns=-1)
        assert len(result) == 20
        assert result == messages

    def test_truncate_by_turns_basic(self):
        """Test basic truncate_by_turns functionality."""
        truncator = ContextTruncator()
        # Create 10 messages = 5 turns (user/assistant pairs)
        messages = self.create_messages(10)
        result = truncator.truncate_by_turns(
            messages, keep_most_recent_turns=3, drop_turns=1
        )

        assert result == messages[-6:]

    def test_truncate_by_turns_with_system_message(self):
        """Test truncate_by_turns preserves system messages."""
        truncator = ContextTruncator()
        messages = self.create_messages(10, include_system=True)
        result = truncator.truncate_by_turns(
            messages, keep_most_recent_turns=2, drop_turns=1
        )

        # System message should always be preserved
        assert result[0].role == "system"
        assert result[0].content == "System prompt"

    def test_truncate_by_turns_zero_keep(self):
        """Test truncate_by_turns with keep_most_recent_turns=0."""
        truncator = ContextTruncator()
        messages = self.create_messages(10)
        result = truncator.truncate_by_turns(
            messages, keep_most_recent_turns=0, drop_turns=1
        )

        # Keep the latest complete turn even when the configured limit is zero.
        assert result == messages[-2:]

    def test_truncate_by_turns_below_threshold(self):
        """Test truncate_by_turns when messages are below threshold."""
        truncator = ContextTruncator()
        # Create 4 messages = 2 turns
        messages = self.create_messages(4)
        result = truncator.truncate_by_turns(
            messages, keep_most_recent_turns=5, drop_turns=1
        )

        # No truncation should happen
        assert len(result) == 4
        assert result == messages

    def test_truncate_by_turns_exact_threshold(self):
        """Test truncate_by_turns when messages exactly match threshold."""
        truncator = ContextTruncator()
        # Create 6 messages = 3 turns
        messages = self.create_messages(6)
        result = truncator.truncate_by_turns(
            messages, keep_most_recent_turns=3, drop_turns=1
        )

        # No truncation should happen
        assert len(result) == 6
        assert result == messages

    def test_truncate_by_turns_ensures_user_first(self):
        """Test that truncate_by_turns ensures user message comes first."""
        truncator = ContextTruncator()
        # Create scenario where truncation might start with assistant
        messages = self.create_messages(20)
        result = truncator.truncate_by_turns(
            messages, keep_most_recent_turns=3, drop_turns=1
        )

        # First non-system message should be user
        assert result[0].role == "user"

    def test_truncate_by_turns_multiple_drop(self):
        """Test truncate_by_turns with multiple turns dropped at once."""
        truncator = ContextTruncator()
        messages = self.create_messages(20)
        result = truncator.truncate_by_turns(
            messages, keep_most_recent_turns=5, drop_turns=3
        )

        # Preserve the existing retention target: 5 - 3 + 1 = 3 turns.
        assert result == messages[-6:]

    # ==================== truncate_by_dropping_oldest_turns Tests ====================

    def test_truncate_by_dropping_oldest_turns_zero(self):
        """Test truncate_by_dropping_oldest_turns with drop_turns=0."""
        truncator = ContextTruncator()
        messages = self.create_messages(10)
        result = truncator.truncate_by_dropping_oldest_turns(messages, drop_turns=0)
        assert result == messages

    def test_truncate_by_dropping_oldest_turns_negative(self):
        """Test truncate_by_dropping_oldest_turns with negative drop_turns."""
        truncator = ContextTruncator()
        messages = self.create_messages(10)
        result = truncator.truncate_by_dropping_oldest_turns(messages, drop_turns=-1)
        assert result == messages

    def test_truncate_by_dropping_oldest_turns_basic(self):
        """Test basic truncate_by_dropping_oldest_turns functionality."""
        truncator = ContextTruncator()
        # Create 10 messages = 5 turns
        messages = self.create_messages(10)
        result = truncator.truncate_by_dropping_oldest_turns(messages, drop_turns=2)

        # Should drop 2 oldest turns (4 messages)
        assert len(result) == 6
        # Should start with user message
        assert result[0].role == "user"

    def test_truncate_by_dropping_oldest_turns_with_system(self):
        """Test truncate_by_dropping_oldest_turns preserves system messages."""
        truncator = ContextTruncator()
        messages = self.create_messages(10, include_system=True)
        result = truncator.truncate_by_dropping_oldest_turns(messages, drop_turns=2)

        # System message should be preserved
        assert result[0].role == "system"
        assert result[0].content == "System prompt"

    def test_truncate_by_dropping_oldest_turns_drop_all(self):
        """Test truncate_by_dropping_oldest_turns dropping all turns."""
        truncator = ContextTruncator()
        # Create 4 messages = 2 turns
        messages = self.create_messages(4)
        result = truncator.truncate_by_dropping_oldest_turns(messages, drop_turns=2)

        assert result == messages[-2:]

    def test_truncate_by_dropping_oldest_turns_drop_more_than_available(self):
        """Test truncate_by_dropping_oldest_turns with drop_turns > available turns."""
        truncator = ContextTruncator()
        # Create 4 messages = 2 turns
        messages = self.create_messages(4)
        result = truncator.truncate_by_dropping_oldest_turns(messages, drop_turns=5)

        assert result == messages[-2:]

    def test_truncate_by_dropping_oldest_turns_ensures_user_first(self):
        """Test that result starts with user message after dropping."""
        truncator = ContextTruncator()
        messages = self.create_messages(20)
        result = truncator.truncate_by_dropping_oldest_turns(messages, drop_turns=3)

        # First message should be user
        if len(result) > 0:
            assert result[0].role == "user"

    # ==================== truncate_by_halving Tests ====================

    def test_truncate_by_halving_empty(self):
        """Test truncate_by_halving with empty list."""
        truncator = ContextTruncator()
        result = truncator.truncate_by_halving([])
        assert result == []

    def test_truncate_by_halving_single_message(self):
        """Test truncate_by_halving with single message."""
        truncator = ContextTruncator()
        messages = [self.create_message("user", "Hello")]
        result = truncator.truncate_by_halving(messages)
        # Should not truncate if <= 2 messages
        assert result == messages

    def test_truncate_by_halving_two_messages(self):
        """Test truncate_by_halving with two messages."""
        truncator = ContextTruncator()
        messages = self.create_messages(2)
        result = truncator.truncate_by_halving(messages)
        # Should not truncate if <= 2 messages
        assert result == messages

    def test_truncate_by_halving_basic(self):
        """Test basic truncate_by_halving functionality."""
        truncator = ContextTruncator()
        # Create 20 messages
        messages = self.create_messages(20)
        result = truncator.truncate_by_halving(messages)

        # Should delete 50% = 10 messages, keep 10
        assert len(result) == 10
        # First message should be user
        assert result[0].role == "user"

    def test_truncate_by_halving_with_system_message(self):
        """Test truncate_by_halving preserves system messages."""
        truncator = ContextTruncator()
        messages = self.create_messages(20, include_system=True)
        result = truncator.truncate_by_halving(messages)

        # System message should be preserved
        assert result[0].role == "system"
        assert result[0].content == "System prompt"

    def test_truncate_by_halving_odd_count(self):
        """Test truncate_by_halving with odd number of messages."""
        truncator = ContextTruncator()
        messages = self.create_messages(11)
        result = truncator.truncate_by_halving(messages)

        # Should delete floor(11/2) = 5 messages, keep 6
        # But after ensuring user first, may be 5
        assert len(result) >= 5
        assert result[0].role == "user"

    def test_truncate_by_halving_ensures_user_first(self):
        """Test that result starts with user message."""
        truncator = ContextTruncator()
        # Create messages starting with user
        messages = self.create_messages(30)
        result = truncator.truncate_by_halving(messages)

        # First message should be user
        assert result[0].role == "user"

    def test_truncate_by_halving_preserves_recent_messages(self):
        """Test that truncate_by_halving keeps the most recent 50%."""
        truncator = ContextTruncator()
        messages = [
            self.create_message("user", "Message 0"),
            self.create_message("assistant", "Message 1"),
            self.create_message("user", "Message 2"),
            self.create_message("assistant", "Message 3"),
        ]
        result = truncator.truncate_by_halving(messages)

        # Should keep last 2 messages
        assert len(result) == 2
        assert result[0].content == "Message 2"
        assert result[1].content == "Message 3"

    # ==================== Integration Tests ====================

    def test_truncate_with_tool_messages(self):
        """Test truncation with tool messages."""
        truncator = ContextTruncator()
        messages = [
            self.create_message("user", "Run tool"),
            self.create_message("assistant", "Running..."),
            self.create_message("tool", "Tool result"),
            self.create_message("user", "Thanks"),
            self.create_message("assistant", "Welcome"),
        ]

        result = truncator.truncate_by_dropping_oldest_turns(messages, drop_turns=1)

        # First turn (user+assistant+tool) should be dropped
        # Tool message should be cleaned up by fix_messages
        assert len(result) <= 2

    def test_chain_multiple_truncations(self):
        """Test chaining multiple truncation methods."""
        truncator = ContextTruncator()
        messages = self.create_messages(40, include_system=True)

        # First: truncate by turns
        result = truncator.truncate_by_turns(
            messages, keep_most_recent_turns=10, drop_turns=2
        )
        # Then: halve
        result = truncator.truncate_by_halving(result)

        # Should have system message + truncated content
        assert result[0].role == "system"
        assert len(result) < len(messages)

    def test_empty_after_system_message(self):
        """Test truncation when only system message exists."""
        truncator = ContextTruncator()
        messages = [self.create_message("system", "System prompt")]

        result = truncator.truncate_by_turns(
            messages, keep_most_recent_turns=5, drop_turns=1
        )

        # Should keep system message
        assert len(result) == 1
        assert result[0].role == "system"

    def test_all_system_messages(self):
        """Test truncation with only system messages."""
        truncator = ContextTruncator()
        messages = [
            self.create_message("system", "System 1"),
            self.create_message("system", "System 2"),
        ]

        result = truncator.truncate_by_turns(
            messages, keep_most_recent_turns=0, drop_turns=1
        )

        # System messages should be preserved, but since there are no non-system
        # messages and keep_most_recent_turns=0, result should be system messages only
        assert len(result) >= 0  # May keep system messages or clear all
        if len(result) > 0:
            assert all(msg.role == "system" for msg in result)

    # ==================== #6196: 长 tool chain 只有一条 user 消息 ====================

    def _build_tool_chain(self, tool_rounds: int = 20) -> list[Message]:
        """构造 system -> user -> (assistant -> tool) * N 的长链，只有一条 user。"""
        msgs = [
            self.create_message("system", "You are a helpful assistant."),
            self.create_message("user", "帮我查一下天气"),
        ]
        for i in range(tool_rounds):
            msgs.append(self.create_message("assistant", f"调用工具 {i}"))
            msgs.append(self.create_message("tool", f"工具结果 {i}"))
        return msgs

    def test_drop_oldest_preserves_sole_user(self):
        """#6196: drop 1 turn 不应丢掉唯一的 user 消息。"""
        truncator = ContextTruncator()
        msgs = self._build_tool_chain(20)  # 1 system + 1 user + 40 asst/tool = 42
        result = truncator.truncate_by_dropping_oldest_turns(msgs, drop_turns=1)
        roles = [m.role for m in result]
        assert "user" in roles, "唯一的 user 消息被丢掉了"
        assert roles[0] == "system"

    def test_halving_preserves_sole_user(self):
        """#6196: 对半砍不应丢掉唯一的 user 消息。"""
        truncator = ContextTruncator()
        msgs = self._build_tool_chain(20)
        result = truncator.truncate_by_halving(msgs)
        roles = [m.role for m in result]
        assert "user" in roles, "唯一的 user 消息被丢掉了"

    def test_truncate_by_turns_preserves_sole_user(self):
        """#6196: keep_most_recent_turns 也不应丢掉唯一的 user 消息。"""
        truncator = ContextTruncator()
        msgs = self._build_tool_chain(20)
        result = truncator.truncate_by_turns(
            msgs, keep_most_recent_turns=3, drop_turns=1
        )
        roles = [m.role for m in result]
        assert "user" in roles, "唯一的 user 消息被丢掉了"

    def test_drop_oldest_heavy_drops_still_has_user(self):
        """#6196: 大量 drop 也不会丢 user。"""
        truncator = ContextTruncator()
        msgs = self._build_tool_chain(30)
        result = truncator.truncate_by_dropping_oldest_turns(msgs, drop_turns=10)
        roles = [m.role for m in result]
        assert "user" in roles

    def test_normal_multi_user_not_affected(self):
        """正常多 user 对话不受影响。"""
        truncator = ContextTruncator()
        msgs = self.create_messages(20, include_system=True)
        result_before = truncator.truncate_by_dropping_oldest_turns(msgs, drop_turns=2)
        # 多 user 场景下截断后仍有 user
        roles = [m.role for m in result_before]
        assert "user" in roles
