"""Dashscope validates application settings and isolates RAG option mutation."""

from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runners.base import AgentState
from astrbot.core.agent.runners.dashscope.dashscope_agent_runner import (
    DashscopeAgentRunner,
)
from astrbot.core.provider.entities import ProviderRequest


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "missing,label",
    [
        ("dashscope_api_key", "API Key"),
        ("dashscope_app_id", "APP ID"),
        ("dashscope_app_type", "APP 类型"),
    ],
)
async def test_reset_requires_each_application_field(missing, label):
    config = {
        "dashscope_api_key": "key",
        "dashscope_app_id": "application",
        "dashscope_app_type": "agent",
    }
    config.pop(missing)
    with pytest.raises(Exception, match=label):
        await DashscopeAgentRunner().reset(
            MagicMock(),
            ProviderRequest(prompt="hello"),
            ContextWrapper(context=None),
            MagicMock(),
            BaseAgentRunHooks(),
            provider_config=config,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rag,has_rag",
    [
        ({}, False),
        ({"pipeline_ids": []}, False),
        ({"pipeline_ids": ["pipeline"]}, True),
        ({"file_ids": ["file"]}, True),
    ],
)
async def test_reset_normalizes_timeout_and_keeps_caller_rag_options(rag, has_rag):
    config = {
        "dashscope_api_key": "key",
        "dashscope_app_id": "application",
        "dashscope_app_type": "agent",
        "timeout": "8",
        "rag_options": {**rag, "output_reference": True},
    }
    original = deepcopy(config)
    runner = DashscopeAgentRunner()
    await runner.reset(
        MagicMock(),
        ProviderRequest(prompt="hello"),
        ContextWrapper(context=None),
        MagicMock(),
        BaseAgentRunHooks(),
        provider_config=config,
        streaming=True,
    )
    assert runner.timeout == 8 and runner.streaming and runner.output_reference
    assert runner.rag_options == rag and runner.has_rag_options() is has_rag
    assert config == original
    assert runner.state == AgentState.IDLE and not runner.done()
    assert runner.get_final_llm_resp() is None


@pytest.mark.asyncio
async def test_transport_failure_sets_terminal_error(monkeypatch):
    runner = DashscopeAgentRunner()
    hooks = AsyncMock(spec=BaseAgentRunHooks)
    await runner.reset(
        MagicMock(),
        ProviderRequest(prompt="hello"),
        ContextWrapper(context=None),
        MagicMock(),
        hooks,
        provider_config={
            "dashscope_api_key": "key",
            "dashscope_app_id": "application",
            "dashscope_app_type": "agent",
        },
    )

    async def fail():
        raise OSError("controlled failure")
        yield None

    monkeypatch.setattr(runner, "_execute_dashscope_request", fail)
    responses = [response async for response in runner.step()]
    assert len(responses) == 1 and responses[0].type == "err"
    assert runner.state == AgentState.ERROR and runner.done()
    assert "controlled failure" in runner.get_final_llm_resp().completion_text
    hooks.on_agent_begin.assert_awaited_once()
