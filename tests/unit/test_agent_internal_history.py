from __future__ import annotations

import pytest

from tests.unit.agent_sub_stage_support import *  # noqa: F403


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
async def test_internal_save_to_history_replaces_aborted_partial_response():
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
    assert pending.assistant_semantic_output == "Output stopped."
    assert list(pending.history_snapshot) == [
        {"role": "user", "content": "Stop output."},
    ]


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
async def test_internal_save_to_history_records_synthetic_aborted_turn():
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
    assert pending is not None
    assert pending.assistant_semantic_output == "Output stopped."
    assert list(pending.history_snapshot) == [
        {"role": "user", "content": "Stop output."},
    ]


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
