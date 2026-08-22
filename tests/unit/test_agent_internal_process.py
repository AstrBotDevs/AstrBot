from __future__ import annotations

import pytest

from astrbot.core.message.components import Json
from tests.unit.agent_sub_stage_support import *  # noqa: F403


@pytest.mark.asyncio
async def test_internal_process_skips_empty_messages_without_provider_request(
    monkeypatch,
):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.max_step = 5
    stage.unsupported_streaming_strategy = "turn_off"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.ctx = _pipeline_context(_internal_plugin_context())
    event = FakeInternalProcessEvent(message_str="   ", message_components=[])

    try_capture = MagicMock()
    stage.ctx.execution_context.follow_up_coordinator.try_capture = try_capture

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]

    assert yielded == []
    try_capture.assert_not_called()
    event.send_typing.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message_components",
    [
        [Reply(id="reply-1")],
        [Image(file="https://example.com/image.png")],
        [Json(data={"meta": {"news": {"title": "News"}}})],
    ],
)
async def test_internal_process_accepts_non_text_messages_with_reply_or_media(
    monkeypatch,
    message_components,
):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.max_step = 5
    stage.unsupported_streaming_strategy = "turn_off"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.main_agent_cfg = object()
    stage.ctx = _pipeline_context(_internal_plugin_context())
    event = FakeInternalProcessEvent(
        message_str="   ",
        message_components=message_components,
    )
    runner = FakeInternalRunner()
    req = ProviderRequest(conversation=SimpleNamespace(cid="conv-non-text"))
    build_result = SimpleNamespace(
        agent_runner=runner,
        provider_request=req,
        provider=runner.provider,
        reset_coro=None,
    )
    save_to_history = AsyncMock()

    async def fake_run_agent(*args, **kwargs):
        yield

    monkeypatch.setattr(
        stage.ctx.execution_context.session_lock_manager,
        "acquire_lock",
        lambda _umo: _AsyncLockContext(),
    )
    monkeypatch.setattr(
        internal,
        "replace",
        lambda _cfg, **kwargs: _fake_build_cfg(**kwargs),
    )
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))
    build_main_agent = AsyncMock(return_value=build_result)
    monkeypatch.setattr(internal, "build_main_agent", build_main_agent)
    monkeypatch.setattr(internal, "run_agent", fake_run_agent)
    monkeypatch.setattr(stage, "_save_to_history", save_to_history)
    monkeypatch.setattr(internal, "_record_internal_agent_stats", AsyncMock())
    _set_metrics_upload(stage, AsyncMock())

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]
    await asyncio.sleep(0)

    assert yielded == [None]
    build_main_agent.assert_awaited_once()
    event.send_typing.assert_awaited_once()
    save_to_history.assert_awaited_once()


@pytest.mark.asyncio
async def test_internal_process_stops_when_follow_up_ticket_was_consumed(monkeypatch):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.max_step = 5
    stage.unsupported_streaming_strategy = "turn_off"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.ctx = _pipeline_context(_internal_plugin_context())
    event = FakeInternalProcessEvent(message_str="follow up")
    capture = SimpleNamespace(ticket=SimpleNamespace(seq=3))

    finalize = AsyncMock()
    stage.ctx.execution_context.follow_up_coordinator.try_capture = MagicMock(
        return_value=capture
    )
    stage.ctx.execution_context.follow_up_coordinator.prepare_capture = AsyncMock(
        return_value=(True, False)
    )
    stage.ctx.execution_context.follow_up_coordinator.finalize_capture = finalize

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]

    assert yielded == []
    event.send_typing.assert_not_awaited()
    finalize.assert_awaited_once_with(
        capture,
        activated=False,
        consumed_marked=True,
    )


@pytest.mark.asyncio
async def test_internal_process_sends_error_message_and_finalizes_follow_up_on_exception(
    monkeypatch,
):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.max_step = 5
    stage.unsupported_streaming_strategy = "turn_off"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.main_agent_cfg = SimpleNamespace()
    stage.ctx = _pipeline_context(_internal_plugin_context())
    event = FakeInternalProcessEvent(message_str="hello")
    capture = SimpleNamespace(ticket=SimpleNamespace(seq=4))

    monkeypatch.setattr(
        stage.ctx.execution_context.session_lock_manager,
        "acquire_lock",
        lambda _umo: _AsyncLockContext(),
    )
    stage.ctx.execution_context.follow_up_coordinator.try_capture = MagicMock(
        return_value=capture
    )
    stage.ctx.execution_context.follow_up_coordinator.prepare_capture = AsyncMock(
        return_value=(False, True)
    )
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(
        internal,
        "build_main_agent",
        AsyncMock(side_effect=RuntimeError("builder failed")),
    )
    monkeypatch.setattr(
        internal,
        "get_agent_error_message",
        lambda _event: "custom internal failure",
    )
    finalize = AsyncMock()
    stage.ctx.execution_context.follow_up_coordinator.finalize_capture = finalize

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]

    assert yielded == []
    event.send_typing.assert_awaited_once()
    event.stop_typing.assert_awaited_once()
    event.send.assert_awaited_once()
    assert event.send.await_args.args[0].get_plain_text() == "custom internal failure"
    finalize.assert_awaited_once_with(
        capture,
        activated=True,
        consumed_marked=False,
    )


@pytest.mark.asyncio
async def test_internal_process_finalizes_follow_up_when_waiting_hook_blocks(
    monkeypatch,
):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.max_step = 5
    stage.unsupported_streaming_strategy = "turn_off"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.main_agent_cfg = object()
    stage.ctx = _pipeline_context(_internal_plugin_context())
    event = FakeInternalProcessEvent(message_str="hello")
    capture = SimpleNamespace(ticket=SimpleNamespace(seq=9))
    finalize = AsyncMock()

    stage.ctx.execution_context.follow_up_coordinator.try_capture = MagicMock(
        return_value=capture
    )
    stage.ctx.execution_context.follow_up_coordinator.prepare_capture = AsyncMock(
        return_value=(False, True)
    )
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=True))
    stage.ctx.execution_context.follow_up_coordinator.finalize_capture = finalize

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]

    assert yielded == []
    event.send_typing.assert_awaited_once()
    event.stop_typing.assert_awaited_once()
    finalize.assert_awaited_once_with(
        capture,
        activated=True,
        consumed_marked=False,
    )


@pytest.mark.asyncio
async def test_internal_process_sends_llm_error_message_when_build_returns_none(
    monkeypatch,
):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.max_step = 5
    stage.unsupported_streaming_strategy = "turn_off"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.main_agent_cfg = object()
    stage.ctx = _pipeline_context(_internal_plugin_context())
    event = FakeInternalProcessEvent(
        message_str="hello",
        extras={internal.LLM_ERROR_MESSAGE_EXTRA_KEY: "provider unavailable"},
    )

    monkeypatch.setattr(
        stage.ctx.execution_context.session_lock_manager,
        "acquire_lock",
        lambda _umo: _AsyncLockContext(),
    )
    monkeypatch.setattr(
        internal, "replace", lambda _cfg, **kwargs: _fake_build_cfg(**kwargs)
    )
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(internal, "build_main_agent", AsyncMock(return_value=None))

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]

    assert yielded == []
    event.send.assert_awaited_once()
    assert (
        event.send.await_args.args[0].get_plain_text()
        == "Error occurred during AI execution."
    )
    event.stop_typing.assert_awaited_once()


@pytest.mark.asyncio
async def test_internal_process_build_none_finalizes_follow_up_capture(monkeypatch):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.max_step = 5
    stage.unsupported_streaming_strategy = "turn_off"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.main_agent_cfg = object()
    stage.ctx = _pipeline_context(_internal_plugin_context())
    event = FakeInternalProcessEvent(
        message_str="hello",
        extras={internal.LLM_ERROR_MESSAGE_EXTRA_KEY: "provider unavailable"},
    )
    capture = SimpleNamespace(ticket=SimpleNamespace(seq=11))
    finalize = AsyncMock()

    monkeypatch.setattr(
        stage.ctx.execution_context.session_lock_manager,
        "acquire_lock",
        lambda _umo: _AsyncLockContext(),
    )
    monkeypatch.setattr(
        internal, "replace", lambda _cfg, **kwargs: _fake_build_cfg(**kwargs)
    )
    stage.ctx.execution_context.follow_up_coordinator.try_capture = MagicMock(
        return_value=capture
    )
    stage.ctx.execution_context.follow_up_coordinator.prepare_capture = AsyncMock(
        return_value=(False, True)
    )
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(internal, "build_main_agent", AsyncMock(return_value=None))
    stage.ctx.execution_context.follow_up_coordinator.finalize_capture = finalize

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]

    assert yielded == []
    event.send.assert_awaited_once()
    assert (
        event.send.await_args.args[0].get_plain_text()
        == "Error occurred during AI execution."
    )
    finalize.assert_awaited_once_with(
        capture,
        activated=True,
        consumed_marked=False,
    )


@pytest.mark.asyncio
async def test_internal_process_skips_send_when_build_returns_none_without_llm_error(
    monkeypatch,
):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.max_step = 5
    stage.unsupported_streaming_strategy = "turn_off"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.main_agent_cfg = object()
    stage.ctx = _pipeline_context(_internal_plugin_context())
    event = FakeInternalProcessEvent(message_str="hello")

    monkeypatch.setattr(
        stage.ctx.execution_context.session_lock_manager,
        "acquire_lock",
        lambda _umo: _AsyncLockContext(),
    )
    monkeypatch.setattr(
        internal, "replace", lambda _cfg, **kwargs: _fake_build_cfg(**kwargs)
    )
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(internal, "build_main_agent", AsyncMock(return_value=None))

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]

    assert yielded == []
    event.send.assert_not_awaited()
    event.stop_typing.assert_awaited_once()


@pytest.mark.asyncio
async def test_internal_process_closes_reset_coro_when_llm_request_hook_blocks(
    monkeypatch,
):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.max_step = 5
    stage.unsupported_streaming_strategy = "turn_off"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.main_agent_cfg = object()
    stage.ctx = _pipeline_context(_internal_plugin_context())
    event = FakeInternalProcessEvent(message_str="hello")
    reset_coro = MagicMock()
    build_result = SimpleNamespace(
        agent_runner=FakeInternalRunner(),
        provider_request=ProviderRequest(),
        provider=SimpleNamespace(provider_config={"api_base": ""}),
        reset_coro=reset_coro,
    )

    monkeypatch.setattr(
        stage.ctx.execution_context.session_lock_manager,
        "acquire_lock",
        lambda _umo: _AsyncLockContext(),
    )
    monkeypatch.setattr(
        internal, "replace", lambda _cfg, **kwargs: _fake_build_cfg(**kwargs)
    )
    monkeypatch.setattr(
        internal, "call_event_hook", AsyncMock(side_effect=[False, True])
    )
    monkeypatch.setattr(
        internal, "build_main_agent", AsyncMock(return_value=build_result)
    )

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]

    assert yielded == []
    reset_coro.close.assert_called_once_with()
    event.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_internal_process_llm_request_hook_block_finalizes_follow_up_capture(
    monkeypatch,
):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.max_step = 5
    stage.unsupported_streaming_strategy = "turn_off"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.main_agent_cfg = object()
    stage.ctx = _pipeline_context(_internal_plugin_context())
    event = FakeInternalProcessEvent(message_str="hello")
    capture = SimpleNamespace(ticket=SimpleNamespace(seq=12))
    reset_coro = MagicMock()
    finalize = AsyncMock()
    build_result = SimpleNamespace(
        agent_runner=FakeInternalRunner(),
        provider_request=ProviderRequest(),
        provider=SimpleNamespace(provider_config={"api_base": ""}),
        reset_coro=reset_coro,
    )

    monkeypatch.setattr(
        stage.ctx.execution_context.session_lock_manager,
        "acquire_lock",
        lambda _umo: _AsyncLockContext(),
    )
    monkeypatch.setattr(
        internal, "replace", lambda _cfg, **kwargs: _fake_build_cfg(**kwargs)
    )
    stage.ctx.execution_context.follow_up_coordinator.try_capture = MagicMock(
        return_value=capture
    )
    stage.ctx.execution_context.follow_up_coordinator.prepare_capture = AsyncMock(
        return_value=(False, True)
    )
    monkeypatch.setattr(
        internal, "call_event_hook", AsyncMock(side_effect=[False, True])
    )
    monkeypatch.setattr(
        internal, "build_main_agent", AsyncMock(return_value=build_result)
    )
    stage.ctx.execution_context.follow_up_coordinator.finalize_capture = finalize

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]

    assert yielded == []
    reset_coro.close.assert_called_once_with()
    event.send.assert_not_awaited()
    finalize.assert_awaited_once_with(
        capture,
        activated=True,
        consumed_marked=False,
    )


@pytest.mark.asyncio
async def test_internal_process_stops_when_waiting_hook_blocks(monkeypatch):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.max_step = 5
    stage.unsupported_streaming_strategy = "turn_off"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.main_agent_cfg = object()
    stage.ctx = _pipeline_context(_internal_plugin_context())
    event = FakeInternalProcessEvent(message_str="hello")

    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=True))
    build_main_agent = AsyncMock()
    monkeypatch.setattr(internal, "build_main_agent", build_main_agent)

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]

    assert yielded == []
    event.send_typing.assert_awaited_once()
    event.stop_typing.assert_awaited_once()
    build_main_agent.assert_not_awaited()


@pytest.mark.asyncio
async def test_internal_process_continues_when_send_typing_fails(monkeypatch):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.max_step = 5
    stage.unsupported_streaming_strategy = "turn_off"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.main_agent_cfg = object()
    stage.ctx = _pipeline_context(_internal_plugin_context())
    event = FakeInternalProcessEvent(
        message_str="hello",
        extras={internal.LLM_ERROR_MESSAGE_EXTRA_KEY: "provider unavailable"},
    )
    event.send_typing.side_effect = RuntimeError("typing failed")
    logger_warning = MagicMock()

    monkeypatch.setattr(
        stage.ctx.execution_context.session_lock_manager,
        "acquire_lock",
        lambda _umo: _AsyncLockContext(),
    )
    monkeypatch.setattr(
        internal, "replace", lambda _cfg, **kwargs: _fake_build_cfg(**kwargs)
    )
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(internal, "build_main_agent", AsyncMock(return_value=None))
    monkeypatch.setattr(internal.logger, "warning", logger_warning)

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]

    assert yielded == []
    event.send.assert_awaited_once()
    assert (
        event.send.await_args.args[0].get_plain_text()
        == "Error occurred during AI execution."
    )
    event.stop_typing.assert_awaited_once()
    logger_warning.assert_called()


@pytest.mark.asyncio
async def test_internal_process_swallows_stop_typing_failures(monkeypatch):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.max_step = 5
    stage.unsupported_streaming_strategy = "turn_off"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.main_agent_cfg = object()
    stage.ctx = _pipeline_context(_internal_plugin_context())
    event = FakeInternalProcessEvent(message_str="hello")
    event.stop_typing.side_effect = RuntimeError("stop typing failed")
    logger_warning = MagicMock()

    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=True))
    monkeypatch.setattr(internal.logger, "warning", logger_warning)

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]

    assert yielded == []
    event.send_typing.assert_awaited_once()
    event.stop_typing.assert_awaited_once()
    logger_warning.assert_called()


@pytest.mark.asyncio
async def test_internal_process_sends_error_for_blocked_provider_api_base(monkeypatch):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.max_step = 5
    stage.unsupported_streaming_strategy = "turn_off"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.main_agent_cfg = object()
    stage.ctx = _pipeline_context(_internal_plugin_context())
    event = FakeInternalProcessEvent(message_str="hello")
    runner = FakeInternalRunner()
    build_result = SimpleNamespace(
        agent_runner=runner,
        provider_request=ProviderRequest(
            conversation=SimpleNamespace(cid="conv-blocked")
        ),
        provider=SimpleNamespace(
            provider_config={
                "api_base": f"https://{next(iter(internal.BLOCKED_PROVIDER_HOSTS))}/v1"
            },
            get_model=lambda: "fake-model",
        ),
        reset_coro=None,
    )

    monkeypatch.setattr(
        stage.ctx.execution_context.session_lock_manager,
        "acquire_lock",
        lambda _umo: _AsyncLockContext(),
    )
    monkeypatch.setattr(
        internal, "replace", lambda _cfg, **kwargs: _fake_build_cfg(**kwargs)
    )
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(
        internal, "build_main_agent", AsyncMock(return_value=build_result)
    )
    register_runner = MagicMock()
    stage.ctx.execution_context.follow_up_coordinator.register_active_runner = (
        register_runner
    )

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]

    assert yielded == []
    register_runner.assert_not_called()
    event.send.assert_awaited_once()
    assert (
        event.send.await_args.args[0].get_plain_text()
        == "Error occurred during AI execution."
    )
    event.stop_typing.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("final_resp", "expected_text"),
    [
        (
            LLMResponse(role="assistant", completion_text="final text"),
            "final text",
        ),
        (
            LLMResponse(
                role="assistant",
                result_chain=MessageChain().message("chain text"),
            ),
            "chain text",
        ),
        (
            LLMResponse(role="assistant"),
            "",
        ),
    ],
)
async def test_internal_process_streaming_sets_finish_result_from_final_response(
    monkeypatch,
    final_resp,
    expected_text,
):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = True
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.max_step = 5
    stage.unsupported_streaming_strategy = "turn_off"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.main_agent_cfg = object()
    stage.ctx = _pipeline_context(_internal_plugin_context())
    event = FakeInternalProcessEvent(message_str="hello")
    runner = FakeInternalRunner(final_resp=final_resp, done=True)
    req = ProviderRequest(conversation=SimpleNamespace(cid="conv-stream"))
    build_result = SimpleNamespace(
        agent_runner=runner,
        provider_request=req,
        provider=runner.provider,
        reset_coro=None,
    )
    save_to_history = AsyncMock()
    scheduled_tasks: list[asyncio.Task] = []

    async def fake_run_agent(*args, **kwargs):
        if False:
            yield

    def fake_create_task(coro, *, name=None):
        task = asyncio.get_running_loop().create_task(coro, name=name)
        scheduled_tasks.append(task)
        return task

    monkeypatch.setattr(
        stage.ctx.execution_context.session_lock_manager,
        "acquire_lock",
        lambda _umo: _AsyncLockContext(),
    )
    monkeypatch.setattr(
        internal, "replace", lambda _cfg, **kwargs: _fake_build_cfg(**kwargs)
    )
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(
        internal, "build_main_agent", AsyncMock(return_value=build_result)
    )
    monkeypatch.setattr(internal, "run_agent", fake_run_agent)
    monkeypatch.setattr(stage, "_save_to_history", save_to_history)
    monkeypatch.setattr(internal, "_record_internal_agent_stats", AsyncMock())
    _set_metrics_upload(stage, AsyncMock())
    monkeypatch.setattr(task_utils.asyncio, "create_task", fake_create_task)

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]
    await asyncio.gather(*scheduled_tasks)

    assert yielded == [None]
    assert (
        event.result_history[-2].result_content_type
        == ResultContentType.STREAMING_RESULT
    )
    assert (
        event.result_history[-1].result_content_type
        == ResultContentType.STREAMING_FINISH
    )
    assert event.result_history[-1].get_plain_text() == expected_text
    save_to_history.assert_awaited_once()


@pytest.mark.asyncio
async def test_internal_process_turns_streaming_into_general_when_platform_lacks_support(
    monkeypatch,
):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = True
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.max_step = 5
    stage.unsupported_streaming_strategy = "turn_off"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.main_agent_cfg = object()
    stage.ctx = _pipeline_context(_internal_plugin_context())
    event = FakeInternalProcessEvent(message_str="hello")
    event.platform_meta.support_streaming_message = False
    runner = FakeInternalRunner()
    req = ProviderRequest(conversation=SimpleNamespace(cid="conv-general-stream"))
    build_result = SimpleNamespace(
        agent_runner=runner,
        provider_request=req,
        provider=runner.provider,
        reset_coro=None,
    )
    save_to_history = AsyncMock()
    run_agent_calls: list[dict] = []

    async def fake_run_agent(*args, **kwargs):
        run_agent_calls.append({"args": args, "kwargs": kwargs})
        yield

    monkeypatch.setattr(
        stage.ctx.execution_context.session_lock_manager,
        "acquire_lock",
        lambda _umo: _AsyncLockContext(),
    )
    monkeypatch.setattr(
        internal,
        "replace",
        lambda _cfg, **kwargs: _fake_build_cfg(**kwargs),
    )
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(
        internal, "build_main_agent", AsyncMock(return_value=build_result)
    )
    monkeypatch.setattr(internal, "run_agent", fake_run_agent)
    monkeypatch.setattr(stage, "_save_to_history", save_to_history)
    monkeypatch.setattr(internal, "_record_internal_agent_stats", AsyncMock())
    _set_metrics_upload(stage, AsyncMock())

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]
    await asyncio.sleep(0)

    assert yielded == [None]
    assert len(run_agent_calls) == 1
    assert run_agent_calls[0]["args"][4] is True
    assert event.result_history == []
    save_to_history.assert_awaited_once()


@pytest.mark.asyncio
async def test_internal_process_awaits_reset_before_running_agent(monkeypatch):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.max_step = 5
    stage.unsupported_streaming_strategy = "turn_off"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.main_agent_cfg = object()
    stage.ctx = _pipeline_context(_internal_plugin_context())
    event = FakeInternalProcessEvent(message_str="hello")
    runner = FakeInternalRunner()
    req = ProviderRequest(conversation=SimpleNamespace(cid="conv-reset"))
    reset_flag = _AwaitableFlag()
    build_result = SimpleNamespace(
        agent_runner=runner,
        provider_request=req,
        provider=runner.provider,
        reset_coro=reset_flag,
    )
    save_to_history = AsyncMock()
    scheduled_tasks: list[asyncio.Task] = []

    async def fake_run_agent(*args, **kwargs):
        assert reset_flag.awaited is True
        yield

    def fake_create_task(coro, *, name=None):
        task = asyncio.get_running_loop().create_task(coro, name=name)
        scheduled_tasks.append(task)
        return task

    monkeypatch.setattr(
        stage.ctx.execution_context.session_lock_manager,
        "acquire_lock",
        lambda _umo: _AsyncLockContext(),
    )
    monkeypatch.setattr(
        internal, "replace", lambda _cfg, **kwargs: _fake_build_cfg(**kwargs)
    )
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(
        internal, "build_main_agent", AsyncMock(return_value=build_result)
    )
    monkeypatch.setattr(internal, "run_agent", fake_run_agent)
    monkeypatch.setattr(stage, "_save_to_history", save_to_history)
    monkeypatch.setattr(internal, "_record_internal_agent_stats", AsyncMock())
    _set_metrics_upload(stage, AsyncMock())
    monkeypatch.setattr(task_utils.asyncio, "create_task", fake_create_task)

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]
    await asyncio.gather(*scheduled_tasks)

    assert yielded == [None]
    assert reset_flag.awaited is True
    save_to_history.assert_awaited_once()


@pytest.mark.asyncio
async def test_internal_process_live_mode_sets_stream_and_saves_history(monkeypatch):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.max_step = 5
    stage.unsupported_streaming_strategy = "turn_off"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.main_agent_cfg = object()
    stage.ctx = _pipeline_context(_internal_plugin_context("tts-provider"))
    event = FakeInternalProcessEvent(
        message_str="hello",
        extras={"action_type": "live"},
    )
    runner = FakeInternalRunner()
    req = ProviderRequest(conversation=SimpleNamespace(cid="conv-live"))
    build_result = SimpleNamespace(
        agent_runner=runner,
        provider_request=req,
        provider=runner.provider,
        reset_coro=None,
    )
    save_to_history = AsyncMock()
    metric_upload = AsyncMock()
    scheduled_tasks: list[asyncio.Task] = []

    async def fake_run_live_agent(*args, **kwargs):
        yield MessageChain().message("live chunk")

    def fake_create_task(coro, *, name=None):
        task = asyncio.get_running_loop().create_task(coro, name=name)
        scheduled_tasks.append(task)
        return task

    monkeypatch.setattr(
        stage.ctx.execution_context.session_lock_manager,
        "acquire_lock",
        lambda _umo: _AsyncLockContext(),
    )
    monkeypatch.setattr(
        internal, "replace", lambda _cfg, **kwargs: _fake_build_cfg(**kwargs)
    )
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(
        internal, "build_main_agent", AsyncMock(return_value=build_result)
    )
    monkeypatch.setattr(internal, "run_live_agent", fake_run_live_agent)
    monkeypatch.setattr(stage, "_save_to_history", save_to_history)
    monkeypatch.setattr(internal, "_record_internal_agent_stats", AsyncMock())
    _set_metrics_upload(stage, metric_upload)
    monkeypatch.setattr(task_utils.asyncio, "create_task", fake_create_task)

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]
    await asyncio.gather(*scheduled_tasks)

    assert yielded == [None]
    assert (
        event.result_history[-1].result_content_type
        == ResultContentType.STREAMING_RESULT
    )
    streamed_chunks = [
        chain.get_plain_text() async for chain in event.result_history[-1].async_stream
    ]
    assert streamed_chunks == ["live chunk"]
    save_to_history.assert_awaited_once()
    assert save_to_history.await_args.args[0] is event
    assert save_to_history.await_args.args[1] is req
    assert save_to_history.await_args.kwargs["user_aborted"] is False
    assert metric_upload.await_count == 1


@pytest.mark.asyncio
async def test_internal_process_live_mode_skips_history_when_runner_not_done(
    monkeypatch,
):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.max_step = 5
    stage.unsupported_streaming_strategy = "turn_off"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.main_agent_cfg = object()
    stage.ctx = _pipeline_context(_internal_plugin_context())
    event = FakeInternalProcessEvent(
        message_str="hello",
        extras={"action_type": "live"},
    )
    runner = FakeInternalRunner(done=False)
    build_result = SimpleNamespace(
        agent_runner=runner,
        provider_request=ProviderRequest(
            conversation=SimpleNamespace(cid="conv-live-skip")
        ),
        provider=runner.provider,
        reset_coro=None,
    )
    save_to_history = AsyncMock()
    scheduled_tasks: list[asyncio.Task] = []

    async def fake_run_live_agent(*args, **kwargs):
        yield MessageChain().message("live chunk")

    def fake_create_task(coro, *, name=None):
        task = asyncio.get_running_loop().create_task(coro, name=name)
        scheduled_tasks.append(task)
        return task

    monkeypatch.setattr(
        stage.ctx.execution_context.session_lock_manager,
        "acquire_lock",
        lambda _umo: _AsyncLockContext(),
    )
    monkeypatch.setattr(
        internal, "replace", lambda _cfg, **kwargs: _fake_build_cfg(**kwargs)
    )
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(
        internal, "build_main_agent", AsyncMock(return_value=build_result)
    )
    monkeypatch.setattr(internal, "run_live_agent", fake_run_live_agent)
    monkeypatch.setattr(stage, "_save_to_history", save_to_history)
    monkeypatch.setattr(internal, "_record_internal_agent_stats", AsyncMock())
    _set_metrics_upload(stage, AsyncMock())
    monkeypatch.setattr(task_utils.asyncio, "create_task", fake_create_task)

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]
    await asyncio.gather(*scheduled_tasks)

    assert yielded == [None]
    save_to_history.assert_not_awaited()


@pytest.mark.asyncio
async def test_internal_process_live_mode_skips_history_when_event_stopped_without_abort(
    monkeypatch,
):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.max_step = 5
    stage.unsupported_streaming_strategy = "turn_off"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.main_agent_cfg = object()
    stage.ctx = _pipeline_context(_internal_plugin_context("tts-provider"))
    event = FakeInternalProcessEvent(
        message_str="hello",
        extras={"action_type": "live"},
        stopped=True,
    )
    runner = FakeInternalRunner(done=True, aborted=False)
    build_result = SimpleNamespace(
        agent_runner=runner,
        provider_request=ProviderRequest(
            conversation=SimpleNamespace(cid="conv-live-stopped")
        ),
        provider=runner.provider,
        reset_coro=None,
    )
    save_to_history = AsyncMock()
    scheduled_tasks: list[asyncio.Task] = []

    async def fake_run_live_agent(*args, **kwargs):
        yield MessageChain().message("live chunk")

    def fake_create_task(coro, *, name=None):
        task = asyncio.get_running_loop().create_task(coro, name=name)
        scheduled_tasks.append(task)
        return task

    monkeypatch.setattr(
        stage.ctx.execution_context.session_lock_manager,
        "acquire_lock",
        lambda _umo: _AsyncLockContext(),
    )
    monkeypatch.setattr(
        internal, "replace", lambda _cfg, **kwargs: _fake_build_cfg(**kwargs)
    )
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(
        internal, "build_main_agent", AsyncMock(return_value=build_result)
    )
    monkeypatch.setattr(internal, "run_live_agent", fake_run_live_agent)
    monkeypatch.setattr(stage, "_save_to_history", save_to_history)
    monkeypatch.setattr(internal, "_record_internal_agent_stats", AsyncMock())
    _set_metrics_upload(stage, AsyncMock())
    monkeypatch.setattr(task_utils.asyncio, "create_task", fake_create_task)

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]
    await asyncio.gather(*scheduled_tasks)

    assert yielded == [None]
    save_to_history.assert_not_awaited()


@pytest.mark.asyncio
async def test_internal_process_live_mode_saves_history_when_event_stopped_but_runner_aborted(
    monkeypatch,
):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.max_step = 5
    stage.unsupported_streaming_strategy = "turn_off"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.main_agent_cfg = object()
    stage.ctx = _pipeline_context(_internal_plugin_context("tts-provider"))
    event = FakeInternalProcessEvent(
        message_str="hello",
        extras={"action_type": "live"},
        stopped=True,
    )
    runner = FakeInternalRunner(done=True, aborted=True)
    req = ProviderRequest(conversation=SimpleNamespace(cid="conv-live-aborted"))
    build_result = SimpleNamespace(
        agent_runner=runner,
        provider_request=req,
        provider=runner.provider,
        reset_coro=None,
    )
    save_to_history = AsyncMock()
    scheduled_tasks: list[asyncio.Task] = []

    async def fake_run_live_agent(*args, **kwargs):
        yield MessageChain().message("live chunk")

    def fake_create_task(coro, *, name=None):
        task = asyncio.get_running_loop().create_task(coro, name=name)
        scheduled_tasks.append(task)
        return task

    monkeypatch.setattr(
        stage.ctx.execution_context.session_lock_manager,
        "acquire_lock",
        lambda _umo: _AsyncLockContext(),
    )
    monkeypatch.setattr(
        internal, "replace", lambda _cfg, **kwargs: _fake_build_cfg(**kwargs)
    )
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(
        internal, "build_main_agent", AsyncMock(return_value=build_result)
    )
    monkeypatch.setattr(internal, "run_live_agent", fake_run_live_agent)
    monkeypatch.setattr(stage, "_save_to_history", save_to_history)
    monkeypatch.setattr(internal, "_record_internal_agent_stats", AsyncMock())
    _set_metrics_upload(stage, AsyncMock())
    monkeypatch.setattr(task_utils.asyncio, "create_task", fake_create_task)

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]
    await asyncio.gather(*scheduled_tasks)

    assert yielded == [None]
    save_to_history.assert_awaited_once()
    assert save_to_history.await_args.args[0] is event
    assert save_to_history.await_args.args[1] is req
    assert save_to_history.await_args.kwargs["user_aborted"] is True


@pytest.mark.asyncio
async def test_internal_process_skips_history_save_when_event_stopped_without_abort(
    monkeypatch,
):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.max_step = 5
    stage.unsupported_streaming_strategy = "turn_off"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.main_agent_cfg = object()
    stage.ctx = _pipeline_context(_internal_plugin_context())
    event = FakeInternalProcessEvent(message_str="hello", stopped=True)
    runner = FakeInternalRunner(aborted=False)
    build_result = SimpleNamespace(
        agent_runner=runner,
        provider_request=ProviderRequest(conversation=SimpleNamespace(cid="conv-1")),
        provider=runner.provider,
        reset_coro=None,
    )
    save_to_history = AsyncMock()
    register_runner = MagicMock()
    unregister_runner = MagicMock()

    async def fake_run_agent(*args, **kwargs):
        yield

    monkeypatch.setattr(
        stage.ctx.execution_context.session_lock_manager,
        "acquire_lock",
        lambda _umo: _AsyncLockContext(),
    )
    monkeypatch.setattr(
        internal, "replace", lambda _cfg, **kwargs: _fake_build_cfg(**kwargs)
    )
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(
        internal, "build_main_agent", AsyncMock(return_value=build_result)
    )
    monkeypatch.setattr(internal, "run_agent", fake_run_agent)
    monkeypatch.setattr(stage, "_save_to_history", save_to_history)
    stage.ctx.execution_context.follow_up_coordinator.register_active_runner = (
        register_runner
    )
    stage.ctx.execution_context.follow_up_coordinator.unregister_active_runner = (
        unregister_runner
    )
    _set_metrics_upload(stage, AsyncMock())
    monkeypatch.setattr(internal, "_record_internal_agent_stats", AsyncMock())

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]
    await asyncio.sleep(0)

    assert yielded == [None]
    save_to_history.assert_not_awaited()
    register_runner.assert_called_once_with(event.unified_msg_origin, runner)
    unregister_runner.assert_called_once_with(event.unified_msg_origin, runner)


@pytest.mark.asyncio
async def test_internal_process_saves_history_when_event_stopped_but_runner_aborted(
    monkeypatch,
):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.max_step = 5
    stage.unsupported_streaming_strategy = "turn_off"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.main_agent_cfg = object()
    stage.ctx = _pipeline_context(_internal_plugin_context())
    event = FakeInternalProcessEvent(message_str="hello", stopped=True)
    runner = FakeInternalRunner(aborted=True)
    req = ProviderRequest(conversation=SimpleNamespace(cid="conv-2"))
    build_result = SimpleNamespace(
        agent_runner=runner,
        provider_request=req,
        provider=runner.provider,
        reset_coro=None,
    )
    save_to_history = AsyncMock()

    async def fake_run_agent(*args, **kwargs):
        yield

    monkeypatch.setattr(
        stage.ctx.execution_context.session_lock_manager,
        "acquire_lock",
        lambda _umo: _AsyncLockContext(),
    )
    monkeypatch.setattr(
        internal, "replace", lambda _cfg, **kwargs: _fake_build_cfg(**kwargs)
    )
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(
        internal, "build_main_agent", AsyncMock(return_value=build_result)
    )
    monkeypatch.setattr(internal, "run_agent", fake_run_agent)
    monkeypatch.setattr(stage, "_save_to_history", save_to_history)
    _set_metrics_upload(stage, AsyncMock())
    monkeypatch.setattr(internal, "_record_internal_agent_stats", AsyncMock())

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]
    await asyncio.sleep(0)

    assert yielded == [None]
    save_to_history.assert_awaited_once()
    assert save_to_history.await_args.args[0] is event
    assert save_to_history.await_args.args[1] is req
    assert save_to_history.await_args.kwargs["user_aborted"] is True


@pytest.mark.asyncio
async def test_internal_process_unregisters_runner_and_sends_error_when_history_save_fails(
    monkeypatch,
):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.max_step = 5
    stage.unsupported_streaming_strategy = "turn_off"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.main_agent_cfg = object()
    stage.ctx = _pipeline_context(_internal_plugin_context())
    event = FakeInternalProcessEvent(message_str="hello")
    runner = FakeInternalRunner()
    req = ProviderRequest(conversation=SimpleNamespace(cid="conv-history-fail"))
    build_result = SimpleNamespace(
        agent_runner=runner,
        provider_request=req,
        provider=runner.provider,
        reset_coro=None,
    )
    save_to_history = AsyncMock(side_effect=RuntimeError("history failed"))
    register_runner = MagicMock()
    unregister_runner = MagicMock()

    async def fake_run_agent(*args, **kwargs):
        yield

    monkeypatch.setattr(
        stage.ctx.execution_context.session_lock_manager,
        "acquire_lock",
        lambda _umo: _AsyncLockContext(),
    )
    monkeypatch.setattr(
        internal, "replace", lambda _cfg, **kwargs: _fake_build_cfg(**kwargs)
    )
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(
        internal, "build_main_agent", AsyncMock(return_value=build_result)
    )
    monkeypatch.setattr(internal, "run_agent", fake_run_agent)
    monkeypatch.setattr(stage, "_save_to_history", save_to_history)
    stage.ctx.execution_context.follow_up_coordinator.register_active_runner = (
        register_runner
    )
    stage.ctx.execution_context.follow_up_coordinator.unregister_active_runner = (
        unregister_runner
    )
    monkeypatch.setattr(internal, "_record_internal_agent_stats", AsyncMock())
    _set_metrics_upload(stage, AsyncMock())
    monkeypatch.setattr(
        internal,
        "get_agent_error_message",
        lambda _event: "Error occurred during AI execution.",
    )

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]
    await asyncio.sleep(0)

    assert yielded == [None]
    register_runner.assert_called_once_with(event.unified_msg_origin, runner)
    unregister_runner.assert_called_once_with(event.unified_msg_origin, runner)
    save_to_history.assert_awaited_once()
    event.send.assert_awaited_once()
    assert (
        event.send.await_args.args[0].get_plain_text()
        == "Error occurred during AI execution."
    )
    event.stop_typing.assert_awaited_once()


@pytest.mark.asyncio
async def test_internal_process_sends_error_when_stats_task_creation_fails_before_history_save(
    monkeypatch,
):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.max_step = 5
    stage.unsupported_streaming_strategy = "turn_off"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.main_agent_cfg = object()
    stage.ctx = _pipeline_context(_internal_plugin_context())
    event = FakeInternalProcessEvent(message_str="hello")
    runner = FakeInternalRunner()
    req = ProviderRequest(conversation=SimpleNamespace(cid="conv-stats-task-fail"))
    build_result = SimpleNamespace(
        agent_runner=runner,
        provider_request=req,
        provider=runner.provider,
        reset_coro=None,
    )
    save_to_history = AsyncMock()
    register_runner = MagicMock()
    unregister_runner = MagicMock()

    async def fake_run_agent(*args, **kwargs):
        yield

    def fail_create_task(coro, *, name=None):
        coro.close()
        raise RuntimeError("schedule stats failed")

    monkeypatch.setattr(
        stage.ctx.execution_context.session_lock_manager,
        "acquire_lock",
        lambda _umo: _AsyncLockContext(),
    )
    monkeypatch.setattr(
        internal, "replace", lambda _cfg, **kwargs: _fake_build_cfg(**kwargs)
    )
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(
        internal, "build_main_agent", AsyncMock(return_value=build_result)
    )
    monkeypatch.setattr(internal, "run_agent", fake_run_agent)
    monkeypatch.setattr(stage, "_save_to_history", save_to_history)
    stage.ctx.execution_context.follow_up_coordinator.register_active_runner = (
        register_runner
    )
    stage.ctx.execution_context.follow_up_coordinator.unregister_active_runner = (
        unregister_runner
    )
    monkeypatch.setattr(internal, "_record_internal_agent_stats", AsyncMock())
    _set_metrics_upload(stage, AsyncMock())
    monkeypatch.setattr(task_utils.asyncio, "create_task", fail_create_task)
    monkeypatch.setattr(
        internal,
        "get_agent_error_message",
        lambda _event: "Error occurred during AI execution.",
    )

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]

    assert yielded == [None]
    save_to_history.assert_not_awaited()
    register_runner.assert_called_once_with(event.unified_msg_origin, runner)
    unregister_runner.assert_called_once_with(event.unified_msg_origin, runner)
    event.send.assert_awaited_once()
    assert (
        event.send.await_args.args[0].get_plain_text()
        == "Error occurred during AI execution."
    )
    event.stop_typing.assert_awaited_once()


@pytest.mark.asyncio
async def test_internal_process_sends_error_when_metric_task_creation_fails_after_history_save(
    monkeypatch,
):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_tool_use = True
    stage.show_tool_call_result = False
    stage.show_reasoning = False
    stage.buffer_intermediate_messages = False
    stage.max_step = 5
    stage.unsupported_streaming_strategy = "turn_off"
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.main_agent_cfg = object()
    stage.ctx = _pipeline_context(_internal_plugin_context())
    event = FakeInternalProcessEvent(message_str="hello")
    runner = FakeInternalRunner()
    req = ProviderRequest(conversation=SimpleNamespace(cid="conv-metric-task-fail"))
    build_result = SimpleNamespace(
        agent_runner=runner,
        provider_request=req,
        provider=runner.provider,
        reset_coro=None,
    )
    save_to_history = AsyncMock()
    register_runner = MagicMock()
    unregister_runner = MagicMock()
    created_coroutines: list = []
    scheduled_tasks: list[asyncio.Task] = []

    async def fake_run_agent(*args, **kwargs):
        yield

    def fail_on_second_create_task(coro, *, name=None):
        created_coroutines.append(coro)
        if len(created_coroutines) == 1:
            coro.close()
            task = asyncio.get_running_loop().create_task(asyncio.sleep(0), name=name)
            scheduled_tasks.append(task)
            return task
        coro.close()
        raise RuntimeError("schedule metric failed")

    monkeypatch.setattr(
        stage.ctx.execution_context.session_lock_manager,
        "acquire_lock",
        lambda _umo: _AsyncLockContext(),
    )
    monkeypatch.setattr(
        internal, "replace", lambda _cfg, **kwargs: _fake_build_cfg(**kwargs)
    )
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(
        internal, "build_main_agent", AsyncMock(return_value=build_result)
    )
    monkeypatch.setattr(internal, "run_agent", fake_run_agent)
    monkeypatch.setattr(stage, "_save_to_history", save_to_history)
    stage.ctx.execution_context.follow_up_coordinator.register_active_runner = (
        register_runner
    )
    stage.ctx.execution_context.follow_up_coordinator.unregister_active_runner = (
        unregister_runner
    )
    monkeypatch.setattr(internal, "_record_internal_agent_stats", AsyncMock())
    _set_metrics_upload(stage, AsyncMock())
    monkeypatch.setattr(task_utils.asyncio, "create_task", fail_on_second_create_task)
    monkeypatch.setattr(
        internal,
        "get_agent_error_message",
        lambda _event: "Error occurred during AI execution.",
    )

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]
    await asyncio.gather(*scheduled_tasks)

    assert yielded == [None]
    save_to_history.assert_awaited_once()
    register_runner.assert_called_once_with(event.unified_msg_origin, runner)
    unregister_runner.assert_called_once_with(event.unified_msg_origin, runner)
    event.send.assert_awaited_once()
    assert (
        event.send.await_args.args[0].get_plain_text()
        == "Error occurred during AI execution."
    )
    event.stop_typing.assert_awaited_once()
