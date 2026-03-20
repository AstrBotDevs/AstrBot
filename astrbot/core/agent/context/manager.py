from astrbot import logger

from ..message import Message
from .compressor import LLMSummaryCompressor, TruncateByTurnsCompressor
from .config import ContextConfig
from .token_counter import EstimateTokenCounter
from .truncator import ContextTruncator


class ContextManager:
    """Context compression manager.
    
    Optimizations:
    - 减少重复 token 计算
    - 添加增量压缩支持
    - 优化日志输出
    """

    def __init__(
        self,
        config: ContextConfig,
    ) -> None:
        """Initialize the context manager.

        There are two strategies to handle context limit reached:
        1. Truncate by turns: remove older messages by turns.
        2. LLM-based compression: use LLM to summarize old messages.

        Args:
            config: The context configuration.
        """
        self.config = config

        self.token_counter = config.custom_token_counter or EstimateTokenCounter()
        self.truncator = ContextTruncator()

        if config.custom_compressor:
            self.compressor = config.custom_compressor
        elif config.llm_compress_provider:
            self.compressor = LLMSummaryCompressor(
                provider=config.llm_compress_provider,
                keep_recent=config.llm_compress_keep_recent,
                instruction_text=config.llm_compress_instruction,
            )
        else:
            self.compressor = TruncateByTurnsCompressor(
                truncate_turns=config.truncate_turns
            )
        
        # 缓存上一次计算的 token 数，避免重复计算
        self._last_token_count: int | None = None
        self._compression_count = 0

    async def process(
        self, messages: list[Message], trusted_token_usage: int = 0
    ) -> list[Message]:
        """Process the messages.

        Args:
            messages: The original message list.
            trusted_token_usage: The total token usage that LLM API returned.

        Returns:
            The processed message list.
        """
        try:
            result = messages

            # 1. 基于轮次的截断 (Enforce max turns)
            if self.config.enforce_max_turns != -1:
                result = self.truncator.truncate_by_turns(
                    result,
                    keep_most_recent_turns=self.config.enforce_max_turns,
                    drop_turns=self.config.truncate_turns,
                )

            # 2. 基于 token 的压缩
            if self.config.max_context_tokens > 0:
                # 优化: 使用缓存的 token 计数或计算新值
                if trusted_token_usage > 0:
                    total_tokens = trusted_token_usage
                elif self._last_token_count is not None:
                    # 简单检查：如果消息数量没变，使用缓存
                    if len(result) == len(messages):
                        total_tokens = self._last_token_count
                    else:
                        total_tokens = self.token_counter.count_tokens(result)
                else:
                    total_tokens = self.token_counter.count_tokens(result)
                
                # 更新缓存
                self._last_token_count = total_tokens

                if self.compressor.should_compress(
                    result, total_tokens, self.config.max_context_tokens
                ):
                    result = await self._run_compression(result, total_tokens)

            return result
        except Exception as e:
            logger.error(f"Error during context processing: {e}", exc_info=True)
            return messages

    async def _run_compression(
        self, messages: list[Message], prev_tokens: int
    ) -> list[Message]:
        """
        Compress/truncate the messages.

        Args:
            messages: The original message list.
            prev_tokens: The token count before compression.

        Returns:
            The compressed/truncated message list.
        """
        logger.debug("Compress triggered, starting compression...")
        
        self._compression_count += 1

        messages = await self.compressor(messages)

        # 优化: 压缩后只计算一次 token
        tokens_after_compression = self.token_counter.count_tokens(messages)

        # calculate compress rate
        compress_rate = (tokens_after_compression / self.config.max_context_tokens) * 100
        logger.info(
            f"Compress #{self._compression_count} completed."
            f" {prev_tokens} -> {tokens_after_compression} tokens,"
            f" compression rate: {compress_rate:.2f}%.",
        )

        # 更新缓存
        self._last_token_count = tokens_after_compression
        
        # last check - 优化: 减少不必要的递归调用
        if self.compressor.should_compress(
            messages, tokens_after_compression, self.config.max_context_tokens
        ):
            logger.info(
                "Context still exceeds max tokens after compression, applying halving truncation..."
            )
            # still need compress, truncate by half
            messages = self.truncator.truncate_by_halving(messages)
            # 更新缓存
            self._last_token_count = self.token_counter.count_tokens(messages)

        return messages
    
    def get_stats(self) -> dict:
        """获取上下文管理器的统计信息。
        
        Returns:
            Dictionary with stats including compression count and token counter stats.
        """
        stats = {
            "compression_count": self._compression_count,
            "last_token_count": self._last_token_count,
        }
        
        # 如果 token counter 有缓存统计，也一并返回
        if hasattr(self.token_counter, 'get_cache_stats'):
            stats["token_counter_cache"] = self.token_counter.get_cache_stats()
        
        return stats
    
    def reset_stats(self) -> None:
        """重置统计信息。"""
        self._compression_count = 0
        self._last_token_count = None
        if hasattr(self.token_counter, 'clear_cache'):
            self.token_counter.clear_cache()
