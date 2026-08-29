import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.websockets import WebSocketDisconnect

from astrbot.core.webchat.queue_manager import WebChatQueueManager
from astrbot.core.webchat.run_coordinator import WebChatRunCoordinator
from astrbot.dashboard.services.auth_service import (
    DashboardSessionPrincipal,
    DashboardTokenValidator,
)
from astrbot.dashboard.services.webchat_service import WebChatService

_WEBCHAT_JWT_SECRET = "webchat-test-secret-with-32-bytes"


def _service(auth_service=None) -> WebChatService:
    return WebChatService(
        SimpleNamespace(),
        preferences=SimpleNamespace(temporary_cache={}),
        config={"dashboard": {"jwt_secret": _WEBCHAT_JWT_SECRET}},
        platform_message_history_manager=SimpleNamespace(),
        webchat_run_coordinator=WebChatRunCoordinator(WebChatQueueManager()),
        auth_service=auth_service,
    )


def _record(record_id: int):
    return SimpleNamespace(
        id=record_id,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_authenticate_dashboard_session_token():
    service = _service()
    token = DashboardTokenValidator(_WEBCHAT_JWT_SECRET).issue("dashboard-user")

    assert service.authenticate_token(token) == "dashboard-user"


def test_webchat_proof_cache_is_cleared_when_chat_session_changes():
    service = _service()
    session = service.create_session(
        "alice",
        DashboardSessionPrincipal(
            username="alice",
            sid="dashboard-sid",
            jti="jti",
            account_id="account-1",
        ),
    )
    first = service._dashboard_principal_payload(
        session,
        {
            "tool.local_exec": "opaque-proof",
            "system.restart": "must-not-forward",
            "tool.python_exec": "x" * 513,
        },
        webchat_session_id="session-a",
    )
    second = service._dashboard_principal_payload(
        session,
        webchat_session_id="session-b",
    )

    assert first["_dashboard_principal"]["step_up_tokens"] == {
        "tool.local_exec": "opaque-proof"
    }
    assert "step_up_tokens" not in second["_dashboard_principal"]
    assert session.webchat_step_up_tokens == {}


@pytest.mark.asyncio
async def test_webchat_rejects_foreign_persistent_session():
    service = _service()
    service.db.get_platform_session_by_id = AsyncMock(
        return_value=SimpleNamespace(platform_id="webchat", creator="bob")
    )
    session = service.create_session(
        "alice",
        DashboardSessionPrincipal(
            username="alice",
            sid="dashboard-sid",
            jti="jti",
            account_id="account-1",
        ),
    )
    sent: list[dict] = []

    async def send_json(payload: dict) -> None:
        sent.append(payload)

    await service.handle_chat_message(
        session,
        {
            "t": "send",
            "session_id": "foreign-session",
            "message_id": "message-1",
            "message": [{"type": "plain", "text": "hello"}],
        },
        send_json,
    )

    assert sent[-1]["code"] == "FORBIDDEN"
    assert service.webchat_run_coordinator.get_run("message-1") is None


@pytest.mark.asyncio
async def test_webchat_bind_creates_missing_webchat_session_for_owner():
    service = _service()
    service.db.get_platform_session_by_id = AsyncMock(return_value=None)
    service.db.create_platform_session = AsyncMock()
    service.ensure_chat_subscription = AsyncMock(return_value="req-created")
    session = service.create_session("alice")
    sent: list[dict] = []

    async def send_json(payload: dict) -> None:
        sent.append(payload)

    await service.handle_chat_message(
        session,
        {"t": "bind", "session_id": "missing-session"},
        send_json,
    )

    service.db.create_platform_session.assert_awaited_once_with(
        creator="alice",
        platform_id="webchat",
        session_id="missing-session",
    )
    service.ensure_chat_subscription.assert_awaited_once()
    assert sent[-1]["type"] == "session_bound"


@pytest.mark.asyncio
async def test_webchat_send_creates_missing_webchat_session_before_validation():
    service = _service()
    service.db.get_platform_session_by_id = AsyncMock(return_value=None)
    service.db.create_platform_session = AsyncMock()
    service.build_chat_message_parts = AsyncMock(return_value=[])
    session = service.create_session("alice")
    sent: list[dict] = []

    async def send_json(payload: dict) -> None:
        sent.append(payload)

    await service.handle_chat_message(
        session,
        {
            "t": "send",
            "session_id": "missing-session",
            "message_id": "message-1",
            "message": [{"type": "plain", "text": ""}],
        },
        send_json,
    )

    service.db.create_platform_session.assert_awaited_once_with(
        creator="alice",
        platform_id="webchat",
        session_id="missing-session",
    )
    assert sent[-1]["code"] == "INVALID_MESSAGE_FORMAT"


@pytest.mark.asyncio
async def test_run_websocket_session_rejects_disabled_dashboard_account():
    auth_service = SimpleNamespace(
        validate_dashboard_principal=AsyncMock(return_value=False)
    )
    service = _service(auth_service)
    token = DashboardTokenValidator(_WEBCHAT_JWT_SECRET).issue(
        "dashboard-user", account_id="account-1"
    )
    closed: list[tuple[int, str]] = []

    async def close(code: int, reason: str) -> None:
        closed.append((code, reason))

    async def receive_json() -> dict:
        raise AssertionError("receive_json should not be called")

    async def send_json(payload: dict) -> None:
        raise AssertionError(f"send_json should not be called: {payload}")

    await service.run_websocket_session(
        token=token,
        receive_json=receive_json,
        send_json=send_json,
        close=close,
    )

    assert closed == [(1008, "Invalid token")]
    auth_service.validate_dashboard_principal.assert_awaited_once()


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
        receive_json=receive_json,
        send_json=send_json,
        close=close,
    )

    assert closed == [(1008, "Missing authentication token")]


@pytest.mark.asyncio
async def test_run_websocket_session_routes_messages_and_cleans_session(monkeypatch):
    service = _service()
    messages = iter([{"ct": "chat", "t": "bind", "session_id": "chat-session"}])
    routed: list[tuple[str, str, dict]] = []

    monkeypatch.setattr(service, "authenticate_token", lambda _token: "alice")

    async def handle_chat_message(session, message, _send_json) -> None:
        routed.append(("chat", session.username, message))

    monkeypatch.setattr(service, "handle_chat_message", handle_chat_message)

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
        receive_json=receive_json,
        send_json=send_json,
        close=close,
    )

    assert [(kind, username) for kind, username, _ in routed] == [("chat", "alice")]
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
        "astrbot.dashboard.services.webchat_service.logger.error",
        fail_error_log,
    )

    await service.run_websocket_session(
        token="valid",
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
async def test_run_websocket_session_multiplexes_chat_requests(monkeypatch):
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
        await service.handle_chat_message(session, {"t": "interrupt"}, send_json)

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
async def test_handle_chat_interrupt_with_message_id_targets_one_request():
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
            {"t": "interrupt", "message_id": "request-2"},
            send_json,
        )

        assert session.interrupted_chat_requests == {"request-2"}
        assert sent == [
            {
                "ct": "chat",
                "t": "error",
                "data": "INTERRUPTED",
                "code": "INTERRUPTED",
                "message_id": "request-2",
            }
        ]
    finally:
        await service.cleanup_session(session)


@pytest.mark.asyncio
async def test_handle_chat_message_scopes_events_to_request():
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
        input_queue = service.webchat_run_coordinator.queue_manager.get_or_create_queue(
            session_id
        )
        await asyncio.wait_for(input_queue.get(), timeout=1)
        await service.webchat_run_coordinator.queue_manager.put_back_queue(
            message_id,
            {
                "type": "end",
                "data": "",
                "streaming": False,
                "message_id": message_id,
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
        service.webchat_run_coordinator.queue_manager.remove_queues(session_id)


@pytest.mark.asyncio
async def test_run_websocket_session_logs_runtime_error_and_still_cleans_session(
    monkeypatch,
):
    service = _service()
    logged_errors: list[str] = []

    monkeypatch.setattr(service, "authenticate_token", lambda _token: "alice")
    monkeypatch.setattr(
        "astrbot.dashboard.services.webchat_service.logger.error",
        lambda message, *args, **kwargs: logged_errors.append(str(message)),
    )

    async def receive_json() -> dict:
        raise RuntimeError("socket boom")

    async def send_json(_payload: dict) -> None:
        pass

    async def close(_code: int, _reason: str) -> None:
        raise AssertionError("close should not be called")

    await service.run_websocket_session(
        token="valid",
        receive_json=receive_json,
        send_json=send_json,
        close=close,
    )

    assert any("WebSocket error: socket boom" in message for message in logged_errors)
    assert service.sessions == {}


def test_extract_web_search_refs_filters_supported_results_and_attaches_favicon():
    service = _service()
    service.preferences.temporary_cache = {
        "_ws_favicon": {"https://example.com/1": "favicon-data"}
    }

    refs = service.extract_web_search_refs(
        "answer <ref>1</ref> <ref>3</ref>",
        [
            {
                "type": "tool_call",
                "tool_calls": [
                    {
                        "name": "web_search_tavily",
                        "result": json.dumps(
                            {
                                "results": [
                                    {
                                        "index": "1",
                                        "url": "https://example.com/1",
                                        "title": "One",
                                        "snippet": "First",
                                    },
                                    {
                                        "index": "2",
                                        "url": "https://example.com/2",
                                        "title": "Two",
                                        "snippet": "Second",
                                    },
                                ]
                            }
                        ),
                    },
                    {
                        "name": "unsupported_tool",
                        "result": '{"results":[{"index":"3"}]}',
                    },
                ],
            }
        ],
    )

    assert refs == {
        "used": [
            {
                "index": "1",
                "url": "https://example.com/1",
                "title": "One",
                "snippet": "First",
                "favicon": "favicon-data",
            }
        ]
    }


def test_extract_web_search_refs_returns_empty_for_invalid_tool_payload():
    service = _service()
    refs = service.extract_web_search_refs(
        "answer <ref>1</ref>",
        [
            {
                "type": "tool_call",
                "tool_calls": [
                    {"name": "web_search_tavily", "result": "{bad json"},
                    {"name": "web_search_tavily"},
                ],
            }
        ],
    )

    assert refs == {}


def test_authenticate_token_maps_invalid_and_expired_errors(monkeypatch):
    service = _service()

    monkeypatch.setattr(
        service.token_validator,
        "validate",
        MagicMock(side_effect=__import__("jwt").ExpiredSignatureError("expired")),
    )
    with pytest.raises(Exception, match="Token expired"):
        service.authenticate_token("token")

    monkeypatch.setattr(
        service.token_validator,
        "validate",
        MagicMock(side_effect=__import__("jwt").InvalidTokenError("invalid")),
    )
    with pytest.raises(Exception, match="Invalid token"):
        service.authenticate_token("token")


@pytest.mark.asyncio
async def test_create_attachment_from_file_delegates_with_expected_paths(
    monkeypatch, tmp_path
):
    service = _service()
    service.attachments_dir = str(tmp_path / "attachments")
    service.webchat_img_dir = str(tmp_path / "webchat" / "imgs")
    service.db.insert_attachment = AsyncMock()
    captured = {}

    async def fake_create_attachment_part_from_existing_file(
        filename,
        *,
        attach_type,
        insert_attachment,
        attachments_dir,
        fallback_dirs,
    ):
        captured.update(
            {
                "filename": filename,
                "attach_type": attach_type,
                "insert_attachment": insert_attachment,
                "attachments_dir": attachments_dir,
                "fallback_dirs": fallback_dirs,
            }
        )
        return {"attachment_id": "att-1", "type": attach_type}

    monkeypatch.setattr(
        "astrbot.dashboard.services.webchat_service.create_attachment_part_from_existing_file",
        fake_create_attachment_part_from_existing_file,
    )

    result = await service.create_attachment_from_file("photo.png", "image")

    assert result == {"attachment_id": "att-1", "type": "image"}
    assert captured == {
        "filename": "photo.png",
        "attach_type": "image",
        "insert_attachment": service.db.insert_attachment,
        "attachments_dir": service.attachments_dir,
        "fallback_dirs": [service.webchat_img_dir],
    }


@pytest.mark.asyncio
async def test_save_bot_message_builds_history_and_persists_checkpoint():
    service = _service()
    service.platform_history_mgr.insert = AsyncMock(return_value=_record(77))

    saved = await service.save_bot_message(
        "conv-1",
        [{"type": "plain", "text": "hello"}],
        {"latency": 10},
        {"used": [{"index": "1"}]},
        "checkpoint-1",
    )

    assert saved.id == 77
    service.platform_history_mgr.insert.assert_awaited_once_with(
        platform_id="webchat",
        user_id="conv-1",
        content={
            "type": "bot",
            "message": [{"type": "plain", "text": "hello"}],
            "agent_stats": {"latency": 10},
            "refs": {"used": [{"index": "1"}]},
        },
        sender_id="bot",
        sender_name="bot",
        llm_checkpoint_id="checkpoint-1",
    )


@pytest.mark.asyncio
async def test_handle_chat_message_bind_requires_session_id():
    service = _service()
    session = service.create_session("alice")
    sent_payloads: list[dict] = []

    async def send_json(payload: dict) -> None:
        sent_payloads.append(payload)

    await service.handle_chat_message(
        session,
        {"t": "bind"},
        send_json,
    )

    assert sent_payloads == [
        {
            "ct": "chat",
            "t": "error",
            "data": "session_id is required",
            "code": "INVALID_MESSAGE_FORMAT",
        }
    ]


@pytest.mark.asyncio
async def test_cleanup_chat_subscriptions_cancels_tasks_and_clears_state(monkeypatch):
    service = _service()
    session = service.create_session("alice")
    removed_request_ids: list[str] = []

    async def _wait_forever():
        await asyncio.Event().wait()

    task = asyncio.create_task(_wait_forever())
    service.webchat_run_coordinator.create_run(
        session_id="conv-1",
        username=session.username,
        request_id="req-1",
        kind="subscription",
    )
    service.webchat_run_coordinator.create_run(
        session_id="conv-2",
        username=session.username,
        request_id="req-2",
        kind="subscription",
    )
    session.chat_subscriptions = {"conv-1": "req-1", "conv-2": "req-2"}
    session.chat_subscription_tasks = {"conv-1": task}
    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "remove_back_queue",
        removed_request_ids.append,
    )

    await service.cleanup_chat_subscriptions(session)

    assert task.cancelled()
    assert removed_request_ids == ["req-1", "req-2"]
    assert session.chat_subscriptions == {}
    assert session.chat_subscription_tasks == {}


@pytest.mark.asyncio
async def test_cleanup_session_runs_subscription_cleanup_and_removes_session():
    service = _service()
    session = service.create_session("alice")
    service.cleanup_chat_subscriptions = AsyncMock()

    await service.cleanup_session(session)

    service.cleanup_chat_subscriptions.assert_awaited_once_with(session)
    assert session.session_id not in service.sessions


@pytest.mark.asyncio
async def test_cleanup_session_is_noop_for_unknown_session():
    service = _service()
    session = service.create_session("alice")
    del service.sessions[session.session_id]
    service.cleanup_chat_subscriptions = AsyncMock()

    await service.cleanup_session(session)

    service.cleanup_chat_subscriptions.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_chat_subscription_reuses_existing_active_task():
    service = _service()
    session = service.create_session("alice")

    async def _wait_forever():
        await asyncio.Event().wait()

    task = asyncio.create_task(_wait_forever())
    session.chat_subscriptions = {"chat-session": "req-1"}
    session.chat_subscription_tasks = {"chat-session": task}

    try:
        request_id = await service.ensure_chat_subscription(
            session,
            "chat-session",
            AsyncMock(),
        )
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert request_id == "req-1"
    assert session.chat_subscription_tasks["chat-session"] is task


@pytest.mark.asyncio
async def test_ensure_chat_subscription_replaces_completed_task(monkeypatch):
    service = _service()
    session = service.create_session("alice")
    completed = asyncio.get_running_loop().create_future()
    completed.set_result(None)
    session.chat_subscriptions = {"chat-session": "req-old"}
    session.chat_subscription_tasks = {"chat-session": completed}
    created_tasks: list[asyncio.Task] = []

    monkeypatch.setattr(
        "astrbot.dashboard.services.webchat_service.uuid.uuid4",
        lambda: SimpleNamespace(hex="new-sub-id"),
    )

    def fake_create_task(coro, *, name=None):
        coro.close()
        task = asyncio.get_running_loop().create_task(asyncio.sleep(0), name=name)
        created_tasks.append(task)
        return task

    monkeypatch.setattr(
        "astrbot.dashboard.services.webchat_service.asyncio.create_task",
        fake_create_task,
    )

    request_id = await service.ensure_chat_subscription(
        session,
        "chat-session",
        AsyncMock(),
    )
    await asyncio.gather(*created_tasks)

    assert request_id == "ws_sub_new-sub-id"
    assert session.chat_subscriptions["chat-session"] == "ws_sub_new-sub-id"
    assert session.chat_subscription_tasks["chat-session"] in created_tasks


@pytest.mark.asyncio
async def test_ensure_chat_subscription_create_task_failure_rolls_back_subscription_marker(
    monkeypatch,
):
    service = _service()
    session = service.create_session("alice")

    monkeypatch.setattr(
        "astrbot.dashboard.services.webchat_service.uuid.uuid4",
        lambda: SimpleNamespace(hex="broken-sub-id"),
    )

    def fail_create_task(coro, *, name=None):
        coro.close()
        raise RuntimeError("task create failed")

    monkeypatch.setattr(
        "astrbot.dashboard.services.webchat_service.asyncio.create_task",
        fail_create_task,
    )

    with pytest.raises(RuntimeError, match="task create failed"):
        await service.ensure_chat_subscription(
            session,
            "chat-session",
            AsyncMock(),
        )

    assert session.chat_subscriptions == {}
    assert session.chat_subscription_tasks == {}


@pytest.mark.asyncio
async def test_forward_chat_subscription_forwards_payload_and_cleans_state(monkeypatch):
    service = _service()
    session = service.create_session("alice")
    session.chat_subscriptions = {"chat-session": "req-1"}
    removed_request_ids: list[str] = []
    sent_payloads: list[dict] = []
    back_queue: asyncio.Queue = asyncio.Queue()

    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "get_or_create_back_queue",
        lambda _request_id, _conversation_id=None: back_queue,
    )
    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "remove_back_queue",
        removed_request_ids.append,
    )

    run = service.webchat_run_coordinator.create_run(
        session_id="chat-session",
        username=session.username,
        request_id="req-1",
        kind="subscription",
    )

    async def send_json(payload: dict) -> None:
        sent_payloads.append(payload)

    task = service.webchat_run_coordinator.start_task(
        run,
        service.forward_chat_subscription(session, run, send_json),
        name="test_chat_subscription",
    )
    session.chat_subscription_tasks["chat-session"] = task
    back_queue.put_nowait({"type": "plain", "data": "hello"})
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert sent_payloads == [{"ct": "chat", "type": "plain", "data": "hello"}]
    assert removed_request_ids == ["req-1"]
    assert session.chat_subscriptions == {}
    assert session.chat_subscription_tasks == {}


@pytest.mark.asyncio
async def test_forward_chat_subscription_cleans_state_when_send_fails(monkeypatch):
    service = _service()
    session = service.create_session("alice")
    session.chat_subscriptions = {"chat-session": "req-2"}
    removed_request_ids: list[str] = []
    back_queue: asyncio.Queue = asyncio.Queue()
    back_queue.put_nowait({"type": "plain", "data": "hello"})

    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "get_or_create_back_queue",
        lambda _request_id, _conversation_id=None: back_queue,
    )
    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "remove_back_queue",
        removed_request_ids.append,
    )

    run = service.webchat_run_coordinator.create_run(
        session_id="chat-session",
        username=session.username,
        request_id="req-2",
        kind="subscription",
    )

    async def send_json(_payload: dict) -> None:
        raise RuntimeError("send failed")

    task = service.webchat_run_coordinator.start_task(
        run,
        service.forward_chat_subscription(session, run, send_json),
        name="test_chat_subscription",
    )
    session.chat_subscription_tasks["chat-session"] = task
    await task

    assert removed_request_ids == ["req-2"]
    assert session.chat_subscriptions == {}
    assert session.chat_subscription_tasks == {}


@pytest.mark.asyncio
async def test_handle_chat_message_interrupt_without_request_id_targets_active_requests():
    service = _service()
    session = service.create_session("alice")
    sent_payloads: list[dict] = []

    async def send_json(payload: dict) -> None:
        sent_payloads.append(payload)

    await service.handle_chat_message(session, {"t": "interrupt"}, send_json)

    assert session.interrupted_chat_requests == set()
    assert sent_payloads == [
        {
            "ct": "chat",
            "t": "error",
            "data": "INTERRUPTED",
            "code": "INTERRUPTED",
        }
    ]


@pytest.mark.asyncio
async def test_handle_chat_message_rejects_unsupported_message_type():
    service = _service()
    session = service.create_session("alice")
    sent_payloads: list[dict] = []

    async def send_json(payload: dict) -> None:
        sent_payloads.append(payload)

    await service.handle_chat_message(
        session,
        {"t": "mystery"},
        send_json,
    )

    assert sent_payloads == [
        {
            "ct": "chat",
            "t": "error",
            "data": "Unsupported message type: mystery",
            "code": "INVALID_MESSAGE_FORMAT",
        }
    ]


@pytest.mark.asyncio
async def test_handle_chat_message_bind_reuses_existing_subscription_request_id():
    service = _service()
    session = service.create_session("alice")
    service.ensure_chat_subscription = AsyncMock(return_value="req-existing")
    sent_payloads: list[dict] = []

    async def send_json(payload: dict) -> None:
        sent_payloads.append(payload)

    await service.handle_chat_message(
        session,
        {"t": "bind", "session_id": "chat-session"},
        send_json,
    )

    service.ensure_chat_subscription.assert_awaited_once_with(
        session,
        "chat-session",
        send_json,
    )
    assert sent_payloads == [
        {
            "ct": "chat",
            "type": "session_bound",
            "session_id": "chat-session",
            "message_id": "req-existing",
        }
    ]


@pytest.mark.asyncio
async def test_handle_chat_message_send_is_not_blocked_by_other_requests():
    service = _service()
    service.build_chat_message_parts = AsyncMock(return_value=[])
    session = service.create_session("alice")
    sent_payloads: list[dict] = []

    async def send_json(payload: dict) -> None:
        sent_payloads.append(payload)

    await service.handle_chat_message(
        session,
        {
            "t": "send",
            "message_id": "request-while-active",
            "message": [{"type": "plain", "text": "hello"}],
        },
        send_json,
    )

    assert sent_payloads == [
        {
            "ct": "chat",
            "t": "error",
            "data": "Message content is empty",
            "code": "INVALID_MESSAGE_FORMAT",
            "message_id": "request-while-active",
        }
    ]


@pytest.mark.asyncio
async def test_handle_chat_message_send_rejects_non_list_message_payload():
    service = _service()
    session = service.create_session("alice")
    sent_payloads: list[dict] = []

    async def send_json(payload: dict) -> None:
        sent_payloads.append(payload)

    await service.handle_chat_message(
        session,
        {"t": "send", "message_id": "not-a-list", "message": "not-a-list"},
        send_json,
    )

    assert sent_payloads == [
        {
            "ct": "chat",
            "t": "error",
            "data": "message must be list",
            "code": "INVALID_MESSAGE_FORMAT",
            "message_id": "not-a-list",
        }
    ]


@pytest.mark.asyncio
async def test_handle_chat_message_send_rejects_empty_message_parts():
    service = _service()
    service.build_chat_message_parts = AsyncMock(return_value=[])
    session = service.create_session("alice")
    sent_payloads: list[dict] = []

    async def send_json(payload: dict) -> None:
        sent_payloads.append(payload)

    await service.handle_chat_message(
        session,
        {
            "t": "send",
            "message_id": "empty-message",
            "message": [{"type": "plain", "text": ""}],
        },
        send_json,
    )

    assert sent_payloads == [
        {
            "ct": "chat",
            "t": "error",
            "data": "Message content is empty",
            "code": "INVALID_MESSAGE_FORMAT",
            "message_id": "empty-message",
        }
    ]


@pytest.mark.asyncio
async def test_handle_chat_message_send_reports_processing_failure_and_cleans_queue(
    monkeypatch,
    caplog,
):
    service = _service()
    service.ensure_chat_subscription = AsyncMock(return_value="sub-err")
    service.build_chat_message_parts = AsyncMock(
        return_value=[{"type": "plain", "text": "hello"}]
    )
    session = service.create_session("alice")
    removed_request_ids: list[str] = []
    sent_payloads: list[dict] = []

    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "get_or_create_queue",
        lambda _conversation_id: (_ for _ in ()).throw(RuntimeError("queue boom")),
    )
    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "remove_back_queue",
        removed_request_ids.append,
    )

    async def send_json(payload: dict) -> None:
        sent_payloads.append(payload)

    await service.handle_chat_message(
        session,
        {
            "t": "send",
            "session_id": "chat-session",
            "message_id": "msg-error",
            "message": [{"type": "plain", "text": "hello"}],
        },
        send_json,
    )

    assert sent_payloads == [
        {
            "ct": "chat",
            "t": "error",
            "data": "Unable to process the message.",
            "code": "PROCESSING_ERROR",
            "message_id": "msg-error",
        }
    ]
    assert "queue boom" in caplog.text
    assert "queue boom" not in sent_payloads[0]["data"]
    assert removed_request_ids == ["msg-error"]


@pytest.mark.asyncio
async def test_handle_chat_message_send_logs_pending_flush_failure_and_still_cleans_queue(
    monkeypatch,
):
    service = _service()
    service.ensure_chat_subscription = AsyncMock(return_value="sub-flush")
    service.build_chat_message_parts = AsyncMock(
        return_value=[{"type": "plain", "text": "hello"}]
    )
    service.platform_history_mgr.insert = AsyncMock(return_value=_record(12))
    service.save_bot_message = AsyncMock(side_effect=RuntimeError("flush failed"))
    session = service.create_session("alice")
    chat_queue: asyncio.Queue = asyncio.Queue()
    back_queue: asyncio.Queue = asyncio.Queue()
    removed_request_ids: list[str] = []
    logged_exceptions: list[str] = []

    back_queue.put_nowait(
        {
            "message_id": "msg-flush",
            "type": "plain",
            "data": "Hello",
            "streaming": False,
        }
    )

    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "get_or_create_queue",
        lambda _conversation_id: chat_queue,
    )
    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "get_or_create_back_queue",
        lambda _request_id, _conversation_id=None: back_queue,
    )
    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "remove_back_queue",
        removed_request_ids.append,
    )
    monkeypatch.setattr(
        "astrbot.dashboard.services.webchat_service.logger.exception",
        lambda message, *args, **kwargs: logged_exceptions.append(str(message)),
    )

    async def send_json(_payload: dict) -> None:
        return None

    await service.handle_chat_message(
        session,
        {
            "t": "send",
            "session_id": "chat-session",
            "message_id": "msg-flush",
            "message": [{"type": "plain", "text": "hello"}],
        },
        send_json,
    )

    assert service.save_bot_message.await_count >= 1
    assert removed_request_ids == ["msg-flush"]
    assert any(
        "Failed to persist pending chat message: flush failed" in message
        for message in logged_exceptions
    )


@pytest.mark.asyncio
async def test_handle_chat_message_send_enqueues_and_persists_messages(monkeypatch):
    service = _service()
    service.platform_history_mgr.insert = AsyncMock(return_value=_record(10))
    service.ensure_chat_subscription = AsyncMock(return_value="sub-1")
    service.build_chat_message_parts = AsyncMock(
        return_value=[{"type": "plain", "text": "hello"}]
    )
    service.save_bot_message = AsyncMock(return_value=_record(20))
    service.db.get_attachment_by_id = AsyncMock()
    service.db.get_platform_session_by_id = AsyncMock(
        return_value=SimpleNamespace(platform_id="webchat", creator="alice")
    )
    session = service.create_session(
        "alice",
        DashboardSessionPrincipal(
            username="alice",
            sid="dashboard-sid",
            jti="jti",
            account_id="account-1",
        ),
    )
    chat_queue: asyncio.Queue = asyncio.Queue()
    back_queue: asyncio.Queue = asyncio.Queue()
    removed_request_ids: list[str] = []
    sent_payloads: list[dict] = []

    back_queue.put_nowait(
        {
            "message_id": "msg-1",
            "type": "plain",
            "data": "Hello ",
            "streaming": True,
        }
    )
    back_queue.put_nowait(
        {
            "message_id": "msg-1",
            "type": "plain",
            "data": "world",
            "streaming": True,
        }
    )
    back_queue.put_nowait(
        {
            "message_id": "msg-1",
            "type": "complete",
            "data": "",
            "streaming": True,
        }
    )
    back_queue.put_nowait(
        {
            "message_id": "msg-1",
            "type": "end",
            "data": "",
            "streaming": False,
        }
    )

    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "get_or_create_queue",
        lambda _conversation_id: chat_queue,
    )
    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "get_or_create_back_queue",
        lambda _request_id, _conversation_id=None: back_queue,
    )
    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "remove_back_queue",
        removed_request_ids.append,
    )

    async def send_json(payload: dict) -> None:
        sent_payloads.append(payload)

    await service.handle_chat_message(
        session,
        {
            "t": "send",
            "session_id": "chat-session",
            "message_id": "msg-1",
            "message": [{"type": "plain", "text": "hello"}],
            "webchat_step_up_tokens": {"tool.local_exec": "opaque-proof"},
        },
        send_json,
    )

    queued_username, queued_session_id, queued_payload = await chat_queue.get()
    assert queued_username == "alice"
    assert queued_session_id == "chat-session"
    assert queued_payload["message"] == [{"type": "plain", "text": "hello"}]
    assert queued_payload["message_id"] == "msg-1"
    assert queued_payload["_dashboard_principal"]["step_up_tokens"] == {
        "tool.local_exec": "opaque-proof"
    }
    assert session.webchat_step_up_tokens == {}

    service.platform_history_mgr.insert.assert_awaited_once()
    service.save_bot_message.assert_awaited_once()
    save_args = service.save_bot_message.await_args.args
    assert save_args[0] == "chat-session"
    assert save_args[1] == [{"type": "plain", "text": "Hello world"}]
    assert save_args[2] == {}
    assert save_args[3] == {}
    llm_checkpoint_id = save_args[4]
    assert isinstance(llm_checkpoint_id, str)

    assert sent_payloads[0]["type"] == "user_message_saved"
    assert sent_payloads[0]["data"]["id"] == 10
    assert sent_payloads[0]["data"]["llm_checkpoint_id"] == llm_checkpoint_id
    assert sent_payloads[1:5] == [
        {
            "ct": "chat",
            "message_id": "msg-1",
            "type": "plain",
            "data": "Hello ",
            "streaming": True,
        },
        {
            "ct": "chat",
            "message_id": "msg-1",
            "type": "plain",
            "data": "world",
            "streaming": True,
        },
        {
            "ct": "chat",
            "message_id": "msg-1",
            "type": "complete",
            "data": "",
            "streaming": True,
        },
        {
            "ct": "chat",
            "type": "message_saved",
            "data": {
                "id": 20,
                "created_at": "2026-01-01T00:00:00+00:00",
                "llm_checkpoint_id": llm_checkpoint_id,
            },
            "message_id": "msg-1",
        },
    ]
    assert sent_payloads[5] == {
        "ct": "chat",
        "message_id": "msg-1",
        "type": "end",
        "data": "",
        "streaming": False,
    }
    assert removed_request_ids == ["msg-1"]


@pytest.mark.asyncio
async def test_handle_chat_message_send_ignores_empty_mismatched_and_bad_agent_stats(
    monkeypatch,
):
    service = _service()
    service.platform_history_mgr.insert = AsyncMock(return_value=_record(13))
    service.ensure_chat_subscription = AsyncMock(return_value="sub-3")
    service.build_chat_message_parts = AsyncMock(
        return_value=[{"type": "plain", "text": "hello"}]
    )
    service.save_bot_message = AsyncMock(return_value=_record(23))
    session = service.create_session("alice")
    chat_queue: asyncio.Queue = asyncio.Queue()
    back_queue: asyncio.Queue = asyncio.Queue()
    sent_payloads: list[dict] = []
    removed_request_ids: list[str] = []

    back_queue.put_nowait(None)
    back_queue.put_nowait(
        {
            "message_id": "someone-else",
            "type": "plain",
            "data": "ignored",
            "streaming": False,
        }
    )
    back_queue.put_nowait(
        {
            "message_id": "msg-3",
            "type": "plain",
            "data": "{bad json",
            "chain_type": "agent_stats",
        }
    )
    back_queue.put_nowait(
        {
            "message_id": "msg-3",
            "type": "plain",
            "data": "kept",
            "streaming": False,
        }
    )
    back_queue.put_nowait(
        {
            "message_id": "msg-3",
            "type": "end",
            "data": "",
            "streaming": False,
        }
    )

    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "get_or_create_queue",
        lambda _conversation_id: chat_queue,
    )
    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "get_or_create_back_queue",
        lambda _request_id, _conversation_id=None: back_queue,
    )
    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "remove_back_queue",
        removed_request_ids.append,
    )

    async def send_json(payload: dict) -> None:
        sent_payloads.append(payload)

    await service.handle_chat_message(
        session,
        {
            "t": "send",
            "session_id": "chat-session",
            "message_id": "msg-3",
            "message": [{"type": "plain", "text": "hello"}],
        },
        send_json,
    )

    service.save_bot_message.assert_awaited_once()
    save_args = service.save_bot_message.await_args.args
    assert save_args[1] == [{"type": "plain", "text": "kept"}]
    assert save_args[2] == {}
    assert sent_payloads[1] == {
        "ct": "chat",
        "message_id": "msg-3",
        "type": "plain",
        "data": "kept",
        "streaming": False,
    }
    assert removed_request_ids == ["msg-3"]


@pytest.mark.asyncio
async def test_handle_chat_message_send_falls_back_when_extract_web_search_refs_fails(
    monkeypatch,
):
    service = _service()
    service.platform_history_mgr.insert = AsyncMock(return_value=_record(14))
    service.ensure_chat_subscription = AsyncMock(return_value="sub-4")
    service.build_chat_message_parts = AsyncMock(
        return_value=[{"type": "plain", "text": "hello"}]
    )
    service.save_bot_message = AsyncMock(return_value=_record(24))
    session = service.create_session("alice")
    chat_queue: asyncio.Queue = asyncio.Queue()
    back_queue: asyncio.Queue = asyncio.Queue()
    removed_request_ids: list[str] = []
    logged_exceptions: list[str] = []

    back_queue.put_nowait(
        {
            "message_id": "msg-4",
            "type": "plain",
            "data": "answer <ref>1</ref>",
            "streaming": False,
        }
    )
    back_queue.put_nowait(
        {
            "message_id": "msg-4",
            "type": "end",
            "data": "",
            "streaming": False,
        }
    )

    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "get_or_create_queue",
        lambda _conversation_id: chat_queue,
    )
    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "get_or_create_back_queue",
        lambda _request_id, _conversation_id=None: back_queue,
    )
    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "remove_back_queue",
        removed_request_ids.append,
    )
    monkeypatch.setattr(
        service,
        "extract_web_search_refs",
        MagicMock(side_effect=RuntimeError("refs boom")),
    )
    monkeypatch.setattr(
        "astrbot.dashboard.services.webchat_service.logger.exception",
        lambda message, *args, **kwargs: logged_exceptions.append(str(message)),
    )

    async def send_json(_payload: dict) -> None:
        return None

    await service.handle_chat_message(
        session,
        {
            "t": "send",
            "session_id": "chat-session",
            "message_id": "msg-4",
            "message": [{"type": "plain", "text": "hello"}],
        },
        send_json,
    )

    service.save_bot_message.assert_awaited_once()
    save_args = service.save_bot_message.await_args.args
    assert save_args[1] == [{"type": "plain", "text": "answer <ref>1</ref>"}]
    assert save_args[3] == {}
    assert removed_request_ids == ["msg-4"]
    assert any(
        "Failed to extract web search refs: refs boom" in message
        for message in logged_exceptions
    )


@pytest.mark.asyncio
async def test_handle_chat_message_send_persists_agent_stats_and_attachment(
    monkeypatch,
):
    service = _service()
    service.platform_history_mgr.insert = AsyncMock(return_value=_record(11))
    service.ensure_chat_subscription = AsyncMock(return_value="sub-2")
    service.build_chat_message_parts = AsyncMock(
        return_value=[{"type": "plain", "text": "hello"}]
    )
    service.create_attachment_from_file = AsyncMock(
        return_value={"type": "image", "attachment_id": "att-1"}
    )
    service.save_bot_message = AsyncMock(return_value=_record(21))
    session = service.create_session("alice")
    chat_queue: asyncio.Queue = asyncio.Queue()
    back_queue: asyncio.Queue = asyncio.Queue()
    sent_payloads: list[dict] = []
    removed_request_ids: list[str] = []

    back_queue.put_nowait(
        {
            "message_id": "msg-2",
            "type": "plain",
            "data": '{"latency": 12}',
            "chain_type": "agent_stats",
        }
    )
    back_queue.put_nowait(
        {
            "message_id": "msg-2",
            "type": "image",
            "data": "[IMAGE]photo.png",
            "streaming": False,
        }
    )
    back_queue.put_nowait(
        {
            "message_id": "msg-2",
            "type": "end",
            "data": "",
            "streaming": False,
        }
    )

    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "get_or_create_queue",
        lambda _conversation_id: chat_queue,
    )
    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "get_or_create_back_queue",
        lambda _request_id, _conversation_id=None: back_queue,
    )
    monkeypatch.setattr(
        service.webchat_run_coordinator.queue_manager,
        "remove_back_queue",
        removed_request_ids.append,
    )

    async def send_json(payload: dict) -> None:
        sent_payloads.append(payload)

    await service.handle_chat_message(
        session,
        {
            "t": "send",
            "session_id": "chat-session",
            "message_id": "msg-2",
            "message": [{"type": "plain", "text": "hello"}],
        },
        send_json,
    )

    service.create_attachment_from_file.assert_awaited_once_with("photo.png", "image")
    service.save_bot_message.assert_awaited_once_with(
        "chat-session",
        [{"type": "image", "attachment_id": "att-1"}],
        {"latency": 12},
        {},
        service.save_bot_message.await_args.args[4],
    )
    assert any(
        payload
        == {
            "ct": "chat",
            "type": "attachment_saved",
            "data": {"id": "att-1", "type": "image"},
            "message_id": "msg-2",
        }
        for payload in sent_payloads
    )
    assert any(
        payload
        == {
            "ct": "chat",
            "type": "agent_stats",
            "data": {"latency": 12},
            "message_id": "msg-2",
        }
        for payload in sent_payloads
    )
    assert removed_request_ids == ["msg-2"]
