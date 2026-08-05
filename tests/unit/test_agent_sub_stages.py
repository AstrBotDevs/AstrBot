import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent.llm_types import LLMResponse, ProviderRequest, TokenUsage
from astrbot.core.agent.message import CheckpointData, Message
from astrbot.core.assistant_history import build_pending_assistant_history
from astrbot.core.message.components import Image, Record, Reply
from astrbot.core.message.message_event_result import (
    MessageChain,
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.pipeline.process_stage.method.agent_sub_stages import (
    internal,
    third_party,
)
from astrbot.core.platform.send_result import DeliveryAttempt, DeliveryReceipt
from astrbot.core.utils import task_utils


class FakeEvent:
    def __init__(self, *, extras: dict | None = None):
        self.unified_msg_origin = "webchat:FriendMessage:test-session"
        self._extras = extras or {}
        self.result_history: list[MessageEventResult] = []

    def get_extra(self, key: str):
        return self._extras.get(key)

    def set_extra(self, key: str, value) -> None:
        self._extras[key] = value

    def set_result(self, result: MessageEventResult) -> None:
        self.result_history.append(result)


class FakeInternalProcessEvent(FakeEvent):
    def __init__(
        self,
        *,
        message_str: str = "hello",
        extras: dict | None = None,
        message_components: list | None = None,
        stopped: bool = False,
    ):
        super().__init__(extras=extras)
        self.message_str = message_str
        self.message_obj = SimpleNamespace(message=message_components or [])
        self.platform_meta = SimpleNamespace(support_streaming_message=True)
        self.trace = MagicMock()
        self.trace.record = MagicMock()
        self.send = AsyncMock()
        self.send_typing = AsyncMock()
        self.stop_typing = AsyncMock()
        self._stopped = stopped

    def is_stopped(self) -> bool:
        return self._stopped


def _internal_plugin_context(tts_provider=None) -> SimpleNamespace:
    return SimpleNamespace(
        get_using_tts_provider=lambda _umo: tts_provider,
        database=SimpleNamespace(insert_provider_stat=AsyncMock()),
        session_lock_manager=SimpleNamespace(
            acquire_lock=lambda _umo: _AsyncLockContext()
        ),
        background_tasks=set(),
        follow_up_coordinator=SimpleNamespace(
            try_capture=MagicMock(return_value=None),
            prepare_capture=AsyncMock(),
            finalize_capture=AsyncMock(),
            register_active_runner=MagicMock(),
            unregister_active_runner=MagicMock(),
        ),
    )


def _pipeline_context(execution_context: SimpleNamespace) -> SimpleNamespace:
    if not hasattr(execution_context, "background_tasks"):
        execution_context.background_tasks = set()
    if not hasattr(execution_context, "metrics"):
        execution_context.metrics = SimpleNamespace(upload=AsyncMock())
    return SimpleNamespace(
        execution_context=execution_context,
        handlers=SimpleNamespace(),
        plugins=SimpleNamespace(),
    )


def _set_metrics_upload(stage, upload) -> None:
    """Replace only the telemetry port bound to this test runtime."""
    stage.ctx.execution_context.metrics.upload = upload


class FakeThirdPartyRunner:
    def __init__(
        self,
        responses=None,
        *,
        final_resp: LLMResponse | None = None,
        step_exception: Exception | None = None,
        done: bool = True,
    ):
        self._responses = responses or []
        self._final_resp = final_resp
        self._step_exception = step_exception
        self._done = done
        self.reset = AsyncMock()
        self.close = AsyncMock()

    async def step_until_done(self, max_step: int = 30):
        if self._step_exception is not None:
            raise self._step_exception

        for response in self._responses:
            yield response

    def get_final_llm_resp(self) -> LLMResponse | None:
        return self._final_resp

    def done(self) -> bool:
        return self._done


class FakeInternalRunner:
    def __init__(
        self,
        *,
        final_resp: LLMResponse | None = None,
        done: bool = True,
        aborted: bool = False,
    ):
        self._final_resp = final_resp or LLMResponse(
            role="assistant",
            completion_text="done",
        )
        self._done = done
        self._aborted = aborted
        self.run_context = SimpleNamespace(
            messages=[Message(role="assistant", content="done")]
        )
        self.stats = SimpleNamespace(
            to_dict=lambda: {"steps": 1},
            token_usage=TokenUsage(output=1),
        )
        self.provider = SimpleNamespace(
            get_model=lambda: "fake-model",
            meta=lambda: SimpleNamespace(type="fake-provider", id="fake-provider"),
            provider_config={"id": "provider-1"},
        )

    def done(self) -> bool:
        return self._done

    def was_aborted(self) -> bool:
        return self._aborted

    def get_final_llm_resp(self) -> LLMResponse | None:
        return self._final_resp


def _fake_build_cfg(**kwargs):
    return SimpleNamespace(**kwargs)


def _runner_response(resp_type: str, text: str):
    return SimpleNamespace(
        type=resp_type,
        data={"chain": MessageChain().message(text)},
    )


class _AsyncLockContext:
    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _AwaitableFlag:
    def __init__(self):
        self.awaited = False

    def __await__(self):
        async def _inner():
            self.awaited = True
            return None

        return _inner().__await__()


@pytest.mark.asyncio
async def test_internal_save_to_history_filters_messages_and_appends_checkpoints():
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.ctx = _pipeline_context(SimpleNamespace())
    event = FakeEvent(extras={"llm_checkpoint_id": "ck-latest"})
    req = ProviderRequest(conversation=SimpleNamespace(cid="conv-1", token_usage=5))

    user_message = Message(role="user", content="hello")
    assistant_message = Message(role="assistant", content="answer")
    assistant_message._checkpoint_after = CheckpointData(id="ck-prev")
    skipped_user = Message(role="user", content="transient")
    skipped_user._no_save = True

    llm_response = LLMResponse(
        role="assistant",
        completion_text="answer",
        usage=TokenUsage(input_other=2, output=3),
    )

    pending = await stage._save_to_history(
        event,
        req,
        llm_response,
        [
            Message(role="system", content="sys"),
            user_message,
            skipped_user,
            assistant_message,
        ],
        runner_stats=SimpleNamespace(token_usage=TokenUsage(output=99)),
    )

    stage.conv_manager.update_conversation.assert_not_awaited()
    assert pending is not None
    assert pending.unified_msg_origin == event.unified_msg_origin
    assert pending.conversation_id == "conv-1"
    assert list(pending.history_snapshot) == [
        {"role": "user", "content": "hello"},
        {"role": "_checkpoint", "content": {"id": "ck-prev"}},
    ]
    assert pending.assistant_semantic_output == "answer"
    assert pending.checkpoint_id == "ck-latest"
    assert pending.token_usage is None


@pytest.mark.asyncio
async def test_internal_save_to_history_sanitizes_images_without_mutating_agent_messages():
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.ctx = _pipeline_context(SimpleNamespace())
    event = FakeEvent()
    req = ProviderRequest(conversation=SimpleNamespace(cid="conv-1"))
    image_data = "data:image/png;base64,aGVsbG8="
    temporary_image_path = "/tmp/astrbot/tool-image.png"
    message = Message.model_validate(
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": image_data},
                },
                {
                    "type": "image_url",
                    "image_url": {"url": temporary_image_path},
                },
            ],
        }
    )

    pending = await stage._save_to_history(
        event,
        req,
        LLMResponse(role="assistant", completion_text="answer"),
        [message],
        runner_stats=None,
    )

    stage.conv_manager.update_conversation.assert_not_awaited()
    assert pending is not None
    assert image_data in str(pending.history_snapshot)
    assert temporary_image_path in str(pending.history_snapshot)
    assert message.content[0].image_url.url == image_data
    assert message.content[1].image_url.url == temporary_image_path


@pytest.mark.asyncio
async def test_internal_save_to_history_keeps_aborted_error_response():
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.ctx = _pipeline_context(SimpleNamespace())
    event = FakeEvent()
    req = ProviderRequest(conversation=SimpleNamespace(cid="conv-2"))

    pending = await stage._save_to_history(
        event,
        req,
        LLMResponse(role="err", completion_text="partial output"),
        [Message(role="assistant", content="partial output")],
        runner_stats=None,
        user_aborted=True,
    )

    stage.conv_manager.update_conversation.assert_not_awaited()
    assert pending is not None
    assert pending.assistant_semantic_output == "partial output"


@pytest.mark.asyncio
async def test_internal_save_to_history_skips_empty_non_aborted_response():
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.ctx = _pipeline_context(SimpleNamespace())

    pending = await stage._save_to_history(
        FakeEvent(),
        ProviderRequest(conversation=SimpleNamespace(cid="conv-3")),
        LLMResponse(role="assistant", completion_text=""),
        [Message(role="assistant", content="")],
        runner_stats=None,
        user_aborted=False,
    )

    stage.conv_manager.update_conversation.assert_not_called()
    assert pending is None


@pytest.mark.asyncio
async def test_internal_save_to_history_keeps_tool_only_turn_without_text():
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.ctx = _pipeline_context(SimpleNamespace())
    req = ProviderRequest(
        conversation=SimpleNamespace(cid="conv-tools", token_usage=17),
        tool_calls_result=[{"name": "kb_search", "result": "ok"}],
    )

    pending = await stage._save_to_history(
        FakeEvent(),
        req,
        None,
        [Message(role="assistant", content="tool output saved")],
        runner_stats=None,
    )

    stage.conv_manager.update_conversation.assert_not_awaited()
    assert pending is None


@pytest.mark.asyncio
async def test_internal_save_to_history_skips_non_aborted_non_assistant_response():
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.ctx = _pipeline_context(SimpleNamespace())

    pending = await stage._save_to_history(
        FakeEvent(),
        ProviderRequest(conversation=SimpleNamespace(cid="conv-err")),
        LLMResponse(role="tool", completion_text="tool-only"),
        [Message(role="assistant", content="tool-only")],
        runner_stats=None,
        user_aborted=False,
    )

    stage.conv_manager.update_conversation.assert_not_called()
    assert pending is None


@pytest.mark.asyncio
async def test_internal_save_to_history_keeps_checkpoint_after_failed_response():
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.ctx = _pipeline_context(SimpleNamespace())
    event = FakeEvent(extras={"llm_checkpoint_id": "ck-failed"})
    req = ProviderRequest(conversation=SimpleNamespace(cid="conv-failed"))

    pending = await stage._save_to_history(
        event,
        req,
        LLMResponse(role="err", completion_text="upstream failed"),
        [
            Message(role="system", content="system"),
            Message(role="user", content="hello"),
        ],
        runner_stats=None,
    )

    stage.conv_manager.update_conversation.assert_not_awaited()
    assert pending is None


@pytest.mark.asyncio
async def test_internal_save_to_history_keeps_checkpoint_for_terminal_tool_turn():
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.ctx = _pipeline_context(SimpleNamespace())
    event = FakeEvent(extras={"llm_checkpoint_id": "ck-terminal-tool"})
    req = ProviderRequest(
        conversation=SimpleNamespace(cid="conv-terminal-tool", token_usage=19),
        tool_calls_result=[{"name": "terminal_tool", "result": "done"}],
    )

    pending = await stage._save_to_history(
        event,
        req,
        None,
        [
            Message(role="user", content="hello"),
            Message(role="assistant", content="tool"),
        ],
        runner_stats=None,
    )

    stage.conv_manager.update_conversation.assert_not_awaited()
    assert pending is None


@pytest.mark.asyncio
async def test_internal_save_to_history_saves_empty_placeholder_for_aborted_empty_response():
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.ctx = _pipeline_context(SimpleNamespace())

    pending = await stage._save_to_history(
        FakeEvent(),
        ProviderRequest(conversation=SimpleNamespace(cid="conv-abort")),
        None,
        [Message(role="assistant", content="partial")],
        runner_stats=None,
        user_aborted=True,
    )

    stage.conv_manager.update_conversation.assert_not_awaited()
    assert pending is None


@pytest.mark.asyncio
async def test_internal_save_to_history_skips_when_request_or_conversation_missing():
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.ctx = _pipeline_context(SimpleNamespace())
    event = FakeEvent()
    response = LLMResponse(role="assistant", completion_text="answer")
    messages = [Message(role="assistant", content="answer")]

    missing_request_pending = await stage._save_to_history(
        event,
        None,
        response,
        messages,
        runner_stats=None,
    )
    missing_conversation_pending = await stage._save_to_history(
        event,
        ProviderRequest(conversation=None),
        response,
        messages,
        runner_stats=None,
    )

    stage.conv_manager.update_conversation.assert_not_called()
    assert missing_request_pending is None
    assert missing_conversation_pending is None


@pytest.mark.asyncio
async def test_internal_save_to_history_preserves_non_initial_system_messages():
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.ctx = _pipeline_context(SimpleNamespace())

    pending = await stage._save_to_history(
        FakeEvent(),
        ProviderRequest(conversation=SimpleNamespace(cid="conv-system")),
        LLMResponse(role="assistant", completion_text="answer"),
        [
            Message(role="system", content="drop me"),
            Message(role="user", content="hello"),
            Message(role="system", content="keep me"),
            Message(role="assistant", content="answer"),
        ],
        runner_stats=None,
    )

    stage.conv_manager.update_conversation.assert_not_awaited()
    assert pending is not None
    assert list(pending.history_snapshot) == [
        {"role": "user", "content": "hello"},
        {"role": "system", "content": "keep me"},
    ]


@pytest.mark.asyncio
async def test_internal_save_to_history_schedules_runtime_memory_postprocess(
    monkeypatch,
):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    persona_runtime_manager = SimpleNamespace()
    memory_manager = SimpleNamespace()
    stage.ctx = _pipeline_context(
        SimpleNamespace(
            persona_runtime_manager=persona_runtime_manager,
            memory_manager=memory_manager,
        )
    )
    event = FakeEvent(extras={"selected_persona_id": "persona-a"})
    req = ProviderRequest(conversation=SimpleNamespace(cid="conv-post"))
    scheduled = []

    def fake_create_tracked_task(tasks, coro, *, name):
        scheduled.append((tasks, coro, name))
        coro.close()

    monkeypatch.setattr(internal, "create_tracked_task", fake_create_tracked_task)

    pending = await stage._save_to_history(
        event,
        req,
        LLMResponse(role="assistant", completion_text="answer"),
        [
            Message(role="system", content="drop"),
            Message(role="user", content="I like tea."),
            Message(role="assistant", content="answer"),
        ],
        runner_stats=None,
    )

    assert pending is not None
    event.set_extra(
        "delivery_receipt",
        DeliveryReceipt.aggregate(
            [DeliveryAttempt(status="accepted", semantic_text="answer")],
        ),
    )
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock())
    await stage._finalize_pending_history(event, req, pending)
    stage.conv_manager.update_conversation.assert_awaited_once()
    assert len(scheduled) == 1
    assert scheduled[0][2] == "runtime_memory_postprocess"


@pytest.mark.asyncio
async def test_internal_save_to_history_does_not_postprocess_empty_terminal_tool_turn(
    monkeypatch,
):
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.ctx = _pipeline_context(
        SimpleNamespace(
            persona_runtime_manager=SimpleNamespace(),
            memory_manager=SimpleNamespace(),
        )
    )
    scheduled = []
    postprocess = AsyncMock()

    def fake_create_tracked_task(tasks, coro, *, name):
        scheduled.append((tasks, coro, name))
        coro.close()

    monkeypatch.setattr(internal, "create_tracked_task", fake_create_tracked_task)
    monkeypatch.setattr(internal, "_run_runtime_memory_postprocess", postprocess)

    pending = await stage._save_to_history(
        FakeEvent(),
        ProviderRequest(
            conversation=SimpleNamespace(cid="conv-post-empty", token_usage=3),
            tool_calls_result=[{"name": "terminal_tool", "result": "done"}],
        ),
        None,
        [Message(role="assistant", content="tool output")],
        runner_stats=None,
    )

    assert scheduled == []
    postprocess.assert_not_called()
    assert pending is None


@pytest.mark.asyncio
async def test_internal_save_to_history_uses_conversation_token_usage():
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.conv_manager = SimpleNamespace(update_conversation=AsyncMock())
    stage.ctx = _pipeline_context(SimpleNamespace())

    skipped_assistant = Message(role="assistant", content="draft")
    skipped_assistant._no_save = True

    pending = await stage._save_to_history(
        FakeEvent(),
        ProviderRequest(
            conversation=SimpleNamespace(cid="conv-no-save", token_usage=64)
        ),
        LLMResponse(role="assistant", completion_text="final answer"),
        [
            Message(role="system", content="drop me"),
            Message(role="user", content="hello"),
            skipped_assistant,
            Message(role="assistant", content="final answer"),
        ],
        runner_stats=SimpleNamespace(token_usage=TokenUsage(output=42)),
    )

    stage.conv_manager.update_conversation.assert_not_awaited()
    assert pending is not None
    assert list(pending.history_snapshot) == [
        {"role": "user", "content": "hello"},
    ]
    assert pending.token_usage == 64


@pytest.mark.asyncio
async def test_streaming_pending_history_is_frozen_before_delivery_receipt():
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    event = FakeEvent()
    runner = FakeInternalRunner()
    pending = build_pending_assistant_history(
        unified_msg_origin=event.unified_msg_origin,
        conversation_id="conv-stream-pending",
        history_snapshot=[{"role": "user", "content": "question"}],
        token_usage=1,
        assistant_semantic_output="answer",
        checkpoint_id=None,
        run_id="run-stream",
    )
    stage._save_to_history = AsyncMock(return_value=pending)

    async def stream():
        yield MessageChain().message("answer")

    yielded = [
        item
        async for item in stage._stream_with_pending_history(
            event,
            ProviderRequest(conversation=SimpleNamespace(cid="conv-stream-pending")),
            runner,
            stream(),
        )
    ]

    assert len(yielded) == 1
    stage._save_to_history.assert_awaited_once()
    assert event.get_extra("_pending_assistant_history") is pending
    assert event.get_extra("delivery_receipt") is None


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
    stage.ctx.execution_context.follow_up_coordinator.register_active_runner = register_runner

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
    stage.ctx.execution_context.follow_up_coordinator.register_active_runner = register_runner
    stage.ctx.execution_context.follow_up_coordinator.unregister_active_runner = unregister_runner
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
    stage.ctx.execution_context.follow_up_coordinator.register_active_runner = register_runner
    stage.ctx.execution_context.follow_up_coordinator.unregister_active_runner = unregister_runner
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
    stage.ctx.execution_context.follow_up_coordinator.register_active_runner = register_runner
    stage.ctx.execution_context.follow_up_coordinator.unregister_active_runner = unregister_runner
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
    stage.ctx.execution_context.follow_up_coordinator.register_active_runner = register_runner
    stage.ctx.execution_context.follow_up_coordinator.unregister_active_runner = unregister_runner
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("aborted", "final_resp", "expected_status"),
    [
        (False, LLMResponse(role="assistant", completion_text="done"), "completed"),
        (False, LLMResponse(role="err", completion_text="boom"), "error"),
        (True, LLMResponse(role="assistant", completion_text="partial"), "aborted"),
    ],
)
async def test_record_internal_agent_stats_persists_expected_status(
    monkeypatch,
    aborted,
    final_resp,
    expected_status,
):
    insert_provider_stat = AsyncMock()
    db = SimpleNamespace(insert_provider_stat=insert_provider_stat)

    event = FakeEvent()
    req = ProviderRequest(conversation=SimpleNamespace(cid="conv-stats"))
    runner = FakeInternalRunner(aborted=aborted)

    await internal._record_internal_agent_stats(event, req, runner, final_resp, db)

    insert_provider_stat.assert_awaited_once_with(
        umo=event.unified_msg_origin,
        conversation_id="conv-stats",
        provider_id="provider-1",
        provider_model="fake-model",
        status=expected_status,
        stats={"steps": 1},
        agent_type="internal",
    )


@pytest.mark.asyncio
async def test_record_internal_agent_stats_falls_back_to_provider_meta_id_without_request(
    monkeypatch,
):
    insert_provider_stat = AsyncMock()
    db = SimpleNamespace(insert_provider_stat=insert_provider_stat)

    runner = FakeInternalRunner()
    runner.provider.provider_config = {}

    await internal._record_internal_agent_stats(
        FakeEvent(),
        None,
        runner,
        LLMResponse(role="assistant", completion_text="done"),
        db,
    )

    insert_provider_stat.assert_awaited_once_with(
        umo="webchat:FriendMessage:test-session",
        conversation_id=None,
        provider_id="fake-provider",
        provider_model="fake-model",
        status="completed",
        stats={"steps": 1},
        agent_type="internal",
    )


@pytest.mark.asyncio
async def test_record_internal_agent_stats_skips_when_provider_or_stats_missing(
    monkeypatch,
):
    insert_provider_stat = AsyncMock()
    db = SimpleNamespace(insert_provider_stat=insert_provider_stat)

    event = FakeEvent()
    req = ProviderRequest(conversation=SimpleNamespace(cid="conv-stats"))
    no_provider_runner = FakeInternalRunner()
    no_provider_runner.provider = None
    no_stats_runner = FakeInternalRunner()
    no_stats_runner.stats = None

    await internal._record_internal_agent_stats(
        event, req, no_provider_runner, None, db
    )
    await internal._record_internal_agent_stats(event, req, no_stats_runner, None, db)

    insert_provider_stat.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_internal_agent_stats_swallows_persistence_failures(monkeypatch):
    warning = MagicMock()
    db = SimpleNamespace(
        insert_provider_stat=AsyncMock(side_effect=RuntimeError("db write failed"))
    )
    monkeypatch.setattr(internal.logger, "warning", warning)

    await internal._record_internal_agent_stats(
        FakeEvent(),
        ProviderRequest(conversation=SimpleNamespace(cid="conv-stats")),
        FakeInternalRunner(),
        LLMResponse(role="assistant", completion_text="done"),
        db,
    )

    warning.assert_called_once()
    assert "Persist provider stats failed" in warning.call_args.args[0]
