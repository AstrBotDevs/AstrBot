from typing import TYPE_CHECKING, Protocol, runtime_checkable

from ..message import Message

if TYPE_CHECKING:
    from astrbot import logger
else:
    try:
        from astrbot import logger
    except ImportError:
        import logging

        logger = logging.getLogger("astrbot")

if TYPE_CHECKING:
    from astrbot.core.provider.provider import Provider

from ..context.truncator import ContextTruncator


@runtime_checkable
class ContextCompressor(Protocol):
    """
    Protocol for context compressors.
    Provides an interface for compressing message lists.
    """

    def should_compress(
        self, messages: list[Message], current_tokens: int, max_tokens: int
    ) -> bool:
        """Check if compression is needed.

        Args:
            messages: The message list to evaluate.
            current_tokens: The current token count.
            max_tokens: The maximum allowed tokens for the model.

        Returns:
            True if compression is needed, False otherwise.
        """
        ...

    async def __call__(self, messages: list[Message]) -> list[Message]:
        """Compress the message list.

        Args:
            messages: The original message list.

        Returns:
            The compressed message list.
        """
        ...


class TruncateByTurnsCompressor:
    """Truncate by turns compressor implementation.
    Truncates the message list by removing older turns.
    """

    def __init__(
        self, truncate_turns: int = 1, compression_threshold: float = 0.82
    ) -> None:
        """Initialize the truncate by turns compressor.

        Args:
            truncate_turns: The number of turns to remove when truncating (default: 1).
            compression_threshold: The compression trigger threshold (default: 0.82).
        """
        self.truncate_turns = truncate_turns
        self.compression_threshold = compression_threshold

    def should_compress(
        self, messages: list[Message], current_tokens: int, max_tokens: int
    ) -> bool:
        """Check if compression is needed.

        Args:
            messages: The message list to evaluate.
            current_tokens: The current token count.
            max_tokens: The maximum allowed tokens.

        Returns:
            True if compression is needed, False otherwise.
        """
        if max_tokens <= 0 or current_tokens <= 0:
            return False
        usage_rate = current_tokens / max_tokens
        return usage_rate > self.compression_threshold

    async def __call__(self, messages: list[Message]) -> list[Message]:
        truncator = ContextTruncator()
        truncated_messages = truncator.truncate_by_dropping_oldest_turns(
            messages,
            drop_turns=self.truncate_turns,
        )
        return truncated_messages


def _message_to_dict(msg: Message) -> dict:
    """Convert a Message to a plain dict suitable for round splitting."""
    d = {"role": msg.role}
    if msg.content is not None:
        d["content"] = msg.content
    if getattr(msg, "tool_calls", None):
        d["tool_calls"] = msg.tool_calls
    if getattr(msg, "tool_call_id", None):
        d["tool_call_id"] = msg.tool_call_id
    return d


def _dict_to_message(d: dict) -> Message:
    """Convert a plain dict back to a Message."""
    return Message(**d)


def _extract_system_messages(messages: list[Message]) -> list[Message]:
    """Return the leading system messages from a message list."""
    result = []
    for msg in messages:
        if msg.role == "system":
            result.append(msg)
        else:
            break
    return result


class LLMSummaryCompressor:
    """LLM-based summary compressor.
    Uses LLM to summarize the old conversation history, keeping the latest messages.
    """

    def __init__(
        self,
        provider: "Provider",
        keep_recent: int = 4,
        instruction_text: str | None = None,
        compression_threshold: float = 0.82,
    ) -> None:
        """Initialize the LLM summary compressor.

        Args:
            provider: The LLM provider instance.
            keep_recent: The number of latest messages to keep (default: 4).
            instruction_text: Custom instruction for summary generation.
            compression_threshold: The compression trigger threshold (default: 0.82).
        """
        self.provider = provider
        self.keep_recent = keep_recent
        self.compression_threshold = compression_threshold
        self.existing_summary: str = ""

        self.instruction_text = instruction_text or (
            "Based on our full conversation history, produce a concise summary of key takeaways and/or project progress.\n"
            "The primary goal of this summary is to enable seamless continuation of the work that follows.\n"
            "1. Systematically cover all core topics discussed and the final conclusion/outcome for each; clearly highlight the latest primary focus.\n"
            "2. If any tools were used, summarize tool usage (total call count) and extract the most valuable insights from tool outputs.\n"
            "3. If any materials (files, documents, code, references) were read during the conversation that may be helpful for subsequent work, list each one with its scope and path.\n"
            "4. If there was an initial user goal, state it first and describe the current progress/status.\n"
            "5. Write the summary in the user's language.\n"
        )

    def should_compress(
        self, messages: list[Message], current_tokens: int, max_tokens: int
    ) -> bool:
        """Check if compression is needed.

        Args:
            messages: The message list to evaluate.
            current_tokens: The current token count.
            max_tokens: The maximum allowed tokens.

        Returns:
            True if compression is needed, False otherwise.
        """
        if max_tokens <= 0 or current_tokens <= 0:
            return False
        usage_rate = current_tokens / max_tokens
        return usage_rate > self.compression_threshold

    async def __call__(self, messages: list[Message]) -> list[Message]:
        """Use LLM to generate a summary of the conversation history.

        Uses round-based splitting to preserve user-assistant turn boundaries.
        On LLM failure, returns the original messages unchanged (caller should
        fall back to truncation).
        """
        from .round_utils import rounds_to_text, split_into_rounds

        # Convert messages to dict list for round splitting
        msg_dicts = [_message_to_dict(m) for m in messages]
        rounds = split_into_rounds(msg_dicts)

        if len(rounds) <= self.keep_recent:
            return messages

        old_rounds = rounds[: -self.keep_recent]
        recent_rounds = rounds[-self.keep_recent :]

        if not old_rounds:
            return messages

        # Build LLM payload
        old_text = rounds_to_text(old_rounds)
        existing_note = ""
        if self.existing_summary:
            existing_note = (
                "\nExisting memory summary (merge with old rounds above):\n"
                f"{self.existing_summary}\n"
            )
        prompt = (
            f"{self.instruction_text}\n\n"
            "--- BEGIN CONVERSATION ROUNDS TO SUMMARIZE ---\n"
            f"{old_text}\n"
            "--- END CONVERSATION ROUNDS ---"
            f"{existing_note}"
        )

        # Generate summary
        try:
            response = await self.provider.text_chat(prompt=prompt)
            summary_content = (response.completion_text or "").strip()
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return messages

        if not summary_content:
            logger.warning("LLM context compression returned an empty summary.")
            return messages

        # Build result: system messages + summary pair + recent rounds
        result = _extract_system_messages(messages)

        result.append(
            Message(
                role="user",
                content=f"Our previous history conversation summary: {summary_content}",
            )
        )
        result.append(
            Message(
                role="assistant",
                content="Acknowledged the summary of our previous conversation history.",
            )
        )

        # Flatten recent rounds back to message list
        for rnd in recent_rounds:
            for seg in rnd:
                result.append(_dict_to_message(seg))

        return result
