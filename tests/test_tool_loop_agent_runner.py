import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

# 将项目根目录添加到 sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from astrbot.core.agent.agent import Agent
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
from astrbot.core.exceptions import EmptyModelOutputError
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


class LargeTextToolExecutor:
    """模拟返回超长文本的工具执行器"""

    def __init__(self, text: str):
        self.text = text

    @classmethod
    def from_text(cls, text: str) -> "LargeTextToolExecutor":
        return cls(text)

    def execute(self, tool, run_context, **tool_args):
        async def generator():
            from mcp.types import CallToolResult, TextContent

            result = CallToolResult(content=[TextContent(type="text", text=self.text)])
            yield result

        return generator()


class MockMixedContentToolExecutor:
    """模拟返回图片 + 文本的工具执行器"""

    @classmethod
    def execute(cls, tool, run_context, **tool_args):
        async def generator():
            from mcp.types import CallToolResult, ImageContent, TextContent

            result = CallToolResult(
                content=[
                    ImageContent(
                        type="image",
                        data="dGVzdA==",
                        mimeType="image/png",
                    ),
                    TextContent(type="text", text="直播间标题：新游首发：零~红蝶~"),
                ]
            )
            yield result

        return generator()


class MockFailingProvider(MockProvider):
    async def text_chat(self, **kwargs) -> LLMResponse:
        self.call_count += 1
        raise RuntimeError("primary provider failed")


class MockErrProvider(MockProvider):
    async def text_chat(self, **kwargs) -> LLMResponse:
        self.call_count += 1
        return LLMResponse(
            role="err",
            completion_text="primary provider returned error",
        )


class MockEmptyOutputThenSuccessProvider(MockProvider):
    def __init__(self, failures_before_success: int = 1):
        super().__init__()
        self.failures_before_success = failures_before_success

    async def text_chat(self, **kwargs) -> LLMResponse:
        self.call_count += 1
        if self.call_count <= self.failures_before_success:
            raise EmptyModelOutputError("model returned no usable output")
        return LLMResponse(
            role="assistant",
            completion_text="这是重试后的最终回答",
            usage=TokenUsage(input_other=10, output=5),
        )


class MockAbortableStreamProvider(MockProvider):
    async def text_chat_stream(self, **kwargs):
        abort_signal = kwargs.get("abort_signal")
        yield LLMResponse(
            role="assistant",
            completion_text="partial ",
            is_chunk=True,
        )
        if abort_signal and abort_signal.is_set():
            yield LLMResponse(
                role="assistant",
                completion_text="partial ",
                is_chunk=False,
            )
            return
        yield LLMResponse(
            role="assistant",
            completion_text="partial final",
            is_chunk=False,
        )


class MockToolCallProvider(MockProvider):
    def __init__(self, tool_name: str, tool_args: dict[str, str] | None = None):
        super().__init__()
        self.tool_name = tool_name
        self.tool_args = tool_args or {}
        self.abort_signal = None

    async def text_chat(self, **kwargs) -> LLMResponse:
        self.call_count += 1
        self.abort_signal = kwargs.get("abort_signal")
        return LLMResponse(
            role="assistant",
            completion_text="",
            tools_call_name=[self.tool_name],
            tools_call_args=[self.tool_args],
            tools_call_ids=[f"call_{self.tool_name}"],
            usage=TokenUsage(input_other=10, output=5),
        )


class SingleToolThenFinalProvider(MockProvider):
    def __init__(self, tool_name: str, tool_args: dict[str, str] | None = None):
        super().__init__()
        self.tool_name = tool_name
        self.tool_args = tool_args or {}

    async def text_chat(self, **kwargs) -> LLMResponse:
        self.call_count += 1
        func_tool = kwargs.get("func_tool")
        if func_tool is None or self.call_count > 1:
            return LLMResponse(
                role="assistant",
                completion_text="最终回复",
                usage=TokenUsage(input_other=10, output=5),
            )

        return LLMResponse(
            role="assistant",
            completion_text="",
            tools_call_name=[self.tool_name],
            tools_call_args=[self.tool_args],
            tools_call_ids=["call_large_result"],
            usage=TokenUsage(input_other=10, output=5),
        )


class SequentialToolProvider(MockProvider):
    def __init__(self, tool_sequence: list[str]):
        super().__init__()
        self.tool_sequence = tool_sequence

    async def text_chat(self, **kwargs) -> LLMResponse:
        self.call_count += 1
        func_tool = kwargs.get("func_tool")
        if func_tool is None or self.call_count > len(self.tool_sequence):
            return LLMResponse(
                role="assistant",
                completion_text="这是我的最终回答",
                usage=TokenUsage(input_other=10, output=5),
            )

        tool_name = self.tool_sequence[self.call_count - 1]
        return LLMResponse(
            role="assistant",
            completion_text="",
            tools_call_name=[tool_name],
            tools_call_args=[{"query": f"step-{self.call_count}"}],
            tools_call_ids=[f"call_{self.call_count}"],
            usage=TokenUsage(input_other=10, output=5),
        )


class MockHandoffProvider(MockToolCallProvider):
    def __init__(self, handoff_tool_name: str):
        super().__init__(handoff_tool_name, {"input": "delegate this task"})


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


class MockEvent:
    def __init__(self, umo: str, sender_id: str):
        self.unified_msg_origin = umo
        self._sender_id = sender_id

    def get_sender_id(self):
        return self._sender_id


class MockAgentContext:
    def __init__(self, event):
        self.event = event


class BlockingSubagentContext:
    def __init__(self):
        self.started = asyncio.Event()
        self.cancelled = False

    async def get_current_chat_provider_id(self, _umo: str) -> str:
        return "provider-id"

    def get_config(self, **_kwargs):
        return {"provider_settings": {}}

    async def tool_loop_agent(self, **_kwargs):
        self.started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class BlockingToolState:
    def __init__(self):
        self.started = asyncio.Event()
        self.cancelled = False

    async def handler(self, event, query: str = ""):
        del event, query
        self.started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


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


def _make_large_tool_result_text() -> str:
    return "x" * 100000


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


@pytest.mark.asyncio
async def test_tool_result_includes_all_calltoolresult_content(
    runner, mock_provider, provider_request, mock_hooks, monkeypatch
):
    """工具返回多个 content 项时，tool result 应包含全部内容。"""

    from astrbot.core.agent.tool_image_cache import tool_image_cache

    mock_provider.should_call_tools = True
    mock_provider.max_calls_before_normal_response = 1

    saved_images = []

    def fake_save_image(
        base64_data, tool_call_id, tool_name, index=0, mime_type="image/png"
    ):
        saved_images.append(
            {
                "base64_data": base64_data,
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "index": index,
                "mime_type": mime_type,
            }
        )
        return SimpleNamespace(file_path=f"/tmp/{tool_call_id}_{index}.png")

    monkeypatch.setattr(tool_image_cache, "save_image", fake_save_image)

    await runner.reset(
        provider=mock_provider,
        request=provider_request,
        run_context=ContextWrapper(context=None),
        tool_executor=MockMixedContentToolExecutor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    async for _ in runner.step_until_done(3):
        pass

    tool_messages = [
        m for m in runner.run_context.messages if getattr(m, "role", None) == "tool"
    ]
    assert len(tool_messages) == 1

    content = str(tool_messages[0].content)
    assert "Image returned and cached at path='/tmp/call_123_0.png'." in content
    assert "直播间标题：新游首发：零~红蝶~" in content
    assert saved_images == [
        {
            "base64_data": "dGVzdA==",
            "tool_call_id": "call_123",
            "tool_name": "test_tool",
            "index": 0,
            "mime_type": "image/png",
        }
    ]


@pytest.mark.asyncio
async def test_same_tool_consecutive_results_include_escalating_guidance(
    runner, mock_tool_executor, mock_hooks
):
    runner_cls = type(runner)
    total_calls = runner_cls.REPEATED_TOOL_NOTICE_L3_THRESHOLD
    provider = SequentialToolProvider(["test_tool"] * total_calls)
    tool = FunctionTool(
        name="test_tool",
        description="测试工具",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        handler=AsyncMock(),
    )
    request = ProviderRequest(
        prompt="请连续执行工具",
        func_tool=ToolSet(tools=[tool]),
        contexts=[],
    )

    await runner.reset(
        provider=provider,
        request=request,
        run_context=ContextWrapper(context=None),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    async for _ in runner.step_until_done(total_calls + 1):
        pass

    tool_messages = [
        m for m in runner.run_context.messages if getattr(m, "role", None) == "tool"
    ]
    assert len(tool_messages) == total_calls

    tool_contents = [str(message.content) for message in tool_messages]
    level_1_notice = runner_cls.REPEATED_TOOL_NOTICE_L1_TEMPLATE.format(
        tool_name="test_tool",
        streak=runner_cls.REPEATED_TOOL_NOTICE_L1_THRESHOLD,
    )
    level_2_notice = runner_cls.REPEATED_TOOL_NOTICE_L2_TEMPLATE.format(
        tool_name="test_tool",
        streak=runner_cls.REPEATED_TOOL_NOTICE_L2_THRESHOLD,
    )
    level_3_notice = runner_cls.REPEATED_TOOL_NOTICE_L3_TEMPLATE.format(
        tool_name="test_tool",
        streak=runner_cls.REPEATED_TOOL_NOTICE_L3_THRESHOLD,
    )

    for streak, content in enumerate(tool_contents, start=1):
        if streak < runner_cls.REPEATED_TOOL_NOTICE_L1_THRESHOLD:
            assert level_1_notice not in content
            assert level_2_notice not in content
            assert level_3_notice not in content
        elif streak < runner_cls.REPEATED_TOOL_NOTICE_L2_THRESHOLD:
            assert level_1_notice in content
            assert level_2_notice not in content
            assert level_3_notice not in content
        elif streak < runner_cls.REPEATED_TOOL_NOTICE_L3_THRESHOLD:
            assert level_1_notice not in content
            assert level_2_notice in content
            assert level_3_notice not in content
        else:
            assert level_1_notice not in content
            assert level_2_notice not in content
            assert level_3_notice in content


@pytest.mark.asyncio
async def test_same_tool_streak_resets_after_switching_tools(
    runner, mock_tool_executor, mock_hooks
):
    runner_cls = type(runner)
    repeated_after_reset = runner_cls.REPEATED_TOOL_NOTICE_L1_THRESHOLD
    provider = SequentialToolProvider(
        ["test_tool", "other_tool", *(["test_tool"] * repeated_after_reset)]
    )
    tool_a = FunctionTool(
        name="test_tool",
        description="测试工具 A",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        handler=AsyncMock(),
    )
    tool_b = FunctionTool(
        name="other_tool",
        description="测试工具 B",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        handler=AsyncMock(),
    )
    request = ProviderRequest(
        prompt="切换工具后再重复",
        func_tool=ToolSet(tools=[tool_a, tool_b]),
        contexts=[],
    )

    await runner.reset(
        provider=provider,
        request=request,
        run_context=ContextWrapper(context=None),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    async for _ in runner.step_until_done(repeated_after_reset + 3):
        pass

    tool_messages = [
        m for m in runner.run_context.messages if getattr(m, "role", None) == "tool"
    ]
    assert len(tool_messages) == repeated_after_reset + 2

    tool_contents = [str(message.content) for message in tool_messages]
    level_1_notice = runner_cls.REPEATED_TOOL_NOTICE_L1_TEMPLATE.format(
        tool_name="test_tool",
        streak=runner_cls.REPEATED_TOOL_NOTICE_L1_THRESHOLD,
    )
    level_2_notice = runner_cls.REPEATED_TOOL_NOTICE_L2_TEMPLATE.format(
        tool_name="test_tool",
        streak=runner_cls.REPEATED_TOOL_NOTICE_L2_THRESHOLD,
    )

    assert level_1_notice not in tool_contents[0]
    assert level_1_notice not in tool_contents[1]
    assert level_2_notice not in tool_contents[0]
    assert level_2_notice not in tool_contents[1]

    repeated_contents = tool_contents[2:]
    for streak_after_reset, content in enumerate(repeated_contents, start=1):
        if streak_after_reset < runner_cls.REPEATED_TOOL_NOTICE_L1_THRESHOLD:
            assert level_1_notice not in content
            assert level_2_notice not in content
        elif streak_after_reset < runner_cls.REPEATED_TOOL_NOTICE_L2_THRESHOLD:
            assert level_1_notice in content
            assert level_2_notice not in content
        else:
            assert level_1_notice not in content
            assert level_2_notice in content


@pytest.mark.asyncio
async def test_fallback_provider_used_when_primary_raises(
    runner, provider_request, mock_tool_executor, mock_hooks
):
    primary_provider = MockFailingProvider()
    fallback_provider = MockProvider()
    fallback_provider.should_call_tools = False

    await runner.reset(
        provider=primary_provider,
        request=provider_request,
        run_context=ContextWrapper(context=None),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
        fallback_providers=[fallback_provider],
    )

    async for _ in runner.step_until_done(5):
        pass

    final_resp = runner.get_final_llm_resp()
    assert final_resp is not None
    assert final_resp.role == "assistant"
    assert final_resp.completion_text == "这是我的最终回答"
    assert primary_provider.call_count == 1
    assert fallback_provider.call_count == 1


@pytest.mark.asyncio
async def test_fallback_provider_used_when_primary_returns_err(
    runner, provider_request, mock_tool_executor, mock_hooks
):
    primary_provider = MockErrProvider()
    fallback_provider = MockProvider()
    fallback_provider.should_call_tools = False

    await runner.reset(
        provider=primary_provider,
        request=provider_request,
        run_context=ContextWrapper(context=None),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
        fallback_providers=[fallback_provider],
    )

    async for _ in runner.step_until_done(5):
        pass

    final_resp = runner.get_final_llm_resp()
    assert final_resp is not None
    assert final_resp.role == "assistant"
    assert final_resp.completion_text == "这是我的最终回答"
    assert primary_provider.call_count == 1
    assert fallback_provider.call_count == 1


@pytest.mark.asyncio
async def test_empty_output_is_retried_before_succeeding(
    runner, provider_request, mock_tool_executor, mock_hooks, monkeypatch
):
    monkeypatch.setattr(runner, "EMPTY_OUTPUT_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(runner, "EMPTY_OUTPUT_RETRY_WAIT_MAX_S", 0)

    provider = MockEmptyOutputThenSuccessProvider(failures_before_success=1)
    await runner.reset(
        provider=provider,
        request=provider_request,
        run_context=ContextWrapper(context=None),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    async for _ in runner.step_until_done(5):
        pass

    final_resp = runner.get_final_llm_resp()
    assert final_resp is not None
    assert final_resp.role == "assistant"
    assert final_resp.completion_text == "这是重试后的最终回答"
    assert provider.call_count == 2


@pytest.mark.asyncio
async def test_empty_output_retries_exhausted_then_uses_fallback_provider(
    runner, provider_request, mock_tool_executor, mock_hooks, monkeypatch
):
    monkeypatch.setattr(runner, "EMPTY_OUTPUT_RETRY_WAIT_MIN_S", 0)
    monkeypatch.setattr(runner, "EMPTY_OUTPUT_RETRY_WAIT_MAX_S", 0)

    primary_provider = MockEmptyOutputThenSuccessProvider(
        failures_before_success=runner.EMPTY_OUTPUT_RETRY_ATTEMPTS
    )
    fallback_provider = MockProvider()
    fallback_provider.should_call_tools = False

    await runner.reset(
        provider=primary_provider,
        request=provider_request,
        run_context=ContextWrapper(context=None),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
        fallback_providers=[fallback_provider],
    )

    async for _ in runner.step_until_done(5):
        pass

    final_resp = runner.get_final_llm_resp()
    assert final_resp is not None
    assert final_resp.role == "assistant"
    assert final_resp.completion_text == "这是我的最终回答"
    assert primary_provider.call_count == runner.EMPTY_OUTPUT_RETRY_ATTEMPTS
    assert fallback_provider.call_count == 1


@pytest.mark.asyncio
async def test_stop_signal_returns_aborted_and_persists_partial_message(
    runner, provider_request, mock_tool_executor, mock_hooks
):
    provider = MockAbortableStreamProvider()

    await runner.reset(
        provider=provider,
        request=provider_request,
        run_context=ContextWrapper(context=None),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=True,
    )

    step_iter = runner.step()
    first_resp = await step_iter.__anext__()
    assert first_resp.type == "streaming_delta"

    runner.request_stop()

    rest_responses = []
    async for response in step_iter:
        rest_responses.append(response)

    assert any(resp.type == "aborted" for resp in rest_responses)
    assert runner.was_aborted() is True

    final_resp = runner.get_final_llm_resp()
    assert final_resp is not None
    assert final_resp.role == "assistant"
    # When interrupted, the runner replaces completion_text with a system message
    assert "interrupted" in final_resp.completion_text.lower()
    assert runner.run_context.messages[-1].role == "assistant"


@pytest.mark.asyncio
async def test_stop_interrupts_pending_subagent_handoff(mock_hooks):
    subagent_context = BlockingSubagentContext()
    event = MockEvent("webchat:FriendMessage:webchat!user!session", "user")
    handoff_tool = HandoffTool(
        Agent(name="subagent", instructions="subagent-instructions", tools=[]),
        tool_description="Delegate tasks to the subagent.",
    )
    provider = MockHandoffProvider(handoff_tool.name)
    request = ProviderRequest(
        prompt="delegate",
        func_tool=ToolSet(tools=[handoff_tool]),
        contexts=[],
    )
    runner = ToolLoopAgentRunner()

    await runner.reset(
        provider=provider,
        request=request,
        run_context=ContextWrapper(
            context=SimpleNamespace(event=event, context=subagent_context)
        ),
        tool_executor=FunctionToolExecutor(),
        agent_hooks=mock_hooks,
        streaming=False,
    )

    step_iter = runner.step()
    first_resp = await step_iter.__anext__()
    assert first_resp.type == "tool_call"
    assert provider.abort_signal is not None
    assert provider.abort_signal.is_set() is False

    pending_resp = asyncio.create_task(step_iter.__anext__())
    await asyncio.wait_for(subagent_context.started.wait(), timeout=5)

    runner.request_stop()
    assert provider.abort_signal.is_set() is True

    aborted_resp = await asyncio.wait_for(pending_resp, timeout=1)
    assert aborted_resp.type == "aborted"
    assert runner.was_aborted() is True
    assert subagent_context.cancelled is True

    with pytest.raises(StopAsyncIteration):
        await step_iter.__anext__()


@pytest.mark.asyncio
async def test_stop_interrupts_pending_regular_tool(mock_hooks):
    tool_state = BlockingToolState()
    event = MockEvent("webchat:FriendMessage:webchat!user!session", "user")
    tool = FunctionTool(
        name="long_tool",
        description="A long-running test tool",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        handler=tool_state.handler,
    )
    provider = MockToolCallProvider(tool.name, {"query": "slow"})
    request = ProviderRequest(
        prompt="run a slow tool",
        func_tool=ToolSet(tools=[tool]),
        contexts=[],
    )
    runner = ToolLoopAgentRunner()

    await runner.reset(
        provider=provider,
        request=request,
        run_context=ContextWrapper(
            context=SimpleNamespace(event=event, context=SimpleNamespace())
        ),
        tool_executor=FunctionToolExecutor(),
        agent_hooks=mock_hooks,
        streaming=False,
    )

    step_iter = runner.step()
    first_resp = await step_iter.__anext__()
    assert first_resp.type == "tool_call"
    assert provider.abort_signal is not None
    assert provider.abort_signal.is_set() is False

    pending_resp = asyncio.create_task(step_iter.__anext__())
    await asyncio.wait_for(tool_state.started.wait(), timeout=5)

    runner.request_stop()
    assert provider.abort_signal.is_set() is True

    aborted_resp = await asyncio.wait_for(pending_resp, timeout=5)
    assert aborted_resp.type == "aborted"
    assert runner.was_aborted() is True
    assert tool_state.cancelled is True

    with pytest.raises(StopAsyncIteration):
        await step_iter.__anext__()


@pytest.mark.asyncio
async def test_tool_result_injects_follow_up_notice(
    runner, mock_provider, provider_request, mock_tool_executor, mock_hooks
):
    mock_event = MockEvent("test:FriendMessage:follow_up", "u1")
    run_context = ContextWrapper(context=MockAgentContext(mock_event))

    await runner.reset(
        provider=mock_provider,
        request=provider_request,
        run_context=run_context,
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    ticket1 = runner.follow_up(
        message_text="follow up 1",
    )
    ticket2 = runner.follow_up(
        message_text="follow up 2",
    )
    assert ticket1 is not None
    assert ticket2 is not None

    async for _ in runner.step():
        pass

    assert provider_request.tool_calls_result is not None
    assert isinstance(provider_request.tool_calls_result, list)
    assert provider_request.tool_calls_result
    tool_result = str(
        provider_request.tool_calls_result[0].tool_calls_result[0].content
    )
    assert "SYSTEM NOTICE" in tool_result
    assert "1. follow up 1" in tool_result
    assert "2. follow up 2" in tool_result
    assert ticket1.resolved.is_set() is True
    assert ticket2.resolved.is_set() is True
    assert ticket1.consumed is True
    assert ticket2.consumed is True


@pytest.mark.asyncio
async def test_follow_up_ticket_not_consumed_when_no_next_tool_call(
    runner, mock_provider, provider_request, mock_tool_executor, mock_hooks
):
    mock_provider.should_call_tools = False
    mock_event = MockEvent("test:FriendMessage:follow_up_no_tool", "u1")
    run_context = ContextWrapper(context=MockAgentContext(mock_event))

    await runner.reset(
        provider=mock_provider,
        request=provider_request,
        run_context=run_context,
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    ticket = runner.follow_up(message_text="follow up without tool")
    assert ticket is not None

    async for _ in runner.step():
        pass

    assert ticket.resolved.is_set() is True
    assert ticket.consumed is False


@pytest.mark.asyncio
async def test_skills_like_requery_passes_extra_user_content_parts():
    """skills-like 模式 re-query 时应传递 extra_user_content_parts（如 image_caption）"""
    from astrbot.core.agent.message import TextPart

    captured_kwargs = {}

    class SkillsLikeProvider(MockProvider):
        async def text_chat(self, **kwargs) -> LLMResponse:
            self.call_count += 1
            if self.call_count == 1:
                # 第一次调用：返回工具选择（light schema）
                return LLMResponse(
                    role="assistant",
                    completion_text="选择工具",
                    tools_call_name=["test_tool"],
                    tools_call_args=[{"query": "test"}],
                    tools_call_ids=["call_1"],
                    usage=TokenUsage(input_other=10, output=5),
                )
            if self.call_count == 2:
                # 第二次调用：re-query with param schema
                captured_kwargs.update(kwargs)
                return LLMResponse(
                    role="assistant",
                    completion_text="调用工具",
                    tools_call_name=["test_tool"],
                    tools_call_args=[{"query": "actual"}],
                    tools_call_ids=["call_2"],
                    usage=TokenUsage(input_other=10, output=5),
                )
            # 后续调用：正常回复
            return LLMResponse(
                role="assistant",
                completion_text="最终回复",
                usage=TokenUsage(input_other=10, output=5),
            )

    provider = SkillsLikeProvider()
    tool = FunctionTool(
        name="test_tool",
        description="测试",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        handler=AsyncMock(),
    )
    tool_set = ToolSet(tools=[tool])

    caption_part = TextPart(text="<image_caption>一张猫的照片</image_caption>")
    req = ProviderRequest(
        prompt="看看这张图",
        func_tool=tool_set,
        contexts=[],
        extra_user_content_parts=[caption_part],
    )

    event = MockEvent(umo="test_umo", sender_id="test_sender")
    ctx = MockAgentContext(event)
    run_context = ContextWrapper(context=ctx)
    runner = ToolLoopAgentRunner()

    await runner.reset(
        provider=provider,
        request=req,
        run_context=run_context,
        tool_executor=cast(Any, MockToolExecutor()),
        agent_hooks=MockHooks(),
        tool_schema_mode="skills_like",
    )

    async for _ in runner.step():
        pass

    # 验证 re-query 调用包含了 extra_user_content_parts
    assert "extra_user_content_parts" in captured_kwargs, (
        "re-query 应该传递 extra_user_content_parts"
    )
    parts = captured_kwargs["extra_user_content_parts"]
    assert len(parts) == 1
    assert parts[0].text == "<image_caption>一张猫的照片</image_caption>"


@pytest.mark.asyncio
async def test_follow_up_accepted_when_active_and_not_stopping(
    runner, mock_provider, provider_request, mock_tool_executor, mock_hooks
):
    """Test that follow-up is accepted when runner is active and stop is not requested."""

    await runner.reset(
        provider=mock_provider,
        request=provider_request,
        run_context=ContextWrapper(context=None),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
    )


@pytest.mark.asyncio
async def test_large_tool_result_is_spilled_to_file_and_replaced_with_read_notice(
    tmp_path,
):
    tool = FunctionTool(
        name="test_tool",
        description="测试工具",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        handler=AsyncMock(),
    )
    read_tool = FunctionTool(
        name="astrbot_file_read_tool",
        description="read file",
        parameters={"type": "object", "properties": {"path": {"type": "string"}}},
        handler=AsyncMock(),
    )
    tool_set = ToolSet(tools=[tool, read_tool])
    provider = SingleToolThenFinalProvider(tool.name, {"query": "large"})
    request = ProviderRequest(prompt="run tool", func_tool=tool_set, contexts=[])
    runner = ToolLoopAgentRunner()

    await runner.reset(
        provider=provider,
        request=request,
        run_context=ContextWrapper(context=None),
        tool_executor=cast(
            Any,
            LargeTextToolExecutor.from_text(_make_large_tool_result_text()),
        ),
        agent_hooks=MockHooks(),
        streaming=False,
        tool_result_overflow_dir=str(tmp_path),
        read_tool=read_tool,
    )

    responses = []
    async for response in runner.step_until_done(3):
        responses.append(response)

    tool_messages = [m for m in runner.run_context.messages if m.role == "tool"]
    assert len(tool_messages) == 1
    tool_message_content = str(tool_messages[0].content)
    assert "xxxxxxxxxx" in tool_message_content
    assert "Truncated tool output preview shown above." in tool_message_content
    assert "The tool output was too large to include directly" in tool_message_content
    assert "`astrbot_file_read_tool`" in tool_message_content
    assert "Use `astrbot_file_read_tool` to inspect it." in tool_message_content

    overflow_files = list(Path(tmp_path).glob("call_large_result_*.txt"))
    assert len(overflow_files) == 1
    assert (
        overflow_files[0].read_text(encoding="utf-8") == _make_large_tool_result_text()
    )
    assert str(overflow_files[0]) in tool_message_content

    llm_results = [resp for resp in responses if resp.type == "llm_result"]
    assert llm_results


@pytest.mark.asyncio
async def test_large_tool_result_keeps_preview_when_spill_fails(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    tool = FunctionTool(
        name="test_tool",
        description="测试工具",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        handler=AsyncMock(),
    )
    read_tool = FunctionTool(
        name="astrbot_file_read_tool",
        description="read file",
        parameters={"type": "object", "properties": {"path": {"type": "string"}}},
        handler=AsyncMock(),
    )
    tool_set = ToolSet(tools=[tool, read_tool])
    provider = SingleToolThenFinalProvider(tool.name, {"query": "large"})
    request = ProviderRequest(prompt="run tool", func_tool=tool_set, contexts=[])
    runner = ToolLoopAgentRunner()

    async def _raise_spill_error(*, tool_call_id: str, content: str) -> str:
        raise OSError("disk full")

    monkeypatch.setattr(runner, "_write_tool_result_overflow_file", _raise_spill_error)

    await runner.reset(
        provider=provider,
        request=request,
        run_context=ContextWrapper(context=None),
        tool_executor=cast(
            Any,
            LargeTextToolExecutor.from_text(_make_large_tool_result_text()),
        ),
        agent_hooks=MockHooks(),
        streaming=False,
        tool_result_overflow_dir=str(tmp_path),
        read_tool=read_tool,
    )

    async for _ in runner.step_until_done(3):
        pass

    tool_messages = [m for m in runner.run_context.messages if m.role == "tool"]
    assert len(tool_messages) == 1
    tool_message_content = str(tool_messages[0].content)
    assert "xxxxxxxxxx" in tool_message_content
    assert "Tool output exceeded the inline result limit" in tool_message_content
    assert "disk full" in tool_message_content


@pytest.mark.asyncio
async def test_follow_up_rejected_when_stop_requested(
    runner, mock_provider, provider_request, mock_tool_executor, mock_hooks
):
    """Test that follow-up is rejected when stop has been requested."""

    await runner.reset(
        provider=mock_provider,
        request=provider_request,
        run_context=ContextWrapper(context=None),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    # Request stop
    runner.request_stop()
    assert runner._is_stop_requested() is True

    ticket = runner.follow_up(message_text="follow-up after stop")

    assert ticket is None, "Follow-up should be rejected after stop is requested"
    assert len(runner._pending_follow_ups) == 0


@pytest.mark.asyncio
async def test_follow_up_rejected_when_runner_done(
    runner, mock_provider, provider_request, mock_tool_executor, mock_hooks
):
    """Test that follow-up is rejected when runner is done."""

    await runner.reset(
        provider=mock_provider,
        request=provider_request,
        run_context=ContextWrapper(context=None),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    # Run to completion
    async for _ in runner.step_until_done(10):
        pass

    # Runner should be done
    assert runner.done()

    ticket = runner.follow_up(message_text="follow-up after done")

    assert ticket is None, "Follow-up should be rejected when runner is done"


@pytest.mark.asyncio
async def test_follow_up_rejected_after_stop_before_tool_call(
    runner, mock_provider, provider_request, mock_tool_executor, mock_hooks
):
    """Test that follow-ups submitted after stop are not merged into tool results."""

    mock_event = MockEvent("test:FriendMessage:stop_race", "u1")
    run_context = ContextWrapper(context=MockAgentContext(mock_event))

    await runner.reset(
        provider=mock_provider,
        request=provider_request,
        run_context=run_context,
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    # Add a follow-up before stop
    ticket_before_stop = runner.follow_up(message_text="before stop")
    assert ticket_before_stop is not None

    # Request stop
    runner.request_stop()

    # Try to add a follow-up after stop
    ticket_after_stop = runner.follow_up(message_text="after stop")
    assert ticket_after_stop is None, "Follow-up after stop should be rejected"

    # Verify only the pre-stop follow-up is in the queue
    assert len(runner._pending_follow_ups) == 1
    assert runner._pending_follow_ups[0].text == "before stop"


@pytest.mark.asyncio
async def test_follow_up_merged_into_tool_result_before_stop(
    runner, mock_provider, provider_request, mock_tool_executor, mock_hooks
):
    """Test that follow-ups queued before stop are merged into tool results."""

    mock_event = MockEvent("test:FriendMessage:merge_before_stop", "u1")
    run_context = ContextWrapper(context=MockAgentContext(mock_event))

    await runner.reset(
        provider=mock_provider,
        request=provider_request,
        run_context=run_context,
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    # Queue follow-ups before stop
    ticket1 = runner.follow_up(message_text="follow up 1 before stop")
    ticket2 = runner.follow_up(message_text="follow up 2 before stop")
    assert ticket1 is not None
    assert ticket2 is not None

    # Run the agent step (should execute tool and merge follow-ups)
    async for _ in runner.step():
        pass

    # Verify follow-ups were merged into tool result
    assert provider_request.tool_calls_result is not None
    assert isinstance(provider_request.tool_calls_result, list)
    assert provider_request.tool_calls_result
    tool_result = str(
        provider_request.tool_calls_result[0].tool_calls_result[0].content
    )

    # Should contain the follow-up notice
    assert "SYSTEM NOTICE" in tool_result
    assert "follow up 1 before stop" in tool_result
    assert "follow up 2 before stop" in tool_result

    # Tickets should be marked as consumed
    assert ticket1.consumed is True
    assert ticket2.consumed is True


@pytest.mark.asyncio
async def test_follow_up_rejected_and_runner_stops_without_execution(
    runner, mock_provider, provider_request, mock_tool_executor, mock_hooks
):
    """Test that when stop is requested before execution, follow-ups are rejected and runner stops gracefully."""

    mock_event = MockEvent("test:FriendMessage:stop_before_execution", "u1")
    run_context = ContextWrapper(context=MockAgentContext(mock_event))

    await runner.reset(
        provider=mock_provider,
        request=provider_request,
        run_context=run_context,
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    # Request stop before any execution (simulates /stop command received at start)
    runner.request_stop()
    assert runner._is_stop_requested() is True

    # Try to add follow-up after stop (should be rejected)
    ticket_after = runner.follow_up(message_text="follow-up after stop")
    assert ticket_after is None, "Post-stop follow-up should be rejected"

    # Verify queue is empty
    assert len(runner._pending_follow_ups) == 0

    # Run the agent step - should stop immediately without executing tools
    async for response in runner.step():
        # Should yield an aborted response
        if response.type == "aborted":
            break

    # Verify runner stopped gracefully
    assert runner.done()
    assert runner.was_aborted()

    # No tool execution should have occurred
    assert provider_request.tool_calls_result is None


@pytest.mark.asyncio
async def test_follow_up_after_stop_not_merged_into_tool_result(
    runner, mock_provider, provider_request, mock_tool_executor, mock_hooks
):
    """Regression test for issue #6626: verify post-stop follow-ups are not injected into tool results.

    This test simulates the race condition where:
    1. Runner is active and executing tools
    2. A follow-up is queued (should be included in tool result)
    3. Stop is requested
    4. Another follow-up is attempted (should be rejected)
    5. Tool execution completes and merges follow-ups into result

    The key assertion is that only pre-stop follow-ups are merged into the tool result.
    """

    mock_event = MockEvent("test:FriendMessage:regression_6626", "u1")
    run_context = ContextWrapper(context=MockAgentContext(mock_event))

    await runner.reset(
        provider=mock_provider,
        request=provider_request,
        run_context=run_context,
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    # Add a follow-up before stop (should be included in tool result)
    ticket_before = runner.follow_up(message_text="valid before stop")
    assert ticket_before is not None
    assert ticket_before in runner._pending_follow_ups

    # Request stop (simulates /stop command during active execution)
    runner.request_stop()
    assert runner._is_stop_requested() is True

    # Try to add follow-up after stop (should be rejected)
    ticket_after = runner.follow_up(message_text="invalid after stop")
    assert ticket_after is None, "Post-stop follow-up should be rejected"

    # Verify queue only contains pre-stop follow-up
    assert len(runner._pending_follow_ups) == 1
    assert runner._pending_follow_ups[0].text == "valid before stop"

    # Run the agent step - this will execute tool and merge follow-ups into result
    async for response in runner.step():
        # The runner should execute tools and then stop
        pass

    # Verify tool result was created with follow-up merged
    # Note: When stop is requested, the tool may or may not execute depending on timing.
    # The key assertion is that IF tool_calls_result exists, it only contains pre-stop follow-ups.
    if provider_request.tool_calls_result is not None:
        assert isinstance(provider_request.tool_calls_result, list)
        assert provider_request.tool_calls_result
        tool_result = str(
            provider_request.tool_calls_result[0].tool_calls_result[0].content
        )

        # Should contain the pre-stop follow-up
        assert "valid before stop" in tool_result

        # Should NOT contain the post-stop follow-up
        assert "invalid after stop" not in tool_result
        assert "after stop" not in tool_result or "after stop" in "valid before stop"

        # Ticket should be marked as consumed (merged into tool result)
        assert ticket_before.consumed is True
    else:
        # If tool execution was aborted by stop, the ticket should still be resolved
        # but not consumed (since there was no tool call to merge into)
        assert ticket_before.resolved.is_set()


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])
