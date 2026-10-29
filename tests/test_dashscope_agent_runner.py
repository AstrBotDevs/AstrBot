from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from dashscope.app.application_response import ApplicationOutput, ApplicationResponse

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runners.dashscope import dashscope_agent_runner as runner_module
from astrbot.core.provider.entities import ProviderRequest


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
async def test_configured_timeout_is_forwarded_to_application(monkeypatch, streaming):
    """Pass the configured timeout to the SDK in both response modes."""
    monkeypatch.setattr(
        runner_module,
        "sp",
        SimpleNamespace(
            get_async=AsyncMock(side_effect=lambda **kwargs: kwargs["default"]),
        ),
    )
    response = ApplicationResponse(
        status_code=200, output=ApplicationOutput(text="hello", session_id="")
    )
    call = Mock(return_value=iter([response]) if streaming else response)
    monkeypatch.setattr(runner_module.Application, "call", call)
    runner = runner_module.DashscopeAgentRunner()
    await runner.reset(
        request=ProviderRequest(prompt="hello", session_id="test-session"),
        run_context=ContextWrapper(context=None),
        agent_hooks=SimpleNamespace(
            on_agent_begin=AsyncMock(), on_agent_done=AsyncMock()
        ),
        provider_config={
            "dashscope_api_key": "test-key",
            "dashscope_app_id": "test-app",
            "dashscope_app_type": "agent",
            "timeout": "1",
        },
        streaming=streaming,
    )

    responses = [response async for response in runner.step_until_done()]

    call.assert_called_once()
    assert call.call_args.kwargs["request_timeout"] == 1
    assert call.call_args.kwargs["stream"] is streaming
    assert responses[-1].type == "llm_result"
