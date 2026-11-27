import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.dashboard.api.chat import resume_chat_run
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
    core_lifecycle = SimpleNamespace(
        conversation_manager=Mock(),
        platform_message_history_manager=platform_history_mgr,
        umop_config_router=Mock(),
    )
    db = Mock()
    db.get_platform_session_by_id = AsyncMock(
        return_value=SimpleNamespace(
            session_id="existing-session",
            creator="alice",
        )
    )
    db.create_platform_session = AsyncMock()
    service = ChatService(db, core_lifecycle)
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
    run = next(iter(service.chat_runs.values()))

    try:
        service.db.get_platform_session_by_id.assert_awaited_once_with(session_id)
        service.db.create_platform_session.assert_awaited_once_with(
            creator="alice",
            platform_id="webchat",
            session_id=session_id,
            is_group=0,
        )
    finally:
        await stream.aclose()
        if run.task and not run.task.done():
            run.task.cancel()
            await asyncio.gather(run.task, return_exceptions=True)
        chat_service.webchat_queue_mgr.remove_queues(session_id)


def _decode_sse_event(event: str) -> dict:
    """Decode one JSON SSE event emitted by ChatService.

    Args:
        event: Complete SSE event text.

    Returns:
        Decoded event payload.
    """
    return json.loads(event.removeprefix("data: ").strip())


@pytest.mark.asyncio
async def test_chat_stream_rejects_session_owned_by_another_user(
    chat_service_instance,
):
    service = chat_service_instance
    service.db.get_platform_session_by_id.return_value = SimpleNamespace(
        session_id="alice-session",
        creator="alice",
    )

    with pytest.raises(ChatServiceError, match="Permission denied"):
        await service.build_chat_stream(
            "bob",
            {"message": "canary", "session_id": "alice-session"},
        )

    service.db.create_platform_session.assert_not_awaited()
    history_mgr = service.core_lifecycle.platform_message_history_manager
    history_mgr.insert.assert_not_awaited()
    assert not service.chat_runs


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
    run = next(iter(service.chat_runs.values()))

    try:
        assert _decode_sse_event(await anext(stream))["type"] == "session_id"
        await stream.aclose()
        assert not run.subscribers
        assert run.task is not None and not run.task.done()

        await chat_service.webchat_queue_mgr.put_back_queue(
            run.run_id,
            {
                "type": "plain",
                "data": "completed after refresh",
                "streaming": True,
                "message_id": run.run_id,
            },
        )
        await chat_service.webchat_queue_mgr.put_back_queue(
            run.run_id,
            {
                "type": "complete",
                "data": "completed after refresh",
                "streaming": True,
                "message_id": run.run_id,
            },
        )
        await chat_service.webchat_queue_mgr.put_back_queue(
            run.run_id,
            {
                "type": "end",
                "data": "",
                "streaming": False,
                "message_id": run.run_id,
            },
        )
        await asyncio.wait_for(run.task, timeout=1)

        saved_parts = service.save_bot_message.await_args.args[1]
        assert saved_parts == [{"type": "plain", "text": "completed after refresh"}]
        assert run.run_id not in service.chat_runs
    finally:
        if run.task and not run.task.done():
            run.task.cancel()
            await asyncio.gather(run.task, return_exceptions=True)
        chat_service.webchat_queue_mgr.remove_queues(session_id)


@pytest.mark.asyncio
async def test_resumed_stream_starts_with_full_snapshot(chat_service_instance):
    service = chat_service_instance
    session_id = "resume-session"
    legacy_stream = await service.build_chat_stream(
        "alice",
        {"message": "hello", "session_id": session_id},
    )
    run = next(iter(service.chat_runs.values()))

    try:
        await anext(legacy_stream)
        await legacy_stream.aclose()
        await chat_service.webchat_queue_mgr.put_back_queue(
            run.run_id,
            {
                "type": "plain",
                "data": "before refresh",
                "streaming": True,
                "message_id": run.run_id,
            },
        )
        for _ in range(10):
            if run.message_parts:
                break
            await asyncio.sleep(0)

        active_runs = service.get_active_chat_runs("alice", session_id)
        assert [active_run["run_id"] for active_run in active_runs] == [run.run_id]

        resumed_stream = await service.build_chat_run_stream("alice", run.run_id)
        snapshot_event = _decode_sse_event(await anext(resumed_stream))
        assert snapshot_event["type"] == "run_snapshot"
        assert snapshot_event["data"]["content"]["message"] == [
            {"type": "plain", "text": "before refresh"}
        ]

        await chat_service.webchat_queue_mgr.put_back_queue(
            run.run_id,
            {
                "type": "plain",
                "data": " and after refresh",
                "streaming": True,
                "message_id": run.run_id,
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
                "message_id": run.run_id,
            },
            {
                "type": "end",
                "data": "",
                "streaming": False,
                "message_id": run.run_id,
            },
        ):
            await chat_service.webchat_queue_mgr.put_back_queue(run.run_id, payload)
        await asyncio.wait_for(run.task, timeout=1)
    finally:
        if run.task and not run.task.done():
            run.task.cancel()
            await asyncio.gather(run.task, return_exceptions=True)
        chat_service.webchat_queue_mgr.remove_queues(session_id)


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
        first_run_id = next(iter(service.chat_runs))
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
        tasks = [run.task for run in service.chat_runs.values() if run.task]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        chat_service.webchat_queue_mgr.remove_queues(session_id)


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
    run = next(iter(service.chat_runs.values()))
    subscriber = next(iter(run.subscribers))

    try:
        for index in range(chat_service.CHAT_RUN_SUBSCRIBER_QUEUE_SIZE + 1):
            service._publish_chat_run(
                run,
                {"type": "plain", "data": str(index), "streaming": True},
            )

        assert subscriber.maxsize == chat_service.CHAT_RUN_SUBSCRIBER_QUEUE_SIZE
        assert subscriber.qsize() == 1
        assert not run.subscribers
        assert _decode_sse_event(await anext(stream))["type"] == "session_id"
        assert _decode_sse_event(await anext(stream))["type"] == "user_message_saved"
        with pytest.raises(StopAsyncIteration):
            await anext(stream)
    finally:
        await stream.aclose()
        if run.task and not run.task.done():
            run.task.cancel()
            await asyncio.gather(run.task, return_exceptions=True)
        chat_service.webchat_queue_mgr.remove_queues(session_id)


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
    run = next(iter(service.chat_runs.values()))
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
        await chat_service.webchat_queue_mgr.put_back_queue(
            run.run_id,
            {
                "type": "image",
                "data": "[IMAGE]result.png",
                "streaming": True,
                "message_id": run.run_id,
            },
        )
        await asyncio.wait_for(attachment_started.wait(), timeout=1)

        resumed_stream = await service.build_chat_run_stream("alice", run.run_id)
        snapshot_event = _decode_sse_event(await anext(resumed_stream))
        assert snapshot_event["data"]["content"]["message"] == []

        release_attachment.set()
        image_event = _decode_sse_event(
            await asyncio.wait_for(anext(resumed_stream), timeout=1)
        )
        assert image_event["type"] == "image"
        assert image_event["data"] == "[IMAGE]result.png"
        await resumed_stream.aclose()

        await chat_service.webchat_queue_mgr.put_back_queue(
            run.run_id,
            {
                "type": "end",
                "data": "",
                "streaming": False,
                "message_id": run.run_id,
            },
        )
        await asyncio.wait_for(run.task, timeout=1)
    finally:
        release_attachment.set()
        if run.task and not run.task.done():
            run.task.cancel()
            await asyncio.gather(run.task, return_exceptions=True)
        chat_service.webchat_queue_mgr.remove_queues(session_id)


@pytest.mark.asyncio
async def test_legacy_chat_stream_keeps_existing_event_shape(chat_service_instance):
    service = chat_service_instance
    session_id = "legacy-session"
    stream = await service.build_chat_stream(
        "alice",
        {"message": "hello", "session_id": session_id},
    )
    run = next(iter(service.chat_runs.values()))

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
            "message_id": run.run_id,
        }
        await chat_service.webchat_queue_mgr.put_back_queue(
            run.run_id,
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
        chat_service.webchat_queue_mgr.remove_queues(session_id)


@pytest.mark.asyncio
async def test_chat_stream_forwards_normalized_request_flags(chat_service_instance):
    """Test chat requests pass normalized flags to the WebChat adapter queue."""
    service = chat_service_instance
    session_id = "request-flags-session"
    stream = await service.build_chat_stream(
        "alice",
        {
            "message": "hello",
            "session_id": session_id,
            "enable_streaming": False,
            "flags": {
                "enable_inline_genui": True,
                "enable_default_system_prompt": False,
            },
        },
    )
    run = next(iter(service.chat_runs.values()))

    try:
        chat_queue = chat_service.webchat_queue_mgr.get_or_create_queue(session_id)
        _, _, payload = await asyncio.wait_for(chat_queue.get(), timeout=1)
        assert payload["flags"] == {
            "enable_inline_genui": True,
            "enable_default_system_prompt": False,
            "enable_streaming": False,
            "enable_reasoning": True,
        }
        assert "enable_streaming" not in payload
    finally:
        await stream.aclose()
        if run.task and not run.task.done():
            run.task.cancel()
            await asyncio.gather(run.task, return_exceptions=True)
        chat_service.webchat_queue_mgr.remove_queues(session_id)


@pytest.mark.asyncio
async def test_chat_stream_forwards_follow_up_status_by_default(
    chat_service_instance,
):
    service = chat_service_instance
    session_id = "follow-up-status-session"
    stream = await service.build_chat_stream(
        "alice",
        {
            "message": "hello",
            "session_id": session_id,
        },
    )
    run = next(iter(service.chat_runs.values()))

    try:
        assert _decode_sse_event(await anext(stream))["type"] == "session_id"
        assert _decode_sse_event(await anext(stream))["type"] == "user_message_saved"

        status_payload = {
            "type": "follow_up_captured",
            "data": {"target_run_id": "original-run"},
            "streaming": False,
            "message_id": run.run_id,
        }
        await chat_service.webchat_queue_mgr.put_back_queue(
            run.run_id,
            status_payload,
        )
        assert _decode_sse_event(await asyncio.wait_for(anext(stream), 1)) == (
            status_payload
        )

        await chat_service.webchat_queue_mgr.put_back_queue(
            run.run_id,
            {
                "type": "end",
                "data": "",
                "streaming": False,
                "message_id": run.run_id,
            },
        )
        await asyncio.wait_for(run.task, timeout=1)
    finally:
        await stream.aclose()
        if run.task and not run.task.done():
            run.task.cancel()
            await asyncio.gather(run.task, return_exceptions=True)
        chat_service.webchat_queue_mgr.remove_queues(session_id)


@pytest.mark.asyncio
async def test_save_uploaded_file_rejects_oversized_content_length(
    chat_service_instance,
):
    class FakeUpload:
        filename = "big.bin"
        content_type = "application/octet-stream"
        content_length = chat_service.MAX_UPLOAD_FILE_SIZE_BYTES + 1

    with pytest.raises(ChatServiceError, match="File too large"):
        await chat_service_instance.save_uploaded_file(FakeUpload())


@pytest.mark.asyncio
async def test_save_uploaded_file_rejects_oversized_saved_file(
    chat_service_instance,
):
    from pathlib import Path

    class FakeUpload:
        filename = "big.bin"
        content_type = "application/octet-stream"
        content_length = None

        async def save(self, path, *, max_bytes=None):
            saved = Path(path)
            saved.write_bytes(b"x")
            with saved.open("rb+") as f:
                f.truncate(chat_service.MAX_UPLOAD_FILE_SIZE_BYTES + 1)
            # Mirror save_upload_stream: enforce the cap mid-write and
            # remove the partial file on overflow.
            if max_bytes is not None and saved.stat().st_size > max_bytes:
                saved.unlink()
                raise chat_service.UploadTooLargeError(max_bytes)

    with pytest.raises(ChatServiceError, match="File too large"):
        await chat_service_instance.save_uploaded_file(FakeUpload())

    assert not list(Path(chat_service_instance.attachments_dir).iterdir())


@pytest.mark.asyncio
@pytest.mark.parametrize("queue_size", [6, 8])
async def test_completed_chat_stream_preserves_pending_output(
    chat_service_instance, monkeypatch, queue_size
):
    """Keep final output queued until the subscriber consumes it.

    Args:
        chat_service_instance: Chat service with isolated persistence.
        monkeypatch: Fixture for setting the subscriber queue capacity.
        queue_size: Capacity, including a case with no room for a close marker.
    """
    monkeypatch.setattr(chat_service, "CHAT_RUN_SUBSCRIBER_QUEUE_SIZE", queue_size)
    service = chat_service_instance
    session_id = "completed-buffer-session"
    stream = await service.build_chat_stream(
        "alice", {"message": "hello", "session_id": session_id}
    )
    run = next(iter(service.chat_runs.values()))
    try:
        await anext(stream)
        await anext(stream)
        payloads = [
            {
                "type": "plain",
                "chain_type": "tool_call",
                "data": json.dumps({"id": "tool-1", "name": "web_search", "ts": 1}),
                "streaming": True,
            },
            {
                "type": "plain",
                "chain_type": "tool_call_result",
                "data": json.dumps({"id": "tool-1", "result": "Found", "ts": 3}),
                "streaming": True,
            },
            {"type": "plain", "data": "Final reply", "streaming": True},
            {
                "type": "plain",
                "chain_type": "agent_stats",
                "data": json.dumps({"start_time": 1, "end_time": 4}),
                "streaming": True,
            },
            {"type": "end", "data": "", "streaming": False},
        ]
        for payload in payloads:
            run.back_queue.put_nowait({**payload, "message_id": run.run_id})
        await asyncio.wait_for(run.task, timeout=1)
        received = []
        while True:
            try:
                event = await asyncio.wait_for(anext(stream), timeout=1)
            except StopAsyncIteration:
                break
            received.append(_decode_sse_event(event))
        assert [event["type"] for event in received] == [
            "plain",
            "plain",
            "plain",
            "agent_stats",
            "message_saved",
            "end",
        ]
        assert json.loads(received[1]["data"])["result"] == "Found"
        assert received[2]["data"] == "Final reply"
        assert received[3]["data"] == {"start_time": 1, "end_time": 4}
    finally:
        await stream.aclose()
        if run.task and not run.task.done():
            run.task.cancel()
            await asyncio.gather(run.task, return_exceptions=True)
        chat_service.webchat_queue_mgr.remove_queues(session_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
async def test_error_cards_survive_stream_completion_and_history(
    chat_service_instance, streaming
):
    from astrbot.core.message.components import Json
    from astrbot.core.message.message_event_result import MessageChain
    from astrbot.core.platform.sources.webchat.webchat_event import WebChatMessageEvent

    service = chat_service_instance
    session_id = "error-session"
    stream = await service.build_chat_stream(
        "alice", {"message": "hello", "session_id": session_id}
    )
    run = next(iter(service.chat_runs.values()))
    error = {"code": "noProvider", "message": "Configure a model"}
    try:
        await WebChatMessageEvent._send(
            run.run_id,
            MessageChain().message("Partial reply"),
            session_id,
            streaming=True,
        )
        await WebChatMessageEvent._send(
            run.run_id,
            MessageChain(chain=[Json(error)], type="chatui_error"),
            session_id,
            streaming=streaming,
        )
        await chat_service.webchat_queue_mgr.put_back_queue(
            run.run_id, {"type": "complete", "data": "Partial reply", "streaming": True}
        )
        await WebChatMessageEvent._send(run.run_id, None, session_id)
        frames = [_decode_sse_event(frame) async for frame in stream]
        await asyncio.wait_for(run.task, timeout=1)
        expected = [
            {"type": "plain", "text": "Partial reply"},
            {"type": "error", **error},
        ]
        assert run.message_parts == expected
        # A turn is one record: later saves update it with everything so far.
        calls = service.save_bot_message.await_args_list
        assert calls[-1].args[1] == expected
        assert all(call.kwargs.get("record") is not None for call in calls[1:])
        assert [frame["data"] for frame in frames if frame["type"] == "error"] == [
            error
        ]
    finally:
        await stream.aclose()
        if run.task and not run.task.done():
            run.task.cancel()
            await asyncio.gather(run.task, return_exceptions=True)
        chat_service.webchat_queue_mgr.remove_queues(session_id)


@pytest.mark.asyncio
async def test_native_web_search_sources_persist_and_emit_refs(chat_service_instance):
    from astrbot.core.message.components import Json
    from astrbot.core.message.message_event_result import MessageChain
    from astrbot.core.platform.sources.webchat.webchat_event import WebChatMessageEvent

    service = chat_service_instance
    session_id = "grounding-refs-session"
    sources = [
        {
            "index": "1",
            "url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/a",
            "title": "AstrBot Docs",
        }
    ]
    stream = await service.build_chat_stream(
        "alice", {"message": "hello", "session_id": session_id}
    )
    run = next(iter(service.chat_runs.values()))
    try:
        await WebChatMessageEvent._send(
            run.run_id,
            MessageChain().message("Grounded answer"),
            session_id,
            streaming=True,
        )
        await WebChatMessageEvent._send(
            run.run_id,
            MessageChain(chain=[Json({"sources": sources})], type="web_search_sources"),
            session_id,
            streaming=False,
        )
        await chat_service.webchat_queue_mgr.put_back_queue(
            run.run_id,
            {"type": "complete", "data": "Grounded answer", "streaming": True},
        )
        await WebChatMessageEvent._send(run.run_id, None, session_id)
        frames = [_decode_sse_event(frame) async for frame in stream]
        await asyncio.wait_for(run.task, timeout=1)

        assert run.message_parts == [{"type": "plain", "text": "Grounded answer"}]
        assert service.save_bot_message.await_args.args[3] == {"used": sources}
        saved_events = [frame for frame in frames if frame["type"] == "message_saved"]
        assert saved_events
        assert all(event["data"]["refs"] == {"used": sources} for event in saved_events)
    finally:
        await stream.aclose()
        if run.task and not run.task.done():
            run.task.cancel()
            await asyncio.gather(run.task, return_exceptions=True)
        chat_service.webchat_queue_mgr.remove_queues(session_id)
