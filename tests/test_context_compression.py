"""Tests for context compression optimizations.

这些测试验证了上下文压缩模块的优化功能:
1. Token 估算算法的精确性
2. 缓存机制的有效性
3. 压缩器的增量压缩支持
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock

from astrbot.core.agent.context.token_counter import EstimateTokenCounter
from astrbot.core.agent.context.compressor import (
    TruncateByTurnsCompressor,
    LLMSummaryCompressor,
    split_history,
)
from astrbot.core.agent.context.manager import ContextManager
from astrbot.core.agent.context.config import ContextConfig
from astrbot.core.agent.message import Message


class TestEstimateTokenCounter:
    """Test cases for improved token counter."""

    def setup_method(self):
        """Setup test fixtures."""
        self.counter = EstimateTokenCounter()

    def test_chinese_text_token_estimation(self):
        """测试中文文本的 token 估算。"""
        text = "你好，世界！这是一段中文测试文本。"
        tokens = self.counter._estimate_tokens(text)
        # 中文应该约占 0.55 tokens/字符
        assert tokens > 0
        # 验证估算值合理
        assert tokens < len(text)  # 应该比字符数少

    def test_english_text_token_estimation(self):
        """测试英文文本的 token 估算。"""
        text = "Hello, world! This is an English test text."
        tokens = self.counter._estimate_tokens(text)
        assert tokens > 0
        # 英文应该约占 0.25 tokens/字符
        assert tokens < len(text)

    def test_mixed_text_token_estimation(self):
        """测试中英文混合文本的 token 估算。"""
        text = "你好 Hello, 世界 World! 混合 Mix 文本 Text。"
        tokens = self.counter._estimate_tokens(text)
        assert tokens > 0

    def test_digit_token_estimation(self):
        """测试数字的 token 估算。"""
        text = "1234567890"
        tokens = self.counter._estimate_tokens(text)
        assert tokens > 0

    def test_empty_text(self):
        """测试空文本。"""
        tokens = self.counter._estimate_tokens("")
        assert tokens == 0

    def test_message_list_token_counting(self):
        """测试消息列表的 token 计数。"""
        messages = [
            Message(role="system", content="You are a helpful assistant."),
            Message(role="user", content="你好"),
            Message(role="assistant", content="你好！有什么可以帮助你的吗？"),
        ]
        tokens = self.counter.count_tokens(messages)
        assert tokens > 0

    def test_cache_functionality(self):
        """测试缓存功能。"""
        messages = [
            Message(role="user", content="测试消息"),
            Message(role="assistant", content="测试回复"),
        ]
        
        # 第一次计数
        tokens1 = self.counter.count_tokens(messages)
        
        # 第二次计数应该使用缓存
        tokens2 = self.counter.count_tokens(messages)
        
        assert tokens1 == tokens2
        
        # 检查缓存统计
        stats = self.counter.get_cache_stats()
        assert stats["hits"] >= 1

    def test_cache_clear(self):
        """测试缓存清除。"""
        messages = [Message(role="user", content="测试")]
        self.counter.count_tokens(messages)
        
        # 清除缓存
        self.counter.clear_cache()
        
        stats = self.counter.get_cache_stats()
        assert stats["hits"] == 0
        assert stats["cache_size"] == 0


class TestTruncateByTurnsCompressor:
    """Test cases for truncate by turns compressor."""

    def setup_method(self):
        """Setup test fixtures."""
        self.compressor = TruncateByTurnsCompressor(truncate_turns=1)

    def test_should_compress_above_threshold(self):
        """测试超过阈值时触发压缩。"""
        messages = [
            Message(role="user", content="测试消息"),
            Message(role="assistant", content="测试回复"),
        ]
        # max_tokens=100, 当前 tokens 应该远超阈值
        assert self.compressor.should_compress(messages, 90, 100) is True

    def test_should_compress_below_threshold(self):
        """测试未超过阈值时不触发压缩。"""
        messages = [Message(role="user", content="短消息")]
        assert self.compressor.should_compress(messages, 10, 100) is False

    def test_should_compress_zero_max_tokens(self):
        """测试 max_tokens 为 0 时不触发压缩。"""
        messages = [Message(role="user", content="测试")]
        assert self.compressor.should_compress(messages, 50, 0) is False


class TestSplitHistory:
    """Test cases for split_history function."""

    def test_split_with_enough_messages(self):
        """测试消息数量足够时的分割。"""
        messages = [
            Message(role="system", content="System"),
            Message(role="user", content="User 1"),
            Message(role="assistant", content="Assistant 1"),
            Message(role="user", content="User 2"),
            Message(role="assistant", content="Assistant 2"),
            Message(role="user", content="User 3"),
            Message(role="assistant", content="Assistant 3"),
        ]
        
        system, to_summarize, recent = split_history(messages, keep_recent=2)
        
        assert len(system) == 1  # system message
        assert len(recent) >= 2  # 至少保留最近的消息

    def test_split_with_few_messages(self):
        """测试消息数量不足时的分割。"""
        messages = [
            Message(role="user", content="User 1"),
            Message(role="assistant", content="Assistant 1"),
        ]
        
        system, to_summarize, recent = split_history(messages, keep_recent=4)
        
        assert len(to_summarize) == 0  # 没有需要摘要的消息
        assert len(recent) == 2


class TestLLMSummaryCompressor:
    """Test cases for LLM summary compressor."""

    def setup_method(self):
        """Setup test fixtures."""
        self.mock_provider = Mock()
        self.mock_provider.text_chat = AsyncMock()
        self.mock_provider.text_chat.return_value = Mock(completion_text="这是一段摘要。")
        
        self.compressor = LLMSummaryCompressor(
            provider=self.mock_provider,
            keep_recent=2
        )

    @pytest.mark.asyncio
    async def test_generate_summary(self):
        """测试生成摘要。"""
        messages = [
            Message(role="system", content="System"),
            Message(role="user", content="User 1"),
            Message(role="assistant", content="Assistant 1"),
            Message(role="user", content="User 2"),
            Message(role="assistant", content="Assistant 2"),
            Message(role="user", content="User 3"),
            Message(role="assistant", content="Assistant 3"),
        ]
        
        result = await self.compressor(messages)
        
        # 验证摘要已生成
        assert len(result) >= 3
        # 验证 LLM 被调用
        self.mock_provider.text_chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_summary(self):
        """测试摘要缓存。"""
        messages = [
            Message(role="system", content="System"),
            Message(role="user", content="User 1"),
            Message(role="assistant", content="Assistant 1"),
            Message(role="user", content="User 2"),
            Message(role="assistant", content="Assistant 2"),
        ]
        
        # 第一次调用
        await self.compressor(messages)
        
        # 第二次调用应该使用缓存
        await self.compressor(messages)
        
        # LLM 只应该被调用一次
        assert self.mock_provider.text_chat.call_count == 1


class TestContextManager:
    """Test cases for context manager."""

    def setup_method(self):
        """Setup test fixtures."""
        self.config = ContextConfig(
            max_context_tokens=1000,
            truncate_turns=1,
            enforce_max_turns=-1,
        )
        self.manager = ContextManager(self.config)

    @pytest.mark.asyncio
    async def test_process_no_compression_needed(self):
        """测试不需要压缩的情况。"""
        messages = [
            Message(role="user", content="短消息"),
        ]
        
        result = await self.manager.process(messages)
        
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_process_with_compression(self):
        """测试需要压缩的情况。"""
        # 创建大量消息以触发压缩
        messages = []
        for i in range(50):
            messages.append(Message(role="user", content=f"用户消息 {i} " * 50))
            messages.append(Message(role="assistant", content=f"助手回复 {i} " * 50))
        
        # 设置较小的 max_context_tokens 以触发压缩
        self.config.max_context_tokens = 100
        
        result = await self.manager.process(messages)
        
        # 验证消息被压缩
        assert len(result) < len(messages)

    def test_get_stats(self):
        """测试获取统计信息。"""
        stats = self.manager.get_stats()
        
        assert "compression_count" in stats
        assert "last_token_count" in stats

    def test_reset_stats(self):
        """测试重置统计信息。"""
        self.manager._compression_count = 5
        
        self.manager.reset_stats()
        
        assert self.manager._compression_count == 0
        assert self.manager._last_token_count is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
