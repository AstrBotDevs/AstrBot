"""Coze runner validation and cleanup at its transport boundary."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runners.base import AgentState
from astrbot.core.agent.runners.coze.coze_agent_runner import CozeAgentRunner
from astrbot.core.provider.entities import ProviderRequest


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "config,error",
    [
        ({}, "API Key"),
        ({"coze_api_key": "key"}, "Bot ID"),
        (
            {"coze_api_key": "key", "bot_id": "bot", "coze_api_base": "invalid"},
            "Base URL",
        ),
    ],
)
async def test_invalid_config_is_rejected_before_client_creation(config, error):
    runner = CozeAgentRunner()
    with pytest.raises(Exception, match=error):
        await runner.reset(
            ProviderRequest(prompt="hello"),
            ContextWrapper(context=None),
            BaseAgentRunHooks(),
            config,
        )
    assert not hasattr(runner, "api_client")


@pytest.fixture
def coze_runner():
    return CozeAgentRunner(), AsyncMock(spec=BaseAgentRunHooks)


@pytest.mark.asyncio
async def test_reset_normalizes_timeout_and_clears_previous_result(coze_runner):
    runner, hooks = coze_runner
    request = ProviderRequest(prompt="hello")
    await runner.reset(
        request,
        ContextWrapper(context=None),
        hooks,
        {
            "coze_api_key": "key",
            "bot_id": "bot",
            "timeout": "9",
            "auto_save_history": False,
        },
        streaming=True,
    )
    assert runner.req is request and runner.timeout == 9
    assert runner.streaming and runner.auto_save_history is False
    assert runner.state == AgentState.IDLE and not runner.done()
    assert runner.get_final_llm_resp() is None
    assert runner.api_client.session is None


@pytest.mark.asyncio
@pytest.mark.parametrize("exit_mode", ["error", "cancel"])
async def test_step_closes_transport_on_failure_or_cancellation(
    coze_runner, monkeypatch, exit_mode
):
    runner, hooks = coze_runner
    await runner.reset(
        ProviderRequest(prompt="hello"),
        ContextWrapper(context=None),
        hooks,
        {"coze_api_key": "key", "bot_id": "bot"},
    )
    close = AsyncMock()
    runner.api_client = SimpleNamespace(close=close)
    entered = asyncio.Event()

    async def request():
        entered.set()
        if exit_mode == "error":
            raise OSError("controlled failure")
        await asyncio.Event().wait()
        yield None

    monkeypatch.setattr(runner, "_execute_coze_request", request)
    stream = runner.step()
    pending = asyncio.create_task(anext(stream))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        if exit_mode == "error":
            result = await asyncio.wait_for(pending, 2)
            assert result.type == "err"
            assert runner.state == AgentState.ERROR and runner.done()
            assert "controlled failure" in runner.get_final_llm_resp().completion_text
        else:
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(pending, 2)
    finally:
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        await stream.aclose()
    close.assert_awaited_once()
    hooks.on_agent_begin.assert_awaited_once()
