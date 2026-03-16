import os
import sys
from unittest.mock import AsyncMock

import pytest

# 将项目根目录添加到 sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.agent.runners.tool_result_guard import (
    ToolResultGuard,
    ToolResultGuardConfig,
)
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


class MockMissingRequiredArgProvider(MockProvider):
    async def text_chat(self, **kwargs) -> LLMResponse:
        self.call_count += 1
        func_tool = kwargs.get("func_tool")
        if func_tool is None or self.call_count > 1:
            return LLMResponse(
                role="assistant",
                completion_text="这是我的最终回答",
                usage=TokenUsage(input_other=10, output=5),
            )
        return LLMResponse(
            role="assistant",
            completion_text="我需要使用工具来帮助您",
            tools_call_name=["test_tool"],
            tools_call_args=[{"max_results": 5}],
            tools_call_ids=["call_missing_required"],
            usage=TokenUsage(input_other=10, output=5),
        )


class MockCamelCaseArgProvider(MockProvider):
    async def text_chat(self, **kwargs) -> LLMResponse:
        self.call_count += 1
        func_tool = kwargs.get("func_tool")
        if func_tool is None or self.call_count > 1:
            return LLMResponse(
                role="assistant",
                completion_text="这是我的最终回答",
                usage=TokenUsage(input_other=10, output=5),
            )
        return LLMResponse(
            role="assistant",
            completion_text="我需要使用工具来帮助您",
            tools_call_name=["test_tool"],
            tools_call_args=[{"query": 123, "maxResults": "5"}],
            tools_call_ids=["call_camel_case"],
            usage=TokenUsage(input_other=10, output=5),
        )


class MockAnyOfViolationProvider(MockProvider):
    async def text_chat(self, **kwargs) -> LLMResponse:
        self.call_count += 1
        func_tool = kwargs.get("func_tool")
        if func_tool is None or self.call_count > 1:
            return LLMResponse(
                role="assistant",
                completion_text="这是我的最终回答",
                usage=TokenUsage(input_other=10, output=5),
            )
        return LLMResponse(
            role="assistant",
            completion_text="我需要使用工具来帮助您",
            tools_call_name=["test_tool"],
            tools_call_args=[{"note": "only note"}],
            tools_call_ids=["call_anyof_violation"],
            usage=TokenUsage(input_other=10, output=5),
        )


class MockIncompatibleArgsProvider(MockProvider):
    async def text_chat(self, **kwargs) -> LLMResponse:
        self.call_count += 1
        func_tool = kwargs.get("func_tool")
        if func_tool is None or self.call_count > 1:
            return LLMResponse(
                role="assistant",
                completion_text="这是我的最终回答",
                usage=TokenUsage(input_other=10, output=5),
            )
        return LLMResponse(
            role="assistant",
            completion_text="我需要使用工具来帮助您",
            tools_call_name=["test_tool"],
            tools_call_args=[{"irrelevant_field": "x"}],
            tools_call_ids=["call_incompatible_args"],
            usage=TokenUsage(input_other=10, output=5),
        )


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


class MockErrorToolExecutor:
    @classmethod
    def execute(cls, tool, run_context, **tool_args):
        async def generator():
            from mcp.types import CallToolResult, TextContent

            result = CallToolResult(
                content=[TextContent(type="text", text="error: temporary upstream failure")]
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


@pytest.fixture
def mock_provider():
    return MockProvider()


@pytest.fixture
def mock_tool_executor():
    return MockToolExecutor()


@pytest.fixture
def mock_error_tool_executor():
    return MockErrorToolExecutor()


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
def tool_set_required_query():
    tool = FunctionTool(
        name="test_tool",
        description="测试工具",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer"},
            },
            "required": ["query"],
        },
        handler=AsyncMock(),
    )
    return ToolSet(tools=[tool])


@pytest.fixture
def provider_request(tool_set):
    """创建测试用的ProviderRequest"""
    return ProviderRequest(prompt="请帮我查询信息", func_tool=tool_set, contexts=[])


@pytest.fixture
def provider_request_required_query(tool_set_required_query):
    return ProviderRequest(
        prompt="请帮我查询信息",
        func_tool=tool_set_required_query,
        contexts=[],
    )


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
async def test_repeated_tool_output_is_deduplicated_in_context(
    runner, mock_provider, provider_request, mock_tool_executor, mock_hooks
):
    """测试重复工具输出会被压缩，避免上下文持续膨胀。"""

    # 前 3 次都调用相同工具，且工具返回相同文本
    mock_provider.should_call_tools = True
    mock_provider.max_calls_before_normal_response = 3

    await runner.reset(
        provider=mock_provider,
        request=provider_request,
        run_context=ContextWrapper(context=None),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    async for _ in runner.step_until_done(6):
        pass

    assert provider_request.tool_calls_result is not None
    assert isinstance(provider_request.tool_calls_result, list)
    assert provider_request.tool_calls_result

    tool_contents = [
        str(seg.content)
        for tcr in provider_request.tool_calls_result
        for seg in tcr.tool_calls_result
    ]
    assert tool_contents
    assert "工具执行结果" in tool_contents[0]
    assert any(
        content.startswith("[tool-result-deduplicated]") for content in tool_contents[1:]
    )


@pytest.mark.asyncio
async def test_repeated_tool_output_dedup_can_be_disabled(
    runner, mock_provider, provider_request, mock_tool_executor, mock_hooks
):
    """测试关闭去重配置后，重复工具输出保持原样。"""

    mock_provider.should_call_tools = True
    mock_provider.max_calls_before_normal_response = 3

    await runner.reset(
        provider=mock_provider,
        request=provider_request,
        run_context=ContextWrapper(context=None),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
        deduplicate_repeated_tool_results=False,
    )

    async for _ in runner.step_until_done(6):
        pass

    assert provider_request.tool_calls_result is not None
    assert isinstance(provider_request.tool_calls_result, list)

    tool_contents = [
        str(seg.content)
        for tcr in provider_request.tool_calls_result
        for seg in tcr.tool_calls_result
    ]
    assert tool_contents
    assert sum(1 for content in tool_contents if content == "工具执行结果") >= 2
    assert not any(
        content.startswith("[tool-result-deduplicated]") for content in tool_contents
    )


@pytest.mark.asyncio
async def test_missing_required_tool_args_are_reported_without_handler_typeerror(
    runner, provider_request_required_query, mock_tool_executor, mock_hooks
):
    provider = MockMissingRequiredArgProvider()

    await runner.reset(
        provider=provider,
        request=provider_request_required_query,
        run_context=ContextWrapper(context=None),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    async for _ in runner.step_until_done(4):
        pass

    assert provider_request_required_query.tool_calls_result is not None
    assert isinstance(provider_request_required_query.tool_calls_result, list)
    contents = [
        str(seg.content)
        for tcr in provider_request_required_query.tool_calls_result
        for seg in tcr.tool_calls_result
    ]
    assert contents
    assert any("Missing required tool arguments: query" in c for c in contents)
    assert not any("Tool handler parameter mismatch" in c for c in contents)


@pytest.mark.asyncio
async def test_camel_case_tool_args_are_mapped_to_snake_case_and_executed(
    runner, mock_hooks
):
    provider = MockCamelCaseArgProvider()
    captured: dict = {}

    class CaptureToolExecutor:
        @classmethod
        def execute(cls, tool, run_context, **tool_args):
            captured.update(tool_args)

            async def generator():
                from mcp.types import CallToolResult, TextContent

                yield CallToolResult(
                    content=[TextContent(type="text", text="工具执行结果")]
                )

            return generator()

    tool = FunctionTool(
        name="test_tool",
        description="测试工具",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer"},
            },
            "required": ["query", "max_results"],
        },
        handler=AsyncMock(),
    )
    request = ProviderRequest(
        prompt="请帮我查询信息",
        func_tool=ToolSet(tools=[tool]),
        contexts=[],
    )

    await runner.reset(
        provider=provider,
        request=request,
        run_context=ContextWrapper(context=None),
        tool_executor=CaptureToolExecutor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    async for _ in runner.step_until_done(4):
        pass

    assert captured.get("query") == "123"
    assert captured.get("max_results") == 5


@pytest.mark.asyncio
async def test_anyof_contract_violation_is_reported_without_executing_tool(
    runner, mock_hooks
):
    provider = MockAnyOfViolationProvider()
    executed = {"called": False}

    class CaptureToolExecutor:
        @classmethod
        def execute(cls, tool, run_context, **tool_args):
            executed["called"] = True

            async def generator():
                from mcp.types import CallToolResult, TextContent

                yield CallToolResult(
                    content=[TextContent(type="text", text="工具执行结果")]
                )

            return generator()

    tool = FunctionTool(
        name="test_tool",
        description="测试工具",
        parameters={
            "type": "object",
            "properties": {
                "note": {"type": "string"},
                "cron_expression": {"type": "string"},
                "run_at": {"type": "string"},
            },
            "required": ["note"],
            "anyOf": [
                {"required": ["cron_expression"]},
                {"required": ["run_at"]},
            ],
        },
        handler=AsyncMock(),
    )
    request = ProviderRequest(
        prompt="请帮我创建未来任务",
        func_tool=ToolSet(tools=[tool]),
        contexts=[],
    )

    await runner.reset(
        provider=provider,
        request=request,
        run_context=ContextWrapper(context=None),
        tool_executor=CaptureToolExecutor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    async for _ in runner.step_until_done(4):
        pass

    assert executed["called"] is False
    assert request.tool_calls_result is not None
    contents = [
        str(seg.content)
        for tcr in request.tool_calls_result
        for seg in tcr.tool_calls_result
    ]
    assert any("Argument contract violation (anyOf)" in c for c in contents)


@pytest.mark.asyncio
async def test_incompatible_tool_args_are_rejected_early(
    runner, mock_hooks
):
    provider = MockIncompatibleArgsProvider()
    executed = {"called": False}

    class CaptureToolExecutor:
        @classmethod
        def execute(cls, tool, run_context, **tool_args):
            executed["called"] = True

            async def generator():
                from mcp.types import CallToolResult, TextContent

                yield CallToolResult(
                    content=[TextContent(type="text", text="工具执行结果")]
                )

            return generator()

    tool = FunctionTool(
        name="test_tool",
        description="测试工具",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        handler=AsyncMock(),
    )
    request = ProviderRequest(
        prompt="请帮我查询信息",
        func_tool=ToolSet(tools=[tool]),
        contexts=[],
    )

    await runner.reset(
        provider=provider,
        request=request,
        run_context=ContextWrapper(context=None),
        tool_executor=CaptureToolExecutor,
        agent_hooks=mock_hooks,
        streaming=False,
    )

    async for _ in runner.step_until_done(4):
        pass

    assert executed["called"] is False
    assert request.tool_calls_result is not None
    contents = [
        str(seg.content)
        for tcr in request.tool_calls_result
        for seg in tcr.tool_calls_result
    ]
    assert any("No compatible arguments for this tool" in c for c in contents)


@pytest.mark.asyncio
async def test_tool_error_repeat_guard_disables_tools_and_forces_direct_answer(
    runner, mock_provider, provider_request, mock_error_tool_executor, mock_hooks
):
    mock_provider.should_call_tools = True
    mock_provider.max_calls_before_normal_response = 100

    await runner.reset(
        provider=mock_provider,
        request=provider_request,
        run_context=ContextWrapper(context=None),
        tool_executor=mock_error_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
        tool_error_repeat_guard_threshold=2,
    )

    async for _ in runner.step_until_done(6):
        pass

    assert runner.done()
    assert runner.req.func_tool is None
    assert mock_provider.call_count <= 3
    assert any(
        m.role == "user"
        and isinstance(m.content, str)
        and "Tool call error loop detected" in m.content
        for m in runner.run_context.messages
    )


@pytest.mark.asyncio
async def test_tool_error_repeat_guard_can_be_disabled(
    runner, mock_provider, provider_request, mock_error_tool_executor, mock_hooks
):
    mock_provider.should_call_tools = True
    mock_provider.max_calls_before_normal_response = 3

    await runner.reset(
        provider=mock_provider,
        request=provider_request,
        run_context=ContextWrapper(context=None),
        tool_executor=mock_error_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
        tool_error_repeat_guard_threshold=0,
    )

    async for _ in runner.step_until_done(8):
        pass

    assert runner.done()
    assert runner.req.func_tool is not None
    assert not any(
        m.role == "user"
        and isinstance(m.content, str)
        and "Tool call error loop detected" in m.content
        for m in runner.run_context.messages
    )


@pytest.mark.asyncio
async def test_tool_result_dedup_cache_is_pruned_when_exceeding_limit(
    runner, mock_provider, provider_request, mock_tool_executor, mock_hooks
):
    await runner.reset(
        provider=mock_provider,
        request=provider_request,
        run_context=ContextWrapper(context=None),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
        tool_result_dedup_max_entries=2,
    )

    runner._deduplicate_tool_result_content(
        tool_name="tool_a",
        tool_args={"arg": 1},
        content="same-result",
    )
    runner._deduplicate_tool_result_content(
        tool_name="tool_b",
        tool_args={"arg": 2},
        content="same-result",
    )
    runner._deduplicate_tool_result_content(
        tool_name="tool_c",
        tool_args={"arg": 3},
        content="same-result",
    )

    assert len(runner._tool_result_dedup) == 2
    sig_a = "tool_a:" + runner._normalize_tool_args_for_signature({"arg": 1})
    assert sig_a not in runner._tool_result_dedup


@pytest.mark.asyncio
async def test_tool_result_dedup_cache_allows_unbounded_when_limit_disabled(
    runner, mock_provider, provider_request, mock_tool_executor, mock_hooks
):
    await runner.reset(
        provider=mock_provider,
        request=provider_request,
        run_context=ContextWrapper(context=None),
        tool_executor=mock_tool_executor,
        agent_hooks=mock_hooks,
        streaming=False,
        tool_result_dedup_max_entries=None,
    )

    runner._deduplicate_tool_result_content(
        tool_name="tool_a",
        tool_args={"arg": 1},
        content="same-result",
    )
    runner._deduplicate_tool_result_content(
        tool_name="tool_b",
        tool_args={"arg": 2},
        content="same-result",
    )
    runner._deduplicate_tool_result_content(
        tool_name="tool_c",
        tool_args={"arg": 3},
        content="same-result",
    )

    assert len(runner._tool_result_dedup) == 3


def test_tool_args_signature_normalization_is_stable_for_non_json_values(runner):
    class NonJsonArg:
        def __init__(self, payload: str):
            self.payload = payload

    sig_one = runner._normalize_tool_args_for_signature(
        {
            "obj": NonJsonArg("v1"),
            "tags": {"b", "a"},
        }
    )
    sig_two = runner._normalize_tool_args_for_signature(
        {
            "tags": {"a", "b"},
            "obj": NonJsonArg("v1"),
        }
    )

    assert sig_one == sig_two
    assert "0x" not in sig_one


def test_tool_args_signature_normalization_handles_recursive_structures(runner):
    recursive: list[object] = []
    recursive.append(recursive)

    signature = runner._normalize_tool_args_for_signature({"obj": recursive})

    assert "__recursive__" in signature


def test_prepare_tool_call_params_keeps_args_when_schema_has_no_properties(runner):
    tool = FunctionTool(
        name="schema_less_tool",
        description="schema less tool",
        parameters={"type": "object"},
        handler=AsyncMock(),
    )

    prepared = runner._prepare_tool_call_params(
        tool=tool,
        tool_name="schema_less_tool",
        raw_args={"query": "hello"},
    )

    assert prepared.error is None
    assert prepared.valid_params == {"query": "hello"}


def test_prepare_tool_call_params_maps_snake_case_to_camel_case_schema(runner):
    tool = FunctionTool(
        name="camel_schema_tool",
        description="camel schema tool",
        parameters={
            "type": "object",
            "properties": {
                "userId": {"type": "string"},
            },
            "required": ["userId"],
        },
        handler=AsyncMock(),
    )

    prepared = runner._prepare_tool_call_params(
        tool=tool,
        tool_name="camel_schema_tool",
        raw_args={"user_id": 1001},
    )

    assert prepared.error is None
    assert prepared.valid_params == {"userId": "1001"}
    assert prepared.ignored_params == set()


def test_tool_error_detection_supports_non_english_and_traceback_markers(runner):
    assert runner._is_tool_error_content("错误：参数缺失")
    assert runner._is_tool_error_content("Traceback (most recent call last): ...")
    assert not runner._is_tool_error_content("工具执行成功")


def test_tool_result_guard_error_count_pruning_can_use_independent_limit():
    guard = ToolResultGuard(
        ToolResultGuardConfig(
            deduplicate_repeated_tool_results=True,
            tool_result_dedup_max_entries=10,
            tool_error_repeat_guard_threshold=99,
            tool_error_repeat_count_max_entries=2,
        )
    )

    for i in range(3):
        guard.process(
            tool_name="test_tool",
            tool_args={"index": i},
            content="error: failed to execute",
        )

    assert len(guard.error_repeat_counts) == 2


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


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])
