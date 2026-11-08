"""Failed agent construction must not inspect a runner or record empty usage."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.astr_main_agent import MainAgentBuildConfig
from astrbot.core.pipeline.process_stage.method.agent_sub_stages import internal


@pytest.mark.asyncio
@pytest.mark.parametrize("raises", [True, False])
async def test_unbuilt_runner_skips_stats_and_preserves_early_exit(monkeypatch, raises):
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
        plugin_manager=SimpleNamespace(
            context=SimpleNamespace(get_config=MagicMock(return_value={}))
        )
    )
    monkeypatch.setattr(
        internal.SessionServiceManager,
        "should_process_llm_request",
        AsyncMock(return_value=True),
    )
    stage.main_agent_cfg = MainAgentBuildConfig(tool_call_timeout=60)
    stage.streaming_response = False
    stage.show_reasoning = False
    stage.unsupported_streaming_strategy = "turn_off"
    monkeypatch.setattr(internal, "try_capture_follow_up", lambda _event: None)
    monkeypatch.setattr(
        internal, "extract_persona_custom_error_message_from_event", lambda _event: None
    )
    monkeypatch.setattr(internal, "matches_provider_wake_prefix", lambda *_: True)
    builder = AsyncMock(return_value=None)
    if raises:
        builder.side_effect = ValueError("image preparation failed")
    monkeypatch.setattr(internal, "build_main_agent", builder)
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))
    stats = MagicMock()
    monkeypatch.setattr(internal, "_schedule_internal_agent_stats", stats)

    @asynccontextmanager
    async def lock():
        yield

    monkeypatch.setattr(
        internal.session_lock_manager, "acquire_lock", lambda _umo: lock()
    )
    async for _ in stage.process(event, ""):
        pass
    builder.assert_awaited_once()
    stats.assert_not_called()
    event.stop_typing.assert_awaited_once()
    if raises:
        event.send.assert_awaited_once()
        assert "image preparation failed" in event.send.await_args.args[0].chain[0].text
    else:
        event.send.assert_not_awaited()
