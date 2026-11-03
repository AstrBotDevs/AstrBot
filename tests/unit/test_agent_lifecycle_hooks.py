"""Plugin registration and delivery contracts for Agent lifecycle hooks."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.api.event import filter
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.astr_agent_hooks import MainAgentHooks
from astrbot.core.pipeline import context_utils
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.star.register import star_handler as registration
from astrbot.core.star.star import StarMetadata, star_map
from astrbot.core.star.star_handler import (
    EventType,
    StarHandlerMetadata,
    StarHandlerRegistry,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decorator_name", "event_type"),
    [
        ("on_agent_step_start", EventType.OnAgentStepStartEvent),
        ("on_agent_step_end", EventType.OnAgentStepEndEvent),
        ("on_agent_done", EventType.OnAgentDoneEvent),
    ],
)
async def test_public_lifecycle_hooks_use_existing_plugin_registry(
    monkeypatch, decorator_name, event_type
):
    """Public decorators preserve priority, session policy and plugin activation."""
    registry = StarHandlerRegistry()
    monkeypatch.setattr(registration, "star_handlers_registry", registry)
    monkeypatch.setattr(context_utils, "star_handlers_registry", registry)
    calls = []
    for name, priority in (
        ("low", 0),
        ("high", 10),
        ("excluded", 100),
        ("disabled", 100),
    ):
        module = f"test_lifecycle.{name}"
        monkeypatch.setitem(
            star_map,
            module,
            StarMetadata(name=name, activated=name != "disabled"),
        )

        async def handler(event, *args, plugin_name=name):
            calls.append(plugin_name)

        handler.__module__ = module
        getattr(filter, decorator_name)(priority=priority)(handler)

    event = MagicMock(plugins_name=["low", "high", "disabled"])
    event.is_stopped.return_value = False
    rc = ContextWrapper(context=SimpleNamespace(event=event))
    args = (rc, None) if event_type == EventType.OnAgentDoneEvent else (rc,)
    await context_utils.call_event_hook(event, event_type, *args)
    assert calls == ["high", "low"]


@pytest.mark.asyncio
async def test_done_notifies_all_cleanup_handlers_on_stopped_event(monkeypatch):
    """A session stop must not short-circuit the remaining completion handlers."""
    registry = StarHandlerRegistry()
    monkeypatch.setattr(context_utils, "star_handlers_registry", registry)
    hooks = []
    for index in range(2):
        module = f"test_done.{index}"
        monkeypatch.setitem(star_map, module, StarMetadata(name=module))
        handler = AsyncMock()
        hooks.append(handler)
        registry.append(
            StarHandlerMetadata(
                event_type=EventType.OnAgentDoneEvent,
                handler_full_name=module,
                handler_name="cleanup",
                handler_module_path=module,
                handler=handler,
                event_filters=[],
            )
        )
    event = MagicMock(plugins_name=None)
    event.is_stopped.return_value = True
    rc = ContextWrapper(
        context=SimpleNamespace(event=event), run_end_reason="cancelled"
    )
    await MainAgentHooks().on_agent_done(rc, None)
    for handler in hooks:
        handler.assert_awaited_once_with(event, rc, None)


@pytest.mark.asyncio
async def test_plugin_hook_dispatch_preserves_task_cancellation(monkeypatch):
    """The event dispatcher must not swallow cancellation inside a plugin hook."""
    registry = StarHandlerRegistry()
    monkeypatch.setattr(context_utils, "star_handlers_registry", registry)
    module = "test_cancellable_hook"
    monkeypatch.setitem(star_map, module, StarMetadata(name=module))
    started = asyncio.Event()

    async def handler(event, rc):
        started.set()
        await asyncio.Future()

    registry.append(
        StarHandlerMetadata(
            event_type=EventType.OnAgentStepStartEvent,
            handler_full_name=module,
            handler_name="checkpoint",
            handler_module_path=module,
            handler=handler,
            event_filters=[],
        )
    )
    event = MagicMock(plugins_name=None)
    event.is_stopped.return_value = False
    rc = ContextWrapper(context=SimpleNamespace(event=event))
    task = asyncio.create_task(MainAgentHooks().on_agent_step_start(rc))
    await asyncio.wait_for(started.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 2)


@pytest.mark.asyncio
async def test_response_and_done_notifications_are_independent(monkeypatch):
    """Failure cleanup is not an LLM response; normal replies remain editable."""
    dispatch = AsyncMock()
    monkeypatch.setattr("astrbot.core.astr_agent_hooks.call_event_hook", dispatch)
    event = MagicMock()
    rc = ContextWrapper(context=SimpleNamespace(event=event))
    hooks = MainAgentHooks()
    await hooks.on_agent_done(rc, None)
    dispatch.assert_awaited_once_with(event, EventType.OnAgentDoneEvent, rc, None)
    dispatch.reset_mock()
    response = LLMResponse(
        role="assistant", completion_text="done", reasoning_content="reason"
    )
    await hooks.on_llm_response(rc, response)
    await hooks.on_agent_done(rc, response)
    assert [call.args[1] for call in dispatch.await_args_list] == [
        EventType.OnLLMResponseEvent,
        EventType.OnAgentDoneEvent,
    ]
    event.set_extra.assert_called_once_with("_llm_reasoning_content", "reason")
