from __future__ import annotations

import json

import pytest

from astrbot.core.message.components import Json
from tests.unit.agent_sub_stage_support import *  # noqa: F403


@pytest.mark.asyncio
async def test_run_third_party_agent_filters_streaming_and_formats_exceptions():
    runner = FakeThirdPartyRunner(
        responses=[
            _runner_response("streaming_delta", "chunk"),
            _runner_response("llm_result", "final"),
            _runner_response("err", "bad"),
        ],
    )

    streamed = [
        (chain.get_plain_text(), is_error)
        async for chain, is_error in third_party.run_third_party_agent(
            runner,
            stream_to_general=False,
        )
    ]
    general_only = [
        (chain.get_plain_text(), is_error)
        async for chain, is_error in third_party.run_third_party_agent(
            runner,
            stream_to_general=True,
        )
    ]

    assert streamed == [
        ("chunk", False),
        ("Error occurred during AI execution.", True),
    ]
    assert general_only == [
        ("final", False),
        ("Error occurred during AI execution.", True),
    ]

    error_runner = FakeThirdPartyRunner(step_exception=RuntimeError("runner boom"))
    fallback = [
        (chain.get_plain_text(), is_error)
        async for chain, is_error in third_party.run_third_party_agent(
            error_runner,
            custom_error_message="custom failure",
        )
    ]
    assert fallback == [("custom failure", True)]

    generic_fallback = [
        (chain.get_plain_text(), is_error)
        async for chain, is_error in third_party.run_third_party_agent(error_runner)
    ]
    assert generic_fallback == [("Error occurred during AI execution.", True)]


def test_runner_result_aggregator_prefers_final_response_and_has_fallbacks():
    aggregator = third_party._RunnerResultAggregator()
    aggregator.add_chunk(MessageChain().message("partial"), is_error=True)

    final_chain, is_error = aggregator.finalize(
        LLMResponse(
            role="assistant",
            result_chain=MessageChain().message("final answer"),
        ),
    )
    assert MessageChain(chain=final_chain).get_plain_text() == "final answer"
    assert is_error is True

    provider_error_chain, provider_error = aggregator.finalize(
        LLMResponse(
            role="err",
            completion_text="https://provider.example?api_key=secret",
            result_chain=MessageChain().message("Bearer secret-token"),
        ),
    )
    assert (
        MessageChain(chain=provider_error_chain).get_plain_text()
        == "Error occurred during AI execution."
    )
    assert provider_error is True

    missing_chain_error, missing_chain_is_error = aggregator.finalize(
        LLMResponse(
            role="err",
            completion_text="api_key=provider-secret",
        ),
    )
    assert (
        MessageChain(chain=missing_chain_error).get_plain_text()
        == "Error occurred during AI execution."
    )
    assert missing_chain_is_error is True

    missing_final_chain, missing_is_error = aggregator.finalize(None)
    assert MessageChain(chain=missing_final_chain).get_plain_text() == "partial"
    assert missing_is_error is True

    empty_aggregator = third_party._RunnerResultAggregator()
    fallback_chain, fallback_is_error = empty_aggregator.finalize(None)
    assert (
        MessageChain(chain=fallback_chain).get_plain_text()
        == third_party.RUNNER_NO_RESULT_FALLBACK_MESSAGE
    )
    assert fallback_is_error is True

    custom_empty_aggregator = third_party._RunnerResultAggregator("persona failure")
    custom_fallback_chain, custom_fallback_is_error = custom_empty_aggregator.finalize(
        None
    )
    assert MessageChain(chain=custom_fallback_chain).get_plain_text() == (
        "persona failure"
    )
    assert custom_fallback_is_error is True


@pytest.mark.asyncio
async def test_handle_non_streaming_response_uses_final_runner_error_result(
    monkeypatch,
):
    stage = third_party.ThirdPartyAgentSubStage.__new__(
        third_party.ThirdPartyAgentSubStage
    )
    event = FakeEvent()
    runner = FakeThirdPartyRunner(
        final_resp=LLMResponse(
            role="err",
            result_chain=MessageChain().message("runner failed"),
        ),
    )

    async def fake_run_third_party_agent(*args, **kwargs):
        yield MessageChain().message("ignored partial"), False
        yield MessageChain().message("ignored error"), True

    monkeypatch.setattr(
        third_party, "run_third_party_agent", fake_run_third_party_agent
    )

    yields = [
        item
        async for item in stage._handle_non_streaming_response(
            runner=runner,
            event=event,
            stream_to_general=False,
            custom_error_message=None,
        )
    ]

    assert yields == [None, None, None]
    assert event.get_extra(third_party.THIRD_PARTY_RUNNER_ERROR_EXTRA_KEY) is True
    assert (
        event.result_history[-1].result_content_type
        == ResultContentType.AGENT_RUNNER_ERROR
    )
    assert (
        event.result_history[-1].get_plain_text()
        == "Error occurred during AI execution."
    )


@pytest.mark.asyncio
async def test_handle_streaming_response_sets_stream_then_finalizes(monkeypatch):
    stage = third_party.ThirdPartyAgentSubStage.__new__(
        third_party.ThirdPartyAgentSubStage
    )
    event = FakeEvent()
    runner = FakeThirdPartyRunner(
        final_resp=LLMResponse(
            role="assistant",
            result_chain=MessageChain().message("stream final"),
        ),
        done=True,
    )
    close_runner_once = AsyncMock()
    mark_stream_consumed = MagicMock()

    async def fake_run_third_party_agent(*args, **kwargs):
        yield MessageChain().message("chunk-1"), False
        yield MessageChain().message("chunk-2"), False

    monkeypatch.setattr(
        third_party, "run_third_party_agent", fake_run_third_party_agent
    )

    gen = stage._handle_streaming_response(
        runner=runner,
        event=event,
        custom_error_message=None,
        close_runner_once=close_runner_once,
        mark_stream_consumed=mark_stream_consumed,
    )

    assert await gen.__anext__() is None
    stream_result = event.result_history[-1]
    assert stream_result.result_content_type == ResultContentType.STREAMING_RESULT

    streamed_chunks = [
        chain.get_plain_text() async for chain in stream_result.async_stream
    ]
    assert streamed_chunks == ["chunk-1", "chunk-2"]
    mark_stream_consumed.assert_called_once()
    close_runner_once.assert_awaited_once()

    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()

    assert (
        event.result_history[-1].result_content_type
        == ResultContentType.STREAMING_FINISH
    )
    assert event.result_history[-1].get_plain_text() == "stream final"
    assert event.get_extra(third_party.THIRD_PARTY_RUNNER_ERROR_EXTRA_KEY) is False


@pytest.mark.asyncio
async def test_handle_streaming_response_marks_runner_error_and_preserves_finish_result(
    monkeypatch,
):
    stage = third_party.ThirdPartyAgentSubStage.__new__(
        third_party.ThirdPartyAgentSubStage
    )
    event = FakeEvent()
    runner = FakeThirdPartyRunner(
        final_resp=LLMResponse(
            role="assistant",
            result_chain=MessageChain().message("stream final"),
        ),
        done=True,
    )
    close_runner_once = AsyncMock()

    async def fake_run_third_party_agent(*args, **kwargs):
        yield MessageChain().message("partial failure"), True

    monkeypatch.setattr(
        third_party, "run_third_party_agent", fake_run_third_party_agent
    )

    gen = stage._handle_streaming_response(
        runner=runner,
        event=event,
        custom_error_message=None,
        close_runner_once=close_runner_once,
        mark_stream_consumed=MagicMock(),
    )

    assert await gen.__anext__() is None
    stream_result = event.result_history[-1]
    assert [chain.get_plain_text() async for chain in stream_result.async_stream] == [
        "partial failure"
    ]

    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()

    assert close_runner_once.await_count == 1
    assert event.get_extra(third_party.THIRD_PARTY_RUNNER_ERROR_EXTRA_KEY) is True
    assert (
        event.result_history[-1].result_content_type
        == ResultContentType.STREAMING_FINISH
    )
    assert event.result_history[-1].get_plain_text() == "stream final"


@pytest.mark.asyncio
async def test_handle_streaming_response_skips_finish_when_runner_not_done(monkeypatch):
    stage = third_party.ThirdPartyAgentSubStage.__new__(
        third_party.ThirdPartyAgentSubStage
    )
    event = FakeEvent()
    runner = FakeThirdPartyRunner(done=False)

    async def fake_run_third_party_agent(*args, **kwargs):
        yield MessageChain().message("chunk-1"), False

    monkeypatch.setattr(
        third_party, "run_third_party_agent", fake_run_third_party_agent
    )

    gen = stage._handle_streaming_response(
        runner=runner,
        event=event,
        custom_error_message=None,
        close_runner_once=AsyncMock(),
        mark_stream_consumed=MagicMock(),
    )

    assert await gen.__anext__() is None
    assert [
        chain.get_plain_text() async for chain in event.result_history[-1].async_stream
    ] == ["chunk-1"]

    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()

    assert len(event.result_history) == 1
    assert (
        event.result_history[-1].result_content_type
        == ResultContentType.STREAMING_RESULT
    )


@pytest.mark.asyncio
async def test_handle_streaming_response_falls_back_to_streamed_chunks_when_final_response_missing(
    monkeypatch,
):
    stage = third_party.ThirdPartyAgentSubStage.__new__(
        third_party.ThirdPartyAgentSubStage
    )
    event = FakeEvent()
    runner = FakeThirdPartyRunner(final_resp=None, done=True)
    close_runner_once = AsyncMock()

    async def fake_run_third_party_agent(*args, **kwargs):
        yield MessageChain().message("partial answer"), False

    monkeypatch.setattr(
        third_party, "run_third_party_agent", fake_run_third_party_agent
    )

    gen = stage._handle_streaming_response(
        runner=runner,
        event=event,
        custom_error_message=None,
        close_runner_once=close_runner_once,
        mark_stream_consumed=MagicMock(),
    )

    assert await gen.__anext__() is None
    assert [
        chain.get_plain_text() async for chain in event.result_history[-1].async_stream
    ] == ["partial answer"]

    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()

    close_runner_once.assert_awaited_once()
    assert event.get_extra(third_party.THIRD_PARTY_RUNNER_ERROR_EXTRA_KEY) is False
    assert (
        event.result_history[-1].result_content_type
        == ResultContentType.STREAMING_FINISH
    )
    assert event.result_history[-1].get_plain_text() == "partial answer"


@pytest.mark.asyncio
async def test_handle_non_streaming_response_falls_back_when_runner_returns_nothing(
    monkeypatch,
):
    stage = third_party.ThirdPartyAgentSubStage.__new__(
        third_party.ThirdPartyAgentSubStage
    )
    event = FakeEvent()
    runner = FakeThirdPartyRunner(final_resp=None)

    async def fake_run_third_party_agent(*args, **kwargs):
        if False:
            yield MessageChain().message("unused"), False

    monkeypatch.setattr(
        third_party, "run_third_party_agent", fake_run_third_party_agent
    )

    yields = [
        item
        async for item in stage._handle_non_streaming_response(
            runner=runner,
            event=event,
            stream_to_general=False,
            custom_error_message=None,
        )
    ]

    assert yields == [None]
    assert event.get_extra(third_party.THIRD_PARTY_RUNNER_ERROR_EXTRA_KEY) is True
    assert (
        event.result_history[-1].result_content_type
        == ResultContentType.AGENT_RUNNER_ERROR
    )
    assert (
        event.result_history[-1].get_plain_text()
        == third_party.RUNNER_NO_RESULT_FALLBACK_MESSAGE
    )


@pytest.mark.asyncio
async def test_start_stream_watchdog_skips_close_when_stream_already_consumed():
    close_runner_once = AsyncMock()

    task = third_party._start_stream_watchdog(
        timeout_sec=0,
        is_stream_consumed=lambda: True,
        close_runner_once=close_runner_once,
    )
    await task

    close_runner_once.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_stream_watchdog_closes_runner_after_timeout():
    close_runner_once = AsyncMock()

    task = third_party._start_stream_watchdog(
        timeout_sec=0,
        is_stream_consumed=lambda: False,
        close_runner_once=close_runner_once,
    )
    await task

    close_runner_once.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_stream_watchdog_swallows_close_exceptions():
    close_runner_once = AsyncMock(side_effect=RuntimeError("close failed"))

    task = third_party._start_stream_watchdog(
        timeout_sec=0,
        is_stream_consumed=lambda: False,
        close_runner_once=close_runner_once,
    )
    await task

    close_runner_once.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_runner_if_supported_handles_sync_async_and_close_errors():
    sync_runner = SimpleNamespace(closed=False)

    def sync_close():
        sync_runner.closed = True

    sync_runner.close = sync_close
    await third_party._close_runner_if_supported(sync_runner)
    assert sync_runner.closed is True

    async_runner = SimpleNamespace(close=AsyncMock())
    await third_party._close_runner_if_supported(async_runner)
    async_runner.close.assert_awaited_once()

    bad_runner = SimpleNamespace(
        close=MagicMock(side_effect=RuntimeError("close boom"))
    )
    await third_party._close_runner_if_supported(bad_runner)


@pytest.mark.asyncio
async def test_resolve_persona_custom_error_message_returns_none_on_failure(
    monkeypatch,
):
    stage = third_party.ThirdPartyAgentSubStage.__new__(
        third_party.ThirdPartyAgentSubStage
    )
    stage.ctx = _pipeline_context(
        SimpleNamespace(
            conversation_manager=object(),
            persona_manager=object(),
        )
    )
    stage.conf = {"provider_settings": {}}
    logger_debug = MagicMock()

    monkeypatch.setattr(
        third_party,
        "resolve_event_conversation_persona_id",
        AsyncMock(side_effect=RuntimeError("persona lookup failed")),
    )
    monkeypatch.setattr(third_party.logger, "debug", logger_debug)

    result = await stage._resolve_persona_custom_error_message(FakeEvent())

    assert result is None
    logger_debug.assert_called_once()


@pytest.mark.asyncio
async def test_third_party_process_returns_early_when_wake_prefix_does_not_match():
    stage = third_party.ThirdPartyAgentSubStage.__new__(
        third_party.ThirdPartyAgentSubStage
    )
    event = FakeInternalProcessEvent(message_str="hello")

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]

    assert yielded == []
    assert event.result_history == []


@pytest.mark.asyncio
async def test_third_party_process_uses_json_card_summary_when_prompt_is_empty(
    monkeypatch,
):
    stage = third_party.ThirdPartyAgentSubStage.__new__(
        third_party.ThirdPartyAgentSubStage
    )
    stage.prov_id = "runner-1"
    stage.runner_type = "dify"
    stage.streaming_response = False
    stage.unsupported_streaming_strategy = "ignore"
    stage.stream_consumption_close_timeout_sec = 1
    stage.ctx = _pipeline_context(SimpleNamespace())
    stage.conf = {"provider_settings": {}, "provider": [{"id": "runner-1"}]}
    card_data = {"meta": {"news": {"title": "News"}}}
    event = FakeInternalProcessEvent(
        message_str="",
        message_components=[Json(data=card_data)],
    )
    runner = FakeThirdPartyRunner()
    captured: list[object] = []

    class FakeDifyRunner:
        def __new__(cls):
            return runner

        @classmethod
        def __class_getitem__(cls, _item):
            return cls

    async def fake_non_streaming_response(**kwargs):
        captured.append(kwargs)
        yield

    stage._resolve_persona_custom_error_message = AsyncMock(return_value=None)
    monkeypatch.setattr(
        third_party,
        "set_persona_custom_error_message_on_event",
        MagicMock(),
    )
    monkeypatch.setattr(third_party, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(third_party, "DifyAgentRunner", FakeDifyRunner)
    monkeypatch.setattr(
        third_party,
        "AstrAgentContext",
        lambda context, event: SimpleNamespace(context=context, event=event),
    )
    monkeypatch.setattr(
        third_party,
        "AgentContextWrapper",
        lambda context, tool_call_timeout: SimpleNamespace(
            context=context,
            tool_call_timeout=tool_call_timeout,
        ),
    )
    monkeypatch.setattr(
        stage, "_handle_non_streaming_response", fake_non_streaming_response
    )
    _set_metrics_upload(stage, AsyncMock())

    yielded = [item async for item in stage.process(event, provider_wake_prefix="")]
    await asyncio.sleep(0)

    assert yielded == [None]
    req = runner.reset.await_args.kwargs["request"]
    assert "[Shared Card: Title: News]" in req.prompt
    assert json.dumps(card_data) not in req.prompt
    assert captured


@pytest.mark.asyncio
async def test_third_party_process_returns_early_when_request_has_no_prompt_or_media(
    monkeypatch,
):
    stage = third_party.ThirdPartyAgentSubStage.__new__(
        third_party.ThirdPartyAgentSubStage
    )
    stage.prov_id = "runner-1"
    stage.runner_type = "dify"
    stage.ctx = _pipeline_context(SimpleNamespace())
    stage.conf = {"provider": [{"id": "runner-1"}]}
    event = FakeInternalProcessEvent(message_str="ask", message_components=[])

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]

    assert yielded == []
    assert event.result_history == []


@pytest.mark.asyncio
async def test_third_party_process_raises_for_unsupported_runner_type(monkeypatch):
    stage = third_party.ThirdPartyAgentSubStage.__new__(
        third_party.ThirdPartyAgentSubStage
    )
    stage.prov_id = "runner-1"
    stage.runner_type = "unknown"
    stage.streaming_response = False
    stage.unsupported_streaming_strategy = "ignore"
    stage.ctx = _pipeline_context(SimpleNamespace())
    stage.conf = {"provider": [{"id": "runner-1", "name": "Runner One"}]}
    event = FakeInternalProcessEvent(message_str="ask hello")

    stage._resolve_persona_custom_error_message = AsyncMock(return_value=None)
    monkeypatch.setattr(
        third_party,
        "set_persona_custom_error_message_on_event",
        MagicMock(),
    )
    monkeypatch.setattr(third_party, "call_event_hook", AsyncMock(return_value=False))

    with pytest.raises(ValueError, match="Unsupported third party agent runner type"):
        async for _ in stage.process(event, provider_wake_prefix="ask"):
            pass


@pytest.mark.asyncio
async def test_third_party_process_uses_non_streaming_path_when_event_disables_streaming(
    monkeypatch,
):
    stage = third_party.ThirdPartyAgentSubStage.__new__(
        third_party.ThirdPartyAgentSubStage
    )
    stage.prov_id = "runner-1"
    stage.runner_type = "dify"
    stage.streaming_response = True
    stage.unsupported_streaming_strategy = "ignore"
    stage.stream_consumption_close_timeout_sec = 1
    stage.ctx = _pipeline_context(SimpleNamespace())
    stage.conf = {"provider_settings": {}}
    event = FakeInternalProcessEvent(
        message_str="ask hello",
        extras={"enable_streaming": False},
    )
    metric_upload = AsyncMock()
    runner = FakeThirdPartyRunner()
    non_streaming_calls: list[dict] = []

    class FakeDifyRunner:
        def __new__(cls):
            return runner

        @classmethod
        def __class_getitem__(cls, _item):
            return cls

    async def fake_non_streaming_response(**kwargs):
        non_streaming_calls.append(kwargs)
        yield

    async def fake_streaming_response(**kwargs):
        raise AssertionError("streaming path should not be used")
        yield

    stage.conf["provider"] = [{"id": "runner-1", "name": "Runner One"}]
    stage._resolve_persona_custom_error_message = AsyncMock(return_value=None)
    monkeypatch.setattr(
        third_party,
        "set_persona_custom_error_message_on_event",
        MagicMock(),
    )
    monkeypatch.setattr(third_party, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(third_party, "DifyAgentRunner", FakeDifyRunner)
    monkeypatch.setattr(
        third_party,
        "AstrAgentContext",
        lambda context, event: SimpleNamespace(context=context, event=event),
    )
    monkeypatch.setattr(
        third_party,
        "AgentContextWrapper",
        lambda context, tool_call_timeout: SimpleNamespace(
            context=context,
            tool_call_timeout=tool_call_timeout,
        ),
    )
    monkeypatch.setattr(
        stage, "_handle_non_streaming_response", fake_non_streaming_response
    )
    monkeypatch.setattr(stage, "_handle_streaming_response", fake_streaming_response)
    _set_metrics_upload(stage, metric_upload)

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]
    await asyncio.sleep(0)

    assert yielded == [None]
    assert runner.close.await_count == 1
    assert non_streaming_calls[0]["stream_to_general"] is False
    assert metric_upload.await_count == 1
    assert runner.reset.await_args.kwargs["streaming"] is False


@pytest.mark.asyncio
async def test_third_party_process_turns_streaming_into_general_when_platform_does_not_support_it(
    monkeypatch,
):
    stage = third_party.ThirdPartyAgentSubStage.__new__(
        third_party.ThirdPartyAgentSubStage
    )
    stage.prov_id = "runner-1"
    stage.runner_type = "dify"
    stage.streaming_response = True
    stage.unsupported_streaming_strategy = "turn_off"
    stage.stream_consumption_close_timeout_sec = 1
    stage.ctx = _pipeline_context(SimpleNamespace())
    stage.conf = {"provider_settings": {}}
    event = FakeInternalProcessEvent(message_str="ask hello")
    event.platform_meta.support_streaming_message = False
    metric_upload = AsyncMock()
    runner = FakeThirdPartyRunner()
    non_streaming_calls: list[dict] = []

    class FakeDifyRunner:
        def __new__(cls):
            return runner

        @classmethod
        def __class_getitem__(cls, _item):
            return cls

    async def fake_non_streaming_response(**kwargs):
        non_streaming_calls.append(kwargs)
        yield

    async def fake_streaming_response(**kwargs):
        raise AssertionError("streaming path should not be used")
        yield

    stage.conf["provider"] = [{"id": "runner-1", "name": "Runner One"}]
    stage._resolve_persona_custom_error_message = AsyncMock(return_value=None)
    monkeypatch.setattr(
        third_party,
        "set_persona_custom_error_message_on_event",
        MagicMock(),
    )
    monkeypatch.setattr(third_party, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(third_party, "DifyAgentRunner", FakeDifyRunner)
    monkeypatch.setattr(
        third_party,
        "AstrAgentContext",
        lambda context, event: SimpleNamespace(context=context, event=event),
    )
    monkeypatch.setattr(
        third_party,
        "AgentContextWrapper",
        lambda context, tool_call_timeout: SimpleNamespace(
            context=context,
            tool_call_timeout=tool_call_timeout,
        ),
    )
    monkeypatch.setattr(
        stage, "_handle_non_streaming_response", fake_non_streaming_response
    )
    monkeypatch.setattr(stage, "_handle_streaming_response", fake_streaming_response)
    _set_metrics_upload(stage, metric_upload)

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]
    await asyncio.sleep(0)

    assert yielded == [None]
    assert non_streaming_calls[0]["stream_to_general"] is True
    assert runner.reset.await_args.kwargs["streaming"] is True
    assert runner.close.await_count == 1
    assert metric_upload.await_count == 1


@pytest.mark.asyncio
async def test_third_party_process_closes_runner_when_streaming_handler_raises_before_yield(
    monkeypatch,
):
    stage = third_party.ThirdPartyAgentSubStage.__new__(
        third_party.ThirdPartyAgentSubStage
    )
    stage.prov_id = "runner-1"
    stage.runner_type = "dify"
    stage.streaming_response = True
    stage.unsupported_streaming_strategy = "ignore"
    stage.stream_consumption_close_timeout_sec = 1
    stage.ctx = _pipeline_context(SimpleNamespace())
    stage.conf = {"provider_settings": {}}
    event = FakeInternalProcessEvent(message_str="ask hello")
    runner = FakeThirdPartyRunner()
    metric_upload = AsyncMock()
    watchdog_started = asyncio.Event()
    watchdog_cancelled = asyncio.Event()
    watchdog_tasks: list[asyncio.Task[None]] = []

    class FakeDifyRunner:
        def __new__(cls):
            return runner

        @classmethod
        def __class_getitem__(cls, _item):
            return cls

    async def fake_streaming_response(**kwargs):
        await watchdog_started.wait()
        raise RuntimeError("stream setup failed")
        yield

    async def pending_watchdog():
        watchdog_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            watchdog_cancelled.set()
            raise

    def fake_start_stream_watchdog(**kwargs):
        task = asyncio.create_task(pending_watchdog(), name="test:stream-watchdog")
        watchdog_tasks.append(task)
        return task

    stage.conf["provider"] = [{"id": "runner-1", "name": "Runner One"}]
    stage._resolve_persona_custom_error_message = AsyncMock(return_value=None)
    monkeypatch.setattr(
        third_party,
        "set_persona_custom_error_message_on_event",
        MagicMock(),
    )
    monkeypatch.setattr(third_party, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(third_party, "DifyAgentRunner", FakeDifyRunner)
    monkeypatch.setattr(
        third_party,
        "AstrAgentContext",
        lambda context, event: SimpleNamespace(context=context, event=event),
    )
    monkeypatch.setattr(
        third_party,
        "AgentContextWrapper",
        lambda context, tool_call_timeout: SimpleNamespace(
            context=context,
            tool_call_timeout=tool_call_timeout,
        ),
    )
    monkeypatch.setattr(stage, "_handle_streaming_response", fake_streaming_response)
    monkeypatch.setattr(
        third_party,
        "_start_stream_watchdog",
        fake_start_stream_watchdog,
    )
    _set_metrics_upload(stage, metric_upload)

    with pytest.raises(RuntimeError, match="stream setup failed"):
        async for _ in stage.process(event, provider_wake_prefix="ask"):
            pass

    assert runner.close.await_count == 1
    assert metric_upload.await_count == 0
    assert watchdog_cancelled.is_set()
    assert watchdog_tasks[0].done()


@pytest.mark.asyncio
async def test_third_party_process_closes_runner_when_reset_raises_and_skips_metric(
    monkeypatch,
):
    stage = third_party.ThirdPartyAgentSubStage.__new__(
        third_party.ThirdPartyAgentSubStage
    )
    stage.prov_id = "runner-1"
    stage.runner_type = "dify"
    stage.streaming_response = False
    stage.unsupported_streaming_strategy = "ignore"
    stage.stream_consumption_close_timeout_sec = 1
    stage.ctx = _pipeline_context(SimpleNamespace())
    stage.conf = {"provider_settings": {}}
    event = FakeInternalProcessEvent(message_str="ask hello")
    metric_upload = AsyncMock()
    runner = FakeThirdPartyRunner()
    runner.reset = AsyncMock(side_effect=RuntimeError("reset failed"))

    class FakeDifyRunner:
        def __new__(cls):
            return runner

        @classmethod
        def __class_getitem__(cls, _item):
            return cls

    stage.conf["provider"] = [{"id": "runner-1", "name": "Runner One"}]
    stage._resolve_persona_custom_error_message = AsyncMock(return_value=None)
    monkeypatch.setattr(
        third_party,
        "set_persona_custom_error_message_on_event",
        MagicMock(),
    )
    monkeypatch.setattr(third_party, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(third_party, "DifyAgentRunner", FakeDifyRunner)
    monkeypatch.setattr(
        third_party,
        "AstrAgentContext",
        lambda context, event: SimpleNamespace(context=context, event=event),
    )
    monkeypatch.setattr(
        third_party,
        "AgentContextWrapper",
        lambda context, tool_call_timeout: SimpleNamespace(
            context=context,
            tool_call_timeout=tool_call_timeout,
        ),
    )
    _set_metrics_upload(stage, metric_upload)

    with pytest.raises(RuntimeError, match="reset failed"):
        async for _ in stage.process(event, provider_wake_prefix="ask"):
            pass

    assert runner.close.await_count == 1
    assert metric_upload.await_count == 0


@pytest.mark.asyncio
async def test_third_party_process_closes_runner_when_non_streaming_handler_raises(
    monkeypatch,
):
    stage = third_party.ThirdPartyAgentSubStage.__new__(
        third_party.ThirdPartyAgentSubStage
    )
    stage.prov_id = "runner-1"
    stage.runner_type = "dify"
    stage.streaming_response = False
    stage.unsupported_streaming_strategy = "ignore"
    stage.stream_consumption_close_timeout_sec = 1
    stage.ctx = _pipeline_context(SimpleNamespace())
    stage.conf = {"provider_settings": {}}
    event = FakeInternalProcessEvent(message_str="ask hello")
    metric_upload = AsyncMock()
    runner = FakeThirdPartyRunner()

    class FakeDifyRunner:
        def __new__(cls):
            return runner

        @classmethod
        def __class_getitem__(cls, _item):
            return cls

    async def fake_non_streaming_response(**kwargs):
        raise RuntimeError("non-streaming failed")
        yield

    stage.conf["provider"] = [{"id": "runner-1", "name": "Runner One"}]
    stage._resolve_persona_custom_error_message = AsyncMock(return_value=None)
    monkeypatch.setattr(
        third_party,
        "set_persona_custom_error_message_on_event",
        MagicMock(),
    )
    monkeypatch.setattr(third_party, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(third_party, "DifyAgentRunner", FakeDifyRunner)
    monkeypatch.setattr(
        third_party,
        "AstrAgentContext",
        lambda context, event: SimpleNamespace(context=context, event=event),
    )
    monkeypatch.setattr(
        third_party,
        "AgentContextWrapper",
        lambda context, tool_call_timeout: SimpleNamespace(
            context=context,
            tool_call_timeout=tool_call_timeout,
        ),
    )
    monkeypatch.setattr(
        stage, "_handle_non_streaming_response", fake_non_streaming_response
    )
    _set_metrics_upload(stage, metric_upload)

    with pytest.raises(RuntimeError, match="non-streaming failed"):
        async for _ in stage.process(event, provider_wake_prefix="ask"):
            pass

    assert runner.close.await_count == 1
    assert metric_upload.await_count == 0


@pytest.mark.asyncio
async def test_third_party_process_returns_early_when_provider_id_missing(monkeypatch):
    stage = third_party.ThirdPartyAgentSubStage.__new__(
        third_party.ThirdPartyAgentSubStage
    )
    stage.prov_id = ""
    stage.runner_type = "dify"
    stage.streaming_response = False
    stage.unsupported_streaming_strategy = "ignore"
    stage.ctx = _pipeline_context(SimpleNamespace())
    stage.conf = {"provider_settings": {}}
    event = FakeInternalProcessEvent(message_str="ask hello")
    logger_error = MagicMock()

    stage.conf["provider"] = []
    monkeypatch.setattr(third_party.logger, "error", logger_error)

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]

    assert yielded == []
    logger_error.assert_called_once()
    assert event.result_history == []


@pytest.mark.asyncio
async def test_third_party_process_returns_early_when_provider_config_missing(
    monkeypatch,
):
    stage = third_party.ThirdPartyAgentSubStage.__new__(
        third_party.ThirdPartyAgentSubStage
    )
    stage.prov_id = "runner-1"
    stage.runner_type = "dify"
    stage.streaming_response = False
    stage.unsupported_streaming_strategy = "ignore"
    stage.ctx = _pipeline_context(SimpleNamespace())
    stage.conf = {"provider_settings": {}}
    event = FakeInternalProcessEvent(message_str="ask hello")
    logger_error = MagicMock()

    stage.conf["provider"] = []
    monkeypatch.setattr(third_party.logger, "error", logger_error)

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]

    assert yielded == []
    logger_error.assert_called_once()
    assert event.result_history == []


@pytest.mark.asyncio
async def test_third_party_process_stops_when_llm_request_hook_blocks(monkeypatch):
    stage = third_party.ThirdPartyAgentSubStage.__new__(
        third_party.ThirdPartyAgentSubStage
    )
    stage.prov_id = "runner-1"
    stage.runner_type = "dify"
    stage.streaming_response = True
    stage.unsupported_streaming_strategy = "ignore"
    stage.stream_consumption_close_timeout_sec = 1
    stage.ctx = _pipeline_context(SimpleNamespace())
    stage.conf = {"provider_settings": {}}
    event = FakeInternalProcessEvent(message_str="ask hello")

    class FakeDifyRunner:
        def __new__(cls):
            raise AssertionError("runner should not be constructed")

        @classmethod
        def __class_getitem__(cls, _item):
            return cls

    stage.conf["provider"] = [{"id": "runner-1", "name": "Runner One"}]
    stage._resolve_persona_custom_error_message = AsyncMock(return_value=None)
    monkeypatch.setattr(
        third_party,
        "set_persona_custom_error_message_on_event",
        MagicMock(),
    )
    monkeypatch.setattr(third_party, "call_event_hook", AsyncMock(return_value=True))
    monkeypatch.setattr(third_party, "DifyAgentRunner", FakeDifyRunner)

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]

    assert yielded == []
    assert event.result_history == []


@pytest.mark.asyncio
async def test_third_party_process_watchdog_closes_runner_when_stream_never_consumed(
    monkeypatch,
):
    stage = third_party.ThirdPartyAgentSubStage.__new__(
        third_party.ThirdPartyAgentSubStage
    )
    stage.prov_id = "runner-1"
    stage.runner_type = "dify"
    stage.streaming_response = True
    stage.unsupported_streaming_strategy = "ignore"
    stage.stream_consumption_close_timeout_sec = 0
    stage.ctx = _pipeline_context(SimpleNamespace())
    stage.conf = {"provider_settings": {}}
    event = FakeInternalProcessEvent(message_str="ask hello")
    metric_upload = AsyncMock()
    runner = FakeThirdPartyRunner()

    class FakeDifyRunner:
        def __new__(cls):
            return runner

        @classmethod
        def __class_getitem__(cls, _item):
            return cls

    async def fake_streaming_response(**kwargs):
        event.set_result(
            MessageEventResult()
            .set_result_content_type(ResultContentType.STREAMING_RESULT)
            .set_async_stream(_never_consumed_stream()),
        )
        yield

    async def _never_consumed_stream():
        if False:
            yield MessageChain().message("unused")

    stage.conf["provider"] = [{"id": "runner-1", "name": "Runner One"}]
    stage._resolve_persona_custom_error_message = AsyncMock(return_value=None)
    monkeypatch.setattr(
        third_party,
        "set_persona_custom_error_message_on_event",
        MagicMock(),
    )
    monkeypatch.setattr(third_party, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(third_party, "DifyAgentRunner", FakeDifyRunner)
    monkeypatch.setattr(
        third_party,
        "AstrAgentContext",
        lambda context, event: SimpleNamespace(context=context, event=event),
    )
    monkeypatch.setattr(
        third_party,
        "AgentContextWrapper",
        lambda context, tool_call_timeout: SimpleNamespace(
            context=context,
            tool_call_timeout=tool_call_timeout,
        ),
    )
    monkeypatch.setattr(stage, "_handle_streaming_response", fake_streaming_response)
    _set_metrics_upload(stage, metric_upload)

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]
    await asyncio.sleep(0)

    assert yielded == [None]
    assert runner.close.await_count == 1
    assert metric_upload.await_count == 1
    assert (
        event.result_history[-1].result_content_type
        == ResultContentType.STREAMING_RESULT
    )


@pytest.mark.asyncio
async def test_third_party_process_builds_media_only_request_and_uses_non_streaming_path(
    monkeypatch,
):
    stage = third_party.ThirdPartyAgentSubStage.__new__(
        third_party.ThirdPartyAgentSubStage
    )
    stage.prov_id = "runner-1"
    stage.runner_type = "dify"
    stage.streaming_response = False
    stage.unsupported_streaming_strategy = "ignore"
    stage.stream_consumption_close_timeout_sec = 1
    stage.ctx = _pipeline_context(SimpleNamespace())
    stage.conf = {"provider_settings": {}}
    image = MagicMock(spec=Image)
    image.convert_to_file_path = AsyncMock(return_value="/tmp/image.png")
    record = MagicMock(spec=Record)
    record.convert_to_file_path = AsyncMock(return_value="/tmp/audio.wav")
    event = FakeInternalProcessEvent(
        message_str="ask",
        message_components=[image, record],
    )
    metric_upload = AsyncMock()
    runner = FakeThirdPartyRunner()
    captured_calls: list[dict] = []

    class FakeDifyRunner:
        def __new__(cls):
            return runner

        @classmethod
        def __class_getitem__(cls, _item):
            return cls

    async def fake_non_streaming_response(**kwargs):
        captured_calls.append(kwargs)
        yield

    stage.conf["provider"] = [{"id": "runner-1", "name": "Runner One"}]
    stage._resolve_persona_custom_error_message = AsyncMock(return_value=None)
    set_persona_error = MagicMock()
    monkeypatch.setattr(
        third_party,
        "set_persona_custom_error_message_on_event",
        set_persona_error,
    )
    monkeypatch.setattr(third_party, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(third_party, "DifyAgentRunner", FakeDifyRunner)
    monkeypatch.setattr(
        third_party,
        "AstrAgentContext",
        lambda context, event: SimpleNamespace(context=context, event=event),
    )
    monkeypatch.setattr(
        third_party,
        "AgentContextWrapper",
        lambda context, tool_call_timeout: SimpleNamespace(
            context=context,
            tool_call_timeout=tool_call_timeout,
        ),
    )
    monkeypatch.setattr(
        stage, "_handle_non_streaming_response", fake_non_streaming_response
    )
    _set_metrics_upload(stage, metric_upload)

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]
    await asyncio.sleep(0)

    assert yielded == [None]
    assert len(captured_calls) == 1
    req = runner.reset.await_args.kwargs["request"]
    assert req.prompt == ""
    assert req.image_urls == ["/tmp/image.png"]
    assert req.audio_urls == ["/tmp/audio.wav"]
    set_persona_error.assert_called_once_with(event, None)
    assert runner.close.await_count == 1
    assert metric_upload.await_count == 1


@pytest.mark.asyncio
async def test_third_party_process_inlines_qq_face_component_and_quote_context(
    monkeypatch,
):
    stage = third_party.ThirdPartyAgentSubStage.__new__(
        third_party.ThirdPartyAgentSubStage
    )
    stage.prov_id = "runner-1"
    stage.runner_type = "dify"
    stage.streaming_response = False
    stage.unsupported_streaming_strategy = "ignore"
    stage.stream_consumption_close_timeout_sec = 1
    stage.ctx = _pipeline_context(SimpleNamespace())
    stage.conf = {"provider_settings": {}}
    event = FakeInternalProcessEvent(
        message_str="askhello",
        message_components=[
            Face(id=111),
            Reply(id="quoted-face", chain=[Face(id=111)], message_str=""),
        ],
    )
    metric_upload = AsyncMock()
    runner = FakeThirdPartyRunner()

    class FakeDifyRunner:
        def __new__(cls):
            return runner

        @classmethod
        def __class_getitem__(cls, _item):
            return cls

    async def fake_non_streaming_response(**_kwargs):
        yield

    stage.conf["provider"] = [{"id": "runner-1", "name": "Runner One"}]
    stage._resolve_persona_custom_error_message = AsyncMock(return_value=None)
    monkeypatch.setattr(
        third_party,
        "set_persona_custom_error_message_on_event",
        MagicMock(),
    )
    request_hook = AsyncMock(return_value=False)
    monkeypatch.setattr(third_party, "call_event_hook", request_hook)
    monkeypatch.setattr(third_party, "DifyAgentRunner", FakeDifyRunner)
    monkeypatch.setattr(
        third_party,
        "AstrAgentContext",
        lambda context, event: SimpleNamespace(context=context, event=event),
    )
    monkeypatch.setattr(
        third_party,
        "AgentContextWrapper",
        lambda context, tool_call_timeout: SimpleNamespace(
            context=context,
            tool_call_timeout=tool_call_timeout,
        ),
    )
    monkeypatch.setattr(
        stage, "_handle_non_streaming_response", fake_non_streaming_response
    )
    _set_metrics_upload(stage, metric_upload)

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]

    assert yielded == [None]
    req = runner.reset.await_args.kwargs["request"]
    assert req.prompt == (
        "hello\n\n"
        "<Message Components>\n"
        "[QQ Face: 可怜 (id: 111)]\n"
        "</Message Components>\n\n"
        "<Quoted Message>\n"
        "[QQ Face: 可怜 (id: 111)]\n"
        "</Quoted Message>"
    )
    assert request_hook.await_args.args[2] is req
    assert event.message_str == "askhello"
    assert event.message_obj.message[0].id == 111


@pytest.mark.asyncio
async def test_third_party_process_streaming_consumed_closes_runner_after_stream_use(
    monkeypatch,
):
    stage = third_party.ThirdPartyAgentSubStage.__new__(
        third_party.ThirdPartyAgentSubStage
    )
    stage.prov_id = "runner-1"
    stage.runner_type = "dify"
    stage.streaming_response = True
    stage.unsupported_streaming_strategy = "ignore"
    stage.stream_consumption_close_timeout_sec = 1
    stage.ctx = _pipeline_context(SimpleNamespace())
    stage.conf = {"provider_settings": {}}
    event = FakeInternalProcessEvent(message_str="ask hello")
    metric_upload = AsyncMock()
    runner = FakeThirdPartyRunner(
        final_resp=LLMResponse(
            role="assistant",
            result_chain=MessageChain().message("stream final"),
        ),
        done=True,
    )

    class FakeDifyRunner:
        def __new__(cls):
            return runner

        @classmethod
        def __class_getitem__(cls, _item):
            return cls

    stage.conf["provider"] = [{"id": "runner-1", "name": "Runner One"}]
    stage._resolve_persona_custom_error_message = AsyncMock(return_value=None)
    monkeypatch.setattr(
        third_party,
        "set_persona_custom_error_message_on_event",
        MagicMock(),
    )
    monkeypatch.setattr(third_party, "call_event_hook", AsyncMock(return_value=False))
    monkeypatch.setattr(third_party, "DifyAgentRunner", FakeDifyRunner)
    monkeypatch.setattr(
        third_party,
        "AstrAgentContext",
        lambda context, event: SimpleNamespace(context=context, event=event),
    )
    monkeypatch.setattr(
        third_party,
        "AgentContextWrapper",
        lambda context, tool_call_timeout: SimpleNamespace(
            context=context,
            tool_call_timeout=tool_call_timeout,
        ),
    )
    _set_metrics_upload(stage, metric_upload)

    yielded = [item async for item in stage.process(event, provider_wake_prefix="ask")]
    await asyncio.sleep(0)

    assert yielded == [None]
    stream_result = event.result_history[0]
    assert stream_result.result_content_type == ResultContentType.STREAMING_RESULT
    streamed_chunks = [
        chain.get_plain_text() async for chain in stream_result.async_stream
    ]
    assert streamed_chunks == []
    assert (
        event.result_history[-1].result_content_type
        == ResultContentType.STREAMING_FINISH
    )
    assert event.result_history[-1].get_plain_text() == "stream final"
    assert runner.close.await_count == 1
    assert metric_upload.await_count == 1
