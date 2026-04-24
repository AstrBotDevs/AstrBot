"""Focused tests for InternalAgentSubStage trace behavior."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal import (
    InternalAgentSubStage,
)
from astrbot.core.astr_main_agent import MainAgentBuildConfig
from astrbot.core.provider.entities import LLMResponse, ProviderRequest


@pytest.mark.asyncio
async def test_internal_agent_prepare_trace_keeps_string_system_prompt():
    stage = InternalAgentSubStage()
    stage.ctx = MagicMock()
    stage.ctx.plugin_manager = MagicMock()
    stage.ctx.plugin_manager.context = MagicMock()
    stage.streaming_response = False
    stage.unsupported_streaming_strategy = "turn_off"
    stage.max_step = 3
    stage.show_tool_use = False
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.main_agent_cfg = MainAgentBuildConfig(tool_call_timeout=60)
    stage._save_to_history = AsyncMock()

    provider = MagicMock()
    provider.provider_config = {"id": "provider-1", "api_base": ""}
    provider.get_model.return_value = "gpt-4"

    req = ProviderRequest(prompt="hello", system_prompt="SYSTEM")

    agent_runner = MagicMock()
    agent_runner.done.return_value = True
    agent_runner.get_final_llm_resp.return_value = LLMResponse(
        role="assistant", completion_text="done"
    )
    agent_runner.stats = MagicMock()
    agent_runner.stats.to_dict.return_value = {}
    agent_runner.run_context.messages = []
    agent_runner.was_aborted.return_value = False
    agent_runner.provider = provider

    async def noop():
        return None

    build_result = MagicMock(
        agent_runner=agent_runner,
        provider_request=req,
        provider=provider,
        reset_coro=noop(),
    )

    @asynccontextmanager
    async def fake_lock(*args, **kwargs):
        yield

    async def fake_run_agent(*args, **kwargs):
        if False:
            yield None

    def consume_task(coro):
        coro.close()
        return MagicMock()

    event = MagicMock()
    event.message_str = "hello"
    event.message_obj.message = []
    event.unified_msg_origin = "test:private:1"
    event.platform_meta.support_streaming_message = False
    event.get_extra.return_value = None
    event.send_typing = AsyncMock()
    event.stop_typing = AsyncMock()
    event.set_result = MagicMock()
    event.is_stopped.return_value = False
    event.trace = MagicMock()

    with (
        patch(
            "astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal.build_main_agent",
            AsyncMock(return_value=build_result),
        ),
        patch(
            "astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal.call_event_hook",
            AsyncMock(return_value=False),
        ),
        patch(
            "astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal.session_lock_manager.acquire_lock",
            fake_lock,
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
            "astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal.run_agent",
            fake_run_agent,
        ),
        patch(
            "astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal.asyncio.create_task",
            side_effect=consume_task,
        ),
        patch(
            "astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal._record_internal_agent_stats",
            AsyncMock(),
        ),
        patch(
            "astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal.Metric.upload",
            AsyncMock(),
        ),
        patch(
            "astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal.decoded_blocked",
            [],
            create=True,
        ),
    ):
        async for _ in stage.process(event, ""):
            pass

    prepare_trace = next(
        call
        for call in event.trace.record.call_args_list
        if call.args and call.args[0] == "astr_agent_prepare"
    )
    assert prepare_trace.kwargs["system_prompt"] == "SYSTEM"
    assert isinstance(prepare_trace.kwargs["system_prompt"], str)
