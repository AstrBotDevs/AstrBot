from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from astrbot.api import logger

from ..message import Message

if TYPE_CHECKING:
    from astrbot.core.provider.provider import Provider

from ..context.truncator import ContextTruncator


class ContextCompressor(ABC):
    """
    Abstract base class for context compressors.
    Provides an interface for compressing message lists.
    """

    @abstractmethod
    async def compress(self, messages: list[Message]) -> list[Message]:
        """Compress the message list.

        Args:
            messages: The original message list.

        Returns:
            The compressed message list.
        """
        pass


class DefaultCompressor(ContextCompressor):
    """Default compressor implementation.
    Returns the original messages.
    """

    async def compress(self, messages: list[Message]) -> list[Message]:
        return messages


class TruncateByTurnsCompressor(ContextCompressor):
    """Truncate by turns compressor implementation.
    Truncates the message list by removing older turns.
    """

    def __init__(self, truncate_turns: int = 1):
        """Initialize the truncate by turns compressor.

        Args:
            truncate_turns: The number of turns to remove when truncating (default: 1).
        """
        self.truncate_turns = truncate_turns

    async def compress(self, messages: list[Message]) -> list[Message]:
        truncator = ContextTruncator()
        truncated_messages = truncator.truncate_by_turns(
            messages,
            keep_most_recent_turns=0,
            dequeue_turns=self.truncate_turns,
        )
        return truncated_messages


class LLMSummaryCompressor(ContextCompressor):
    """LLM-based summary compressor.
    Uses LLM to summarize the old conversation history, keeping the latest messages.
    """

    def __init__(
        self,
        provider: "Provider",
        keep_recent: int = 4,
        instruction_text: str | None = None,
    ):
        """Initialize the LLM summary compressor.

        Args:
            provider: The LLM provider instance.
            keep_recent: The number of latest messages to keep (default: 4).
        """
        self.provider = provider
        self.keep_recent = keep_recent

        self.instruction_text = instruction_text or (
            "Based on our full conversation history, produce a concise summary of key takeaways and/or project progress.\n"
            "1. Systematically cover all core topics discussed and the final conclusion/outcome for each; clearly highlight the latest primary focus.\n"
            "2. If any tools were used, summarize tool usage (total call count) and extract the most valuable insights from tool outputs.\n"
            "3. If there was an initial user goal, state it first and describe the current progress/status.\n"
            "4. Write the summary in the user's language.\n"
        )

    async def compress(self, messages: list[Message]) -> list[Message]:
        """Use LLM to generate a summary of the conversation history.

        Process:
        1. Divide messages: keep the system message and the latest N messages.
        2. Send the old messages + the instruction message to the LLM.
        3. Reconstruct the message list: [system message, summary message, latest messages].
        """
        if len(messages) <= self.keep_recent + 1:
            return messages

        # keep the system message
        system_msg = messages[0] if messages and messages[0].role == "system" else None
        start_idx = 1 if system_msg else 0

        messages_to_summarize = messages[start_idx : -self.keep_recent]
        recent_messages = messages[-self.keep_recent :]

        if not messages_to_summarize:
            return messages

        # build payload
        instruction_message = Message(role="user", content=self.instruction_text)
        llm_payload = messages_to_summarize + [instruction_message]

        # generate summary
        try:
            response = await self.provider.text_chat(contexts=llm_payload)
            summary_content = response.completion_text
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return messages

        # build result
        result = []
        if system_msg:
            result.append(system_msg)

        result.append(
            Message(
                role="system",
                content=f"History conversation summary: {summary_content}",
            ),
        )

        result.extend(recent_messages)

        return result
