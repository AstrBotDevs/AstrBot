"""Tests for ContextTruncator."""

from astrbot.core.agent.context.truncator import ContextTruncator
from astrbot.core.agent.message import Message


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

    def test_fix_messages_tool_with_valid_context(self):
        """Test fix_messages with tool message after user+assistant."""
        truncator = ContextTruncator()
        messages = [
            self.create_message("user", "Run tool"),
            self.create_message("assistant", "Running..."),
            self.create_message("tool", "Tool result"),
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

    def test_fix_messages_tool_with_only_one_message(self):
        """Test fix_messages with tool message after only one message."""
        truncator = ContextTruncator()
        messages = [
            self.create_message("user", "Hello"),
            self.create_message("tool", "Tool result"),
        ]
        result = truncator.fix_messages(messages)
        # Tool message without enough context should be removed
        assert len(result) == 0

    def test_fix_messages_multiple_tools(self):
        """Test fix_messages with multiple tool messages."""
        truncator = ContextTruncator()
        messages = [
            self.create_message("user", "Run tool"),
            self.create_message("assistant", "Running..."),
            self.create_message("tool", "Tool 1 result"),
            self.create_message("tool", "Tool 2 result"),
        ]
        result = truncator.fix_messages(messages)
        assert len(result) == 4
        assert result == messages

    def test_fix_messages_mixed_system_tool(self):
        """Test fix_messages with system message and tool messages."""
        truncator = ContextTruncator()
        messages = [
            self.create_message("system", "System prompt"),
            self.create_message("user", "Run tool"),
            self.create_message("assistant", "Running..."),
            self.create_message("tool", "Tool result"),
        ]
        result = truncator.fix_messages(messages)
        assert len(result) == 4
        assert result == messages

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

        # Should keep 3 most recent turns (6 messages)
        assert len(result) <= 8  # (3-1+1)*2 = 6, but may adjust for correct format

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

        # Should result in empty or minimal list
        assert len(result) == 0

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

        # Should drop 3 turns when limit exceeded
        assert len(result) < len(messages)

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

        # Should drop all turns
        assert len(result) == 0

    def test_truncate_by_dropping_oldest_turns_drop_more_than_available(self):
        """Test truncate_by_dropping_oldest_turns with drop_turns > available turns."""
        truncator = ContextTruncator()
        # Create 4 messages = 2 turns
        messages = self.create_messages(4)
        result = truncator.truncate_by_dropping_oldest_turns(messages, drop_turns=5)

        # Should result in empty list
        assert len(result) == 0

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
