"""Comprehensive test suite for ContextSanitizer (Issue #10195)."""

import sys
from pathlib import Path

import pytest

# Add parent directory to path to avoid circular import issues
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from astrbot.core.agent.context.config import ContextConfig
from astrbot.core.agent.context.manager import ContextManager
from astrbot.core.agent.context.sanitizer import ContextSanitizer
from astrbot.core.agent.message import (
    AssistantMessageSegment,
    ImageURLPart,
    Message,
    TextPart,
    ThinkPart,
    ToolCall,
    ToolCallMessageSegment,
)


class TestContextSanitizer:
    """Tests for ContextSanitizer."""

    def test_init_defaults(self):
        sanitizer = ContextSanitizer()
        assert sanitizer.sanitize_historical_thoughts is True
        assert sanitizer.sanitize_historical_tools is False
        assert sanitizer.max_historical_tool_result_chars == 500

    def test_sanitize_disabled(self):
        sanitizer = ContextSanitizer(
            sanitize_historical_thoughts=False, sanitize_historical_tools=False
        )
        messages = [
            Message(role="user", content="Hello"),
            Message(
                role="assistant",
                content=[
                    ThinkPart(think="Historical thought"),
                    TextPart(text="Hi!"),
                ],
            ),
            Message(role="user", content="Follow up"),
        ]
        result = sanitizer.sanitize(messages)
        assert len(result) == 3
        # Should not be sanitized
        assert len(result[1].content) == 2

    def test_empty_or_single_turn_messages(self):
        sanitizer = ContextSanitizer()
        assert sanitizer.sanitize([]) == []

        # Only one user turn (no historical turn)
        single_turn = [
            Message(role="system", content="You are a helpful assistant."),
            Message(role="user", content="Hello"),
        ]
        assert sanitizer.sanitize(single_turn) == single_turn

    def test_sanitize_historical_think_part(self):
        """Historical turn's ThinkPart must be stripped, but current turn's ThinkPart must be preserved."""
        sanitizer = ContextSanitizer(sanitize_historical_thoughts=True)
        messages = [
            # Turn 1 (Historical)
            Message(role="user", content="What is 1+1?"),
            Message(
                role="assistant",
                content=[
                    ThinkPart(think="Let me carefully think about 1+1."),
                    TextPart(text="1+1=2"),
                ],
            ),
            # Turn 2 (Current turn)
            Message(role="user", content="What about 2+2?"),
            Message(
                role="assistant",
                content=[
                    ThinkPart(think="Now thinking about 2+2."),
                    TextPart(text="2+2=4"),
                ],
            ),
        ]

        result = sanitizer.sanitize(messages)
        assert len(result) == 4

        # Turn 1 assistant content should have ThinkPart removed
        turn1_assistant = result[1]
        assert len(turn1_assistant.content) == 1
        assert isinstance(turn1_assistant.content[0], TextPart)
        assert turn1_assistant.content[0].text == "1+1=2"

        # Turn 2 assistant content (current turn) should RETAIN ThinkPart
        turn2_assistant = result[3]
        assert len(turn2_assistant.content) == 2
        assert isinstance(turn2_assistant.content[0], ThinkPart)
        assert turn2_assistant.content[0].think == "Now thinking about 2+2."
        assert turn2_assistant.content[1].text == "2+2=4"

    def test_sanitize_historical_think_tags_in_plain_text(self):
        """Historical <think> tags in plain string content must be stripped."""
        sanitizer = ContextSanitizer(sanitize_historical_thoughts=True)
        messages = [
            # Turn 1 (Historical)
            Message(role="user", content="Plan a trip."),
            Message(
                role="assistant",
                content="<think>\nEvaluating flights, hotels, and budget.\n</think>\nHere is the itinerary for your trip.",
            ),
            # Turn 2 (Current turn)
            Message(role="user", content="Can you adjust the budget?"),
            Message(
                role="assistant",
                content="<think>\nChecking cheaper hotels...\n</think>\nHere is the revised budget.",
            ),
        ]

        result = sanitizer.sanitize(messages)
        assert len(result) == 4

        # Turn 1 should have <think> tags stripped
        assert result[1].content == "Here is the itinerary for your trip."

        # Turn 2 (current turn) should preserve <think> tags
        assert "<think>" in result[3].content

    def test_sanitize_historical_think_tags_in_text_part(self):
        """Historical <think> tags inside TextPart must be stripped."""
        sanitizer = ContextSanitizer(sanitize_historical_thoughts=True)
        messages = [
            Message(role="user", content="Explain quantum computing."),
            Message(
                role="assistant",
                content=[
                    TextPart(
                        text="<think>Break this down simply.</think>Quantum computing uses qubits."
                    )
                ],
            ),
            Message(role="user", content="What is superposition?"),
        ]

        result = sanitizer.sanitize(messages)
        assert result[1].content[0].text == "Quantum computing uses qubits."

    def test_assistant_with_only_think_part_and_tool_calls(self):
        """When an assistant message only has ThinkPart and tool_calls, content becomes None."""
        sanitizer = ContextSanitizer(sanitize_historical_thoughts=True)
        tool_call = ToolCall(
            id="call_1",
            function=ToolCall.FunctionBody(
                name="get_weather", arguments='{"city": "Paris"}'
            ),
        )
        messages = [
            Message(role="user", content="Weather in Paris?"),
            AssistantMessageSegment(
                role="assistant",
                content=[ThinkPart(think="I should call get_weather")],
                tool_calls=[tool_call],
            ),
            ToolCallMessageSegment(
                role="tool", tool_call_id="call_1", content="Sunny, 20C"
            ),
            AssistantMessageSegment(
                role="assistant", content="The weather in Paris is sunny."
            ),
            # Next turn
            Message(role="user", content="What about tomorrow?"),
        ]

        result = sanitizer.sanitize(messages)
        # Assistant tool_call message in turn 1 should have content=None and tool_calls preserved
        assert result[1].content is None
        assert result[1].tool_calls == [tool_call]
        assert result[2].role == "tool"
        assert result[2].content == "Sunny, 20C"

    def test_sanitize_historical_bulky_tool_output(self):
        """Historical bulky tool output should be truncated when enabled."""
        large_tool_output = "X" * 1000
        sanitizer = ContextSanitizer(
            sanitize_historical_thoughts=False,
            sanitize_historical_tools=True,
            max_historical_tool_result_chars=100,
        )

        messages = [
            # Turn 1
            Message(role="user", content="Fetch data"),
            AssistantMessageSegment(
                role="assistant",
                tool_calls=[
                    ToolCall(
                        id="call_fetch",
                        function=ToolCall.FunctionBody(name="fetch", arguments="{}"),
                    )
                ],
            ),
            ToolCallMessageSegment(
                role="tool", tool_call_id="call_fetch", content=large_tool_output
            ),
            AssistantMessageSegment(
                role="assistant", content="Fetched data successfully."
            ),
            # Turn 2 (active turn)
            Message(role="user", content="Fetch next page"),
            AssistantMessageSegment(
                role="assistant",
                tool_calls=[
                    ToolCall(
                        id="call_fetch_2",
                        function=ToolCall.FunctionBody(name="fetch", arguments="{}"),
                    )
                ],
            ),
            ToolCallMessageSegment(
                role="tool", tool_call_id="call_fetch_2", content=large_tool_output
            ),
        ]

        result = sanitizer.sanitize(messages)
        # Historical tool result (turn 1) must be truncated
        assert len(result[2].content) < 200
        assert (
            "... [historical tool output truncated to save context]"
            in result[2].content
        )
        assert result[2].tool_call_id == "call_fetch"

        # Active turn tool result (turn 2) must NOT be truncated
        assert result[6].content == large_tool_output
        assert result[6].tool_call_id == "call_fetch_2"

    def test_non_destructive_immutability(self):
        """Sanitizer must not modify original message instances in-place."""
        sanitizer = ContextSanitizer(sanitize_historical_thoughts=True)
        original_think_part = ThinkPart(think="Original thought")
        original_assistant = Message(
            role="assistant",
            content=[original_think_part, TextPart(text="Final answer")],
        )
        messages = [
            Message(role="user", content="Q1"),
            original_assistant,
            Message(role="user", content="Q2"),
        ]

        result = sanitizer.sanitize(messages)

        # Original assistant content list must still have ThinkPart
        assert len(original_assistant.content) == 2
        assert original_assistant.content[0] is original_think_part

        # Result assistant content must be sanitized
        assert len(result[1].content) == 1
        assert isinstance(result[1].content[0], TextPart)

    @pytest.mark.asyncio
    async def test_integration_with_context_manager(self):
        """ContextManager process() should apply sanitizer and reflect token reduction."""
        config = ContextConfig(
            sanitize_historical_thoughts=True,
            sanitize_historical_tools=True,
            max_historical_tool_result_chars=50,
            persist_sanitized_history=True,
        )
        manager = ContextManager(config)

        huge_thinking = "Thinking deep " * 500  # large think block
        messages = [
            Message(role="user", content="Step 1"),
            Message(
                role="assistant",
                content=[
                    ThinkPart(think=huge_thinking),
                    TextPart(text="Done step 1"),
                ],
            ),
            Message(role="user", content="Step 2"),
        ]

        processed = await manager.process(messages)
        assert len(processed) == 3
        # In processed result, turn 1 assistant has ThinkPart removed
        assert len(processed[1].content) == 1
        assert processed[1].content[0].text == "Done step 1"

    @pytest.mark.asyncio
    async def test_persist_sanitized_history_flag(self):
        """When persist_sanitized_history=False, ContextManager.process() should preserve working messages."""
        config = ContextConfig(
            sanitize_historical_thoughts=True,
            persist_sanitized_history=False,
        )
        manager = ContextManager(config)

        messages = [
            Message(role="user", content="Q1"),
            Message(
                role="assistant",
                content=[
                    ThinkPart(think="Historical thought to keep in persistent storage"),
                    TextPart(text="A1"),
                ],
            ),
            Message(role="user", content="Q2"),
        ]

        processed = await manager.process(messages)
        # Should NOT strip thought from working messages
        assert len(processed[1].content) == 2
        assert isinstance(processed[1].content[0], ThinkPart)

        # But sanitizer.sanitize() when projecting for provider DOES strip it
        provider_view = manager.sanitizer.sanitize(processed)
        assert len(provider_view[1].content) == 1
        assert isinstance(provider_view[1].content[0], TextPart)

    def test_sanitize_dict_messages(self):
        """Sanitizer should support lists of plain dicts (such as OpenAI payload format)."""
        sanitizer = ContextSanitizer(
            sanitize_historical_thoughts=True,
            sanitize_historical_tools=True,
            max_historical_tool_result_chars=20,
        )
        dict_messages = [
            {"role": "user", "content": "Question 1"},
            {
                "role": "assistant",
                "content": "<think>Long reasoning</think>Answer 1",
                "reasoning_content": "Long reasoning",
            },
            {"role": "tool", "content": "01234567890123456789extra_payload"},
            {"role": "user", "content": "Question 2 (active)"},
            {
                "role": "assistant",
                "content": "<think>Active reasoning</think>Answer 2",
                "reasoning_content": "Active reasoning",
            },
        ]

        result = sanitizer.sanitize(dict_messages)
        assert len(result) == 5

        # Historical assistant dict (index 1) should be cleaned
        assert result[1]["content"] == "Answer 1"
        assert "reasoning_content" not in result[1]

        # Historical tool dict (index 2) should be truncated
        assert len(result[2]["content"]) > 20
        assert (
            "... [historical tool output truncated to save context]"
            in result[2]["content"]
        )

        # Active turn assistant (index 4) should remain UNTOUCHED
        assert "<think>Active reasoning</think>" in result[4]["content"]
        assert result[4]["reasoning_content"] == "Active reasoning"

    def test_sanitize_dict_multipart_assistant_maintains_dict_types(self):
        """Sanitizer must maintain dictionary types when sanitizing multipart assistant dicts."""
        sanitizer = ContextSanitizer(sanitize_historical_thoughts=True)
        dict_messages = [
            {"role": "user", "content": "Question 1"},
            {
                "role": "assistant",
                "content": [
                    {"type": "think", "think": "Hidden reasoning"},
                    {"type": "text", "text": "Answer 1 <think>extra</think>"},
                ],
            },
            {"role": "user", "content": "Question 2 (active)"},
        ]

        result = sanitizer.sanitize(dict_messages)
        assert len(result) == 3
        assistant_content = result[1]["content"]
        assert isinstance(assistant_content, list)
        assert len(assistant_content) == 1
        # Part MUST be a dict, not a Pydantic object
        assert isinstance(assistant_content[0], dict)
        assert assistant_content[0]["type"] == "text"
        assert assistant_content[0]["text"] == "Answer 1"

    def test_sanitize_historical_images(self):
        """Sanitizer should prune historical images and data URIs when sanitize_historical_images is enabled."""
        sanitizer = ContextSanitizer(
            sanitize_historical_thoughts=True,
            sanitize_historical_images=True,
        )

        dummy_b64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        messages = [
            Message(
                role="user",
                content=[
                    TextPart(text=f"Look at this screenshot: {dummy_b64}"),
                    ImageURLPart(image_url={"url": "http://example.com/sample.png"}),
                ],
            ),
            Message(role="assistant", content="Acknowledged screenshot."),
            Message(
                role="user",
                content=[
                    TextPart(text=f"Now solve this with current image: {dummy_b64}"),
                    ImageURLPart(image_url={"url": "http://example.com/current.png"}),
                ],
            ),
        ]

        result = sanitizer.sanitize(messages)
        assert len(result) == 3

        # Historical user turn (index 0) should have image omitted and data URI replaced
        hist_parts = result[0].content
        assert isinstance(hist_parts, list)
        assert len(hist_parts) == 2
        assert "[data:image omitted]" in hist_parts[0].text
        assert dummy_b64 not in hist_parts[0].text
        assert hist_parts[1].text == "[historical image omitted]"

        # Active user turn (index 2) should remain UNTOUCHED
        active_parts = result[2].content
        assert isinstance(active_parts, list)
        assert dummy_b64 in active_parts[0].text
        assert isinstance(active_parts[1], ImageURLPart)

    def test_sanitize_tool_message_structured_content(self):
        """Sanitizer should truncate structured / non-string content in tool messages."""
        sanitizer = ContextSanitizer(
            sanitize_historical_tools=True,
            max_historical_tool_result_chars=30,
        )

        dict_messages = [
            {"role": "user", "content": "Run tool"},
            {"role": "assistant", "content": "Running tool..."},
            {
                "role": "tool",
                "content": {
                    "result": "extremely_large_payload_that_exceeds_thirty_chars_easily"
                },
            },
            {"role": "user", "content": "Next question"},
        ]

        result = sanitizer.sanitize(dict_messages)
        assert len(result) == 4
        tool_content = result[2]["content"]
        assert isinstance(tool_content, str)
        assert "... [historical tool output truncated to save context]" in tool_content
        assert len(tool_content) > 30
