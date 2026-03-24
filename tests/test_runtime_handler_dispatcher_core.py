from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock

from astrbot_sdk._internal.testing_support import MockCapabilityRouter, MockPeer
from astrbot_sdk.clients.llm import LLMResponse
from astrbot_sdk.context import Context
from astrbot_sdk.conversation import (
    ConversationReplaced,
    ConversationSession,
    ConversationState,
)
from astrbot_sdk.decorators import ConversationMeta
from astrbot_sdk.events import MessageEvent
from astrbot_sdk.llm.entities import ProviderRequest
from astrbot_sdk.protocol.descriptors import HandlerDescriptor, MessageTrigger
from astrbot_sdk.runtime.handler_dispatcher import (
    _ActiveConversation,
    _InjectedEventPayloads,
    HandlerDispatcher,
)
from astrbot_sdk.runtime.loader import LoadedHandler
from astrbot_sdk.star import Star


def _build_event(
    *,
    peer: MockPeer,
    plugin_id: str = "test-plugin",
    text: str = "hello",
    session_id: str = "session-1",
    event_type: str = "message",
    payload_extra: dict[str, object] | None = None,
    raw_extra: dict[str, object] | None = None,
) -> tuple[MessageEvent, Context]:
    payload: dict[str, object] = {
        "type": event_type,
        "event_type": event_type,
        "text": text,
        "session_id": session_id,
        "user_id": "tester",
        "platform": "test",
        "platform_id": "test",
        "message_type": "private",
        "raw": {"event_type": event_type},
    }
    if payload_extra:
        payload.update(payload_extra)
    if raw_extra:
        payload["raw"] = {**payload["raw"], **raw_extra}
    ctx = Context(peer=peer, plugin_id=plugin_id)
    event = MessageEvent.from_payload(payload, context=ctx)
    return event, ctx


def _build_loaded_handler(
    handler,
    *,
    plugin_id: str = "test-plugin",
    owner=None,
    conversation: ConversationMeta | None = None,
) -> LoadedHandler:
    return LoadedHandler(
        descriptor=HandlerDescriptor(
            id=f"{plugin_id}.handler",
            trigger=MessageTrigger(),
        ),
        callable=handler,
        owner=owner if owner is not None else object(),
        plugin_id=plugin_id,
        conversation=conversation,
    )


@pytest.mark.asyncio
async def test_inject_provider_request_reads_nested_payload_without_cache() -> None:
    peer = MockPeer(MockCapabilityRouter())
    dispatcher = HandlerDispatcher(plugin_id="test-plugin", peer=peer, handlers=[])
    request_payload = {
        "prompt": "hello",
        "session_id": "session-1",
        "model": "gpt-test",
    }
    event, _ctx = _build_event(
        peer=peer,
        event_type="llm_request",
        raw_extra={"provider_request": request_payload},
    )

    injected = dispatcher._inject_provider_request(event, None)

    assert injected == ProviderRequest.from_payload(request_payload)


@pytest.mark.asyncio
async def test_run_handler_reuses_llm_response_and_serializes_summary() -> None:
    peer = MockPeer(MockCapabilityRouter())
    dispatcher = HandlerDispatcher(plugin_id="test-plugin", peer=peer, handlers=[])
    response_payload = {
        "text": "hello back",
        "finish_reason": "stop",
        "tool_calls": [],
    }
    event, ctx = _build_event(
        peer=peer,
        event_type="llm_response",
        raw_extra={"llm_response": response_payload},
    )
    injected_payloads = _InjectedEventPayloads()

    first = dispatcher._inject_llm_response(event, injected_payloads)
    second = dispatcher._inject_llm_response(event, injected_payloads)

    assert isinstance(first, LLMResponse)
    assert first is second
    assert first.model_dump(exclude_none=True) == response_payload


@pytest.mark.asyncio
async def test_run_handler_merges_dict_result_flags() -> None:
    peer = MockPeer(MockCapabilityRouter())
    dispatcher = HandlerDispatcher(plugin_id="test-plugin", peer=peer, handlers=[])
    event, ctx = _build_event(peer=peer)

    async def handler(event: MessageEvent) -> dict[str, object]:
        assert event.session_id == "session-1"
        return {"stop": True, "call_llm": True}

    loaded = _build_loaded_handler(handler)

    summary = await dispatcher._run_handler(loaded, event, ctx, {})

    assert summary == {"sent_message": False, "stop": True, "call_llm": True}


@pytest.mark.asyncio
async def test_handle_error_prefers_owner_hook() -> None:
    peer = MockPeer(MockCapabilityRouter())
    dispatcher = HandlerDispatcher(plugin_id="test-plugin", peer=peer, handlers=[])
    event, ctx = _build_event(peer=peer)
    calls: list[tuple[Exception, str, str]] = []

    class Owner:
        async def on_error(
            self,
            exc: Exception,
            error_event: MessageEvent,
            error_ctx: Context,
        ) -> None:
            calls.append((exc, error_event.session_id, error_ctx.plugin_id))

    boom = RuntimeError("boom")

    await dispatcher._handle_error(Owner(), boom, event, ctx)

    assert calls == [(boom, "session-1", "test-plugin")]


@pytest.mark.asyncio
async def test_handle_error_falls_back_to_default_star_handler() -> None:
    peer = MockPeer(MockCapabilityRouter())
    dispatcher = HandlerDispatcher(plugin_id="test-plugin", peer=peer, handlers=[])
    event, ctx = _build_event(peer=peer)
    seen: list[tuple[Exception, str, str]] = []
    original = Star.default_on_error

    async def fake_default_on_error(
        exc: Exception,
        error_event: MessageEvent,
        error_ctx: Context,
    ) -> None:
        seen.append((exc, error_event.session_id, error_ctx.plugin_id))

    Star.default_on_error = fake_default_on_error
    try:
        boom = ValueError("fallback")
        await dispatcher._handle_error(object(), boom, event, ctx)
    finally:
        Star.default_on_error = original

    assert seen == [(boom, "session-1", "test-plugin")]


@pytest.mark.asyncio
async def test_start_conversation_rejects_when_existing_session_is_busy() -> None:
    peer = MockPeer(MockCapabilityRouter())
    dispatcher = HandlerDispatcher(plugin_id="test-plugin", peer=peer, handlers=[])
    event, ctx = _build_event(peer=peer)
    blocker = asyncio.Event()

    async def pending_task() -> None:
        await blocker.wait()

    existing = asyncio.create_task(pending_task())
    conversation = ConversationSession(
        ctx=ctx,
        event=event,
        waiter_manager=dispatcher._session_waiters,
        timeout=30,
    )
    dispatcher._conversations["test-plugin:session-1"] = _ActiveConversation(
        session=conversation,
        task=existing,
    )
    loaded = _build_loaded_handler(
        lambda conversation: None,
        conversation=ConversationMeta(mode="reject", busy_message="still busy"),
    )

    try:
        summary = await dispatcher._start_conversation(
            loaded,
            event,
            ctx,
            {},
            schedule_context=None,
        )
    finally:
        existing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await existing

    assert summary == {"sent_message": True, "stop": True, "call_llm": False}
    assert peer._router.platform_sink.records[-1].text == "still busy"


@pytest.mark.asyncio
async def test_start_conversation_replaces_existing_session_and_registers_new_one() -> (
    None
):
    peer = MockPeer(MockCapabilityRouter())
    dispatcher = HandlerDispatcher(plugin_id="test-plugin", peer=peer, handlers=[])
    event, ctx = _build_event(peer=peer)
    replacement_seen = asyncio.Event()

    async def previous_runner() -> None:
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            replacement_seen.set()
            raise

    previous_task = asyncio.create_task(previous_runner())
    previous_session = ConversationSession(
        ctx=ctx,
        event=event,
        waiter_manager=dispatcher._session_waiters,
        timeout=30,
    )
    previous_session.bind_owner_task(previous_task)
    dispatcher._conversations["test-plugin:session-1"] = _ActiveConversation(
        session=previous_session,
        task=previous_task,
    )
    dispatcher._session_waiters.fail = AsyncMock(return_value=True)  # type: ignore[method-assign]

    async def handler(conversation: ConversationSession) -> None:
        conversation.close(ConversationState.COMPLETED)

    loaded = _build_loaded_handler(
        handler,
        conversation=ConversationMeta(mode="replace", grace_period=0.1),
    )

    summary = await dispatcher._start_conversation(
        loaded,
        event,
        ctx,
        {},
        schedule_context=None,
    )

    assert summary == {"sent_message": False, "stop": True, "call_llm": False}
    await asyncio.wait_for(replacement_seen.wait(), timeout=1)
    assert previous_session.state == ConversationState.REPLACED
    dispatcher._session_waiters.fail.assert_awaited_once()
    fail_call = dispatcher._session_waiters.fail.await_args
    assert fail_call.args[0] == previous_session.session_key
    assert isinstance(fail_call.args[1], ConversationReplaced)

    active = dispatcher._conversations["test-plugin:session-1"]
    assert active.session is not previous_session
    await active.task
    assert "test-plugin:session-1" not in dispatcher._conversations


@pytest.mark.asyncio
async def test_run_conversation_task_marks_conversation_cancelled_on_task_cancel() -> (
    None
):
    peer = MockPeer(MockCapabilityRouter())
    dispatcher = HandlerDispatcher(plugin_id="test-plugin", peer=peer, handlers=[])
    event, ctx = _build_event(peer=peer)
    conversation = ConversationSession(
        ctx=ctx,
        event=event,
        waiter_manager=dispatcher._session_waiters,
        timeout=30,
    )
    entered = asyncio.Event()

    async def handler(conversation: ConversationSession) -> None:
        entered.set()
        await asyncio.Future()

    loaded = _build_loaded_handler(
        handler,
        conversation=ConversationMeta(),
    )

    task = asyncio.create_task(
        dispatcher._run_conversation_task(
            loaded,
            event,
            ctx,
            {},
            conversation,
            schedule_context=None,
        )
    )
    conversation.bind_owner_task(task)
    await entered.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert conversation.state == ConversationState.CANCELLED


@pytest.mark.asyncio
async def test_run_conversation_task_reports_handler_errors_without_reraising() -> None:
    peer = MockPeer(MockCapabilityRouter())
    dispatcher = HandlerDispatcher(plugin_id="test-plugin", peer=peer, handlers=[])
    event, ctx = _build_event(peer=peer)
    conversation = ConversationSession(
        ctx=ctx,
        event=event,
        waiter_manager=dispatcher._session_waiters,
        timeout=30,
    )
    dispatcher._handle_error = AsyncMock()  # type: ignore[method-assign]

    async def handler(conversation: ConversationSession) -> None:
        raise RuntimeError("conversation exploded")

    loaded = _build_loaded_handler(
        handler,
        conversation=ConversationMeta(),
        owner=SimpleNamespace(),
    )

    await dispatcher._run_conversation_task(
        loaded,
        event,
        ctx,
        {},
        conversation,
        schedule_context=None,
    )

    dispatcher._handle_error.assert_awaited_once()
