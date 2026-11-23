"""Process stage dispatches each SDK hook once and closes agent responses."""

from contextlib import aclosing
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.core.pipeline.process_stage import stage as process
from astrbot.core.provider.entities import ProviderRequest


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(process, "FILTERS", [])
    extras = {"activated_handlers": []}
    event = SimpleNamespace(
        get_ui_interaction=lambda: None,
        get_extra=lambda name, default=None: extras.get(name, default),
        set_extra=extras.__setitem__,
        is_stopped=lambda: False,
        call_llm=False,
        _has_send_oper=False,
        is_at_or_wake_command=True,
        get_result=lambda: None,
    )
    stage = process.ProcessStage()
    stage.ctx = SimpleNamespace(astrbot_config={"provider_settings": {"enable": True}})
    stage.sdk_plugin_bridge = None
    return stage, event, extras


@pytest.mark.asyncio
async def test_sdk_message_hook_runs_once_when_provider_is_disabled(setup):
    stage, event, _ = setup
    stage.ctx.astrbot_config["provider_settings"]["enable"] = False
    bridge = SimpleNamespace(
        dispatch_message=AsyncMock(
            return_value=SimpleNamespace(sent_message=True, stopped=False)
        )
    )
    stage.sdk_plugin_bridge = bridge
    stage.agent_sub_stage = SimpleNamespace(process=Mock())
    assert [item async for item in stage.process(event)] == [None]
    bridge.dispatch_message.assert_awaited_once_with(event)
    stage.agent_sub_stage.process.assert_not_called()


@pytest.mark.asyncio
async def test_sdk_llm_decision_controls_default_request(setup):
    stage, event, _ = setup
    bridge = SimpleNamespace(
        dispatch_message=AsyncMock(
            return_value=SimpleNamespace(sent_message=False, stopped=False)
        ),
        get_effective_should_call_llm=Mock(return_value=False),
        get_effective_result=Mock(return_value=None),
    )
    stage.sdk_plugin_bridge = bridge
    stage.agent_sub_stage = SimpleNamespace(process=Mock())
    assert [item async for item in stage.process(event)] == []
    bridge.dispatch_message.assert_awaited_once_with(event)
    bridge.get_effective_should_call_llm.assert_called_once_with(event)
    stage.agent_sub_stage.process.assert_not_called()


@pytest.mark.asyncio
async def test_stopped_events_do_not_dispatch_sdk_messages(setup):
    stage, event, _ = setup
    event.is_stopped = lambda: True
    stage.ctx.astrbot_config["provider_settings"]["enable"] = False
    stage.sdk_plugin_bridge = SimpleNamespace(dispatch_message=AsyncMock())
    assert [item async for item in stage.process(event)] == []
    stage.sdk_plugin_bridge.dispatch_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_plugin_request_without_agent_output_still_reaches_downstream_once(setup):
    stage, event, extras = setup
    request = ProviderRequest(prompt="plugin request")
    extras["activated_handlers"] = [object()]
    calls = []

    async def plugin_results(_event):
        event.call_llm = True
        yield request

    async def agent_results(_event):
        calls.append(extras["provider_request"])
        if False:
            yield

    stage.star_request_sub_stage = SimpleNamespace(process=plugin_results)
    stage.agent_sub_stage = SimpleNamespace(process=agent_results)
    assert [item async for item in stage.process(event)] == [None]
    assert calls == [request]


@pytest.mark.asyncio
async def test_early_pipeline_close_releases_agent_generator(setup):
    stage, event, _ = setup
    closed = []

    async def agent_results(_event):
        try:
            yield None
            pytest.fail(
                "A closed downstream consumer must not request another response"
            )
        finally:
            closed.append(True)

    stage.agent_sub_stage = SimpleNamespace(process=agent_results)
    async with aclosing(stage.process(event)) as responses:
        assert await anext(responses) is None
    assert closed == [True]
