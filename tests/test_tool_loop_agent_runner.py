import asyncio
import copy
import os
import sys
from types import SimpleNamespace
from typing import Any, Callable, cast
from unittest.mock import AsyncMock

import pytest

# 将项目根目录添加到 sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from astrbot.core.agent.agent import Agent
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.message import ImageURLPart, Message, TextPart
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runners.tool_loop_agent_runner import (
    PostToolCompactionConfig,
    PostToolCompactionController,
    ToolLoopAgentRunner,
)
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

    async def text_chat(self, **kwargs) -> LLMResponse:  # type: ignore[override]
        self.call_count += 1

        # 检查工具是否被禁用
        func_tool = kwargs.get("func_tool")

        # 如果工具被禁用或超过最大调用次数,返回正常响应
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

    async def text_chat_stream(self, **kwargs) -> AsyncGenerator[LLMResponse, None]:  # type: ignore[override]
        response = await self.text_chat(**kwargs)
        response.is_chunk = True
        yield response
        response.is_chunk = False
        yield response


class MockToolExecutor:
    """模拟工具执行器"""

    @classmethod
    async def execute(cls, tool, run_context, **tool_args):
        # 模拟工具返回结果,使用正确的类型
        from mcp.types import CallToolResult, TextContent

        result = CallToolResult(
            content=[TextContent(type="text", text="工具执行结果")]
        )
        yield result


class MultiYieldToolExecutor:
    @classmethod
    def execute(cls, tool, run_context, **tool_args):
        async def generator():
            from mcp.types import CallToolResult, TextContent

            yield CallToolResult(
                content=[TextContent(type="text", text="first partial result")]
            )
            yield CallToolResult(
                content=[TextContent(type="text", text="second partial result")]
            )

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
    async def execute(cls, tool, run_context, **tool_args):
        from mcp.types import CallToolResult, ImageContent, TextContent

        result = CallToolResult(
            content=[
                ImageContent(
                    type="image",
                    data="dGVzdA==",
                    mimeType="image/png",
                ),
                TextContent(type="text", text="直播间标题:新游首发:零~红蝶~"),
            ]
        )
        yield result


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


class CapturingProvider(MockProvider):
    def __init__(self, modalities: list[str]):
        super().__init__()
        self.provider_config["modalities"] = modalities
        self.received_contexts = []
        self.received_func_tools = []
        self.should_call_tools = False

    async def text_chat(self, **kwargs) -> LLMResponse:
        self.call_count += 1
        self.received_contexts.append(kwargs.get("contexts"))
        self.received_func_tools.append(kwargs.get("func_tool"))
        return LLMResponse(
            role="assistant",
            completion_text="final",
            usage=TokenUsage(input_other=10, output=5),
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


class PreToolTextThenFinalProvider(MockProvider):
    def __init__(
        self, pre_tool_text: str, reasoning_content: str | None = None
    ):
        super().__init__()
        self.pre_tool_text = pre_tool_text
        self.reasoning_content = reasoning_content

    async def text_chat(self, **kwargs) -> LLMResponse:
        self.call_count += 1
        func_tool = kwargs.get("func_tool")
        if func_tool is None or self.call_count > 1:
            return LLMResponse(
                role="assistant",
                completion_text="final answer",
                usage=TokenUsage(input_other=10, output=5),
            )

        return LLMResponse(
            role="assistant",
            completion_text=self.pre_tool_text,
            reasoning_content=self.reasoning_content,
            tools_call_name=["test_tool"],
            tools_call_args=[{"query": "test"}],
            tools_call_ids=["call_pre_tool"],
            usage=TokenUsage(input_other=10, output=5),
        )


class SequentialToolProvider(MockProvider):
    def __init__(
        self,
        tool_sequence: list[str],
        tool_args_factory: Callable[[int], dict[str, Any]] | None = None,
    ):
        super().__init__()
        self.tool_sequence = tool_sequence
        self.tool_args_factory = tool_args_factory

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
        tool_args = (
            self.tool_args_factory(self.call_count)
            if self.tool_args_factory is not None
            else {"query": f"step-{self.call_count}"}
        )
        return LLMResponse(
            role="assistant",
            completion_text="",
            tools_call_name=[tool_name],
            tools_call_args=[tool_args],
            tools_call_ids=[f"call_{self.call_count}"],
            usage=TokenUsage(input_other=10, output=5),
        )


class MockHandoffProvider(MockToolCallProvider):
    def __init__(self, handoff_tool_name: str):
        super().__init__(handoff_tool_name, {"input": "delegate this task"})


class SilentHandoffThenFinalProvider(MockProvider):
    def __init__(self, handoff_tool_name: str, include_mode: bool = True):
        super().__init__()
        self.handoff_tool_name = handoff_tool_name
        self.include_mode = include_mode
        self.received_contexts = []

    async def text_chat(self, **kwargs) -> LLMResponse:
        self.call_count += 1
        self.received_contexts.append(copy.deepcopy(kwargs.get("contexts")))
        if self.call_count == 1:
            tool_args = {"input": "delegate this task"}
            if self.include_mode:
                tool_args["mode"] = "silent"
            return LLMResponse(
                role="assistant",
                completion_text="",
                tools_call_name=[self.handoff_tool_name],
                tools_call_args=[tool_args],
                tools_call_ids=["call_silent_handoff"],
                usage=TokenUsage(input_other=10, output=5),
            )

        return LLMResponse(
            role="assistant",
            completion_text="main final answer",
            usage=TokenUsage(input_other=10, output=5),
        )


class ImmediateSubagentContext:
    def __init__(self):
        self.tool_loop_agent_calls = []

    async def get_current_chat_provider_id(self, _umo: str) -> str:
        return "provider-id"

    def get_config(self, **_kwargs):
        return {"provider_settings": {}}

    async def tool_loop_agent(self, **kwargs):
        self.tool_loop_agent_calls.append(kwargs)
        return LLMResponse(role="assistant", completion_text="subagent private result")


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

    def get_llm_tool_manager(self):
        from unittest.mock import MagicMock

        return MagicMock()

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

    # 设置模拟provider,让它总是返回工具调用
    mock_provider.should_call_tools = True
    mock_provider.max_calls_before_normal_response = (
        100  # 设置一个很大的值,确保不会自然结束
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

    # 验证工具被禁用(这是最重要的验证点)
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
    """测试正常完成(不触发最大步数限制)"""

    # 设置模拟provider,让它在第2次调用时返回正常响应
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
    # mock_provider在第2次调用后返回正常响应,所以不应该达到max_steps(10)
    assert mock_provider.call_count < max_steps, (
        f"正常完成时调用次数({mock_provider.call_count})应该小于最大步数({max_steps})"
    )

    # 验证没有最大步数警告消息(注意:实际注入的是user角色的消息)
    user_messages = [m for m in runner.run_context.messages if m.role == "user"]
    max_step_messages = [
        m for m in user_messages if "工具调用次数已达到上限" in m.content
    ]
    assert len(max_step_messages) == 0, "正常完成时不应该有步数限制消息"

    # 验证工具仍然可用(没有被禁用)
    assert runner.req.func_tool is not None, "正常完成时工具不应该被禁用"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "pre_tool_text",
    ["*No response*", "I will check this first."],
)
async def test_tool_call_turn_does_not_emit_pre_tool_llm_result(pre_tool_text: str):
    tool = FunctionTool(
        name="test_tool",
        description="test tool",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        handler=AsyncMock(),
    )
    provider = PreToolTextThenFinalProvider(pre_tool_text)
    request = ProviderRequest(
        prompt="run tool",
        func_tool=ToolSet(tools=[tool]),
        contexts=[],
    )
    runner = ToolLoopAgentRunner()

    await runner.reset(
        provider=provider,
        request=request,
        run_context=ContextWrapper(context=None),
        tool_executor=cast(Any, MockToolExecutor()),
        agent_hooks=MockHooks(),
        streaming=False,
    )

    responses = []
    async for response in runner.step_until_done(3):
        responses.append(response)

    llm_result_texts = [
        resp.data["chain"].get_plain_text(with_other_comps_mark=True)
        for resp in responses
        if resp.type == "llm_result"
    ]

    assert pre_tool_text not in llm_result_texts
    assert any(resp.type == "tool_call" for resp in responses)
    assert "final answer" in llm_result_texts


@pytest.mark.asyncio
async def test_tool_call_turn_still_emits_reasoning_content():
    tool = FunctionTool(
        name="test_tool",
        description="test tool",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        handler=AsyncMock(),
    )
    provider = PreToolTextThenFinalProvider(
        pre_tool_text="*No response*",
        reasoning_content="thinking...",
    )
    request = ProviderRequest(
        prompt="run tool",
        func_tool=ToolSet(tools=[tool]),
        contexts=[],
    )
    runner = ToolLoopAgentRunner()

    await runner.reset(
        provider=provider,
        request=request,
        run_context=ContextWrapper(context=None),
        tool_executor=cast(Any, MockToolExecutor()),
        agent_hooks=MockHooks(),
        streaming=False,
    )

    responses = []
    async for response in runner.step_until_done(3):
        responses.append(response)

    reasoning_texts = [
        resp.data["chain"].get_plain_text(with_other_comps_mark=True)
        for resp in responses
        if resp.type == "llm_result" and resp.data["chain"].type == "reasoning"
    ]
    llm_result_texts = [
        resp.data["chain"].get_plain_text(with_other_comps_mark=True)
        for resp in responses
        if resp.type == "llm_result"
    ]

    assert "thinking..." in reasoning_texts
    assert "*No response*" not in llm_result_texts


@pytest.mark.asyncio
async def test_max_step_with_streaming(
    runner, mock_provider, provider_request, mock_tool_executor, mock_hooks
):
    """测试流式响应下的最大步数限制"""

    # 设置模拟provider
    mock_provider.should_call_tools = True
    mock_provider.max_calls_before_normal_response = 100

    # 初始化runner,启用流式响应
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
    """工具返回多个 content 项时,tool result 应包含全部内容｡"""

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
    assert "直播间标题:新游首发:零~红蝶~" in content
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
async def test_async_generator_tool_results_share_one_tool_call_id(
    runner, mock_provider, provider_request, mock_hooks
):
    """Multiple streamed tool results should be merged into one provider result."""

    mock_provider.should_call_tools = True
    mock_provider.max_calls_before_normal_response = 1

    await runner.reset(
        provider=mock_provider,
        request=provider_request,
        run_context=ContextWrapper(context=None),
        tool_executor=MultiYieldToolExecutor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    async for _ in runner.step_until_done(3):
        pass

    tool_messages = [
        m for m in runner.run_context.messages if getattr(m, "role", None) == "tool"
    ]
    assert len(tool_messages) == 1
    assert tool_messages[0].tool_call_id == "call_123"

    content = str(tool_messages[0].content)
    assert "first partial result" in content
    assert "second partial result" in content
    assert content.index("first partial result") < content.index(
        "second partial result"
    )


@pytest.mark.asyncio
async def test_runner_replaces_runtime_image_context_before_provider_call(
    runner, provider_request, mock_hooks
):
    provider = CapturingProvider(modalities=["tool_use"])

    await runner.reset(
        provider=provider,
        request=provider_request,
        run_context=ContextWrapper(context=None),
        tool_executor=MockToolExecutor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    runner.run_context.messages.append(
        Message(
            role="user",
            content=[
                TextPart(text="Review this image"),
                ImageURLPart(
                    image_url=ImageURLPart.ImageURL(
                        url="data:image/png;base64,dGVzdA=="
                    )
                ),
            ],
        )
    )

    async for _ in runner.step_until_done(1):
        pass

    assert provider.received_contexts
    sent_context = provider.received_contexts[0]
    assert sent_context[-1]["content"] == [
        {"type": "text", "text": "Review this image"},
        {"type": "text", "text": "[Image]"},
    ]
    assert len(runner.run_context.messages[-2].content) == 2


@pytest.mark.asyncio
async def test_runner_builds_placeholder_for_unsupported_request_image(
    runner, mock_hooks, tool_set
):
    provider = CapturingProvider(modalities=["tool_use"])
    request = ProviderRequest(
        prompt="Describe it",
        image_urls=["/path/that/should/not/be/read.jpg"],
        func_tool=tool_set,
        contexts=[],
    )

    await runner.reset(
        provider=provider,
        request=request,
        run_context=ContextWrapper(context=None),
        tool_executor=MockToolExecutor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    async for _ in runner.step_until_done(1):
        pass

    sent_context = provider.received_contexts[0]
    assert sent_context[-1]["content"] == [
        {"type": "text", "text": "Describe it"},
        {"type": "text", "text": "[Image]"},
    ]


@pytest.mark.asyncio
async def test_runner_clears_tools_for_provider_without_tool_use(
    runner, provider_request, mock_hooks, mock_tool_executor
):
    provider = CapturingProvider(modalities=["text"])

    await runner.reset(
        provider=provider,
        request=provider_request,
        run_context=ContextWrapper(context=None),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    async for _ in runner.step_until_done(1):
        pass

    assert provider.received_func_tools == [None]


@pytest.mark.asyncio
async def test_same_tool_consecutive_results_include_escalating_guidance(
    runner, mock_tool_executor, mock_hooks
):
    runner_cls = type(runner)
    total_calls = runner_cls.REPEATED_TOOL_NOTICE_L3_THRESHOLD
    provider = SequentialToolProvider(
        ["test_tool"] * total_calls,
        tool_args_factory=lambda _: {"query": "same"},
    )
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
async def test_same_tool_consecutive_calls_with_different_args_do_not_trigger_guidance(
    runner, mock_tool_executor, mock_hooks
):
    runner_cls = type(runner)
    total_calls = runner_cls.REPEATED_TOOL_NOTICE_L3_THRESHOLD
    provider = SequentialToolProvider(["test_tool"] * total_calls)
    tool = FunctionTool(
        name="test_tool",
        description="娴嬭瘯宸ュ叿",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        handler=AsyncMock(),
    )
    request = ProviderRequest(
        prompt="run tool",
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
    for content in tool_contents:
        assert level_1_notice not in content
        assert level_2_notice not in content
        assert level_3_notice not in content


@pytest.mark.asyncio
async def test_same_tool_consecutive_calls_with_equivalent_args_trigger_guidance(
    runner, mock_tool_executor, mock_hooks
):
    runner_cls = type(runner)
    total_calls = runner_cls.REPEATED_TOOL_NOTICE_L3_THRESHOLD
    provider = SequentialToolProvider(
        ["test_tool"] * total_calls,
        tool_args_factory=lambda i: (
            {"a": 1, "b": 2} if i % 2 == 0 else {"b": 2, "a": 1}
        ),
    )
    tool = FunctionTool(
        name="test_tool",
        description="test tool",
        parameters={
            "type": "object",
            "properties": {
                "a": {"type": "integer"},
                "b": {"type": "integer"},
            },
            "required": ["a", "b"],
        },
        handler=AsyncMock(),
    )
    request = ProviderRequest(
        prompt="run tool",
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
        ["test_tool", "other_tool", *(["test_tool"] * repeated_after_reset)],
        tool_args_factory=lambda _: {"query": "same"},
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
async def test_repeated_shell_tool_results_do_not_include_guidance(
    runner, mock_tool_executor, mock_hooks
):
    runner_cls = type(runner)
    total_calls = runner_cls.REPEATED_TOOL_NOTICE_L3_THRESHOLD
    provider = SequentialToolProvider(["astrbot_execute_shell"] * total_calls)
    tool = FunctionTool(
        name="astrbot_execute_shell",
        description="Execute shell commands",
        parameters={"type": "object", "properties": {"command": {"type": "string"}}},
        handler=AsyncMock(),
    )
    request = ProviderRequest(
        prompt="Run several shell commands",
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
    assert all("SYSTEM NOTICE" not in str(message.content) for message in tool_messages)


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
async def test_silent_handoff_returns_result_to_main_agent_without_visible_tool_events(
    mock_hooks,
):
    subagent_context = ImmediateSubagentContext()
    event = MockEvent("webchat:FriendMessage:webchat!user!session", "user")
    handoff_tool = HandoffTool(
        Agent(name="subagent", instructions="subagent-instructions", tools=[]),
        tool_description="Delegate tasks to the subagent.",
    )
    provider = SilentHandoffThenFinalProvider(handoff_tool.name)
    request = ProviderRequest(
        prompt="delegate privately",
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

    responses = []
    async for response in runner.step_until_done(5):
        responses.append(response)

    assert subagent_context.tool_loop_agent_calls
    assert provider.call_count == 2
    assert runner.done() is True
    assert runner.get_final_llm_resp().completion_text == "main final answer"
    assert [response.type for response in responses] == ["llm_result"]

    tool_messages = [
        message
        for message in runner.run_context.messages
        if getattr(message, "role", None) == "tool"
    ]
    tool_call_messages = [
        message
        for message in runner.run_context.messages
        if getattr(message, "tool_calls", None)
    ]
    assert len(tool_messages) == 1
    assert tool_messages[0]._no_save is True
    assert len(tool_call_messages) == 1
    assert tool_call_messages[0]._no_save is True
    assert tool_messages[0].content == "subagent private result"
    assert provider.received_contexts[1][-1].content == "subagent private result"


@pytest.mark.asyncio
async def test_default_silent_handoff_mode_hides_tool_events_when_mode_omitted(
    mock_hooks,
):
    subagent_context = ImmediateSubagentContext()
    event = MockEvent("webchat:FriendMessage:webchat!user!session", "user")
    handoff_tool = HandoffTool(
        Agent(name="subagent", instructions="subagent-instructions", tools=[]),
        tool_description="Delegate tasks to the subagent.",
    )
    handoff_tool.default_handoff_mode = "silent"
    provider = SilentHandoffThenFinalProvider(handoff_tool.name, include_mode=False)
    request = ProviderRequest(
        prompt="delegate privately by default",
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

    responses = []
    async for response in runner.step_until_done(5):
        responses.append(response)

    assert provider.call_count == 2
    assert runner.get_final_llm_resp().completion_text == "main final answer"
    assert [response.type for response in responses] == ["llm_result"]
    assert any(
        getattr(message, "role", None) == "tool" and message._no_save
        for message in runner.run_context.messages
    )


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
async def test_compact_context_after_tool_call_enabled(
    runner, mock_provider, provider_request, mock_tool_executor, mock_hooks
):
    mock_provider.should_call_tools = True
    await runner.reset(
        provider=mock_provider,
        request=provider_request,
        run_context=ContextWrapper(context=None),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
        compact_context_after_tool_call=True,
    )

    runner.context_manager.process = AsyncMock(  # type: ignore[method-assign]
        side_effect=lambda messages, trusted_token_usage=0: messages,
    )

    async for _ in runner.step():
        pass

    assert runner.context_manager.process.await_count == 2


@pytest.mark.asyncio
async def test_compact_context_after_tool_call_disabled_by_default(
    runner, mock_provider, provider_request, mock_tool_executor, mock_hooks
):
    mock_provider.should_call_tools = True
    await runner.reset(
        provider=mock_provider,
        request=provider_request,
        run_context=ContextWrapper(context=None),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    runner.context_manager.process = AsyncMock(  # type: ignore[method-assign]
        side_effect=lambda messages, trusted_token_usage=0: messages,
    )

    async for _ in runner.step():
        pass

    assert runner.context_manager.process.await_count == 1


@pytest.mark.asyncio
async def test_compact_context_after_tool_call_honors_debounce(
    runner, mock_provider, provider_request, mock_tool_executor, mock_hooks
):
    mock_provider.should_call_tools = True
    mock_provider.provider_config["max_context_tokens"] = 100
    await runner.reset(
        provider=mock_provider,
        request=provider_request,
        run_context=ContextWrapper(context=None),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
        compact_context_after_tool_call=True,
        compact_context_soft_ratio=0.3,
        compact_context_hard_ratio=0.4,
        compact_context_debounce_seconds=3600,
    )

    runner.context_manager.token_counter = SimpleNamespace(
        count_tokens=lambda *_args, **_kwargs: 90
    )
    runner.context_manager.process = AsyncMock(  # type: ignore[method-assign]
        side_effect=lambda messages, trusted_token_usage=0: messages,
    )

    # step 1: pre-LLM compact + post-tool compact
    async for _ in runner.step():
        pass
    # step 2: pre-LLM compact + post-tool compact skipped by debounce
    async for _ in runner.step():
        pass

    assert runner.context_manager.process.await_count == 3


def test_post_tool_compaction_soft_zone_respects_min_delta(runner):
    runner.post_tool_compaction = PostToolCompactionConfig(
        enabled=True,
        soft_ratio=0.3,
        hard_ratio=0.9,
        min_delta_tokens=10,
        min_delta_turns=10,
        debounce_seconds=0,
    )
    runner.post_tool_compaction_controller = PostToolCompactionController(
        runner.post_tool_compaction
    )
    runner.context_config = SimpleNamespace(max_context_tokens=100)
    runner.run_context = SimpleNamespace(messages=[object(), object()])
    runner.context_manager = SimpleNamespace(
        token_counter=SimpleNamespace(count_tokens=lambda *_args, **_kwargs: 35)
    )
    runner.post_tool_compaction_controller.refresh_baseline(
        messages=runner.run_context.messages,
        token_counter=SimpleNamespace(count_tokens=lambda *_args, **_kwargs: 30),
    )

    # ratio=0.35 in soft zone, token delta=5 and message delta=0 -> should skip
    assert runner._should_run_post_tool_compaction() is False

    runner.context_manager = SimpleNamespace(
        token_counter=SimpleNamespace(count_tokens=lambda *_args, **_kwargs: 95)
    )
    # ratio=0.95 in hard zone -> force compaction
    assert runner._should_run_post_tool_compaction() is True


def test_post_tool_compaction_handles_token_counter_errors(runner):
    runner.post_tool_compaction = PostToolCompactionConfig(
        enabled=True,
        soft_ratio=0.3,
        hard_ratio=0.9,
        min_delta_tokens=10,
        min_delta_turns=10,
        debounce_seconds=0,
    )
    runner.post_tool_compaction_controller = PostToolCompactionController(
        runner.post_tool_compaction
    )
    runner.context_config = SimpleNamespace(max_context_tokens=100)
    runner.run_context = SimpleNamespace(messages=[object(), object()])

    def _raise(*_args, **_kwargs):
        raise RuntimeError("counter broken")

    runner.context_manager = SimpleNamespace(
        token_counter=SimpleNamespace(count_tokens=_raise)
    )

    assert runner._should_run_post_tool_compaction() is False


def test_post_tool_compaction_debounce_is_not_extended(monkeypatch):
    config = PostToolCompactionConfig(
        enabled=True,
        soft_ratio=0.3,
        hard_ratio=0.9,
        min_delta_tokens=0,
        min_delta_turns=0,
        debounce_seconds=100,
    )
    controller = PostToolCompactionController(config)
    messages = [object()]
    token_counter = SimpleNamespace(count_tokens=lambda *_args, **_kwargs: 95)

    # refresh baseline before checks
    controller.refresh_baseline(
        messages=messages,
        token_counter=SimpleNamespace(count_tokens=lambda *_args, **_kwargs: 30),
    )

    ts = iter([1.0, 10.0, 20.0, 105.0])
    monkeypatch.setattr(
        "astrbot.core.agent.runners.tool_loop_agent_runner.time.monotonic",
        lambda: next(ts),
    )

    # first check performs decision and sets baseline timestamp
    assert (
        controller.should_compact(
            messages=messages,
            token_counter=token_counter,
            max_context_tokens=100,
        )
        is True
    )
    # next two checks are debounced
    assert (
        controller.should_compact(
            messages=messages,
            token_counter=token_counter,
            max_context_tokens=100,
        )
        is False
    )
    assert (
        controller.should_compact(
            messages=messages,
            token_counter=token_counter,
            max_context_tokens=100,
        )
        is False
    )
    # should become eligible at t=105 if debounce anchor remains at first real check (t=1)
    assert (
        controller.should_compact(
            messages=messages,
            token_counter=token_counter,
            max_context_tokens=100,
        )
        is True
    )


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])
