import pytest

from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.agent.tool_executor import BaseFunctionToolExecutor
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial


@pytest.mark.asyncio
async def test_persistent_history_is_not_replaced_by_trimmed_request_context():
    provider = ProviderOpenAIOfficial(
        provider_config={
            "id": "test-openai",
            "type": "openai_chat_completion",
            "model": "gpt-4o-mini",
            "key": ["test-key"],
        },
        provider_settings={},
    )
    request = ProviderRequest(
        prompt="current request",
        contexts=[
            {"role": "user", "content": "old request"},
            {"role": "assistant", "content": "old response"},
        ],
    )
    try:
        runner = ToolLoopAgentRunner()
        await runner.reset(
            provider=provider,
            request=request,
            run_context=ContextWrapper(context=None),
            tool_executor=BaseFunctionToolExecutor(),
            agent_hooks=BaseAgentRunHooks(),
        )

        runner.run_context.messages = runner.run_context.messages[-1:]

        assert [message.role for message in runner.get_persistent_messages()] == [
            "user",
            "assistant",
            "user",
        ]
    finally:
        await provider.terminate()
