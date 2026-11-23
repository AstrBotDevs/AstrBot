"""Content safety stops blocked events and emits feedback only when addressed."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.core.pipeline.content_safety_check import stage as safety


def make_event(addressed):
    results = []
    return SimpleNamespace(
        is_at_or_wake_command=addressed,
        get_message_str=lambda: "input text",
        get_messages=lambda: [],
        set_result=Mock(side_effect=results.append),
        get_result=lambda: results[-1] if results else None,
        stop_event=Mock(),
        send=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_initialize_passes_the_content_safety_configuration(monkeypatch):
    config = {"strategy": "local"}
    selector = object()
    factory = Mock(return_value=selector)
    monkeypatch.setattr(safety, "StrategySelector", factory)
    stage = safety.ContentSafetyCheckStage()
    await stage.initialize(SimpleNamespace(astrbot_config={"content_safety": config}))
    factory.assert_called_once_with(config)
    assert stage.strategy_selector is selector


@pytest.mark.asyncio
@pytest.mark.parametrize("allowed", [True, False])
@pytest.mark.parametrize("addressed", [True, False])
async def test_safety_decision_controls_event_stop_and_feedback(allowed, addressed):
    stage = safety.ContentSafetyCheckStage()
    stage.strategy_selector = SimpleNamespace(
        check=Mock(return_value=(allowed, "test rule"))
    )
    event = make_event(addressed)
    assert await stage.process(event) is None
    stage.strategy_selector.check.assert_called_once_with("input text")
    assert event.stop_event.call_count == (0 if allowed else 1)
    assert event.set_result.call_count == (1 if addressed and not allowed else 0)
    if addressed and not allowed:
        result = event.get_result()
        event.send.assert_awaited_once_with(result)
        assert "blocked" in result.chain[0].text
    else:
        event.send.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [RuntimeError("send failed"), asyncio.CancelledError()]
)
async def test_warning_delivery_failure_stops_input_and_propagates(error):
    stage = safety.ContentSafetyCheckStage()
    stage.strategy_selector = SimpleNamespace(
        check=Mock(return_value=(False, "test rule"))
    )
    event = make_event(addressed=True)
    event.send.side_effect = error

    with pytest.raises(type(error)) as caught:
        await stage.process(event)

    assert caught.value is error
    event.stop_event.assert_called_once_with()
    event.send.assert_awaited_once_with(event.get_result())
    assert "blocked" in event.get_result().chain[0].text
