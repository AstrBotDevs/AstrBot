from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.message.components import Plain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.pipeline.process_stage.method.agent_sub_stages import (
    internal as internal_module,
)
from astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal import (
    InternalAgentSubStage,
)


class ConcreteAstrMessageEvent(AstrMessageEvent):
    async def send(self, message):
        await super().send(message)


@pytest.fixture
def mock_ctx():
    plugin_context = MagicMock()
    plugin_context.conversation_manager = MagicMock()
    plugin_context.get_config.return_value = {"timezone": "UTC"}
    plugin_context.get_using_tts_provider.return_value = None

    ctx = MagicMock()
    ctx.astrbot_config = {
        "provider_settings": {
            "streaming_response": False,
            "unsupported_streaming_strategy": "turn_off",
            "max_context_length": 32,
            "dequeue_context_length": 4,
        },
        "kb_agentic_mode": False,
        "subagent_orchestrator": {},
    }
    ctx.plugin_manager.context = plugin_context
    return ctx


@pytest.fixture
def stage(mock_ctx):
    async def _make_stage():
        obj = InternalAgentSubStage()
        await obj.initialize(mock_ctx)
        obj._save_to_history = AsyncMock()
        return obj

    return _make_stage


@pytest.fixture
def event():
    platform_meta = PlatformMetadata(
        name="test_platform",
        description="Test platform",
        id="test_platform_id",
        support_streaming_message=False,
    )
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.self_id = "bot123"
    message.session_id = "session123"
    message.message_id = "msg123"
    message.sender = MessageMember(user_id="user123", nickname="TestUser")
    message.message = [Plain(text="Hello world")]
    message.message_str = "Hello world"
    message.raw_message = None
    return ConcreteAstrMessageEvent(
        message_str="Hello world",
        message_obj=message,
        platform_meta=platform_meta,
        session_id="session123",
    )


@asynccontextmanager
async def fake_lock(_umo):
    yield


def make_build_result() -> SimpleNamespace:
    provider = MagicMock()
    provider.provider_config = {"id": "provider-1", "api_base": ""}
    provider.get_model.return_value = "test-model"
    provider.meta.return_value = SimpleNamespace(type="test")

    final_resp = SimpleNamespace(
        completion_text="done",
        result_chain=None,
        role="assistant",
        usage=None,
    )
    agent_runner = MagicMock()
    agent_runner.done.return_value = True
    agent_runner.was_aborted.return_value = False
    agent_runner.get_final_llm_resp.return_value = final_resp
    agent_runner.run_context = SimpleNamespace(messages=[])
    agent_runner.stats = MagicMock()
    agent_runner.stats.to_dict.return_value = {}
    agent_runner.provider = provider

    return SimpleNamespace(
        agent_runner=agent_runner,
        provider_request=SimpleNamespace(
            system_prompt="sys",
            func_tool=None,
            conversation=object(),
            tool_calls_result=None,
        ),
        provider=provider,
        reset_coro=None,
    )


async def empty_run_agent(*args, **kwargs):
    if False:
        yield None


@pytest.mark.asyncio
async def test_process_swallows_send_typing_error_and_still_releases(stage, event):
    event.send_typing = AsyncMock(side_effect=RuntimeError("boom"))
    event.stop_typing = AsyncMock()
    obj = await stage()

    with (
        patch.object(internal_module.logger, "warning") as warning_mock,
        patch.object(internal_module, "try_capture_follow_up", return_value=None),
        patch.object(internal_module, "call_event_hook", AsyncMock(return_value=False)),
        patch.object(internal_module.session_lock_manager, "acquire_lock", fake_lock),
        patch.object(internal_module, "build_main_agent", AsyncMock(return_value=None)),
    ):
        results = [item async for item in obj.process(event, provider_wake_prefix="")]

    assert results == []
    event.stop_typing.assert_awaited_once()
    warning_mock.assert_called_once_with("send_typing failed", exc_info=True)


@pytest.mark.asyncio
async def test_process_releases_typing_when_build_returns_none(stage, event):
    event.send_typing = AsyncMock()
    event.stop_typing = AsyncMock()
    obj = await stage()

    with (
        patch.object(internal_module, "try_capture_follow_up", return_value=None),
        patch.object(internal_module, "call_event_hook", AsyncMock(return_value=False)),
        patch.object(internal_module.session_lock_manager, "acquire_lock", fake_lock),
        patch.object(internal_module, "build_main_agent", AsyncMock(return_value=None)),
    ):
        results = [item async for item in obj.process(event, provider_wake_prefix="")]

    assert results == []
    event.send_typing.assert_awaited_once()
    event.stop_typing.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_releases_typing_when_llm_request_hook_short_circuits(
    stage, event
):
    event.send_typing = AsyncMock()
    event.stop_typing = AsyncMock()
    obj = await stage()
    build_result = make_build_result()

    with (
        patch.object(internal_module, "try_capture_follow_up", return_value=None),
        patch.object(
            internal_module,
            "call_event_hook",
            AsyncMock(side_effect=[False, True]),
        ),
        patch.object(internal_module.session_lock_manager, "acquire_lock", fake_lock),
        patch.object(
            internal_module,
            "build_main_agent",
            AsyncMock(return_value=build_result),
        ),
    ):
        results = [item async for item in obj.process(event, provider_wake_prefix="")]

    assert results == []
    event.stop_typing.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_releases_typing_after_normal_reply(stage, event):
    event.send_typing = AsyncMock()
    event.stop_typing = AsyncMock()
    obj = await stage()
    build_result = make_build_result()

    with (
        patch.object(internal_module, "try_capture_follow_up", return_value=None),
        patch.object(
            internal_module,
            "call_event_hook",
            AsyncMock(side_effect=[False, False]),
        ),
        patch.object(internal_module.session_lock_manager, "acquire_lock", fake_lock),
        patch.object(
            internal_module,
            "build_main_agent",
            AsyncMock(return_value=build_result),
        ),
        patch.object(internal_module, "run_agent", empty_run_agent),
        patch.object(internal_module, "register_active_runner"),
        patch.object(internal_module, "unregister_active_runner"),
    ):
        results = [item async for item in obj.process(event, provider_wake_prefix="")]

    assert results == []
    event.stop_typing.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_does_not_stop_typing_early_for_streaming_platforms(stage, event):
    event.platform_meta.support_streaming_message = True
    event.send_typing = AsyncMock()
    event.stop_typing = AsyncMock()
    obj = await stage()
    obj.streaming_response = True
    build_result = make_build_result()

    with (
        patch.object(internal_module, "try_capture_follow_up", return_value=None),
        patch.object(
            internal_module,
            "call_event_hook",
            AsyncMock(side_effect=[False, False]),
        ),
        patch.object(internal_module.session_lock_manager, "acquire_lock", fake_lock),
        patch.object(
            internal_module,
            "build_main_agent",
            AsyncMock(return_value=build_result),
        ),
        patch.object(internal_module, "run_agent", empty_run_agent),
        patch.object(internal_module, "register_active_runner"),
        patch.object(internal_module, "unregister_active_runner"),
    ):
        results = [item async for item in obj.process(event, provider_wake_prefix="")]

    assert len(results) == 1
    event.stop_typing.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_releases_typing_on_error_fallback_send(stage, event):
    event.send_typing = AsyncMock()
    event.stop_typing = AsyncMock()
    event.send = AsyncMock()
    obj = await stage()

    with (
        patch.object(internal_module, "try_capture_follow_up", return_value=None),
        patch.object(internal_module, "call_event_hook", AsyncMock(return_value=False)),
        patch.object(internal_module.session_lock_manager, "acquire_lock", fake_lock),
        patch.object(
            internal_module,
            "build_main_agent",
            AsyncMock(side_effect=RuntimeError("boom")),
        ),
    ):
        results = [item async for item in obj.process(event, provider_wake_prefix="")]

    assert results == []
    event.send.assert_awaited_once()
    event.stop_typing.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_swallows_stop_typing_error(stage, event):
    event.send_typing = AsyncMock()
    event.stop_typing = AsyncMock(side_effect=RuntimeError("stop failed"))
    obj = await stage()

    with (
        patch.object(internal_module.logger, "warning") as warning_mock,
        patch.object(internal_module, "try_capture_follow_up", return_value=None),
        patch.object(internal_module, "call_event_hook", AsyncMock(return_value=False)),
        patch.object(internal_module.session_lock_manager, "acquire_lock", fake_lock),
        patch.object(internal_module, "build_main_agent", AsyncMock(return_value=None)),
    ):
        results = [item async for item in obj.process(event, provider_wake_prefix="")]

    assert results == []
    event.send_typing.assert_awaited_once()
    event.stop_typing.assert_awaited_once()
    warning_mock.assert_called_once_with("stop_typing failed", exc_info=True)
