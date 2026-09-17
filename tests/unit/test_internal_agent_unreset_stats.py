"""An unreset internal runner must not be inspected while leaving the stage."""

import inspect
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.astr_main_agent import MainAgentBuildConfig
from astrbot.core.pipeline.process_stage.method.agent_sub_stages import internal
from astrbot.core.provider.entities import ProviderRequest


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_at_hook", [True, False])
async def test_unreset_runner_skips_stats_and_preserves_early_exit(
    monkeypatch, stop_at_hook
):
    event = MagicMock()
    event.message_str = "hello"
    event.message_obj.message = []
    event.unified_msg_origin = "test:FriendMessage:session"
    event.get_extra.return_value = None
    event.send_typing = AsyncMock()
    event.stop_typing = AsyncMock()
    event.send = AsyncMock()
    event.platform_meta.support_streaming_message = True

    stage = internal.InternalAgentSubStage()
    stage.ctx = SimpleNamespace(
        plugin_manager=SimpleNamespace(context=SimpleNamespace())
    )
    stage.main_agent_cfg = MainAgentBuildConfig(tool_call_timeout=60)
    stage.streaming_response = False
    stage.show_reasoning = False
    stage.unsupported_streaming_strategy = "turn_off"

    provider = SimpleNamespace(provider_config={"api_base": "https://example.test"})
    request = ProviderRequest(prompt="hello")
    runner = SimpleNamespace(get_final_llm_resp=MagicMock())
    runner.get_final_llm_resp.side_effect = AttributeError("runner was not reset")

    async def reset_runner():
        raise AssertionError("reset must not start after early exit")

    reset_coro = reset_runner()
    monkeypatch.setattr(internal, "try_capture_follow_up", lambda _event: None)
    monkeypatch.setattr(
        internal, "extract_persona_custom_error_message_from_event", lambda _event: None
    )
    monkeypatch.setattr(
        internal,
        "build_main_agent",
        AsyncMock(
            return_value=SimpleNamespace(
                agent_runner=runner,
                provider_request=request,
                provider=provider,
                reset_coro=reset_coro,
            )
        ),
    )
    monkeypatch.setattr(internal, "_provider_supports_modality", lambda *_: False)
    hooks = AsyncMock(side_effect=[False, stop_at_hook])
    monkeypatch.setattr(internal, "call_event_hook", hooks)
    stats = MagicMock()
    monkeypatch.setattr(internal, "_schedule_internal_agent_stats", stats)
    if not stop_at_hook:
        monkeypatch.setattr(
            internal,
            "prepare_request_images",
            AsyncMock(side_effect=ValueError("image preparation failed")),
        )

    @asynccontextmanager
    async def lock():
        yield

    monkeypatch.setattr(
        internal.session_lock_manager, "acquire_lock", lambda _umo: lock()
    )

    async for _ in stage.process(event, ""):
        pass

    assert inspect.getcoroutinestate(reset_coro) == inspect.CORO_CLOSED
    runner.get_final_llm_resp.assert_not_called()
    stats.assert_not_called()
    event.stop_typing.assert_awaited_once()
    if stop_at_hook:
        event.send.assert_not_awaited()
    else:
        event.send.assert_awaited_once()
        error_text = event.send.await_args.args[0].chain[0].text
        assert "image preparation failed" in error_text
        assert "runner was not reset" not in error_text
