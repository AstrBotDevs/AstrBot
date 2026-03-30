from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.astr_main_agent import MainAgentBuildConfig, MainAgentBuildResult
from astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal import (
    InternalAgentSubStage,
)
from astrbot.core.provider.entities import LLMResponse, ProviderRequest


@asynccontextmanager
async def _dummy_session_lock():
    yield


async def _dummy_run_agent(*args, **kwargs):
    yield None


async def _dummy_reset():
    return None


@pytest.mark.asyncio
async def test_internal_stage_uses_effective_runner_streaming_flag():
    stage = InternalAgentSubStage()
    stage.ctx = MagicMock()
    stage.ctx.plugin_manager.context = MagicMock()
    stage.ctx.astrbot_config = {"provider_settings": {"wake_prefix": "!"}}
    stage.provider_wake_prefix = "!"
    stage.streaming_response = True
    stage.unsupported_streaming_strategy = "realtime_segmenting"
    stage.max_step = 5
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.main_agent_cfg = MainAgentBuildConfig(tool_call_timeout=60)
    stage._save_to_history = AsyncMock()

    event = MagicMock()
    event.message_str = "draw a shiba"
    event.message_obj.message = []
    event.unified_msg_origin = "webchat:private:test"
    event.get_extra.side_effect = lambda key, default=None: {
        "enable_streaming": True,
        "provider_request": None,
        "action_type": None,
    }.get(key, default)
    event.platform_meta.support_streaming_message = True
    event.send_typing = AsyncMock()
    event.trace = MagicMock()
    event.is_stopped.return_value = False

    agent_runner = MagicMock()
    agent_runner.streaming = False
    agent_runner.done.return_value = True
    agent_runner.was_aborted.return_value = False
    agent_runner.get_final_llm_resp.return_value = LLMResponse(
        role="assistant", completion_text="done"
    )
    agent_runner.run_context.messages = []
    agent_runner.stats.to_dict.return_value = {}
    agent_runner.provider.get_model.return_value = "gemini-3-pro-image-preview"
    agent_runner.provider.meta.return_value.type = "googlegenai_chat_completion"

    provider = MagicMock()
    provider.provider_config = {"id": "google_gemini", "api_base": ""}
    provider.get_model.return_value = "gemini-3-pro-image-preview"

    build_result = MainAgentBuildResult(
        agent_runner=agent_runner,
        provider_request=ProviderRequest(prompt="draw a shiba"),
        provider=provider,
        reset_coro=_dummy_reset(),
    )

    with (
        patch(
            "astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal.build_main_agent",
            AsyncMock(return_value=build_result),
        ),
        patch(
            "astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal.run_agent",
            _dummy_run_agent,
        ),
        patch(
            "astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal.call_event_hook",
            AsyncMock(return_value=False),
        ),
        patch(
            "astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal.try_capture_follow_up",
            return_value=None,
        ),
        patch(
            "astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal.register_active_runner"
        ),
        patch(
            "astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal.unregister_active_runner"
        ),
        patch(
            "astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal.session_lock_manager.acquire_lock",
            return_value=_dummy_session_lock(),
        ),
        patch(
            "astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal.Metric.upload",
            AsyncMock(return_value=None),
        ),
        patch(
            "astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal.asyncio.create_task",
            side_effect=lambda coro: coro.close(),
        ),
    ):
        yielded = []
        async for item in stage.process(event):
            yielded.append(item)

    assert yielded == [None]
    event.trace.record.assert_any_call(
        "astr_agent_prepare",
        system_prompt="",
        tools=[],
        stream=False,
        chat_provider={
            "id": "google_gemini",
            "model": "gemini-3-pro-image-preview",
        },
    )
