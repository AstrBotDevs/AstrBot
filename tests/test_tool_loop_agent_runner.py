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
from astrbot.core.agent.message import ImageURLPart, Message, TextPart
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runners.base import AgentState
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import (
    LLMResponse,
    ProviderMeta,
    ProviderRequest,
    ProviderType,
    TokenUsage,
)
from astrbot.core.provider.provider import Provider, TTSProvider
from astrbot.core.provider.sources import request_retry
from astrbot.core.provider.sources.request_retry import retry_provider_request


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


class MockLeakyAbortProvider(MockProvider):
    def __init__(self, event=None):
        super().__init__()
        self.event = event

    async def text_chat(self, **kwargs) -> LLMResponse:
        self.call_count += 1
        if self.event is not None:
            self.event.set_extra("agent_stop_requested", True)
        return LLMResponse(
            role="assistant",
            completion_text="late completion text",
            result_chain=MessageChain().message("late result chain"),
            tools_call_name=["late_tool"],
            tools_call_args=[{"query": "late"}],
            tools_call_ids=["call_late"],
            tools_call_extra_content={"call_late": {"extra": "late"}},
            reasoning_content="late reasoning",
            reasoning_signature="late signature",
            raw_completion=object(),
            id="late-id",
            usage=TokenUsage(input_other=10, output=5),
        )


class MockDelayedTextProvider(MockProvider):
    def __init__(self):
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def text_chat(self, **kwargs) -> LLMResponse:
        self.call_count += 1
        self.started.set()
        await self.release.wait()
        return LLMResponse(
            role="assistant",
            completion_text="delayed visible text",
            usage=TokenUsage(input_other=10, output=5),
        )


class MockDelayedTTSProvider(TTSProvider):
    def __init__(self, audio_path: Path | None):
        super().__init__({"type": "test_tts", "id": "test_tts"}, {})
        self.audio_path = audio_path
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.call_count = 0

    async def get_audio(self, text: str) -> str:
        self.call_count += 1
        self.started.set()
        await self.release.wait()
        return str(self.audio_path) if self.audio_path else ""

    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            id="test_tts",
            model=None,
            type="test_tts",
            provider_type=ProviderType.TEXT_TO_SPEECH,
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


class CapturingToolLoopProvider(MockProvider):
    def __init__(self, tool_name: str):
        super().__init__()
        self.tool_name = tool_name
        self.received_contexts = []

    async def text_chat(self, **kwargs) -> LLMResponse:
        self.call_count += 1
        self.received_contexts.append(list(kwargs.get("contexts") or []))
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
            tools_call_args=[{"query": "test"}],
            tools_call_ids=["call_context_refresh"],
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
        self.agent_done_response = None

    async def on_agent_begin(self, run_context):
        self.agent_begin_called = True

    async def on_tool_start(self, run_context, tool, tool_args):
        self.tool_start_called = True

    async def on_tool_end(self, run_context, tool, tool_args, tool_result):
        self.tool_end_called = True

    async def on_agent_done(self, run_context, llm_response):
        self.agent_done_called = True
        self.agent_done_response = llm_response


class LateStopAfterYieldRunner:
    def __init__(
        self,
        event,
        text: str,
        stop_after_yield: bool = True,
    ):
        self.run_context = ContextWrapper(context=MockAgentContext(event))
        self.text = text
        self.streaming = True
        self.stop_after_yield = stop_after_yield
        self._done = False
        self._aborted = False

    async def step(self):
        yield SimpleNamespace(
            type="streaming_delta",
            data={"chain": MessageChain().message(self.text)},
        )
        if self.stop_after_yield:
            self.run_context.context.event.set_extra("agent_stop_requested", True)
        self._done = True

    def done(self):
        return self._done

    def request_stop(self):
        pass

    def was_aborted(self):
        return self._aborted

    def discard_late_aborted_result(self):
        self._aborted = True
        event = self.run_context.context.event
        event.set_extra("agent_user_aborted", True)
        event.set_extra("agent_stop_requested", False)


class MockEvent:
    def __init__(self, umo: str, sender_id: str):
        self.unified_msg_origin = umo
        self.plugins_name = None
        self._sender_id = sender_id
        self._extras = {}
        self.result = None
        self.trace = SimpleNamespace(record=lambda *args, **kwargs: None)
        self._stopped = False
        self._temporary_local_files = []

    def get_sender_id(self):
        return self._sender_id

    def set_extra(self, key, value):
        self._extras[key] = value

    def get_extra(self, key=None, default=None):
        if key is None:
            return self._extras
        return self._extras.get(key, default)

    def set_result(self, result):
        self.result = result

    def get_result(self):
        return self.result

    def clear_result(self):
        self.result = None

    def is_stopped(self):
        return self._stopped

    def stop(self):
        self._stopped = True

    def track_temporary_local_file(self, path):
        if path not in self._temporary_local_files:
            self._temporary_local_files.append(path)

    def cleanup_temporary_local_files(self):
        paths = list(self._temporary_local_files)
        self._temporary_local_files.clear()
        for path in paths:
            if os.path.exists(path):
                os.remove(path)

    def get_platform_name(self):
        return "test"

    def get_platform_id(self):
        return "test"

    async def send(self, *args, **kwargs):
        return None


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


async def _collect_async_iter(async_iter):
    return [item async for item in async_iter]


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
async def test_max_step_final_request_includes_limit_prompt(
    runner, provider_request, mock_tool_executor, mock_hooks
):
    """The forced final step must use contexts recomputed after max-step prompt."""
    provider = CapturingToolLoopProvider("test_tool")

    await runner.reset(
        provider=provider,
        request=provider_request,
        run_context=ContextWrapper(context=None),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    async def snapshot_context_manager(messages, trusted_token_usage=0):
        return list(messages)

    runner.request_context_manager.process = snapshot_context_manager

    async for _ in runner.step_until_done(1):
        pass

    assert provider.call_count == 2
    final_contexts = provider.received_contexts[-1]
    assert final_contexts[-1].role == "user"
    assert final_contexts[-1].content == runner.MAX_STEPS_REACHED_PROMPT


@pytest.mark.asyncio
async def test_tool_loop_next_request_includes_tool_result(
    runner, provider_request, mock_tool_executor, mock_hooks
):
    """Tool-loop provider contexts must be recomputed after tool results append."""
    provider = CapturingToolLoopProvider("test_tool")

    await runner.reset(
        provider=provider,
        request=provider_request,
        run_context=ContextWrapper(context=None),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    async def snapshot_context_manager(messages, trusted_token_usage=0):
        return list(messages)

    runner.request_context_manager.process = snapshot_context_manager

    async for _ in runner.step_until_done(3):
        pass

    assert provider.call_count == 2
    second_contexts = provider.received_contexts[1]
    tool_messages = [msg for msg in second_contexts if msg.role == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0].tool_call_id == "call_context_refresh"
    assert "工具执行结果" in tool_messages[0].content


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
        return SimpleNamespace(
            file_path=f"/tmp/{tool_call_id}_{index}.png", mime_type=mime_type
        )

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
async def test_stop_signal_returns_aborted_and_discards_delayed_response(
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
    assert final_resp.completion_text == ""
    assert (
        not runner.run_context.messages
        or runner.run_context.messages[-1].role != "assistant"
    )
    assert mock_hooks.agent_done_response is final_resp


@pytest.mark.asyncio
async def test_aborted_final_response_sanitizes_all_model_output_fields(
    runner, provider_request, mock_tool_executor, mock_hooks
):
    event = MockEvent("test:FriendMessage:leaky_abort", "u1")
    provider = MockLeakyAbortProvider(event)

    await runner.reset(
        provider=provider,
        request=provider_request,
        run_context=ContextWrapper(context=MockAgentContext(event)),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    responses = []
    async for response in runner.step():
        responses.append(response)

    assert [response.type for response in responses] == ["aborted"]
    assert runner.was_aborted() is True
    final_resp = runner.get_final_llm_resp()
    assert final_resp is not None
    assert final_resp.role == "assistant"
    assert final_resp.completion_text == ""
    assert final_resp.result_chain is None
    assert final_resp.reasoning_content is None
    assert final_resp.reasoning_signature is None
    assert final_resp.raw_completion is None
    assert final_resp.tools_call_args == []
    assert final_resp.tools_call_name == []
    assert final_resp.tools_call_ids == []
    assert final_resp.tools_call_extra_content == {}
    assert final_resp.id == "late-id"
    assert final_resp.usage is not None
    assert final_resp.usage.total == 15
    assert runner.stats.token_usage.total == 15
    assert mock_hooks.agent_done_called is True
    assert mock_hooks.agent_done_response is final_resp

    serialized_messages = repr(runner.run_context.messages)
    assert "late completion text" not in serialized_messages
    assert "late result chain" not in serialized_messages
    assert "late reasoning" not in serialized_messages
    assert "late_tool" not in serialized_messages


@pytest.mark.parametrize("stop_during", ["begin_hook", "context_process"])
@pytest.mark.asyncio
async def test_stop_around_context_processing_blocks_provider_request(
    stop_during,
    provider_request,
    mock_tool_executor,
):
    event = MockEvent(f"test:FriendMessage:context_{stop_during}", "u1")
    provider = MockProvider()
    provider.should_call_tools = False

    class Hooks(MockHooks):
        async def on_agent_begin(self, run_context):
            await super().on_agent_begin(run_context)
            if stop_during == "begin_hook":
                event.set_extra("agent_stop_requested", True)

    runner = ToolLoopAgentRunner()
    await runner.reset(
        provider=provider,
        request=provider_request,
        run_context=ContextWrapper(context=MockAgentContext(event)),
        tool_executor=mock_tool_executor,
        agent_hooks=Hooks(),
    )

    async def process(messages, **_kwargs):
        event.set_extra("agent_stop_requested", True)
        return messages

    runner.request_context_manager.process = AsyncMock(side_effect=process)
    responses = [response async for response in runner.step()]

    assert [response.type for response in responses] == ["aborted"]
    assert provider.call_count == 0
    if stop_during == "begin_hook":
        runner.request_context_manager.process.assert_not_awaited()
    else:
        runner.request_context_manager.process.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_interrupts_pending_context_processing(
    provider_request,
    mock_tool_executor,
    mock_hooks,
):
    event = MockEvent("test:FriendMessage:context_pending_stop", "u1")
    provider = MockProvider()
    provider.should_call_tools = False
    runner = ToolLoopAgentRunner()
    await runner.reset(
        provider=provider,
        request=provider_request,
        run_context=ContextWrapper(context=MockAgentContext(event)),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
    )
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def process(_messages, **_kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    runner.request_context_manager.process = process
    task = asyncio.create_task(_collect_async_iter(runner.step()))
    await asyncio.wait_for(started.wait(), timeout=1)
    event.set_extra("agent_stop_requested", True)

    responses = await asyncio.wait_for(task, timeout=1)

    assert [response.type for response in responses] == ["aborted"]
    assert provider.call_count == 0
    assert cancelled.is_set() is True


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_first", [False, True])
async def test_await_or_abort_propagates_outer_cancellation(
    stop_first,
    runner,
    provider_request,
    mock_tool_executor,
    mock_hooks,
):
    event = MockEvent("test:FriendMessage:outer_cancel", "u1")
    await runner.reset(
        provider=MockProvider(),
        request=provider_request,
        run_context=ContextWrapper(context=MockAgentContext(event)),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
    )
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def operation():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    task = asyncio.create_task(runner._await_or_abort(operation()))
    await asyncio.wait_for(started.wait(), timeout=1)
    if stop_first:
        runner.request_stop()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set() is True


@pytest.mark.asyncio
async def test_run_agent_discards_buffered_llm_result_after_abort(
    runner, provider_request, mock_tool_executor, mock_hooks
):
    from astrbot.core.astr_agent_run_util import run_agent

    provider = MockDelayedTextProvider()
    event = MockEvent("test:FriendMessage:buffer_abort", "u1")

    await runner.reset(
        provider=provider,
        request=provider_request,
        run_context=ContextWrapper(context=MockAgentContext(event)),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    agent_task = asyncio.create_task(
        _collect_async_iter(
            run_agent(
                runner,
                buffer_intermediate_messages=True,
            )
        )
    )
    await asyncio.wait_for(provider.started.wait(), timeout=5)
    event.set_extra("agent_stop_requested", True)
    provider.release.set()

    chains = await asyncio.wait_for(agent_task, timeout=5)

    assert chains == []
    assert runner.was_aborted() is True
    assert event.result is None


@pytest.mark.asyncio
async def test_live_agent_feeder_discards_residual_buffer_after_stop():
    from astrbot.core.astr_agent_run_util import _run_agent_feeder

    event = MockEvent("test:FriendMessage:live_late_buffer_abort", "u1")
    runner = LateStopAfterYieldRunner(
        event,
        text="partial without punctuation",
    )
    text_queue = asyncio.Queue()

    await _run_agent_feeder(
        cast(Any, runner),
        text_queue,
        max_step=30,
        show_tool_use=True,
        show_tool_call_result=False,
        show_reasoning=False,
        buffer_intermediate_messages=False,
    )

    assert await text_queue.get() is None
    assert text_queue.empty()


@pytest.mark.parametrize("native_stream", [False, True])
@pytest.mark.asyncio
async def test_live_agent_discards_queued_tts_audio_after_stop(tmp_path, native_stream):
    from astrbot.core.astr_agent_run_util import run_live_agent

    class Provider(MockDelayedTTSProvider):
        def support_stream(self) -> bool:
            return native_stream

    audio_path = tmp_path / "late.wav"
    audio_path.write_bytes(b"late-audio")
    event = MockEvent("test:FriendMessage:live_tts_queued_abort", "u1")
    runner = LateStopAfterYieldRunner(
        event,
        text="complete sentence!",
        stop_after_yield=False,
    )
    tts_provider = Provider(audio_path)

    live_task = asyncio.create_task(
        _collect_async_iter(run_live_agent(cast(Any, runner), tts_provider))
    )
    await asyncio.wait_for(tts_provider.started.wait(), timeout=5)
    event.set_extra("agent_stop_requested", True)
    tts_provider.release.set()

    chains = await asyncio.wait_for(live_task, timeout=5)

    assert chains == []
    assert event._temporary_local_files == [str(audio_path)]
    event.cleanup_temporary_local_files()
    assert not audio_path.exists()


@pytest.mark.asyncio
async def test_cancelled_genie_stream_removes_late_executor_file(
    tmp_path,
    monkeypatch,
):
    """A cancelled native Genie worker must clean a file created later."""
    import threading

    from astrbot.core.astr_agent_run_util import _safe_tts_stream_wrapper
    from astrbot.core.provider.sources import genie_tts

    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def generate(*, save_path, **kwargs):
        started.set()
        release.wait(timeout=1)
        Path(save_path).write_bytes(b"late audio")
        finished.set()

    monkeypatch.setattr(genie_tts, "genie", SimpleNamespace(tts=generate))
    monkeypatch.setattr(genie_tts, "get_astrbot_temp_path", lambda: str(tmp_path))
    provider = object.__new__(genie_tts.GenieTTSProvider)
    provider.character_name = "test"
    event = MockEvent("test:FriendMessage:genie_cancel_cleanup", "u1")
    text_queue = asyncio.Queue()
    audio_queue = asyncio.Queue()
    await text_queue.put("sentence")

    task = asyncio.create_task(
        _safe_tts_stream_wrapper(provider, text_queue, audio_queue, event)
    )
    assert await asyncio.to_thread(started.wait, 1)
    event.set_extra("agent_stop_requested", True)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=0.2)
    release.set()
    assert await asyncio.to_thread(finished.wait, 1)

    assert len(event._temporary_local_files) == 1
    generated_path = Path(event._temporary_local_files[0])
    for _ in range(100):
        if not generated_path.exists():
            break
        await asyncio.sleep(0.01)
    assert not generated_path.exists()


@pytest.mark.asyncio
async def test_cancelled_genie_get_audio_removes_late_executor_file(
    tmp_path,
    monkeypatch,
):
    import threading

    from astrbot.core.provider.sources import genie_tts

    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    generated_paths = []

    def generate(*, save_path, **kwargs):
        generated_paths.append(Path(save_path))
        started.set()
        release.wait(timeout=1)
        Path(save_path).write_bytes(b"late audio")
        finished.set()

    monkeypatch.setattr(genie_tts, "genie", SimpleNamespace(tts=generate))
    monkeypatch.setattr(genie_tts, "get_astrbot_temp_path", lambda: str(tmp_path))
    provider = object.__new__(genie_tts.GenieTTSProvider)
    provider.character_name = "test"

    task = asyncio.create_task(provider.get_audio("sentence"))
    assert await asyncio.to_thread(started.wait, 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    release.set()
    assert await asyncio.to_thread(finished.wait, 1)

    for _ in range(100):
        if generated_paths and not generated_paths[0].exists():
            break
        await asyncio.sleep(0.01)
    assert generated_paths
    assert not generated_paths[0].exists()


@pytest.mark.asyncio
async def test_native_live_tts_does_not_start_queued_text_after_stop(tmp_path):
    from astrbot.core.astr_agent_run_util import run_live_agent

    class NativeTTS(MockDelayedTTSProvider):
        def __init__(self):
            super().__init__(tmp_path / "unused.wav")
            self.texts = []

        def support_stream(self) -> bool:
            return True

        async def get_audio_stream(self, text_queue, audio_queue) -> None:
            while (text := await text_queue.get()) is not None:
                self.texts.append(text)
                self.started.set()
                await self.release.wait()
                await audio_queue.put((text, b"audio"))

    event = MockEvent("test:FriendMessage:native_tts_stop", "u1")
    runner = LateStopAfterYieldRunner(
        event,
        text="first complete sentence! second complete sentence!",
        stop_after_yield=False,
    )
    provider = NativeTTS()
    task = asyncio.create_task(
        _collect_async_iter(run_live_agent(cast(Any, runner), provider))
    )
    await asyncio.wait_for(provider.started.wait(), timeout=1)
    event.set_extra("agent_stop_requested", True)
    provider.release.set()

    assert await asyncio.wait_for(task, timeout=1) == []
    assert provider.texts == ["first complete sentence!"]


@pytest.mark.parametrize("returns_audio_path", [True, False])
@pytest.mark.asyncio
async def test_result_decorate_stops_after_first_tts_result(
    tmp_path, monkeypatch, returns_audio_path
):
    """Normal result decoration must register a late TTS file before aborting."""
    from astrbot.core.message.components import Plain
    from astrbot.core.message.message_event_result import (
        MessageEventResult,
        ResultContentType,
    )
    from astrbot.core.pipeline.result_decorate import stage as decorate_stage

    audio_path = tmp_path / "decorated-stop.wav"
    audio_path.write_bytes(b"audio")
    provider = MockDelayedTTSProvider(audio_path if returns_audio_path else None)
    event = MockEvent("test:FriendMessage:decorate_tts_stop", "u1")
    event.set_result(
        MessageEventResult(
            chain=[Plain("sentence"), Plain("second sentence")],
            result_content_type=ResultContentType.LLM_RESULT,
        )
    )
    stage = decorate_stage.ResultDecorateStage()
    stage.content_safe_check_reply = False
    stage.reply_prefix = ""
    stage.enable_segmented_reply = False
    stage.show_reasoning = False
    stage.tts_trigger_probability = 1
    stage.ctx = SimpleNamespace(
        plugin_manager=SimpleNamespace(
            context=SimpleNamespace(get_using_tts_provider=lambda _umo: provider)
        ),
        astrbot_config={
            "provider_tts_settings": {"enable": True},
        },
    )
    monkeypatch.setattr(
        decorate_stage.star_handlers_registry,
        "get_handlers_by_event_type",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        decorate_stage.SessionServiceManager,
        "should_process_tts_request",
        AsyncMock(return_value=True),
    )

    task = asyncio.create_task(_collect_async_iter(stage.process(event)))
    await asyncio.wait_for(provider.started.wait(), timeout=1)
    event.set_extra("agent_stop_requested", True)
    provider.release.set()
    await asyncio.wait_for(task, timeout=1)

    assert provider.call_count == 1
    assert event._temporary_local_files == (
        [str(audio_path)] if returns_audio_path else []
    )
    assert event.get_result() is None
    event.cleanup_temporary_local_files()
    if returns_audio_path:
        assert not audio_path.exists()


@pytest.mark.parametrize(
    ("stop_key", "expect_llm_hook"),
    [
        (None, True),
        ("agent_user_aborted", False),
        ("agent_stop_requested", False),
    ],
)
@pytest.mark.asyncio
async def test_main_agent_hooks_respect_stop_state(
    monkeypatch,
    stop_key,
    expect_llm_hook,
):
    from astrbot.core import astr_agent_hooks
    from astrbot.core.astr_agent_hooks import MainAgentHooks
    from astrbot.core.star.star_handler import EventType

    calls = []

    async def fake_call_event_hook(event, hook_type, *args, **kwargs):
        calls.append((hook_type, args))
        return False

    async def fake_call_agent_done_hook(event, run_context, llm_response):
        calls.append((EventType.OnAgentDoneEvent, (run_context, llm_response)))

    monkeypatch.setattr(astr_agent_hooks, "call_event_hook", fake_call_event_hook)
    monkeypatch.setattr(
        astr_agent_hooks,
        "call_agent_done_hook",
        fake_call_agent_done_hook,
    )

    event = MockEvent("test:FriendMessage:hook_state", "u1")
    if stop_key:
        event.set_extra(stop_key, True)
    response = LLMResponse(
        role="assistant",
        completion_text="response text",
        reasoning_content="response reasoning",
    )
    await MainAgentHooks().on_agent_done(
        ContextWrapper(context=MockAgentContext(event)), response
    )

    called_types = [hook_type for hook_type, _ in calls]
    assert (EventType.OnLLMResponseEvent in called_types) is expect_llm_hook
    assert EventType.OnAgentDoneEvent in called_types
    assert event.get_extra("_llm_reasoning_content") == (
        "response reasoning" if expect_llm_hook else None
    )


@pytest.mark.parametrize(
    "hook_type_name",
    ["OnLLMResponseEvent", "OnUsingLLMToolEvent", "OnLLMToolRespondEvent"],
)
def test_agent_output_hooks_stop_propagating_after_soft_stop(hook_type_name):
    from astrbot.core.pipeline.context_utils import _should_stop_hook_propagation
    from astrbot.core.star.star_handler import EventType

    event = MockEvent("test:FriendMessage:hook_propagation_stop", "u1")
    event.set_extra("agent_stop_requested", True)

    assert _should_stop_hook_propagation(event, EventType[hook_type_name]) is True


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
async def test_skills_like_requery_stop_skips_repair_request(
    provider_request,
    mock_tool_executor,
    mock_hooks,
):
    class SkillsLikeRepairStopProvider(MockProvider):
        def __init__(self, event):
            super().__init__()
            self.event = event

        async def text_chat(self, **kwargs) -> LLMResponse:
            self.call_count += 1
            if self.call_count == 1:
                return LLMResponse(
                    role="assistant",
                    completion_text="选择工具",
                    tools_call_name=["test_tool"],
                    tools_call_args=[{"query": "test"}],
                    tools_call_ids=["call_1"],
                )

            self.event.set_extra("agent_stop_requested", True)
            return LLMResponse(role="assistant", completion_text="")

    event = MockEvent(umo="test_umo", sender_id="test_sender")
    provider = SkillsLikeRepairStopProvider(event)
    runner = ToolLoopAgentRunner()

    await runner.reset(
        provider=provider,
        request=provider_request,
        run_context=ContextWrapper(context=MockAgentContext(event)),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        tool_schema_mode="skills_like",
    )

    responses = [response async for response in runner.step()]

    assert [response.type for response in responses] == ["llm_result", "aborted"]
    assert provider.call_count == 2


@pytest.mark.asyncio
async def test_stop_interrupts_pending_skills_like_requery(
    provider_request,
    mock_tool_executor,
    mock_hooks,
):
    class PendingRequeryProvider(MockProvider):
        def __init__(self):
            super().__init__()
            self.requery_started = asyncio.Event()
            self.requery_cancelled = asyncio.Event()

        async def text_chat(self, **_kwargs) -> LLMResponse:
            self.call_count += 1
            if self.call_count == 1:
                return LLMResponse(
                    role="assistant",
                    completion_text="选择工具",
                    tools_call_name=["test_tool"],
                    tools_call_args=[{"query": "test"}],
                    tools_call_ids=["call_1"],
                )

            self.requery_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                self.requery_cancelled.set()

    event = MockEvent("test:FriendMessage:skills_requery_pending_stop", "u1")
    provider = PendingRequeryProvider()
    runner = ToolLoopAgentRunner()
    await runner.reset(
        provider=provider,
        request=provider_request,
        run_context=ContextWrapper(context=MockAgentContext(event)),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        tool_schema_mode="skills_like",
    )

    task = asyncio.create_task(_collect_async_iter(runner.step()))
    await asyncio.wait_for(provider.requery_started.wait(), timeout=1)
    event.set_extra("agent_stop_requested", True)
    responses = await asyncio.wait_for(task, timeout=1)

    assert [response.type for response in responses] == ["llm_result", "aborted"]
    assert provider.call_count == 2
    assert provider.requery_cancelled.is_set() is True


@pytest.mark.asyncio
async def test_skills_like_requery_fallback_checks_stop_before_yielding_text(
    provider_request,
    mock_tool_executor,
):
    class StopAfterFallbackDoneHooks(MockHooks):
        async def on_agent_done(self, run_context, llm_response):
            await super().on_agent_done(run_context, llm_response)
            run_context.context.event.set_extra("agent_stop_requested", True)

    class SkillsLikeFallbackProvider(MockProvider):
        async def text_chat(self, **kwargs) -> LLMResponse:
            self.call_count += 1
            if self.call_count == 1:
                return LLMResponse(
                    role="assistant",
                    completion_text="选择工具",
                    tools_call_name=["test_tool"],
                    tools_call_args=[{"query": "test"}],
                    tools_call_ids=["call_1"],
                    usage=TokenUsage(input_other=10, output=5),
                )

            return LLMResponse(
                role="assistant",
                completion_text="skills_like fallback text",
                reasoning_content="skills_like fallback reasoning",
                usage=TokenUsage(input_other=10, output=5),
            )

    event = MockEvent(umo="test_umo", sender_id="test_sender")
    provider = SkillsLikeFallbackProvider()
    runner = ToolLoopAgentRunner()
    hooks = StopAfterFallbackDoneHooks()

    await runner.reset(
        provider=provider,
        request=provider_request,
        run_context=ContextWrapper(context=MockAgentContext(event)),
        tool_executor=mock_tool_executor,
        agent_hooks=hooks,
        tool_schema_mode="skills_like",
    )

    responses = [response async for response in runner.step()]

    assert [response.type for response in responses] == ["llm_result", "aborted"]
    visible_text = "".join(
        response.data["chain"].get_plain_text()
        for response in responses
        if response.type != "aborted"
    )
    assert "skills_like fallback text" not in visible_text
    assert "skills_like fallback reasoning" not in visible_text
    assert runner.was_aborted() is True
    final_resp = runner.get_final_llm_resp()
    assert final_resp is not None
    assert final_resp.completion_text == ""
    assert "skills_like fallback text" not in repr(runner.run_context.messages)
    assert "skills_like fallback reasoning" not in repr(runner.run_context.messages)


@pytest.mark.asyncio
async def test_fallback_provider_not_called_after_stop_on_primary_error_response(
    provider_request,
    mock_tool_executor,
):
    class StopErrProvider(MockErrProvider):
        def __init__(self, event):
            super().__init__()
            self.provider_config["id"] = "primary"
            self.event = event

        async def text_chat(self, **kwargs) -> LLMResponse:
            response = await super().text_chat(**kwargs)
            self.event.set_extra("agent_stop_requested", True)
            return response

    event = MockEvent("test:FriendMessage:fallback_stop", "u1")
    primary = StopErrProvider(event)
    fallback = MockProvider()
    fallback.provider_config["id"] = "fallback"
    fallback.should_call_tools = False
    runner = ToolLoopAgentRunner()

    await runner.reset(
        provider=primary,
        request=provider_request,
        run_context=ContextWrapper(context=MockAgentContext(event)),
        tool_executor=mock_tool_executor,
        agent_hooks=MockHooks(),
        fallback_providers=[fallback],
    )

    responses = [response async for response in runner.step()]

    assert [response.type for response in responses] == ["aborted"]
    assert primary.call_count == 1
    assert fallback.call_count == 0


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
    runner._transition_state(AgentState.RUNNING)

    ticket = runner.follow_up(message_text="follow up while active")

    assert ticket is not None
    assert ticket in runner._pending_follow_ups
    assert len(runner._pending_follow_ups) == 1


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
async def test_empty_output_stop_prevents_retry(
    provider_request,
    mock_tool_executor,
    mock_hooks,
):
    """A stop raised with the first empty output must suppress later attempts."""

    class StopAfterEmptyProvider(MockProvider):
        def __init__(self, event):
            super().__init__()
            self.event = event

        async def text_chat(self, **kwargs) -> LLMResponse:
            self.call_count += 1
            self.event.set_extra("agent_stop_requested", True)
            raise EmptyModelOutputError("empty")

    event = MockEvent("test:FriendMessage:empty_retry_stop", "u1")
    provider = StopAfterEmptyProvider(event)
    runner = ToolLoopAgentRunner()
    await runner.reset(
        provider=provider,
        request=provider_request,
        run_context=ContextWrapper(context=MockAgentContext(event)),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    responses = [response async for response in runner.step()]

    assert provider.call_count == 1
    assert [response.type for response in responses] == ["aborted"]


@pytest.mark.asyncio
async def test_streaming_output_is_not_retried_after_empty_output_error(
    provider_request,
    mock_tool_executor,
    mock_hooks,
):
    """A broken stream must not replay already published chunks."""

    class StreamThenEmptyProvider(MockProvider):
        async def text_chat_stream(self, **kwargs):
            self.call_count += 1
            chunk = LLMResponse(role="assistant", completion_text="partial")
            chunk.is_chunk = True
            yield chunk
            raise EmptyModelOutputError("empty after stream started")

    provider = StreamThenEmptyProvider()
    event = MockEvent("test:FriendMessage:stream_empty_no_retry", "u1")
    runner = ToolLoopAgentRunner()
    await runner.reset(
        provider=provider,
        request=provider_request,
        run_context=ContextWrapper(context=MockAgentContext(event)),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=True,
    )

    responses = [response async for response in runner.step()]

    assert provider.call_count == 1
    assert [response.type for response in responses] == ["streaming_delta", "err"]


@pytest.mark.asyncio
async def test_empty_output_backoff_is_interrupted_by_event_stop(
    provider_request,
    mock_tool_executor,
    mock_hooks,
):
    """A soft stop during retry backoff must wake without another request."""

    class BackoffProvider(MockProvider):
        def __init__(self):
            super().__init__()
            self.first_attempt_finished = asyncio.Event()

        async def text_chat(self, **kwargs) -> LLMResponse:
            self.call_count += 1
            self.first_attempt_finished.set()
            raise EmptyModelOutputError("empty")

    event = MockEvent("test:FriendMessage:backoff_stop", "u1")
    provider = BackoffProvider()
    runner = ToolLoopAgentRunner()
    await runner.reset(
        provider=provider,
        request=provider_request,
        run_context=ContextWrapper(context=MockAgentContext(event)),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    task = asyncio.create_task(_collect_async_iter(runner.step()))
    await asyncio.wait_for(provider.first_attempt_finished.wait(), timeout=1)
    started = asyncio.get_running_loop().time()
    event.set_extra("agent_stop_requested", True)
    responses = await asyncio.wait_for(task, timeout=1)
    elapsed = asyncio.get_running_loop().time() - started

    assert provider.call_count == 1
    assert elapsed < 0.5
    assert [response.type for response in responses] == ["aborted"]


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.asyncio
async def test_stop_interrupts_provider_internal_retry_backoff(
    monkeypatch,
    streaming,
    provider_request,
    mock_tool_executor,
    mock_hooks,
):
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MIN_S", 10)
    monkeypatch.setattr(request_retry, "REQUEST_RETRY_WAIT_MAX_S", 10)

    class InternalRetryProvider(MockProvider):
        def __init__(self):
            super().__init__()
            self.first_attempt_finished = asyncio.Event()

        async def _request(self) -> LLMResponse:
            self.call_count += 1
            if self.call_count == 1:
                self.first_attempt_finished.set()
                raise OSError("retryable")
            return LLMResponse(role="assistant", completion_text="late")

        async def text_chat(self, **_kwargs) -> LLMResponse:
            return await retry_provider_request(
                "runner-stop-test",
                self._request,
                max_attempts=2,
            )

        async def text_chat_stream(self, **_kwargs):
            yield await retry_provider_request(
                "runner-stop-test",
                self._request,
                max_attempts=2,
            )

    event = MockEvent("test:FriendMessage:provider_internal_retry_stop", "u1")
    provider = InternalRetryProvider()
    runner = ToolLoopAgentRunner()
    await runner.reset(
        provider=provider,
        request=provider_request,
        run_context=ContextWrapper(context=MockAgentContext(event)),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=streaming,
    )

    task = asyncio.create_task(_collect_async_iter(runner.step()))
    await asyncio.wait_for(provider.first_attempt_finished.wait(), timeout=1)
    started = asyncio.get_running_loop().time()
    event.set_extra("agent_stop_requested", True)
    responses = await asyncio.wait_for(task, timeout=1)
    elapsed = asyncio.get_running_loop().time() - started

    assert provider.call_count == 1
    assert elapsed < 0.5
    assert [response.type for response in responses] == ["aborted"]


@pytest.mark.parametrize("tool_schema_mode", ["skills_like", "full"])
@pytest.mark.asyncio
async def test_stop_after_tool_selection_yield_blocks_requery_and_executor(
    tool_schema_mode,
    provider_request,
):
    """Resuming a tool-selection yield after stop must not start new work."""

    class CountingExecutor:
        def __init__(self):
            self.calls = 0

        def execute(self, tool, run_context, **tool_args):
            self.calls += 1
            raise AssertionError("executor must not be constructed after stop")

    event = MockEvent(f"test:FriendMessage:{tool_schema_mode}_yield_stop", "u1")
    provider = MockProvider()
    hooks = MockHooks()
    executor = CountingExecutor()
    runner = ToolLoopAgentRunner()
    await runner.reset(
        provider=provider,
        request=provider_request,
        run_context=ContextWrapper(context=MockAgentContext(event)),
        tool_executor=cast(Any, executor),
        agent_hooks=hooks,
        streaming=False,
        tool_schema_mode=tool_schema_mode,
    )

    step = runner.step()
    first = await anext(step)
    event.set_extra("agent_stop_requested", True)
    remaining = [response async for response in step]

    assert first.type == "llm_result"
    assert [response.type for response in remaining] == ["aborted"]
    assert provider.call_count == 1
    assert hooks.tool_start_called is False
    assert executor.calls == 0


@pytest.mark.parametrize("delivered", [False, True])
@pytest.mark.asyncio
async def test_final_response_history_follows_delivery_boundary(
    delivered,
    provider_request,
    mock_tool_executor,
    mock_hooks,
):
    """Only a response committed at delivery survives a late stop."""
    from astrbot.core.agent.stop_policy import AGENT_OUTPUT_DELIVERY_CONFIRMED_KEY
    from astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal import (
        InternalAgentSubStage,
    )

    event = MockEvent(f"test:FriendMessage:delivery_{delivered}", "u1")
    provider = MockProvider()
    provider.should_call_tools = False
    runner = ToolLoopAgentRunner()
    await runner.reset(
        provider=provider,
        request=provider_request,
        run_context=ContextWrapper(context=MockAgentContext(event)),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    step = runner.step()
    first = await anext(step)
    assert first.type == "llm_result"
    if delivered:
        event.set_extra(AGENT_OUTPUT_DELIVERY_CONFIRMED_KEY, True)
    else:
        assert not InternalAgentSubStage._confirm_agent_output_delivery(event, runner)
    event.set_extra("agent_stop_requested", True)
    assert not InternalAgentSubStage._confirm_agent_output_delivery(event, runner)
    remaining = [response async for response in step]

    assert [response.type for response in remaining] == (
        [] if delivered else ["aborted"]
    )
    assert runner.was_aborted() is not delivered
    assert ("这是我的最终回答" in repr(runner.run_context.messages)) is delivered


@pytest.mark.parametrize("stop_kind", ["mid_dispatch", "soft", "hard"])
@pytest.mark.asyncio
async def test_agent_done_handlers_receive_isolated_responses_after_stop(
    monkeypatch, stop_kind
):
    """All done handlers run, with fresh safe responses after any stop."""
    from astrbot.core.pipeline import context_utils

    event = MockEvent(f"test:FriendMessage:done_{stop_kind}_stop", "u1")
    if stop_kind == "soft":
        event.set_extra("agent_stop_requested", True)
    elif stop_kind == "hard":
        event.stop()

    first_started = asyncio.Event()
    release_first = asyncio.Event()
    seen = []

    async def first_handler(event, run_context, response):
        seen.append(("first", response))
        if stop_kind == "mid_dispatch":
            response.id = "poisoned-id"
            response.usage.output = 998
            first_started.set()
            await release_first.wait()

    async def second_handler(event, run_context, response):
        seen.append(("second", response))
        response.completion_text = "plugin poison"
        response.usage.output = 999
        event.set_extra("agent_stop_requested", False)
        event.set_extra("agent_user_aborted", False)
        event._stopped = False

    async def third_handler(event, run_context, response):
        seen.append(("third", response))

    handlers = [
        SimpleNamespace(
            handler=handler,
            handler_module_path=f"stop_test_plugin_{index}",
            handler_name=f"handler_{index}",
        )
        for index, handler in enumerate(
            [first_handler, second_handler, third_handler], start=1
        )
    ]
    monkeypatch.setattr(
        context_utils.star_handlers_registry,
        "get_handlers_by_event_type",
        lambda *args, **kwargs: handlers,
    )
    monkeypatch.setattr(
        context_utils,
        "star_map",
        {
            handler.handler_module_path: SimpleNamespace(
                name=handler.handler_module_path
            )
            for handler in handlers
        },
    )
    response = LLMResponse(
        role="assistant",
        completion_text="raw secret",
        reasoning_content="raw reasoning",
        id="response-id",
        usage=TokenUsage(input_other=1, output=2),
    )

    task = asyncio.create_task(
        context_utils.call_agent_done_hook(event, object(), response)
    )
    if stop_kind == "mid_dispatch":
        await asyncio.wait_for(first_started.wait(), timeout=1)
        event.set_extra("agent_stop_requested", True)
        release_first.set()
    await asyncio.wait_for(task, timeout=1)

    assert [name for name, _ in seen] == ["first", "second", "third"]
    if stop_kind == "mid_dispatch":
        assert seen[0][1] is response
        assert seen[0][1].completion_text == "raw secret"
    else:
        assert seen[0][1] is not response
        assert seen[0][1].completion_text == ""
        assert seen[0][1] is not seen[1][1]
    assert seen[1][1].completion_text == "plugin poison"
    assert seen[2][1].completion_text == ""
    assert seen[1][1] is not seen[2][1]
    assert seen[2][1].reasoning_content is None
    assert seen[2][1].id == "response-id"
    assert seen[2][1].usage.output == 2
    assert response.usage.output == (998 if stop_kind == "mid_dispatch" else 2)
    assert event.get_extra("agent_stop_requested") is True


@pytest.mark.asyncio
async def test_agent_done_handler_cancellation_is_not_swallowed(monkeypatch):
    """Task cancellation must escape lifecycle hook isolation."""
    from astrbot.core.pipeline import context_utils

    started = asyncio.Event()

    async def blocking_handler(event, run_context, response):
        started.set()
        await asyncio.Event().wait()

    handler = SimpleNamespace(
        handler=blocking_handler,
        handler_module_path="cancel_test_plugin",
        handler_name="blocking_handler",
    )
    monkeypatch.setattr(
        context_utils.star_handlers_registry,
        "get_handlers_by_event_type",
        lambda *args, **kwargs: [handler],
    )
    monkeypatch.setattr(
        context_utils,
        "star_map",
        {handler.handler_module_path: SimpleNamespace(name="cancel_test_plugin")},
    )
    event = MockEvent("test:FriendMessage:done_cancel", "u1")
    task = asyncio.create_task(
        context_utils.call_agent_done_hook(
            event,
            object(),
            LLMResponse(role="assistant", completion_text="late"),
        )
    )
    await asyncio.wait_for(started.wait(), timeout=1)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_agent_output_hook_cancellation_is_not_swallowed(monkeypatch):
    from astrbot.core.pipeline import context_utils
    from astrbot.core.star.star_handler import EventType

    started = asyncio.Event()

    async def blocking_handler(event):
        started.set()
        await asyncio.Event().wait()

    handler = SimpleNamespace(
        handler=blocking_handler,
        handler_module_path="cancel_output_plugin",
        handler_name="blocking_handler",
    )
    monkeypatch.setattr(
        context_utils.star_handlers_registry,
        "get_handlers_by_event_type",
        lambda *args, **kwargs: [handler],
    )
    monkeypatch.setattr(
        context_utils,
        "star_map",
        {handler.handler_module_path: SimpleNamespace(name="cancel_output_plugin")},
    )
    event = MockEvent("test:FriendMessage:output_cancel", "u1")
    task = asyncio.create_task(
        context_utils.call_event_hook(event, EventType.OnLLMResponseEvent)
    )
    await asyncio.wait_for(started.wait(), timeout=1)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_result_decorate_hook_cancellation_is_not_swallowed(monkeypatch):
    from astrbot.core.message.components import Plain
    from astrbot.core.message.message_event_result import MessageEventResult
    from astrbot.core.pipeline.result_decorate import stage as decorate_stage

    started = asyncio.Event()

    async def blocking_handler(event):
        started.set()
        await asyncio.Event().wait()

    handler = SimpleNamespace(
        handler=blocking_handler,
        handler_module_path="cancel_decorate_plugin",
        handler_name="blocking_handler",
    )
    monkeypatch.setattr(
        decorate_stage.star_handlers_registry,
        "get_handlers_by_event_type",
        lambda *args, **kwargs: [handler],
    )
    monkeypatch.setattr(
        decorate_stage,
        "star_map",
        {handler.handler_module_path: SimpleNamespace(name="cancel_decorate_plugin")},
    )
    event = MockEvent("test:FriendMessage:decorate_cancel", "u1")
    event.set_result(MessageEventResult(chain=[Plain("answer")]))
    stage = decorate_stage.ResultDecorateStage()
    stage.content_safe_check_reply = False

    task = asyncio.create_task(_collect_async_iter(stage.process(event)))
    await asyncio.wait_for(started.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_snapshot_rollback_removes_mutated_hook_history_from_next_turn():
    """Rollback and real history serialization must exclude every final secret."""
    from astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal import (
        InternalAgentSubStage,
    )

    class MutatingStopHooks(MockHooks):
        async def on_agent_done(self, run_context, llm_response):
            llm_response.completion_text = "mutated completion secret"
            llm_response.reasoning_content = "mutated reasoning secret"
            llm_response.result_chain = MessageChain().message("mutated chain secret")
            llm_response.raw_completion = {"secret": "mutated raw secret"}
            run_context.messages.reverse()
            run_context.messages.append(
                Message(role="assistant", content="hook appended secret")
            )
            event.set_extra("agent_stop_requested", True)

    event = MockEvent("test:FriendMessage:history_snapshot_stop", "u1")
    conversation = SimpleNamespace(cid="conversation-id", token_usage=0)
    request = ProviderRequest(
        prompt="original question",
        contexts=[],
        conversation=cast(Any, conversation),
    )
    provider = MockProvider()
    provider.should_call_tools = False
    runner = ToolLoopAgentRunner()
    await runner.reset(
        provider=provider,
        request=request,
        run_context=ContextWrapper(context=MockAgentContext(event)),
        tool_executor=MockToolExecutor(),
        agent_hooks=MutatingStopHooks(),
        streaming=False,
    )

    responses = [response async for response in runner.step()]

    assert [response.type for response in responses] == ["aborted"]
    serialized_messages = repr(runner.run_context.messages)
    for secret in (
        "这是我的最终回答",
        "mutated completion secret",
        "mutated reasoning secret",
        "mutated chain secret",
        "mutated raw secret",
        "hook appended secret",
    ):
        assert secret not in serialized_messages

    update_conversation = AsyncMock()
    stage = InternalAgentSubStage()
    stage.conv_manager = SimpleNamespace(update_conversation=update_conversation)
    await stage._save_to_history(
        event,
        request,
        runner.get_final_llm_resp(),
        runner.run_context.messages,
        runner.stats,
        user_aborted=True,
    )
    saved_history = update_conversation.await_args.kwargs["history"]
    assert "secret" not in repr(saved_history)

    next_runner = ToolLoopAgentRunner()
    await next_runner.reset(
        provider=MockProvider(),
        request=ProviderRequest(prompt="next question", contexts=saved_history),
        run_context=ContextWrapper(context=MockAgentContext(event)),
        tool_executor=MockToolExecutor(),
        agent_hooks=MockHooks(),
        streaming=False,
    )
    assert "secret" not in repr(next_runner.run_context.messages)


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])
