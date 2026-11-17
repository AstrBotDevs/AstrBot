import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from starlette.websockets import WebSocketDisconnect

from astrbot.core.platform.sources.webchat.webchat_queue_mgr import webchat_queue_mgr
from astrbot.dashboard.services.chat_service import ChatService, ChatServiceError
from astrbot.dashboard.services.live_chat_service import LiveChatService


def _service() -> LiveChatService:
    core_lifecycle = SimpleNamespace(
        astrbot_config={"dashboard": {"jwt_secret": "test-secret"}},
        plugin_manager=SimpleNamespace(),
        conversation_manager=Mock(),
        umop_config_router=Mock(),
        platform_message_history_manager=SimpleNamespace(),
    )
    db = SimpleNamespace(
        get_platform_session_by_id=AsyncMock(
            return_value=SimpleNamespace(creator="alice")
        ),
        get_attachment_by_id=AsyncMock(),
    )
    chat_service = ChatService(db, core_lifecycle)
    return LiveChatService(db, core_lifecycle, chat_service)


@pytest.mark.asyncio
async def test_run_websocket_session_closes_when_token_is_missing():
    service = _service()
    closed: list[tuple[int, str]] = []

    async def close(code: int, reason: str) -> None:
        closed.append((code, reason))

    async def receive_json() -> dict:
        raise AssertionError("receive_json should not be called")

    async def send_json(payload: dict) -> None:
        raise AssertionError(f"send_json should not be called: {payload}")

    await service.run_websocket_session(
        token=None,
        force_ct=None,
        receive_json=receive_json,
        send_json=send_json,
        close=close,
    )

    assert closed == [(1008, "Missing authentication token")]
    assert service.sessions == {}


@pytest.mark.asyncio
async def test_run_websocket_session_routes_messages_and_cleans_session(monkeypatch):
    service = _service()
    messages = iter(
        [
            {"ct": "chat", "t": "bind", "session_id": "chat-session"},
            {"t": "start_speaking", "stamp": "s1"},
        ]
    )
    routed: list[tuple[str, str, dict]] = []

    monkeypatch.setattr(service, "authenticate_token", lambda _token: "alice")

    async def handle_chat_message(session, message, _send_json) -> None:
        routed.append(("chat", session.username, message))

    async def handle_live_message(session, message, _send_json) -> None:
        routed.append(("live", session.username, message))

    monkeypatch.setattr(service, "handle_chat_message", handle_chat_message)
    monkeypatch.setattr(service, "handle_live_message", handle_live_message)

    async def receive_json() -> dict:
        try:
            return next(messages)
        except StopIteration as exc:
            raise RuntimeError("disconnect") from exc

    async def send_json(_payload: dict) -> None:
        pass

    async def close(_code: int, _reason: str) -> None:
        raise AssertionError("close should not be called")

    await service.run_websocket_session(
        token="valid",
        force_ct=None,
        receive_json=receive_json,
        send_json=send_json,
        close=close,
    )

    assert [(kind, username) for kind, username, _ in routed] == [
        ("chat", "alice"),
        ("live", "alice"),
    ]
    assert service.sessions == {}


@pytest.mark.asyncio
async def test_run_websocket_session_handles_disconnect_without_error_log(
    monkeypatch,
):
    service = _service()
    messages = iter([{"ct": "chat", "t": "bind", "session_id": "chat-session"}])
    routed: list[dict] = []

    monkeypatch.setattr(service, "authenticate_token", lambda _token: "alice")

    async def handle_chat_message(session, message, _send_json) -> None:
        routed.append({"username": session.username, "message": message})

    monkeypatch.setattr(service, "handle_chat_message", handle_chat_message)

    async def receive_json() -> dict:
        try:
            return next(messages)
        except StopIteration as exc:
            raise WebSocketDisconnect(1006) from exc

    async def send_json(_payload: dict) -> None:
        pass

    async def close(_code: int, _reason: str) -> None:
        raise AssertionError("close should not be called")

    def fail_error_log(*_args, **_kwargs) -> None:
        raise AssertionError("disconnect should not be logged as an error")

    monkeypatch.setattr(
        "astrbot.dashboard.services.live_chat_service.logger.error",
        fail_error_log,
    )

    await service.run_websocket_session(
        token="valid",
        force_ct=None,
        receive_json=receive_json,
        send_json=send_json,
        close=close,
    )

    assert routed == [
        {
            "username": "alice",
            "message": {"ct": "chat", "t": "bind", "session_id": "chat-session"},
        }
    ]
    assert service.sessions == {}


@pytest.mark.asyncio
async def test_run_websocket_session_multiplexes_chat_requests_by_default(
    monkeypatch,
):
    service = _service()
    started = asyncio.Event()
    started_requests: list[str] = []
    messages = iter(
        [
            {
                "ct": "chat",
                "t": "send",
                "session_id": "chat-session",
                "message_id": "request-1",
            },
            {
                "ct": "chat",
                "t": "send",
                "session_id": "chat-session",
                "message_id": "request-2",
            },
        ]
    )

    monkeypatch.setattr(service, "authenticate_token", lambda _token: "alice")

    async def handle_chat_message(_session, message, _send_json) -> None:
        started_requests.append(message["message_id"])
        if len(started_requests) == 2:
            started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(service, "handle_chat_message", handle_chat_message)

    async def receive_json() -> dict:
        try:
            return next(messages)
        except StopIteration as exc:
            await asyncio.wait_for(started.wait(), timeout=1)
            raise WebSocketDisconnect(1000) from exc

    async def send_json(_payload: dict) -> None:
        pass

    async def close(_code: int, _reason: str) -> None:
        raise AssertionError("close should not be called")

    await service.run_websocket_session(
        token="valid",
        force_ct=None,
        receive_json=receive_json,
        send_json=send_json,
        close=close,
    )

    assert started_requests == ["request-1", "request-2"]
    assert service.sessions == {}


@pytest.mark.asyncio
async def test_handle_chat_interrupt_without_message_id_targets_all_requests():
    service = _service()
    session = service.create_session("alice")
    sent: list[dict] = []
    tasks = {
        "request-1": asyncio.create_task(asyncio.Event().wait()),
        "request-2": asyncio.create_task(asyncio.Event().wait()),
    }
    session.chat_request_tasks.update(tasks)

    async def send_json(payload: dict) -> None:
        sent.append(payload)

    try:
        await service.handle_chat_message(
            session,
            {"t": "interrupt"},
            send_json,
        )

        assert session.interrupted_chat_requests == set(tasks)
        assert sent == [
            {
                "ct": "chat",
                "t": "error",
                "data": "INTERRUPTED",
                "code": "INTERRUPTED",
            }
        ]
    finally:
        await service.cleanup_session(session)


@pytest.mark.asyncio
async def test_handle_chat_message_scopes_events_to_request_by_default():
    service = _service()
    session = service.create_session("alice")
    session_id = "multiplexed-chat-session"
    message_id = "request-1"
    sent: list[dict] = []
    service.platform_history_mgr.insert = AsyncMock(
        return_value=SimpleNamespace(id=1, created_at=datetime.now(UTC))
    )
    service.build_chat_message_parts = AsyncMock(
        return_value=[{"type": "plain", "text": "hello"}]
    )
    service.ensure_chat_subscription = AsyncMock(return_value="subscription-1")

    async def send_json(payload: dict) -> None:
        sent.append(payload)

    task = asyncio.create_task(
        service.handle_chat_message(
            session,
            {
                "t": "send",
                "session_id": session_id,
                "message_id": message_id,
                "message": [{"type": "plain", "text": "hello"}],
            },
            send_json,
        )
    )

    try:
        input_queue = webchat_queue_mgr.get_or_create_queue(session_id)
        _, _, request = await asyncio.wait_for(input_queue.get(), timeout=1)

        await webchat_queue_mgr.put_back_queue(
            request["message_id"],
            {
                "type": "end",
                "data": "",
                "streaming": False,
                "message_id": request["message_id"],
            },
        )
        await asyncio.wait_for(task, timeout=1)

        assert sent[0]["type"] == "user_message_saved"
        assert sent[0]["message_id"] == message_id
        assert sent[-1]["type"] == "end"
        assert sent[-1]["message_id"] == message_id
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await service.cleanup_session(session)
        webchat_queue_mgr.remove_queues(session_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("resume_before_completion", [True, False])
@pytest.mark.parametrize("disconnect_on_send", [True, False])
async def test_websocket_refresh_preserves_run_and_final_history(
    monkeypatch, resume_before_completion, disconnect_on_send
):
    service = _service()
    chat = service.chat_service
    session_id = "refresh-during-tool"
    tool_seen = asyncio.Event()
    sent = []
    records = []

    async def insert(**record):
        records.append(record)
        return SimpleNamespace(id=len(records), created_at=datetime.now(UTC))

    service.platform_history_mgr.insert = insert
    monkeypatch.setattr(service, "authenticate_token", lambda _token: "alice")
    request_sent = False

    async def receive_json():
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {
                "ct": "chat",
                "t": "send",
                "session_id": session_id,
                "message_id": "client-request",
                "message": [{"type": "plain", "text": "hello"}],
                "selected_stt_provider": "stt",
                "selected_tts_provider": "tts",
                "persona_prompt": "persona",
                "show_reasoning": True,
                "enable_streaming": False,
            }
        await tool_seen.wait()
        if disconnect_on_send:
            await asyncio.Event().wait()
        raise WebSocketDisconnect(1000)

    async def send_json(payload):
        if payload.get("chain_type") == "tool_call":
            tool_seen.set()
            if disconnect_on_send:
                raise WebSocketDisconnect(1000)
        sent.append(payload)

    socket_task = asyncio.create_task(
        service.run_websocket_session(
            token="valid",
            force_ct=None,
            receive_json=receive_json,
            send_json=send_json,
            close=AsyncMock(),
        )
    )
    run = None
    resumed = None
    try:
        _, _, request = await asyncio.wait_for(
            webchat_queue_mgr.get_or_create_queue(session_id).get(), timeout=1
        )
        assert request["selected_stt_provider"] == "stt"
        assert request["selected_tts_provider"] == "tts"
        assert request["persona_prompt"] == "persona"
        assert request["show_reasoning"] is True
        assert request["flags"]["enable_streaming"] is False
        run = chat.chat_runs[request["message_id"]]
        await webchat_queue_mgr.put_back_queue(
            run.run_id,
            {
                "type": "plain",
                "chain_type": "tool_call",
                "data": json.dumps({"id": "tool-1", "name": "shell", "args": {}}),
                "streaming": True,
                "message_id": run.run_id,
            },
        )
        await asyncio.wait_for(tool_seen.wait(), timeout=1)
        if disconnect_on_send:
            # A failed write drops the forwarding task before the receive loop exits.
            forwarding = next(iter(service.sessions.values())).chat_request_tasks
            await asyncio.wait_for(asyncio.gather(*forwarding.values()), timeout=1)
            socket_task.cancel()
            await asyncio.gather(socket_task, return_exceptions=True)
        else:
            await asyncio.wait_for(socket_task, timeout=1)
        assert service.sessions == {}
        assert not run.task.done()
        assert not run.subscribers
        snapshots = chat.get_active_chat_runs("alice", session_id)
        assert len(snapshots) == 1
        assert snapshots[0]["content"]["message"][0]["type"] == "tool_call"

        if resume_before_completion:
            resumed = await chat.build_chat_run_stream("alice", run.run_id)
            snapshot = json.loads((await anext(resumed)).removeprefix("data: "))
            assert snapshot["type"] == "run_snapshot"
            assert snapshot["data"]["turn_id"] == records[0]["turn_id"]

        for payload in [
            {
                "type": "plain",
                "chain_type": "tool_call_result",
                "data": json.dumps({"id": "tool-1", "result": "tool finished"}),
                "streaming": True,
            },
            {"type": "plain", "data": "Final answer after refresh", "streaming": True},
            {"type": "complete", "data": "", "streaming": True},
            {"type": "end", "data": "", "streaming": False},
        ]:
            await webchat_queue_mgr.put_back_queue(
                run.run_id, {**payload, "message_id": run.run_id}
            )
        await asyncio.wait_for(run.task, timeout=1)

        if resumed is not None:
            events = [
                json.loads(event.removeprefix("data: ")) async for event in resumed
            ]
            assert any(
                event.get("data") == "Final answer after refresh" for event in events
            )
            assert any(event.get("type") == "end" for event in events)
        else:
            with pytest.raises(ChatServiceError):
                await chat.build_chat_run_stream("alice", run.run_id)
        bot_parts = [
            part
            for record in records
            if record["sender_id"] == "bot"
            for part in record["content"]["message"]
        ]
        assert {"type": "plain", "text": "Final answer after refresh"} in bot_parts
        tool = next(part for part in bot_parts if part["type"] == "tool_call")
        assert tool["tool_calls"][0]["result"] == "tool finished"
        assert chat.get_active_chat_runs("alice", session_id) == []
        assert not chat.running_convs
        assert not run.subscribers
        assert webchat_queue_mgr.list_back_request_ids(session_id) == []
        assert all(event["message_id"] == "client-request" for event in sent)
    finally:
        if resumed is not None:
            await resumed.aclose()
        if run is not None and not run.task.done():
            run.task.cancel()
            await asyncio.gather(run.task, return_exceptions=True)
        if not socket_task.done():
            socket_task.cancel()
            await asyncio.gather(socket_task, return_exceptions=True)
        webchat_queue_mgr.remove_queues(session_id)
