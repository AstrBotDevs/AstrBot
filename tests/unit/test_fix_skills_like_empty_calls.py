import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.message import ToolCall
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.provider.entities import LLMResponse, ProviderRequest, TokenUsage
from astrbot.core.provider.provider import Provider


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


def test_llm_response_tool_calls_mismatched_metadata_returns_none():
    """Incomplete tool call metadata should not serialize into OpenAI tool calls."""
    response = LLMResponse(
        role="assistant",
        completion_text="test",
        tools_call_args=[{}],
        tools_call_name=["test_tool"],
        tools_call_ids=[],
    )

    assert response.to_openai_tool_calls() is None
    assert response.to_openai_to_calls_model() is None


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
        # First call: simulate the lightweight skills_like tool selection response.
        if self.call_count == 1:
            return LLMResponse(
                role="assistant",
                completion_text="Calling tool...",
                tools_call_name=["test_tool"],
                tools_call_ids=["call_1"],
                tools_call_args=[{}],
                usage=TokenUsage(output=5),
            )
        # Second call: simulate an abnormal LLM response without tool calls.
        if self.fail_with_none:
            return LLMResponse(
                role="assistant",
                completion_text="Wait, I changed my mind.",
                tools_call_name=None,
                tools_call_ids=None,
                tools_call_args=None,
                usage=TokenUsage(output=5),
            )

        return LLMResponse(
            role="assistant",
            completion_text="Wait, I changed my mind.",
            tools_call_name=[],
            tools_call_ids=[],
            tools_call_args=[],
            usage=TokenUsage(output=5),
        )

    async def text_chat_stream(self, **kwargs):
        yield await self.text_chat(**kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_with_none", [True, False])
async def test_skills_like_empty_requery_fix(fail_with_none):
    """
    Verify that an empty second parameter re-query ([] or None) in
    skills_like mode never produces an illegal empty tool_calls list and
    still preserves the original tool call from the first response.
    """
    provider = MockSkillsLikeProvider(fail_with_none=fail_with_none)

    # Prepare a single callable tool.
    tool = FunctionTool(
        name="test_tool",
        description="A test tool",
        parameters={"type": "object", "properties": {"p": {"type": "string"}}},
        handler=AsyncMock(),
    )
    tool_set = ToolSet(tools=[tool])

    # Prepare the runner and a minimal wrapped context.
    runner = ToolLoopAgentRunner()
    request = ProviderRequest(prompt="Use tool", func_tool=tool_set)

    # Mock the wrapped execution context.
    mock_context = MagicMock()
    run_context = ContextWrapper(context=mock_context)
    hooks = BaseAgentRunHooks()

    await runner.reset(
        provider=provider,
        request=request,
        run_context=run_context,
        tool_executor=MagicMock(),
        agent_hooks=hooks,
        tool_schema_mode="skills_like",
    )

    # Execute one runner step.
    async for _ in runner.step():
        pass

    # Confirm the provider was called twice so the re-query path ran.
    assert provider.call_count == 2, (
        "Provider should be called twice to exercise the re-query path"
    )

    # Even when the second response is empty, the runner should keep the
    # original tool-calling result instead of recording an empty tool_calls list.
    assistant_msgs = [m for m in runner.run_context.messages if m.role == "assistant"]
    assert assistant_msgs, "Expected at least one assistant message"

    # Every assistant message should either omit tool_calls or keep them non-empty.
    for msg in assistant_msgs:
        if hasattr(msg, "tool_calls") and msg.tool_calls is not None:
            assert len(msg.tool_calls) > 0, (
                "Assistant message has an illegal empty tool_calls list"
            )

    # The last assistant message should still carry the original tool call.
    final_assistant = assistant_msgs[-1]
    assert final_assistant.tool_calls, (
        "The final assistant message must keep a valid tool_calls payload"
    )

    # Verify that the retained tool call is the original first-round result.
    tc = final_assistant.tool_calls[0]
    if isinstance(tc, dict):
        assert tc["function"]["name"] == "test_tool"
        assert tc["id"] == "call_1"
    else:
        assert tc.function.name == "test_tool"
        assert tc.id == "call_1"

    print(
        f"TEST PASSED (fail_with_none={fail_with_none}): Verified that no empty tool_calls list was generated and the first tool call was retained."
    )
