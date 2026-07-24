from types import SimpleNamespace

import pytest
from mcp.types import CallToolResult, TextContent

from astrbot.core.agent.execution_policy import (
    AGENT_EXECUTION_POLICY_EXTRA_KEY,
    AGENT_TOOL_AUTHORIZATION_EXTRA_KEY,
)
from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.provider.entities import LLMResponse, ProviderRequest, TokenUsage
from astrbot.core.provider.provider import Provider


class _Event:
    def __init__(self) -> None:
        self.extras = {
            AGENT_EXECUTION_POLICY_EXTRA_KEY: {
                "route": "standard",
                "provider_id": "test",
                "allowed_tools": ["test_tool"],
                "knowledge_mode": "off",
                "max_steps": 3,
                "tool_timeout_seconds": 10,
                "request_max_retries": 0,
                "principal_id": "test:user",
                "permission_snapshot": {"role": "member"},
            }
        }

    def get_extra(self, key: str, default=None):
        return self.extras.get(key, default)

    def set_extra(self, key: str, value) -> None:
        self.extras[key] = value


class _Provider(Provider):
    def __init__(self) -> None:
        super().__init__({"id": "test"}, {})
        self.calls = 0

    async def get_models(self) -> list[str]:
        return ["test"]

    def get_current_key(self) -> str:
        return "test-key"

    def set_key(self, key: str) -> None:
        return None

    async def text_chat(self, **kwargs) -> LLMResponse:
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                role="assistant",
                completion_text="",
                tools_call_name=["test_tool"],
                tools_call_args=[{"query": "value"}],
                tools_call_ids=["call_1"],
                usage=TokenUsage(input_other=1, output=1),
            )
        return LLMResponse(
            role="assistant",
            completion_text="done",
            usage=TokenUsage(input_other=1, output=1),
        )

    async def text_chat_stream(self, **kwargs):
        yield await self.text_chat(**kwargs)


class _RepairProvider(_Provider):
    async def text_chat(self, **kwargs) -> LLMResponse:
        self.calls += 1
        if self.calls == 1:
            args = {}
        elif self.calls == 2:
            args = {"query": "corrected"}
        else:
            return LLMResponse(role="assistant", completion_text="done")
        return LLMResponse(
            role="assistant",
            completion_text="",
            tools_call_name=["test_tool"],
            tools_call_args=[args],
            tools_call_ids=[f"call_{self.calls}"],
        )


class _Executor:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, tool, run_context, **tool_args):
        async def _run():
            self.calls += 1
            yield CallToolResult(content=[TextContent(type="text", text="executed")])

        return _run()


class _Hooks(BaseAgentRunHooks):
    def __init__(self, authorization: bool | None) -> None:
        self.authorization = authorization

    async def on_agent_begin(self, run_context) -> None:
        return None

    async def on_tool_start(self, run_context, tool, tool_args) -> None:
        if self.authorization is None:
            return
        run_context.context.event.set_extra(
            AGENT_TOOL_AUTHORIZATION_EXTRA_KEY,
            {
                "tool_name": tool.name,
                "allowed": self.authorization,
                "message": "denied by test policy",
            },
        )

    async def on_tool_end(self, run_context, tool, tool_args, tool_result) -> None:
        return None

    async def on_agent_done(self, run_context, llm_response) -> None:
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("authorization", "expected_calls"),
    [(True, 1), (False, 0), (None, 0)],
)
async def test_controlled_tool_execution_is_fail_closed(
    authorization: bool | None, expected_calls: int
) -> None:
    event = _Event()
    provider = _Provider()
    executor = _Executor()
    tool = FunctionTool(
        name="test_tool",
        description="test",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
        },
    )
    runner = ToolLoopAgentRunner()
    await runner.reset(
        provider=provider,
        request=ProviderRequest(
            prompt="test",
            contexts=[],
            func_tool=ToolSet(tools=[tool]),
        ),
        run_context=ContextWrapper(context=SimpleNamespace(event=event)),
        tool_executor=executor,
        agent_hooks=_Hooks(authorization),
        streaming=False,
    )

    async for _ in runner.step_until_done(3):
        pass

    assert executor.calls == expected_calls


@pytest.mark.asyncio
async def test_invalid_tool_arguments_are_repaired_before_execution() -> None:
    event = _Event()
    provider = _RepairProvider()
    executor = _Executor()
    tool = FunctionTool(
        name="test_tool",
        description="test",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
    runner = ToolLoopAgentRunner()
    await runner.reset(
        provider=provider,
        request=ProviderRequest(
            prompt="test",
            contexts=[],
            func_tool=ToolSet(tools=[tool]),
        ),
        run_context=ContextWrapper(context=SimpleNamespace(event=event)),
        tool_executor=executor,
        agent_hooks=_Hooks(True),
        streaming=False,
    )

    async for _ in runner.step_until_done(4):
        pass

    assert provider.calls == 3
    assert executor.calls == 1
