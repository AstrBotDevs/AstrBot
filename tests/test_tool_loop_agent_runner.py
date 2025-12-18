import os
import sys
from unittest.mock import AsyncMock

import pytest

# 将项目根目录添加到 sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.provider.entities import LLMResponse, ProviderRequest, TokenUsage
from astrbot.core.provider.provider import Provider


class MockProvider(Provider):
    """模拟Provider用于测试"""

    def __init__(self):
        super().__init__({}, {})
        self.call_count = 0
        self.should_call_tools = True
        self.max_calls_before_normal_response = 10

    def get_current_key(self) -> str:
        return "test_key"

    def set_key(self, key: str):
        pass

    async def get_models(self) -> list[str]:
        return ["test_model"]

    async def text_chat(self, **kwargs) -> LLMResponse:
        self.call_count += 1

        # 检查工具是否被禁用
        func_tool = kwargs.get("func_tool")

        # 如果工具被禁用或超过最大调用次数，返回正常响应
        if func_tool is None or self.call_count > self.max_calls_before_normal_response:
            return LLMResponse(
                role="assistant",
                completion_text="这是我的最终回答",
                usage=TokenUsage(input_other=10, output=5),
            )

        # 模拟工具调用响应
        if self.should_call_tools:
            return LLMResponse(
                role="assistant",
                completion_text="我需要使用工具来帮助您",
                tools_call_name=["test_tool"],
                tools_call_args=[{"query": "test"}],
                tools_call_ids=["call_123"],
                usage=TokenUsage(input_other=10, output=5),
            )

        # 默认返回正常响应
        return LLMResponse(
            role="assistant",
            completion_text="这是我的最终回答",
            usage=TokenUsage(input_other=10, output=5),
        )

    async def text_chat_stream(self, **kwargs):
        response = await self.text_chat(**kwargs)
        response.is_chunk = True
        yield response
        response.is_chunk = False
        yield response


class MockToolExecutor:
    """模拟工具执行器"""

    @classmethod
    def execute(cls, tool, run_context, **tool_args):
        async def generator():
            # 模拟工具返回结果，使用正确的类型
            from mcp.types import CallToolResult, TextContent

            result = CallToolResult(
                content=[TextContent(type="text", text="工具执行结果")]
            )
            yield result

        return generator()


class MockHooks(BaseAgentRunHooks):
    """模拟钩子函数"""

    def __init__(self):
        self.agent_begin_called = False
        self.agent_done_called = False
        self.tool_start_called = False
        self.tool_end_called = False

    async def on_agent_begin(self, run_context):
        self.agent_begin_called = True

    async def on_tool_start(self, run_context, tool, tool_args):
        self.tool_start_called = True

    async def on_tool_end(self, run_context, tool, tool_args, tool_result):
        self.tool_end_called = True

    async def on_agent_done(self, run_context, llm_response):
        self.agent_done_called = True


@pytest.fixture
def mock_provider():
    return MockProvider()


@pytest.fixture
def mock_tool_executor():
    return MockToolExecutor()


@pytest.fixture
def mock_hooks():
    return MockHooks()


@pytest.fixture
def tool_set():
    """创建测试用的工具集"""
    tool = FunctionTool(
        name="test_tool",
        description="测试工具",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        handler=AsyncMock(),
    )
    return ToolSet(tools=[tool])


@pytest.fixture
def provider_request(tool_set):
    """创建测试用的ProviderRequest"""
    return ProviderRequest(prompt="请帮我查询信息", func_tool=tool_set, contexts=[])


@pytest.fixture
def runner():
    """创建ToolLoopAgentRunner实例"""
    return ToolLoopAgentRunner()


@pytest.mark.asyncio
async def test_max_step_limit_functionality(
    runner, mock_provider, provider_request, mock_tool_executor, mock_hooks
):
    """测试最大步数限制功能"""

    # 设置模拟provider，让它总是返回工具调用
    mock_provider.should_call_tools = True
    mock_provider.max_calls_before_normal_response = (
        100  # 设置一个很大的值，确保不会自然结束
    )

    # 初始化runner
    await runner.reset(
        provider=mock_provider,
        request=provider_request,
        run_context=ContextWrapper(context=None),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    # 设置较小的最大步数来测试限制功能
    max_steps = 3

    # 收集所有响应
    responses = []
    async for response in runner.step_until_done(max_steps):
        responses.append(response)

    # 验证结果
    assert runner.done(), "代理应该在达到最大步数后完成"

    # 验证工具被禁用（这是最重要的验证点）
    assert runner.req.func_tool is None, "达到最大步数后工具应该被禁用"

    # 验证有最终响应
    final_responses = [r for r in responses if r.type == "llm_result"]
    assert len(final_responses) > 0, "应该有最终的LLM响应"

    # 验证最后一条消息是assistant的最终回答
    last_message = runner.run_context.messages[-1]
    assert last_message.role == "assistant", "最后一条消息应该是assistant的最终回答"


@pytest.mark.asyncio
async def test_normal_completion_without_max_step(
    runner, mock_provider, provider_request, mock_tool_executor, mock_hooks
):
    """测试正常完成（不触发最大步数限制）"""

    # 设置模拟provider，让它在第2次调用时返回正常响应
    mock_provider.should_call_tools = True
    mock_provider.max_calls_before_normal_response = 2

    # 初始化runner
    await runner.reset(
        provider=mock_provider,
        request=provider_request,
        run_context=ContextWrapper(context=None),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    # 设置足够大的最大步数
    max_steps = 10

    # 收集所有响应
    responses = []
    async for response in runner.step_until_done(max_steps):
        responses.append(response)

    # 验证结果
    assert runner.done(), "代理应该正常完成"

    # 验证没有触发最大步数限制 - 通过检查provider调用次数
    # mock_provider在第2次调用后返回正常响应，所以不应该达到max_steps(10)
    assert mock_provider.call_count < max_steps, (
        f"正常完成时调用次数({mock_provider.call_count})应该小于最大步数({max_steps})"
    )

    # 验证没有最大步数警告消息（注意：实际注入的是user角色的消息）
    user_messages = [m for m in runner.run_context.messages if m.role == "user"]
    max_step_messages = [
        m for m in user_messages if "工具调用次数已达到上限" in m.content
    ]
    assert len(max_step_messages) == 0, "正常完成时不应该有步数限制消息"

    # 验证工具仍然可用（没有被禁用）
    assert runner.req.func_tool is not None, "正常完成时工具不应该被禁用"


@pytest.mark.asyncio
async def test_max_step_with_streaming(
    runner, mock_provider, provider_request, mock_tool_executor, mock_hooks
):
    """测试流式响应下的最大步数限制"""

    # 设置模拟provider
    mock_provider.should_call_tools = True
    mock_provider.max_calls_before_normal_response = 100

    # 初始化runner，启用流式响应
    await runner.reset(
        provider=mock_provider,
        request=provider_request,
        run_context=ContextWrapper(context=None),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=True,
    )

    # 设置较小的最大步数
    max_steps = 2

    # 收集所有响应
    responses = []
    async for response in runner.step_until_done(max_steps):
        responses.append(response)

    # 验证结果
    assert runner.done(), "代理应该在达到最大步数后完成"

    # 验证有流式响应
    streaming_responses = [r for r in responses if r.type == "streaming_delta"]
    assert len(streaming_responses) > 0, "应该有流式响应"

    # 验证工具被禁用
    assert runner.req.func_tool is None, "达到最大步数后工具应该被禁用"

    # 验证最后一条消息是assistant的最终回答
    last_message = runner.run_context.messages[-1]
    assert last_message.role == "assistant", "最后一条消息应该是assistant的最终回答"


@pytest.mark.asyncio
async def test_hooks_called_with_max_step(
    runner, mock_provider, provider_request, mock_tool_executor, mock_hooks
):
    """测试达到最大步数时钩子函数是否被正确调用"""

    # 设置模拟provider
    mock_provider.should_call_tools = True
    mock_provider.max_calls_before_normal_response = 100

    # 初始化runner
    await runner.reset(
        provider=mock_provider,
        request=provider_request,
        run_context=ContextWrapper(context=None),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    # 设置较小的最大步数
    max_steps = 2

    # 执行步骤
    async for response in runner.step_until_done(max_steps):
        pass

    # 验证钩子函数被调用
    assert mock_hooks.agent_begin_called, "on_agent_begin应该被调用"
    assert mock_hooks.agent_done_called, "on_agent_done应该被调用"
    assert mock_hooks.tool_start_called, "on_tool_start应该被调用"
    assert mock_hooks.tool_end_called, "on_tool_end应该被调用"


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])
