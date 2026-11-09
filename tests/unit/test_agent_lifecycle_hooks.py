"""Plugin registration and delivery contracts for Agent lifecycle hooks."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.astr_agent_runtime.hooks import MainAgentHooks
from astrbot.core.pipeline import context_utils
from astrbot.core.star.star import StarMetadata, star_map
from astrbot.core.star.star_handler import (
    EventType,
    StarHandlerMetadata,
    StarHandlerRegistry,
)


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

    async def handler(event, rc, response):
        started.set()
        await asyncio.Future()

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
    event.is_stopped.return_value = False
    rc = ContextWrapper(context=SimpleNamespace(event=event))
    task = asyncio.create_task(MainAgentHooks().on_agent_done(rc, None))
    await asyncio.wait_for(started.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 2)
