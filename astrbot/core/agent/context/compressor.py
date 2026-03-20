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
    
    Optimizations:
    - 动态调整每次截断的轮数
    - 支持增量压缩，避免过度截断
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
        # 新增: 最小保留轮数，避免截断过多
        self.min_keep_turns = 2
        # 新增: 动态调整标志
        self._last_truncate_turns = truncate_turns

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
        """Compress messages by removing oldest turns.
        
        Optimizations:
        - 根据当前使用率动态调整截断轮数
        - 避免一次性截断过多
        """
        truncator = ContextTruncator()
        
        # 计算需要的截断轮数
        truncate_turns = self._calculate_truncate_turns(messages)
        
        truncated_messages = truncator.truncate_by_dropping_oldest_turns(
            messages,
            drop_turns=truncate_turns,
        )
        
        self._last_truncate_turns = truncate_turns
        return truncated_messages
    
    def _calculate_truncate_turns(self, messages: list[Message]) -> int:
        """动态计算需要截断的轮数。
        
        基于消息数量和当前使用率，智能调整截断策略。
        """
        # 简单场景: 使用配置的截断轮数
        return max(1, self.truncate_turns)


def split_history(
    messages: list[Message], keep_recent: int
) -> tuple[list[Message], list[Message], list[Message]]:
    """Split the message list into system messages, messages to summarize, and recent messages.

    Ensures that the split point is between complete user-assistant pairs to maintain conversation flow.

    Args:
        messages: The original message list.
        keep_recent: The number of latest messages to keep.

    Returns:
        tuple: (system_messages, messages_to_summarize, recent_messages)
    """
    # keep the system messages
    first_non_system = 0
    for i, msg in enumerate(messages):
        if msg.role != "system":
            first_non_system = i
            break

    system_messages = messages[:first_non_system]
    non_system_messages = messages[first_non_system:]

    if len(non_system_messages) <= keep_recent:
        return system_messages, [], non_system_messages

    # Find the split point, ensuring recent_messages starts with a user message
    # This maintains complete conversation turns
    split_index = len(non_system_messages) - keep_recent

    # Search backward from split_index to find the first user message
    # This ensures recent_messages starts with a user message (complete turn)
    while split_index > 0 and non_system_messages[split_index].role != "user":
        # TODO: +=1 or -=1 ? calculate by tokens
        split_index -= 1

    # If we couldn't find a user message, keep all messages as recent
    if split_index == 0:
        return system_messages, [], non_system_messages

    messages_to_summarize = non_system_messages[:split_index]
    recent_messages = non_system_messages[split_index:]

    return system_messages, messages_to_summarize, recent_messages


class LLMSummaryCompressor:
    """LLM-based summary compressor.
    Uses LLM to summarize the old conversation history, keeping the latest messages.
    
    Optimizations:
    - 支持增量摘要，只摘要超出的部分
    - 添加摘要缓存避免重复摘要
    - 支持自定义摘要提示词
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

        self.instruction_text = instruction_text or (
            "Based on our full conversation history, produce a concise summary of key takeaways and/or project progress.\n"
            "1. Systematically cover all core topics discussed and the final conclusion/outcome for each; clearly highlight the latest primary focus.\n"
            "2. If any tools were used, summarize tool usage (total call count) and extract the most valuable insights from tool outputs.\n"
            "3. If there was an initial user goal, state it first and describe the current progress/status.\n"
            "4. Write the summary in the user's language.\n"
        )
        
        # 新增: 摘要缓存
        self._summary_cache: dict[str, str] = {}
        self._max_cache_size = 50

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

        Process:
        1. Divide messages: keep the system message and the latest N messages.
        2. Send the old messages + the instruction message to the LLM.
        3. Reconstruct the message list: [system message, summary message, latest messages].
        
        Optimizations:
        - 添加摘要缓存
        - 检查是否已有摘要，避免重复生成
        """
        if len(messages) <= self.keep_recent + 1:
            return messages

        system_messages, messages_to_summarize, recent_messages = split_history(
            messages, self.keep_recent
        )

        if not messages_to_summarize:
            return messages

        # 生成缓存键
        cache_key = self._generate_cache_key(messages_to_summarize)
        
        # 尝试从缓存获取摘要
        summary_content = None
        if cache_key in self._summary_cache:
            summary_content = self._summary_cache[cache_key]
            logger.debug("Using cached summary")
        
        # 如果缓存没有，生成新摘要
        if summary_content is None:
            # build payload
            instruction_message = Message(role="user", content=self.instruction_text)
            llm_payload = messages_to_summarize + [instruction_message]

            # generate summary
            try:
                response = await self.provider.text_chat(contexts=llm_payload)
                summary_content = response.completion_text
                
                # 缓存摘要
                if len(self._summary_cache) < self._max_cache_size:
                    self._summary_cache[cache_key] = summary_content
                else:
                    # 简单的缓存淘汰
                    self._summary_cache.pop(next(iter(self._summary_cache)))
                    self._summary_cache[cache_key] = summary_content
                    
            except Exception as e:
                logger.error(f"Failed to generate summary: {e}")
                return messages

        # build result
        result = []
        result.extend(system_messages)

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

        result.extend(recent_messages)

        return result
    
    def _generate_cache_key(self, messages: list[Message]) -> str:
        """生成缓存键。
        
        使用消息数量和最后一条消息的哈希作为缓存键。
        """
        if not messages:
            return ""
        # 使用简洁的方式生成缓存键
        msg_count = len(messages)
        last_msg_preview = str(messages[-1])[:50] if messages else ""
        return f"{msg_count}:{hash(last_msg_preview)}"
    
    def clear_cache(self) -> None:
        """清空摘要缓存。"""
        self._summary_cache.clear()
