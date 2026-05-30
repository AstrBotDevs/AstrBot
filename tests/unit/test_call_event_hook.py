"""Tests for call_event_hook timeout protection."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.pipeline.context_utils import _DEFAULT_HOOK_TIMEOUT, call_event_hook
from astrbot.core.star.star_handler import EventType


def _make_handler_metadata(
    handler_coro, module_path="test_module", handler_name="test_handler"
):
    handler = MagicMock()
    handler.handler_module_path = module_path
    handler.handler_name = handler_name
    handler.handler = handler_coro
    handler.enabled = True
    return handler


def _make_event(stopped=False, plugins_name=None):
    event = MagicMock()
    event.unified_msg_origin = "test_umo"
    event.plugins_name = plugins_name or []
    event.is_stopped = MagicMock(return_value=stopped)
    return event


@pytest.fixture
def mock_star_map():
    with patch("astrbot.core.pipeline.context_utils.star_map") as sm:
        sm.__getitem__ = MagicMock(return_value=MagicMock(name="TestPlugin"))
        yield sm


@pytest.fixture
def mock_handlers_registry():
    with patch(
        "astrbot.core.pipeline.context_utils.star_handlers_registry"
    ) as registry:
        yield registry


@pytest.mark.asyncio
async def test_hook_completes_within_timeout(mock_star_map, mock_handlers_registry):
    handler_fn = AsyncMock()
    handler_md = _make_handler_metadata(handler_fn)
    mock_handlers_registry.get_handlers_by_event_type = MagicMock(
        return_value=[handler_md]
    )
    event = _make_event()

    result = await call_event_hook(event, EventType.OnLLMRequestEvent, hook_timeout=5.0)

    handler_fn.assert_awaited_once()
    assert result is False


@pytest.mark.asyncio
async def test_hook_timeout_skips_handler(mock_star_map, mock_handlers_registry):
    async def stuck_handler(*args, **kwargs):
        event = asyncio.Event()
        await event.wait()

    handler_md = _make_handler_metadata(stuck_handler)
    mock_handlers_registry.get_handlers_by_event_type = MagicMock(
        return_value=[handler_md]
    )
    event = _make_event()

    result = await call_event_hook(event, EventType.OnLLMRequestEvent, hook_timeout=0.5)

    assert result is False


@pytest.mark.asyncio
async def test_hook_timeout_does_not_block_subsequent_handlers(
    mock_star_map, mock_handlers_registry
):
    async def stuck_handler(*args, **kwargs):
        event = asyncio.Event()
        await event.wait()

    fast_handler_fn = AsyncMock()
    slow_md = _make_handler_metadata(
        stuck_handler, module_path="slow_mod", handler_name="slow_h"
    )
    fast_md = _make_handler_metadata(
        fast_handler_fn, module_path="fast_mod", handler_name="fast_h"
    )
    mock_handlers_registry.get_handlers_by_event_type = MagicMock(
        return_value=[slow_md, fast_md]
    )
    event = _make_event()

    result = await call_event_hook(event, EventType.OnLLMRequestEvent, hook_timeout=0.5)

    fast_handler_fn.assert_awaited_once()
    assert result is False


@pytest.mark.asyncio
async def test_hook_timeout_zero_disables_timeout(
    mock_star_map, mock_handlers_registry
):
    async def slow_handler(*args, **kwargs):
        await asyncio.sleep(0.3)

    handler_md = _make_handler_metadata(slow_handler)
    mock_handlers_registry.get_handlers_by_event_type = MagicMock(
        return_value=[handler_md]
    )
    event = _make_event()

    result = await call_event_hook(event, EventType.OnLLMRequestEvent, hook_timeout=0)

    assert result is False


@pytest.mark.asyncio
async def test_hook_timeout_negative_disables_timeout(
    mock_star_map, mock_handlers_registry
):
    async def slow_handler(*args, **kwargs):
        await asyncio.sleep(0.3)

    handler_md = _make_handler_metadata(slow_handler)
    mock_handlers_registry.get_handlers_by_event_type = MagicMock(
        return_value=[handler_md]
    )
    event = _make_event()

    result = await call_event_hook(event, EventType.OnLLMRequestEvent, hook_timeout=-1)

    assert result is False


@pytest.mark.asyncio
async def test_hook_exception_continues(mock_star_map, mock_handlers_registry):
    async def failing_handler(*args, **kwargs):
        raise RuntimeError("test error")

    handler_md = _make_handler_metadata(failing_handler)
    mock_handlers_registry.get_handlers_by_event_type = MagicMock(
        return_value=[handler_md]
    )
    event = _make_event()

    result = await call_event_hook(event, EventType.OnLLMRequestEvent)

    assert result is False


@pytest.mark.asyncio
async def test_hook_stops_event_propagation(mock_star_map, mock_handlers_registry):
    handler_fn = AsyncMock()
    handler_md = _make_handler_metadata(handler_fn)
    mock_handlers_registry.get_handlers_by_event_type = MagicMock(
        return_value=[handler_md]
    )
    event = _make_event(stopped=True)

    result = await call_event_hook(event, EventType.OnLLMRequestEvent)

    assert result is True


@pytest.mark.asyncio
async def test_default_timeout_value():
    assert _DEFAULT_HOOK_TIMEOUT == 300.0


@pytest.mark.asyncio
async def test_timeout_logs_plugin_name(mock_star_map, mock_handlers_registry):
    async def stuck_handler(*args, **kwargs):
        event = asyncio.Event()
        await event.wait()

    handler_md = _make_handler_metadata(
        stuck_handler, module_path="my_plugin_module", handler_name="on_llm_req"
    )
    mock_handlers_registry.get_handlers_by_event_type = MagicMock(
        return_value=[handler_md]
    )
    event = _make_event()

    with patch("astrbot.core.pipeline.context_utils.logger") as mock_logger:
        await call_event_hook(event, EventType.OnLLMRequestEvent, hook_timeout=0.2)

    warning_calls = [
        call for call in mock_logger.warning.call_args_list if "timed out" in str(call)
    ]
    assert len(warning_calls) == 1
    warning_msg = str(warning_calls[0])
    assert "on_llm_req" in warning_msg


@pytest.mark.asyncio
async def test_args_kwargs_passed_to_handler(mock_star_map, mock_handlers_registry):
    handler_fn = AsyncMock()
    handler_md = _make_handler_metadata(handler_fn)
    mock_handlers_registry.get_handlers_by_event_type = MagicMock(
        return_value=[handler_md]
    )
    event = _make_event()

    extra_arg = MagicMock()
    await call_event_hook(
        event,
        EventType.OnLLMRequestEvent,
        extra_arg,
        hook_timeout=5.0,
        extra_kwarg="test",
    )

    handler_fn.assert_awaited_once()
    call_args = handler_fn.call_args
    assert call_args[0][0] is event
    assert call_args[0][1] is extra_arg
    assert call_args[1].get("extra_kwarg") == "test"


@pytest.mark.asyncio
async def test_timeout_none_falls_back_to_default(
    mock_star_map, mock_handlers_registry
):
    handler_fn = AsyncMock()
    handler_md = _make_handler_metadata(handler_fn)
    mock_handlers_registry.get_handlers_by_event_type = MagicMock(
        return_value=[handler_md]
    )
    event = _make_event()

    result = await call_event_hook(
        event, EventType.OnLLMRequestEvent, hook_timeout=None
    )

    handler_fn.assert_awaited_once()
    assert result is False


@pytest.mark.asyncio
async def test_timeout_string_falls_back_to_default(
    mock_star_map, mock_handlers_registry
):
    handler_fn = AsyncMock()
    handler_md = _make_handler_metadata(handler_fn)
    mock_handlers_registry.get_handlers_by_event_type = MagicMock(
        return_value=[handler_md]
    )
    event = _make_event()

    result = await call_event_hook(
        event, EventType.OnLLMRequestEvent, hook_timeout="30"
    )

    handler_fn.assert_awaited_once()
    assert result is False
