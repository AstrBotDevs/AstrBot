"""Context Sanitizer for multi-turn conversations and agent execution.

Addresses Issue #10195:
- Strips historical reasoning chains (<think> blocks, ThinkPart) from prior completed turns.
- Compacts or truncates bulky historical tool call results (role='tool') from prior completed turns.
- Ensures the active/current turn retains full reasoning and tool execution content.
- Preserves OpenAI/Anthropic/Gemini protocol validity (tool_calls <-> role="tool" pairing).
- Operates non-destructively: returns new message objects without corrupting underlying persistent history.
- Supports both Message objects and raw dictionary formats.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from ..message import Message, TextPart, ThinkPart
from .truncator import ContextTruncator

_THINK_TAG_REGEX = re.compile(r"<think>.*?</think>", flags=re.DOTALL | re.IGNORECASE)


def _get_item_role(item: Any) -> str:
    """Extract role string from Message object or dict."""
    if isinstance(item, Message):
        return item.role
    if isinstance(item, dict):
        return str(item.get("role", ""))
    return getattr(item, "role", "")


class ContextSanitizer:
    """Sanitizer for purifying historical messages before sending to LLM providers."""

    def __init__(
        self,
        sanitize_historical_thoughts: bool = True,
        sanitize_historical_tools: bool = False,
        max_historical_tool_result_chars: int = 500,
        sanitize_historical_images: bool = False,
    ) -> None:
        self.sanitize_historical_thoughts = sanitize_historical_thoughts
        self.sanitize_historical_tools = sanitize_historical_tools
        self.max_historical_tool_result_chars = max_historical_tool_result_chars
        self.sanitize_historical_images = sanitize_historical_images
        self._truncator = ContextTruncator()

    @staticmethod
    def find_last_user_index(
        messages: list[Message] | list[dict[str, Any]],
    ) -> int | None:
        """Find the index of the last user message, marking the start of the current turn."""
        for i in range(len(messages) - 1, -1, -1):
            if _get_item_role(messages[i]) == "user":
                return i
        return None

    def sanitize(
        self, messages: list[Message] | list[dict[str, Any]]
    ) -> list[Message] | list[dict[str, Any]]:
        """Sanitize historical messages while leaving the active/current turn intact.

        Args:
            messages: List of Message objects or dicts in the conversation context.

        Returns:
            A new list of messages with historical noise removed/compacted.
        """
        if not messages:
            return messages

        if not self.sanitize_historical_thoughts and not self.sanitize_historical_tools:
            return messages

        last_user_idx = self.find_last_user_index(messages)
        if last_user_idx is None or last_user_idx == 0:
            # No prior completed turns (e.g. first user turn or system-only)
            return messages

        historical_messages = messages[:last_user_idx]
        current_turn_messages = messages[last_user_idx:]

        sanitized_history: list[Any] = []
        for msg in historical_messages:
            sanitized_history.append(self._sanitize_historical_message(msg))

        # Recombine sanitized history with current turn
        result = sanitized_history + current_turn_messages

        # Ensure message sequence adheres to protocol when operating on Message objects
        if all(isinstance(m, Message) for m in result):
            return self._truncator.fix_messages(result)
        return result

    def _sanitize_historical_message(
        self, msg: Message | dict[str, Any]
    ) -> Message | dict[str, Any]:
        """Sanitize an individual historical message without mutating the original."""
        role = _get_item_role(msg)
        if role == "assistant" and self.sanitize_historical_thoughts:
            return self._sanitize_assistant_message(msg)

        if role == "tool" and self.sanitize_historical_tools:
            return self._sanitize_tool_message(msg)

        return msg

    def _sanitize_assistant_message(
        self, msg: Message | dict[str, Any]
    ) -> Message | dict[str, Any]:
        """Remove reasoning / thought content from a historical assistant message."""
        if isinstance(msg, dict):
            new_msg = copy.deepcopy(msg)
            content = new_msg.get("content")
            if isinstance(content, list):
                filtered_parts = []
                for part in content:
                    if isinstance(part, ThinkPart):
                        continue
                    if isinstance(part, dict) and part.get("type") == "think":
                        continue
                    if isinstance(part, TextPart):
                        cleaned_text = _THINK_TAG_REGEX.sub("", part.text).strip()
                        filtered_parts.append(TextPart(text=cleaned_text))
                    elif isinstance(part, dict) and part.get("type") == "text":
                        cleaned_text = _THINK_TAG_REGEX.sub(
                            "", str(part.get("text", ""))
                        ).strip()
                        part_copy = copy.copy(part)
                        part_copy["text"] = cleaned_text
                        filtered_parts.append(part_copy)
                    else:
                        filtered_parts.append(part)

                if filtered_parts:
                    new_msg["content"] = filtered_parts
                else:
                    new_msg["content"] = None if new_msg.get("tool_calls") else ""
            elif isinstance(content, str):
                new_msg["content"] = _THINK_TAG_REGEX.sub("", content).strip()
            new_msg.pop("reasoning_content", None)
            return new_msg

        new_msg = copy.copy(msg)
        if isinstance(new_msg.content, list):
            # Filter out ThinkPart
            filtered_parts = []
            for part in new_msg.content:
                if isinstance(part, ThinkPart):
                    continue
                if isinstance(part, dict) and part.get("type") == "think":
                    continue
                if isinstance(part, TextPart):
                    cleaned_text = _THINK_TAG_REGEX.sub("", part.text).strip()
                    filtered_parts.append(TextPart(text=cleaned_text))
                elif isinstance(part, dict) and part.get("type") == "text":
                    cleaned_text = _THINK_TAG_REGEX.sub(
                        "", str(part.get("text", ""))
                    ).strip()
                    part_copy = copy.copy(part)
                    part_copy["text"] = cleaned_text
                    filtered_parts.append(part_copy)
                else:
                    filtered_parts.append(part)

            if filtered_parts:
                new_msg.content = filtered_parts
            else:
                if new_msg.tool_calls:
                    new_msg.content = None
                else:
                    new_msg.content = ""
        elif isinstance(new_msg.content, str):
            cleaned_str = _THINK_TAG_REGEX.sub("", new_msg.content).strip()
            new_msg.content = cleaned_str

        return new_msg

    def _sanitize_tool_message(
        self, msg: Message | dict[str, Any]
    ) -> Message | dict[str, Any]:
        """Compact/truncate excessive output in a historical tool message."""
        if isinstance(msg, dict):
            new_msg = copy.copy(msg)
            content = new_msg.get("content")
            if (
                isinstance(content, str)
                and len(content) > self.max_historical_tool_result_chars
            ):
                new_msg["content"] = (
                    content[: self.max_historical_tool_result_chars]
                    + "\n... [historical tool output truncated to save context]"
                )
            return new_msg

        new_msg = copy.copy(msg)
        if isinstance(new_msg.content, str):
            if len(new_msg.content) > self.max_historical_tool_result_chars:
                truncated = (
                    new_msg.content[: self.max_historical_tool_result_chars]
                    + "\n... [historical tool output truncated to save context]"
                )
                new_msg.content = truncated
        return new_msg
