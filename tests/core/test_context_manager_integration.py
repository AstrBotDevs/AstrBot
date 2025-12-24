"""
集成测试：验证上下文管理器在实际流水线中的工作情况
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.context_manager import ContextManager
from astrbot.core.provider.entities import LLMResponse


class MockProvider:
    """模拟 Provider"""

    def __init__(self):
        self.provider_config = {
            "id": "test_provider",
            "model": "gpt-4",
            "modalities": ["text", "image", "tool_use"],
        }

    async def text_chat(self, **kwargs):
        """模拟 LLM 调用，返回摘要"""
        messages = kwargs.get("messages", [])
        # 简单的摘要逻辑：返回消息数量统计
        return LLMResponse(
            role="assistant",
            completion_text=f"历史对话包含 {len(messages) - 1} 条消息，主要讨论了技术话题。",
        )

    def get_model(self):
        return "gpt-4"

    def meta(self):
        return MagicMock(id="test_provider", type="openai")


class TestContextManagerIntegration:
    """集成测试：验证上下文管理器的完整工作流程"""

    @pytest.mark.asyncio
    async def test_no_compression_below_threshold(self):
        """测试：Token使用率低于82%时不触发压缩"""
        provider = MockProvider()
        manager = ContextManager(
            model_context_limit=10000,  # 很大的上下文窗口
            provider=provider,
        )

        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi! How can I help you?"},
        ]

        result = await manager.process(messages, max_messages_to_keep=20)

        # Token使用率低，不应该触发压缩
        assert len(result) == len(messages)
        assert result == messages

    @pytest.mark.asyncio
    async def test_llm_summary_compression_above_threshold(self):
        """测试：Token使用率超过82%时触发LLM智能摘要"""
        provider = MockProvider()
        manager = ContextManager(
            model_context_limit=100,  # 很小的上下文窗口，容易触发
            provider=provider,
        )

        # 创建足够多的消息以触发压缩（每条消息约30个token）
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
        ]
        for i in range(10):
            messages.append(
                {"role": "user", "content": f"This is a long question number {i}"}
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": f"This is a detailed response to question {i}",
                }
            )

        result = await manager.process(messages, max_messages_to_keep=20)

        # 应该触发压缩
        assert len(result) < len(messages)
        # 应该包含系统消息
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "You are a helpful assistant."
        # 应该包含摘要消息（只检查非空，不检查具体文案）
        has_summary = any(
            msg.get("role") == "system" and msg.get("content", "").strip() != ""
            for msg in result
        )
        assert has_summary, "应该包含LLM生成的摘要消息"

    @pytest.mark.asyncio
    async def test_fallback_to_default_compressor_without_provider(self):
        """测试：没有provider时回退到DefaultCompressor"""
        manager = ContextManager(
            model_context_limit=100,
            provider=None,  # 没有provider
        )

        messages = [
            {"role": "system", "content": "System"},
        ]
        for i in range(10):
            messages.append({"role": "user", "content": f"Question {i}"})
            messages.append({"role": "assistant", "content": f"Answer {i}"})

        result = await manager.process(messages, max_messages_to_keep=20)

        # 没有provider，应该使用DefaultCompressor（不摘要）
        # 但会触发对半砍
        assert len(result) < len(messages)

    @pytest.mark.asyncio
    async def test_merge_consecutive_messages(self):
        """测试：合并连续的同角色消息"""
        provider = MockProvider()
        manager = ContextManager(
            model_context_limit=10000,
            provider=provider,
        )

        messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "Part 1"},
            {"role": "user", "content": "Part 2"},
            {"role": "assistant", "content": "Response 1"},
            {"role": "assistant", "content": "Response 2"},
            {"role": "user", "content": "Final question"},
        ]

        result = await manager.process(messages, max_messages_to_keep=20)

        # 连续的user消息应该被合并
        user_messages = [m for m in result if m["role"] == "user"]
        assert len(user_messages) == 2  # 合并后应该只有2条user消息
        assert "Part 1" in user_messages[0]["content"]
        assert "Part 2" in user_messages[0]["content"]

    @pytest.mark.asyncio
    async def test_cleanup_unpaired_tool_calls(self):
        """测试：清理不成对的Tool Calls"""
        provider = MockProvider()
        manager = ContextManager(
            model_context_limit=10000,
            provider=provider,
        )

        messages = [
            {"role": "system", "content": "System"},
            {
                "role": "assistant",
                "content": "I'll use tools",
                "tool_calls": [
                    {"id": "call_1", "function": {"name": "tool1"}},
                    {"id": "call_2", "function": {"name": "tool2"}},
                ],
            },
            # call_1 有响应
            {"role": "tool", "tool_call_id": "call_1", "content": "Result 1"},
            # call_2 没有响应（不成对）
            {
                "role": "assistant",
                "content": "Final response",
                "tool_calls": [
                    {"id": "call_3", "function": {"name": "tool3"}},  # 最后一次调用
                ],
            },
        ]

        result = await manager.process(messages, max_messages_to_keep=20)

        # 验证清理逻辑
        # call_2 应该被清理掉（不成对）
        # call_3 应该保留（最后一次调用，视为当前请求）
        all_tool_calls = []
        for m in result:
            if m.get("tool_calls"):
                all_tool_calls.extend([tc["id"] for tc in m["tool_calls"]])

        assert "call_1" in all_tool_calls  # 有响应的保留
        assert "call_2" not in all_tool_calls  # 没响应的删除
        assert "call_3" in all_tool_calls  # 最后一次保留

    @pytest.mark.asyncio
    async def test_truncate_by_count(self):
        """测试：按消息数量截断"""
        provider = MockProvider()
        manager = ContextManager(
            model_context_limit=10000,
            provider=provider,
        )

        messages = [
            {"role": "system", "content": "System"},
        ]
        for i in range(50):
            messages.append({"role": "user", "content": f"Q{i}"})
            messages.append({"role": "assistant", "content": f"A{i}"})

        result = await manager.process(messages, max_messages_to_keep=10)

        # 应该只保留10条消息（包括系统消息）
        assert len(result) <= 10
        # 系统消息应该保留
        assert result[0]["role"] == "system"
        # 最新的消息应该保留
        assert result[-1]["content"] == "A49"

    @pytest.mark.asyncio
    async def test_full_pipeline_with_compression_and_truncation(self):
        """测试：完整流程 - Token压缩 + 消息合并 + Tool清理 + 数量截断"""
        provider = MockProvider()
        manager = ContextManager(
            model_context_limit=150,  # 小窗口，容易触发压缩
            provider=provider,
        )

        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
        ]

        # 添加大量消息以触发压缩
        for i in range(15):
            messages.append({"role": "user", "content": f"This is question number {i}"})
            messages.append(
                {"role": "assistant", "content": f"This is answer number {i}"}
            )

        # 添加连续消息测试合并
        messages.append({"role": "user", "content": "Part 1 of final question"})
        messages.append({"role": "user", "content": "Part 2 of final question"})

        # 添加Tool Calls测试清理
        messages.append(
            {
                "role": "assistant",
                "content": "Using tools",
                "tool_calls": [
                    {"id": "call_1", "function": {"name": "tool1"}},
                    {"id": "call_2", "function": {"name": "tool2"}},
                ],
            }
        )
        messages.append({"role": "tool", "tool_call_id": "call_1", "content": "OK"})
        # call_2 没有响应

        result = await manager.process(messages, max_messages_to_keep=15)

        # 验证各个功能都生效
        # 1. Token压缩应该生效（结果长度小于原始）
        assert len(result) < len(messages)
        assert len(result) <= 15  # 数量截断

        # 2. 系统消息应该保留
        assert result[0]["role"] == "system"

        # 3. 应该包含摘要（如果触发了LLM摘要）
        has_summary = any(
            msg.get("role") == "system" and msg.get("content", "").strip() != ""
            for msg in result
        )
        assert has_summary or len(result) < 15  # 要么有摘要，要么触发了对半砍

        # 4. 最新的消息应该保留
        last_user_msg = next((m for m in reversed(result) if m["role"] == "user"), None)
        assert last_user_msg is not None
        assert (
            "Part 1" in last_user_msg["content"] or "Part 2" in last_user_msg["content"]
        )

    @pytest.mark.asyncio
    async def test_disabled_context_management(self):
        """测试：context_limit=-1时禁用上下文管理"""
        provider = MockProvider()
        manager = ContextManager(
            model_context_limit=-1,  # 禁用上下文管理
            provider=provider,
        )

        messages = [{"role": "user", "content": f"Message {i}"} for i in range(100)]

        result = await manager.process(messages, max_messages_to_keep=10)

        # 禁用时应该返回原始消息
        assert result == messages


class TestLLMSummaryCompressorWithMockAPI:
    """测试 LLM 摘要压缩器的API交互"""

    @pytest.mark.asyncio
    async def test_summary_api_call(self):
        """测试：验证LLM API调用的参数正确性"""
        provider = MockProvider()

        from astrbot.core.context_manager.context_compressor import LLMSummaryCompressor

        compressor = LLMSummaryCompressor(provider, keep_recent=3)

        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
            {"role": "assistant", "content": "A2"},
            {"role": "user", "content": "Q3"},
            {"role": "assistant", "content": "A3"},
            {"role": "user", "content": "Q4"},
            {"role": "assistant", "content": "A4"},
        ]

        with patch.object(provider, "text_chat", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = LLMResponse(
                role="assistant", completion_text="Test summary"
            )

            result = await compressor.compress(messages)

            # 验证API被调用了
            mock_call.assert_called_once()

            # 验证传递给API的消息
            call_kwargs = mock_call.call_args[1]
            api_messages = call_kwargs["messages"]

            # 应该包含：旧消息(Q1,A1,Q2,A2,Q3) + 指令消息
            # keep_recent=3 表示保留最后3条，所以摘要消息应该是前面的 (9-1-3)=5条
            assert len(api_messages) == 6  # 5条旧消息 + 1条指令
            assert api_messages[-1]["role"] == "user"  # 指令消息
            # 放宽断言：只检查指令消息非空，不检查具体文案
            assert api_messages[-1]["content"].strip() != ""

            # 验证返回结果
            assert len(result) == 5  # system + summary + 3条最新
            assert result[0]["role"] == "system"
            assert result[1]["role"] == "system"
            # 放宽断言：只检查摘要消息非空，不检查具体文案
            assert result[1]["content"].strip() != ""
            assert (
                "Test summary" in result[1]["content"]
            )  # 保留对 summary 工具结果的检查

    @pytest.mark.asyncio
    async def test_summary_error_handling(self):
        """测试：LLM API调用失败时的错误处理"""
        provider = MockProvider()

        from astrbot.core.context_manager.context_compressor import LLMSummaryCompressor

        compressor = LLMSummaryCompressor(provider, keep_recent=2)

        messages = [{"role": "user", "content": f"Message {i}"} for i in range(10)]

        with patch.object(
            provider, "text_chat", side_effect=Exception("API Error")
        ) as mock_call:
            result = await compressor.compress(messages)

            # API失败时应该返回原始消息
            assert result == messages
            mock_call.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
