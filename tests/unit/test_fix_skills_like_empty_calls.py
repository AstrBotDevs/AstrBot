import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.tool import ToolSet, FunctionTool
from astrbot.core.provider.entities import LLMResponse, ProviderRequest, TokenUsage
from astrbot.core.provider.provider import Provider
from astrbot.core.agent.message import Message, ToolCall

def test_llm_response_tool_calls_none_and_empty_list_behaviour():
    """
    When tools_call_args is None or an empty list, both conversion helpers
    should return None to match the OpenAI protocol expectations.
    """
    # tools_call_args = None (will be converted to [] in __init__)
    response_none = LLMResponse(
        role="assistant",
        completion_text="test",
        tools_call_args=None,
    )

    assert response_none.to_openai_tool_calls() is None
    assert response_none.to_openai_to_calls_model() is None

    # tools_call_args = []
    response_empty = LLMResponse(
        role="assistant",
        completion_text="test",
        tools_call_args=[],
    )

    assert response_empty.to_openai_tool_calls() is None
    assert response_empty.to_openai_to_calls_model() is None

def test_llm_response_tool_calls_non_empty_list_behaviour():
    """
    When tools_call_args has at least one item, both conversion helpers
    should return a non-empty list.
    """
    tools_call_args = [{"arg": "value"}]
    tools_call_name = ["test_tool"]
    tools_call_ids = ["call_1"]

    response = LLMResponse(
        role="assistant",
        completion_text="test",
        tools_call_args=tools_call_args,
        tools_call_name=tools_call_name,
        tools_call_ids=tools_call_ids,
    )

    tool_calls = response.to_openai_tool_calls()
    tool_calls_model = response.to_openai_to_calls_model()

    # Both helpers should return a non-empty list
    assert isinstance(tool_calls, list)
    assert isinstance(tool_calls_model, list)
    assert len(tool_calls) == 1
    assert len(tool_calls_model) == 1

    # Verify content
    assert tool_calls[0]["id"] == "call_1"
    assert tool_calls[0]["function"]["name"] == "test_tool"
    assert tool_calls[0]["function"]["arguments"] == json.dumps(tools_call_args[0])
    
    assert isinstance(tool_calls_model[0], ToolCall)
    assert tool_calls_model[0].id == "call_1"
    assert tool_calls_model[0].function.name == "test_tool"
    assert tool_calls_model[0].function.arguments == json.dumps(tools_call_args[0])

class MockSkillsLikeProvider(Provider):
    def __init__(self, fail_with_none=False):
        super().__init__({"id": "test"}, {})
        self.call_count = 0
        self.fail_with_none = fail_with_none

    def get_current_key(self) -> str:
        return "test_key"

    def set_key(self, key: str):
        pass

    async def get_models(self) -> list[str]:
        return ["test_model"]

    async def text_chat(self, **kwargs) -> LLMResponse:
        self.call_count += 1
        # 第一次调用：模拟 skills_like 模式下的轻量级调用，返回工具名但无参数
        if self.call_count == 1:
            return LLMResponse(
                role="assistant",
                completion_text="Calling tool...",
                tools_call_name=["test_tool"],
                tools_call_ids=["call_1"],
                tools_call_args=[{}],
                usage=TokenUsage(output=5)
            )
        # 第二次调用：模拟 LLM 异常响应，不返回任何工具调用
        if self.fail_with_none:
            return LLMResponse(
                role="assistant",
                completion_text="Wait, I changed my mind.",
                tools_call_name=None,
                tools_call_ids=None,
                tools_call_args=None,
                usage=TokenUsage(output=5)
            )
        else:
            return LLMResponse(
                role="assistant",
                completion_text="Wait, I changed my mind.",
                tools_call_name=[],
                tools_call_ids=[],
                tools_call_args=[],
                usage=TokenUsage(output=5)
            )

    async def text_chat_stream(self, **kwargs):
        yield await self.text_chat(**kwargs)

@pytest.mark.asyncio
@pytest.mark.parametrize("fail_with_none", [True, False])
async def test_skills_like_empty_requery_fix(fail_with_none):
    """
    测试在 skills_like 模式下，如果二次参数补全请求返回空（[] 或 None），
    系统是否能正确处理而不产生非法的空 tool_calls 列表，
    并且最终保留的 tool_calls 对应第一次调用而没有被空结果覆盖。
    """
    provider = MockSkillsLikeProvider(fail_with_none=fail_with_none)
    
    # 准备工具
    tool = FunctionTool(
        name="test_tool",
        description="A test tool",
        parameters={"type": "object", "properties": {"p": {"type": "string"}}},
        handler=AsyncMock()
    )
    tool_set = ToolSet(tools=[tool])
    
    # 准备 Runner
    runner = ToolLoopAgentRunner()
    request = ProviderRequest(prompt="Use tool", func_tool=tool_set)
    # 模拟 ContextWrapper
    mock_context = MagicMock()
    run_context = ContextWrapper(context=mock_context)
    hooks = BaseAgentRunHooks()
    
    await runner.reset(
        provider=provider,
        request=request,
        run_context=run_context,
        tool_executor=MagicMock(),
        agent_hooks=hooks,
        tool_schema_mode="skills_like"
    )
    
    # 执行一步
    async for _ in runner.step():
        pass
    
    # 确认 Provider 被调用了两次，以证明重试（re-query）路径生效
    assert provider.call_count == 2, "Provider should be called twice to exercise the re-query path"
    
    # 验证逻辑层修复：
    # 虽然 Provider 第二次返回了空，但 runner 应该保留或安全处理第一次的结果
    assistant_msgs = [m for m in runner.run_context.messages if m.role == "assistant"]
    assert assistant_msgs, "应至少有一条 assistant 消息"
    
    # 所有 assistant 消息要么没有 tool_calls 字段，要么为非空列表
    for msg in assistant_msgs:
        if hasattr(msg, "tool_calls") and msg.tool_calls is not None:
            assert len(msg.tool_calls) > 0, f"Assistant message has illegal empty tool_calls list!"
            
    # 最后一条 assistant 消息应保留有效的 tool_calls，且为第一次调用的工具
    final_assistant = assistant_msgs[-1]
    assert final_assistant.tool_calls, "最终 assistant 消息必须包含有效的 tool_calls"
    
    # 检查第一个 tool call 的内容是否符合预期（来自第一轮响应）
    tc = final_assistant.tool_calls[0]
    if isinstance(tc, dict):
        assert tc["function"]["name"] == "test_tool"
        assert tc["id"] == "call_1"
    else:
        # ToolCall object
        assert tc.function.name == "test_tool"
        assert tc.id == "call_1"

    print(f"TEST PASSED (fail_with_none={fail_with_none}): Verified that no empty tool_calls list was generated and first call was retained.")
