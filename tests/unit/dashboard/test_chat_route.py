import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.core.webchat.queue_manager import WebChatQueueManager
from astrbot.core.webchat.run_coordinator import WebChatRunCoordinator
from astrbot.dashboard.api.chat import resume_chat_run
from astrbot.dashboard.api.open_api import _build_chat_ws_bridge
from astrbot.dashboard.services import chat_service
from astrbot.dashboard.services.chat_service import ChatService, ChatServiceError


@pytest.fixture
def chat_service_instance(monkeypatch, tmp_path):
    """Create a ChatService with isolated persistence dependencies."""
    monkeypatch.setattr(chat_service, "get_astrbot_data_path", lambda: str(tmp_path))
    platform_history_mgr = Mock()
    platform_history_mgr.insert = AsyncMock(
        return_value=SimpleNamespace(
            id=1,
            created_at=datetime.now(UTC),
        )
    )
    db = Mock()
    db.get_platform_session_by_id = AsyncMock(
        return_value=SimpleNamespace(creator="alice", platform_id="webchat")
    )
    db.create_platform_session = AsyncMock()
    service = ChatService(
        db,
        preferences=SimpleNamespace(temporary_cache={}),
        conversation_manager=Mock(),
        platform_message_history_manager=platform_history_mgr,
        umop_config_router=Mock(),
        webchat_run_coordinator=WebChatRunCoordinator(WebChatQueueManager()),
        active_event_control=Mock(),
    )
    service.build_user_message_parts = AsyncMock(
        return_value=[{"type": "plain", "text": "hello"}]
    )
    service.save_bot_message = AsyncMock(
        return_value=SimpleNamespace(
            id=2,
            created_at=datetime.now(UTC),
        )
    )
    return service


@pytest.mark.asyncio
async def test_chat_stream_creates_missing_webchat_platform_session(
    chat_service_instance,
):
    service = chat_service_instance
    session_id = "missing-platform-session"
    service.db.get_platform_session_by_id.return_value = None

    stream = await service.build_chat_stream(
        "alice",
        {"message": "hello", "session_id": session_id},
    )
    run = next(iter(service.chat_run_states.values()))

    try:
        service.db.get_platform_session_by_id.assert_awaited_once_with(session_id)
        service.db.create_platform_session.assert_awaited_once_with(
            creator="alice",
            platform_id="webchat",
            session_id=session_id,
        )
    finally:
        await stream.aclose()
        if run.run.task and not run.run.task.done():
            run.run.task.cancel()
            await asyncio.gather(run.run.task, return_exceptions=True)
        service.webchat_run_coordinator.queue_manager.remove_queues(session_id)


@pytest.mark.asyncio
async def test_chat_stream_rejects_foreign_webchat_platform_session(
    chat_service_instance,
):
    service = chat_service_instance
    service.db.get_platform_session_by_id.return_value = SimpleNamespace(
        creator="bob", platform_id="webchat"
    )

    with pytest.raises(ChatServiceError, match="Permission denied"):
        await service.build_chat_stream(
            "alice",
            {"message": "hello", "session_id": "bob-session"},
        )

    service.platform_history_mgr.insert.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_stream_allows_same_owner_after_create_race(chat_service_instance):
    service = chat_service_instance
    service.db.get_platform_session_by_id.side_effect = [
        None,
        SimpleNamespace(creator="alice", platform_id="webchat"),
    ]
    service.db.create_platform_session.side_effect = RuntimeError("duplicate")

    stream = await service.build_chat_stream(
        "alice",
        {"message": "hello", "session_id": "raced-session"},
    )
    try:
        assert stream is not None
    finally:
        await stream.aclose()
        for run in list(service.chat_run_states.values()):
            if run.run.task and not run.run.task.done():
                run.run.task.cancel()
                await asyncio.gather(run.run.task, return_exceptions=True)
        service.webchat_run_coordinator.queue_manager.remove_queues("raced-session")


@pytest.mark.asyncio
async def test_chat_stream_fails_when_session_creation_is_unavailable(
    chat_service_instance,
):
    service = chat_service_instance
    service.db.get_platform_session_by_id.side_effect = [None, None]
    service.db.create_platform_session.side_effect = RuntimeError("database down")

    with pytest.raises(ChatServiceError, match="Failed to create chat session"):
        await service.build_chat_stream(
            "alice",
            {"message": "hello", "session_id": "unavailable-session"},
        )


def _decode_sse_event(event: str) -> dict:
    """Decode one JSON SSE event emitted by ChatService.

    Args:
        event: Complete SSE event text.

    Returns:
        Decoded event payload.
    """
    return json.loads(event.removeprefix("data: ").strip())


@pytest.mark.asyncio
async def test_resume_chat_run_does_not_expose_service_error():
    service = SimpleNamespace(
        build_chat_run_stream=AsyncMock(
            side_effect=ChatServiceError("internal stack trace details")
        )
    )
    auth = SimpleNamespace(username="alice")

    response = await resume_chat_run("missing-run", auth, service)

    assert response.status_code == 200
    assert json.loads(response.body) == {
        "status": "error",
        "message": "Chat run is unavailable",
    }


def test_open_api_websocket_bridge_uses_chat_preferences_for_search_refs(
    chat_service_instance,
):
    chat_service_instance.preferences = SimpleNamespace(
        temporary_cache={"_ws_favicon": {"https://example.com": "favicon-data"}}
    )

    bridge = _build_chat_ws_bridge(SimpleNamespace(), chat_service_instance)

    refs = bridge.extract_web_search_refs(
        "See <ref>1</ref>",
        [
            {
                "type": "tool_call",
                "tool_calls": [
                    {
                        "name": "web_search_baidu",
                        "result": json.dumps(
                            {
                                "results": [
                                    {
                                        "index": "1",
                                        "url": "https://example.com",
                                        "title": "Example",
                                        "snippet": "Search result",
                                    }
                                ]
                            }
                        ),
                    }
                ],
            }
        ],
    )

    assert refs == {
        "used": [
            {
                "index": "1",
                "url": "https://example.com",
                "title": "Example",
                "snippet": "Search result",
                "favicon": "favicon-data",
            }
        ]
    }


@pytest.mark.asyncio
async def test_chat_stream_disconnect_does_not_own_run_lifecycle(
    chat_service_instance,
):
    service = chat_service_instance
    session_id = "disconnect-session"
    stream = await service.build_chat_stream(
        "alice",
        {"message": "hello", "session_id": session_id},
    )
    run_state = next(iter(service.chat_run_states.values()))
    run = run_state.run

    try:
        assert _decode_sse_event(await anext(stream))["type"] == "session_id"
        await stream.aclose()
        assert not run_state.subscribers
        assert run.task is not None and not run.task.done()

        await service.webchat_run_coordinator.queue_manager.put_back_queue(
            run.request_id,
            {
                "type": "plain",
                "data": "completed after refresh",
                "streaming": True,
                "message_id": run.request_id,
            },
        )
        await service.webchat_run_coordinator.queue_manager.put_back_queue(
            run.request_id,
            {
                "type": "complete",
                "data": "completed after refresh",
                "streaming": True,
                "message_id": run.request_id,
            },
        )
        await service.webchat_run_coordinator.queue_manager.put_back_queue(
            run.request_id,
            {
                "type": "end",
                "data": "",
                "streaming": False,
                "message_id": run.request_id,
            },
        )
        await asyncio.wait_for(run.task, timeout=1)

        saved_parts = service.save_bot_message.await_args.args[1]
        assert saved_parts == [{"type": "plain", "text": "completed after refresh"}]
        assert run.request_id not in service.chat_run_states
    finally:
        if run.task and not run.task.done():
            run.task.cancel()
            await asyncio.gather(run.task, return_exceptions=True)
        service.webchat_run_coordinator.queue_manager.remove_queues(session_id)


@pytest.mark.asyncio
async def test_chat_run_cancellation_persists_and_cleans_before_propagating(
    chat_service_instance,
):
    service = chat_service_instance
    session_id = "cancelled-run-session"
    persistence_started = asyncio.Event()
    release_persistence = asyncio.Event()

    async def save_bot_message(*_args, **_kwargs):
        persistence_started.set()
        await release_persistence.wait()
        return SimpleNamespace(id=3, created_at=datetime.now(UTC))

    service.save_bot_message = AsyncMock(side_effect=save_bot_message)
    stream = await service.build_chat_stream(
        "alice",
        {"message": "hello", "session_id": session_id},
    )
    run_state = next(iter(service.chat_run_states.values()))
    run = run_state.run
    subscriber = next(iter(run_state.subscribers))

    try:
        await service.webchat_run_coordinator.queue_manager.put_back_queue(
            run.request_id,
            {
                "type": "plain",
                "data": "partial answer",
                "streaming": True,
                "message_id": run.request_id,
            },
        )
        for _ in range(20):
            if run_state.message_parts:
                break
            await asyncio.sleep(0)

        assert run.task is not None
        run.task.cancel()
        await asyncio.wait_for(persistence_started.wait(), timeout=1)
        assert not run.task.done()

        release_persistence.set()
        with pytest.raises(asyncio.CancelledError):
            await run.task

        assert run.task.cancelled()
        assert run.status == "stopped"
        service.save_bot_message.assert_awaited_once()
        assert run.request_id not in service.chat_run_states
        assert (
            run.request_id
            not in service.webchat_run_coordinator.queue_manager.back_queues
        )
        assert not service.webchat_run_coordinator.get_session_runs(session_id)
        assert not run_state.subscribers
        assert await subscriber.get() is None
    finally:
        release_persistence.set()
        await stream.aclose()
        if run.task and not run.task.done():
            run.task.cancel()
            await asyncio.gather(run.task, return_exceptions=True)
        service.webchat_run_coordinator.queue_manager.remove_queues(session_id)


@pytest.mark.asyncio
async def test_resumed_stream_starts_with_full_snapshot(chat_service_instance):
    service = chat_service_instance
    session_id = "resume-session"
    legacy_stream = await service.build_chat_stream(
        "alice",
        {"message": "hello", "session_id": session_id},
    )
    run_state = next(iter(service.chat_run_states.values()))
    run = run_state.run

    try:
        await anext(legacy_stream)
        await legacy_stream.aclose()
        await service.webchat_run_coordinator.queue_manager.put_back_queue(
            run.request_id,
            {
                "type": "plain",
                "data": "before refresh",
                "streaming": True,
                "message_id": run.request_id,
            },
        )
        for _ in range(10):
            if run_state.message_parts:
                break
            await asyncio.sleep(0)

        active_runs = service.get_active_chat_runs("alice", session_id)
        assert [active_run["run_id"] for active_run in active_runs] == [run.request_id]

        resumed_stream = await service.build_chat_run_stream("alice", run.request_id)
        snapshot_event = _decode_sse_event(await anext(resumed_stream))
        assert snapshot_event["type"] == "run_snapshot"
        assert snapshot_event["data"]["content"]["message"] == [
            {"type": "plain", "text": "before refresh"}
        ]

        await service.webchat_run_coordinator.queue_manager.put_back_queue(
            run.request_id,
            {
                "type": "plain",
                "data": " and after refresh",
                "streaming": True,
                "message_id": run.request_id,
            },
        )
        next_event = _decode_sse_event(await asyncio.wait_for(anext(resumed_stream), 1))
        assert next_event["data"] == " and after refresh"
        await resumed_stream.aclose()

        for payload in (
            {
                "type": "complete",
                "data": "before refresh and after refresh",
                "streaming": True,
                "message_id": run.request_id,
            },
            {
                "type": "end",
                "data": "",
                "streaming": False,
                "message_id": run.request_id,
            },
        ):
            await service.webchat_run_coordinator.queue_manager.put_back_queue(
                run.request_id,
                payload,
            )
        await asyncio.wait_for(run.task, timeout=1)
    finally:
        if run.task and not run.task.done():
            run.task.cancel()
            await asyncio.gather(run.task, return_exceptions=True)
        service.webchat_run_coordinator.queue_manager.remove_queues(session_id)


@pytest.mark.asyncio
async def test_active_chat_runs_keep_creation_order(chat_service_instance):
    service = chat_service_instance
    session_id = "ordered-runs-session"
    streams = []

    try:
        streams.append(
            await service.build_chat_stream(
                "alice",
                {"message": "first", "session_id": session_id},
            )
        )
        first_run_id = next(iter(service.chat_run_states))
        streams.append(
            await service.build_chat_stream(
                "alice",
                {"message": "follow-up", "session_id": session_id},
            )
        )

        active_runs = service.get_active_chat_runs("alice", session_id)
        assert active_runs[0]["run_id"] == first_run_id
        assert len(active_runs) == 2
    finally:
        for stream in streams:
            await stream.aclose()
        tasks = [
            run_state.run.task
            for run_state in service.chat_run_states.values()
            if run_state.run.task
        ]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        service.webchat_run_coordinator.queue_manager.remove_queues(session_id)


@pytest.mark.asyncio
async def test_slow_chat_run_subscriber_is_closed_at_buffer_limit(
    chat_service_instance,
):
    service = chat_service_instance
    session_id = "slow-subscriber-session"
    stream = await service.build_chat_stream(
        "alice",
        {"message": "hello", "session_id": session_id},
    )
    run_state = next(iter(service.chat_run_states.values()))
    run = run_state.run
    subscriber = next(iter(run_state.subscribers))

    try:
        for index in range(chat_service.CHAT_RUN_SUBSCRIBER_QUEUE_SIZE + 1):
            service._publish_chat_run(
                run_state,
                {"type": "plain", "data": str(index), "streaming": True},
            )

        assert subscriber.maxsize == chat_service.CHAT_RUN_SUBSCRIBER_QUEUE_SIZE
        assert subscriber.qsize() == 1
        assert not run_state.subscribers
        assert _decode_sse_event(await anext(stream))["type"] == "session_id"
        assert _decode_sse_event(await anext(stream))["type"] == "user_message_saved"
        with pytest.raises(StopAsyncIteration):
            await anext(stream)
    finally:
        await stream.aclose()
        if run.task and not run.task.done():
            run.task.cancel()
            await asyncio.gather(run.task, return_exceptions=True)
        service.webchat_run_coordinator.queue_manager.remove_queues(session_id)


@pytest.mark.asyncio
async def test_resume_during_attachment_save_does_not_skip_attachment(
    chat_service_instance,
):
    service = chat_service_instance
    session_id = "attachment-race-session"
    legacy_stream = await service.build_chat_stream(
        "alice",
        {"message": "hello", "session_id": session_id},
    )
    run_state = next(iter(service.chat_run_states.values()))
    run = run_state.run
    attachment_started = asyncio.Event()
    release_attachment = asyncio.Event()

    async def create_attachment(filename, attach_type, display_name=None):
        """Pause attachment persistence to exercise the resume race.

        Args:
            filename: Stored attachment filename.
            attach_type: WebChat attachment type.
            display_name: Optional client-facing filename.

        Returns:
            Persisted attachment metadata.
        """
        del display_name
        attachment_started.set()
        await release_attachment.wait()
        return {
            "attachment_id": "attachment-1",
            "filename": filename,
            "type": attach_type,
        }

    service.create_attachment_from_file = create_attachment

    try:
        await anext(legacy_stream)
        await legacy_stream.aclose()
        await service.webchat_run_coordinator.queue_manager.put_back_queue(
            run.request_id,
            {
                "type": "image",
                "data": "[IMAGE]result.png",
                "streaming": True,
                "message_id": run.request_id,
            },
        )
        await asyncio.wait_for(attachment_started.wait(), timeout=1)

        resumed_stream = await service.build_chat_run_stream("alice", run.request_id)
        snapshot_event = _decode_sse_event(await anext(resumed_stream))
        assert snapshot_event["data"]["content"]["message"] == []

        release_attachment.set()
        image_event = _decode_sse_event(
            await asyncio.wait_for(anext(resumed_stream), timeout=1)
        )
        assert image_event["type"] == "image"
        assert image_event["data"] == "[IMAGE]result.png"
        await resumed_stream.aclose()

        await service.webchat_run_coordinator.queue_manager.put_back_queue(
            run.request_id,
            {
                "type": "end",
                "data": "",
                "streaming": False,
                "message_id": run.request_id,
            },
        )
        await asyncio.wait_for(run.task, timeout=1)
    finally:
        release_attachment.set()
        if run.task and not run.task.done():
            run.task.cancel()
            await asyncio.gather(run.task, return_exceptions=True)
        service.webchat_run_coordinator.queue_manager.remove_queues(session_id)


@pytest.mark.asyncio
async def test_legacy_chat_stream_keeps_existing_event_shape(chat_service_instance):
    service = chat_service_instance
    session_id = "legacy-session"
    stream = await service.build_chat_stream(
        "alice",
        {"message": "hello", "session_id": session_id},
    )
    run_state = next(iter(service.chat_run_states.values()))
    run = run_state.run

    try:
        assert _decode_sse_event(await anext(stream)) == {
            "type": "session_id",
            "data": None,
            "session_id": session_id,
        }
        assert _decode_sse_event(await anext(stream))["type"] == "user_message_saved"
        plain_payload = {
            "type": "plain",
            "data": "unchanged",
            "streaming": True,
            "message_id": run.request_id,
        }
        await service.webchat_run_coordinator.queue_manager.put_back_queue(
            run.request_id,
            plain_payload,
        )
        assert (
            _decode_sse_event(await asyncio.wait_for(anext(stream), 1)) == plain_payload
        )
    finally:
        await stream.aclose()
        if run.task and not run.task.done():
            run.task.cancel()
            await asyncio.gather(run.task, return_exceptions=True)
        service.webchat_run_coordinator.queue_manager.remove_queues(session_id)
