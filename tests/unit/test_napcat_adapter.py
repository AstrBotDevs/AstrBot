import asyncio
import json
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from websockets.exceptions import InvalidStatus

from astrbot.core.command import CommandCatalogStore
from astrbot.core.message.components import (
    RPS,
    Anonymous,
    Contact,
    Dice,
    Face,
    File,
    FlashTransfer,
    Forward,
    Image,
    Json,
    Location,
    Markdown,
    MFace,
    MiniApp,
    Music,
    Node,
    Nodes,
    OnlineFile,
    Plain,
    Poke,
    Record,
    Reply,
    Shake,
    Share,
    Unknown,
    Video,
    Xml,
)
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.pipeline.waking_check.stage import WakingCheckStage
from astrbot.core.platform.astr_message_event import MessageSession
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.send_result import PlatformSendResult
from astrbot.core.platform.sources.napcat import forward_ws_client
from astrbot.core.platform.sources.napcat.exceptions import (
    NapCatApiError,
    NapCatTransportError,
)
from astrbot.core.platform.sources.napcat.generated.ob11_events import OB11AllEvent
from astrbot.core.platform.sources.napcat.napcat_platform_adapter import (
    NapCatPlatformAdapter,
)
from astrbot.core.platform.sources.napcat.types import NapCatFetchedMessage
from astrbot.core.runtime_catalogs import RuntimeCatalogs

pytestmark = pytest.mark.platform


class _ControlledForwardSocket:
    """A deterministic async WebSocket double for transport lifecycle tests."""

    def __init__(
        self,
        payloads: tuple[str, ...] = (),
        *,
        disconnect_error: Exception | None = None,
    ) -> None:
        self._payloads = deque(payloads)
        self._release_event = asyncio.Event()
        self._disconnect_error = disconnect_error
        self.entered = asyncio.Event()
        self.closed = asyncio.Event()
        self.exited = asyncio.Event()
        self.sent_payloads: list[dict[str, object]] = []

    async def send(self, payload: str) -> None:
        self.sent_payloads.append(json.loads(payload))

    async def close(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        self.closed.set()
        self._release_event.set()

    def release(self) -> None:
        self._release_event.set()

    def __aiter__(self) -> _ControlledForwardSocket:
        return self

    async def __anext__(self) -> str:
        if self._payloads:
            return self._payloads.popleft()
        await self._release_event.wait()
        if self._disconnect_error is not None:
            raise self._disconnect_error
        raise StopAsyncIteration


class _ControlledForwardConnection:
    """Async context manager yielding a controlled forward WebSocket."""

    def __init__(self, socket: _ControlledForwardSocket) -> None:
        self.socket = socket

    async def __aenter__(self) -> _ControlledForwardSocket:
        self.socket.entered.set()
        return self.socket

    async def __aexit__(
        self,
        _exc_type: object,
        _exc: object,
        _traceback: object,
    ) -> None:
        self.socket.exited.set()


def _make_adapter(event_queue: asyncio.Queue) -> NapCatPlatformAdapter:
    adapter = NapCatPlatformAdapter(
        {
            "id": "napcat-test",
            "ws_url": "ws://127.0.0.1:3001",
            "timeout_seconds": 5,
            "verify_ssl": True,
            "reconnect_interval_seconds": 1,
            "max_frame_size_mb": 8,
        },
        {},
        event_queue,
    )
    return adapter


def _make_forward_ws_adapter(event_queue: asyncio.Queue) -> NapCatPlatformAdapter:
    adapter = NapCatPlatformAdapter(
        {
            "id": "napcat-forward-ws-test",
            "ws_url": "ws://127.0.0.1:3001/ws",
            "timeout_seconds": 5,
            "verify_ssl": True,
            "token": " forward-secret ",
            "reconnect_interval_seconds": 3,
            "max_frame_size_mb": 8,
        },
        {},
        event_queue,
    )
    return adapter


def _make_manual_event(
    adapter: NapCatPlatformAdapter,
    *,
    sender_id: str = "111222",
    message_type: MessageType = MessageType.FRIEND_MESSAGE,
    group_id: str | None = None,
    message: list | None = None,
):
    message_obj = AstrBotMessage()
    message_obj.type = message_type
    message_obj.self_id = "123456"
    message_obj.session_id = group_id or sender_id
    message_obj.message_id = "local-message-id"
    message_obj.sender = MessageMember(sender_id, "tester")
    message_obj.group_id = group_id
    message_obj.message = message or []
    message_obj.message_str = ""
    message_obj.raw_message = None
    return adapter.create_event(message_obj)


def test_napcat_metadata_exposes_display_name():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    metadata = adapter.meta()

    assert metadata.name == "napcat"
    assert metadata.adapter_display_name == "NapCat"
    assert metadata.support_streaming_message is False


def test_napcat_adapter_reports_supported_actions():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    supported = set(adapter.supported_actions())
    metadata_supported = set(adapter.meta().supported_actions)

    assert adapter.supports_action("set_group_admin") is True
    assert adapter.supports_action("kick_group_members") is True
    assert adapter.supports_action("send_group_notice") is True
    assert adapter.supports_action("send_like") is True
    assert adapter.supports_action("send_poke") is True
    assert adapter.supports_action("definitely_not_supported") is False
    assert supported == metadata_supported
    assert {
        "set_group_admin",
        "set_group_ban",
        "set_group_card",
        "kick_group_member",
        "kick_group_members",
        "leave_group",
        "set_group_whole_ban",
        "set_essence_message",
        "delete_essence_message",
        "send_group_notice",
        "send_like",
        "send_poke",
    }.issubset(supported)

    stats = adapter.get_stats()
    assert set(stats["meta"]["supported_actions"]).issuperset(
        {
            "set_group_admin",
            "kick_group_members",
            "send_group_notice",
            "send_like",
            "send_poke",
        }
    )


def test_napcat_event_exposes_supported_platform_actions():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = _make_manual_event(adapter, sender_id="445566")

    supported = set(event.get_supported_platform_actions())

    assert "send_poke" in supported
    assert "send_group_notice" in supported
    assert event.supports_platform_action("send_like") is True
    assert event.supports_platform_action("unsupported_action") is False


def test_napcat_adapter_configures_forward_ws_client() -> None:
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_forward_ws_adapter(queue)

    assert adapter.client.ws_url == "ws://127.0.0.1:3001/ws"
    assert adapter.client.token == "forward-secret"
    assert adapter.client.reconnect_interval_seconds == 3
    assert adapter.client.max_size_bytes == 8 * 1024 * 1024


def test_napcat_forward_ws_client_exposes_message_segment_builders() -> None:
    adapter = _make_adapter(asyncio.Queue())
    client = adapter.client

    assert client.text("hello").to_dict() == {
        "type": "text",
        "data": {"text": "hello"},
    }
    assert client.at_all().to_dict() == {"type": "at", "data": {"qq": "all"}}
    assert client.file(file="stored.bin", name="shown.bin").to_dict() == {
        "type": "file",
        "data": {"file": "stored.bin", "name": "shown.bin"},
    }
    assert client.music(music_type="qq", music_id=1).to_dict() == {
        "type": "music",
        "data": {"type": "qq", "id": "1"},
    }
    with pytest.raises(ValueError, match="target_id or user_id"):
        client.poke()


@pytest.mark.asyncio
async def test_napcat_adapter_run_and_terminate_manage_forward_ws_lifecycle():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_forward_ws_adapter(queue)
    startup_called = asyncio.Event()

    async def start_client() -> None:
        startup_called.set()

    adapter.client.start = AsyncMock(side_effect=start_client)
    adapter.client.get_version_info = AsyncMock(
        return_value=SimpleNamespace(app_name="NapCat", app_version="4.18.7")
    )
    adapter.client.get_status = AsyncMock(
        return_value=SimpleNamespace(online=True, good=True)
    )
    adapter.client.get_login_info = AsyncMock(
        return_value=SimpleNamespace(user_id=123456, nickname="tester")
    )
    adapter.client.close = AsyncMock()

    run_task = asyncio.create_task(adapter.run())
    await asyncio.wait_for(startup_called.wait(), timeout=1)

    adapter.client.start.assert_awaited_once_with()
    assert run_task.done() is False

    await adapter.terminate()
    await run_task

    adapter.client.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_napcat_adapter_startup_failure_closes_forward_ws_client():
    adapter = _make_forward_ws_adapter(asyncio.Queue())
    adapter.client.start = AsyncMock()
    adapter.client.get_version_info = AsyncMock(
        return_value=SimpleNamespace(app_name="NapCat", app_version="4.18.7")
    )
    adapter.client.get_status = AsyncMock(
        return_value=SimpleNamespace(online=True, good=True)
    )
    adapter.client.get_login_info = AsyncMock(
        return_value=SimpleNamespace(user_id=123456, nickname="tester")
    )
    failure = NapCatApiError(
        "get_version_info",
        status="failed",
        retcode=1403,
        message="token验证失败",
        wording="token验证失败",
    )
    adapter.client.get_version_info = AsyncMock(side_effect=failure)
    adapter.client.close = AsyncMock()

    with pytest.raises(NapCatApiError, match=str(failure)):
        await adapter.run()

    adapter.client.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_napcat_adapter_retries_transient_startup_transport_failure():
    adapter = _make_forward_ws_adapter(asyncio.Queue())
    adapter.client.reconnect_interval_seconds = 0
    startup_checked = asyncio.Event()

    async def start_client() -> None:
        if adapter.client.start.await_count == 1:
            raise NapCatTransportError(
                "start", "forward websocket did not connect within 5.0s"
            )

    adapter.client.start = AsyncMock(side_effect=start_client)
    adapter.client.get_version_info = AsyncMock(
        return_value=SimpleNamespace(app_name="NapCat", app_version="4.18.7")
    )
    adapter.client.get_status = AsyncMock(
        return_value=SimpleNamespace(online=True, good=True)
    )

    async def get_login_info() -> SimpleNamespace:
        startup_checked.set()
        return SimpleNamespace(user_id=123456, nickname="tester")

    adapter.client.get_login_info = AsyncMock(side_effect=get_login_info)
    adapter.client.close = AsyncMock()

    run_task = asyncio.create_task(adapter.run())
    await asyncio.wait_for(startup_checked.wait(), timeout=1)

    assert run_task.done() is False
    assert adapter.client.start.await_count == 2
    adapter.client.close.assert_not_awaited()

    await adapter.terminate()
    await run_task

    adapter.client.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_napcat_adapter_terminate_interrupts_startup_transport_backoff():
    adapter = _make_forward_ws_adapter(asyncio.Queue())
    adapter.client.reconnect_interval_seconds = 3600
    startup_attempted = asyncio.Event()
    backoff_started = asyncio.Event()
    shutdown_event = asyncio.Event()

    class ObservedShutdownEvent:
        def is_set(self) -> bool:
            return shutdown_event.is_set()

        async def wait(self) -> None:
            backoff_started.set()
            await shutdown_event.wait()

        def set(self) -> None:
            shutdown_event.set()

    async def start_client() -> None:
        startup_attempted.set()
        raise NapCatTransportError("start", "NapCat is unavailable")

    adapter.shutdown_event = ObservedShutdownEvent()
    adapter.client.start = AsyncMock(side_effect=start_client)
    adapter.client.close = AsyncMock()
    run_task = asyncio.create_task(adapter.run())

    try:
        await asyncio.wait_for(startup_attempted.wait(), timeout=1)
        await asyncio.wait_for(backoff_started.wait(), timeout=1)

        await adapter.terminate()
        await run_task

        assert adapter.client.start.await_count == 1
        adapter.client.close.assert_awaited_once_with()
    finally:
        if not run_task.done():
            await adapter.terminate()
        await asyncio.gather(run_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_close_cancels_connecting_runner():
    adapter = _make_adapter(asyncio.Queue())
    runner_task = asyncio.create_task(asyncio.Event().wait())
    adapter.client._runner_task = runner_task

    await adapter.client.close()

    assert runner_task.cancelled() is True
    assert adapter.client._runner_task is None


@pytest.mark.asyncio
async def test_napcat_terminate_interrupts_forward_ws_reconnect_backoff(
    monkeypatch: pytest.MonkeyPatch,
):
    adapter = _make_adapter(asyncio.Queue())
    client = adapter.client
    connection_attempted = asyncio.Event()
    backoff_started = asyncio.Event()

    def fail_connect(*args: object, **kwargs: object) -> object:
        del args, kwargs
        connection_attempted.set()
        raise OSError("NapCat is unavailable")

    async def wait_for_reconnect() -> None:
        backoff_started.set()
        await client._stop_event.wait()

    monkeypatch.setattr(forward_ws_client, "connect", fail_connect)
    monkeypatch.setattr(client, "_wait_for_reconnect", wait_for_reconnect)
    runner_task = asyncio.create_task(client._run_loop())
    client._runner_task = runner_task

    await asyncio.wait_for(connection_attempted.wait(), timeout=1)
    await asyncio.wait_for(backoff_started.wait(), timeout=1)

    await adapter.terminate()

    assert adapter.shutdown_event.is_set()
    assert runner_task.cancelled() is True
    assert client._runner_task is None


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_recovers_after_multiple_connect_failures(
    monkeypatch: pytest.MonkeyPatch,
):
    adapter = _make_adapter(asyncio.Queue())
    client = adapter.client
    client.reconnect_interval_seconds = 0
    recovered_socket = _ControlledForwardSocket()
    attempts = 0

    def connect_after_two_failures(*args: object, **kwargs: object) -> object:
        nonlocal attempts
        del args, kwargs
        attempts += 1
        if attempts <= 2:
            raise OSError(f"connection attempt {attempts} failed")
        return _ControlledForwardConnection(recovered_socket)

    monkeypatch.setattr(forward_ws_client, "connect", connect_after_two_failures)

    await asyncio.wait_for(client.start(), timeout=1)

    assert attempts == 3
    assert client._connected_event.is_set()
    assert recovered_socket.entered.is_set()

    await client.close()

    assert recovered_socket.closed.is_set()
    assert recovered_socket.exited.is_set()
    assert client._runner_task is None


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_start_failure_cleans_up_runner(
    monkeypatch: pytest.MonkeyPatch,
):
    adapter = _make_adapter(asyncio.Queue())
    client = adapter.client
    client.action_timeout_seconds = 0

    def fail_connect(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise OSError("NapCat is unavailable")

    monkeypatch.setattr(forward_ws_client, "connect", fail_connect)

    try:
        with pytest.raises(NapCatTransportError, match="did not connect"):
            await client.start()

        assert client._runner_task is None
        assert client._stop_event.is_set()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_napcat_forward_ws_disconnect_fails_and_clears_pending_actions(
    monkeypatch: pytest.MonkeyPatch,
):
    adapter = _make_adapter(asyncio.Queue())
    client = adapter.client
    disconnecting_socket = _ControlledForwardSocket(
        disconnect_error=OSError("connection lost")
    )
    monkeypatch.setattr(
        forward_ws_client,
        "connect",
        lambda *args, **kwargs: _ControlledForwardConnection(disconnecting_socket),
    )
    pending: asyncio.Future[dict[str, object]] = (
        asyncio.get_running_loop().create_future()
    )
    client._pending["old-echo"] = pending

    listen_task = asyncio.create_task(client._connect_and_listen())
    await asyncio.wait_for(disconnecting_socket.entered.wait(), timeout=1)
    disconnecting_socket.release()

    with pytest.raises(OSError, match="connection lost"):
        await listen_task
    with pytest.raises(NapCatTransportError, match="pending action old-echo failed"):
        await pending

    assert client._pending == {}
    assert client._connected_event.is_set() is False
    assert disconnecting_socket.exited.is_set()


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_ignores_stale_connection_response():
    adapter = _make_adapter(asyncio.Queue())
    client = adapter.client
    pending: asyncio.Future[dict[str, object]] = (
        asyncio.get_running_loop().create_future()
    )
    client._pending["reused-echo"] = pending
    client._connection_generation = 2

    try:
        await client._handle_ws_payload(
            json.dumps(
                {
                    "status": "ok",
                    "retcode": 0,
                    "data": {"from": "old connection"},
                    "echo": "reused-echo",
                }
            ),
            connection_generation=1,
        )

        assert pending.done() is False
        assert client._pending["reused-echo"] is pending
    finally:
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending


@pytest.mark.asyncio
async def test_napcat_forward_ws_authentication_failure_stops_reconnects(
    monkeypatch: pytest.MonkeyPatch,
):
    adapter = _make_adapter(asyncio.Queue())
    client = adapter.client
    client.reconnect_interval_seconds = 0
    authentication_payload = json.dumps(
        {
            "status": "failed",
            "retcode": 1403,
            "data": None,
            "message": "token rejected",
            "wording": "token rejected",
            "echo": None,
        }
    )
    rejected_socket = _ControlledForwardSocket((authentication_payload,))
    reconnect_attempted = asyncio.Event()
    replacement_socket = _ControlledForwardSocket()
    attempts = 0

    def connect_with_authentication_failure(*args: object, **kwargs: object) -> object:
        nonlocal attempts
        del args, kwargs
        attempts += 1
        if attempts == 1:
            return _ControlledForwardConnection(rejected_socket)
        reconnect_attempted.set()
        return _ControlledForwardConnection(replacement_socket)

    monkeypatch.setattr(
        forward_ws_client,
        "connect",
        connect_with_authentication_failure,
    )

    with pytest.raises(NapCatApiError, match="token rejected"):
        await asyncio.wait_for(client.start(), timeout=1)

    assert rejected_socket.closed.is_set()
    assert reconnect_attempted.is_set() is False
    assert attempts == 1
    assert client._runner_task is None
    with pytest.raises(NapCatApiError, match="token rejected"):
        await client.call_action("get_version_info")


@pytest.mark.asyncio
async def test_napcat_forward_ws_handshake_authentication_failure_stops_reconnects(
    monkeypatch: pytest.MonkeyPatch,
):
    adapter = _make_adapter(asyncio.Queue())
    client = adapter.client
    client.reconnect_interval_seconds = 0
    reconnect_attempted = asyncio.Event()
    replacement_socket = _ControlledForwardSocket()
    attempts = 0

    def reject_handshake(*args: object, **kwargs: object) -> object:
        nonlocal attempts
        del args, kwargs
        attempts += 1
        if attempts == 1:
            raise InvalidStatus(SimpleNamespace(status_code=401))
        reconnect_attempted.set()
        return _ControlledForwardConnection(replacement_socket)

    monkeypatch.setattr(forward_ws_client, "connect", reject_handshake)

    try:
        with pytest.raises(NapCatApiError, match="WebSocket authentication failed"):
            await asyncio.wait_for(client.start(), timeout=1)

        assert reconnect_attempted.is_set() is False
        assert attempts == 1
        assert client._runner_task is None
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_surfaces_failed_response_without_echo():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    socket = SimpleNamespace(close=AsyncMock())
    adapter.client._socket = socket
    future: asyncio.Future[dict] = asyncio.get_running_loop().create_future()
    adapter.client._pending["echo-1"] = future

    await adapter.client._handle_ws_payload(
        '{"status":"failed","retcode":1403,"data":null,"message":"token验证失败","wording":"token验证失败","echo":null,"stream":"normal-action"}'
    )

    with pytest.raises(NapCatApiError, match="token验证失败"):
        await future
    socket.close.assert_awaited_once_with(
        code=1008,
        reason="NapCat WebSocket authentication failed",
    )


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_background_dispatch_allows_action_response():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    class _FakeSocket:
        def __init__(self) -> None:
            self.sent_payloads: list[dict[str, object]] = []

        async def send(self, payload: str) -> None:
            self.sent_payloads.append(json.loads(payload))

    fake_socket = _FakeSocket()
    adapter.client._socket = fake_socket
    adapter.client._connected_event.set()

    action_started = asyncio.Event()
    action_finished = asyncio.Event()

    async def mock_on_event(_event) -> None:
        action_started.set()
        payload = await adapter.client.call_action("unit_test_action", foo="bar")
        assert payload["status"] == "ok"
        action_finished.set()

    adapter.client.on_event = mock_on_event
    adapter.client._start_payload_task(
        """
        {
          "post_type": "message",
          "message_type": "private",
          "sub_type": "friend",
          "time": 1720000000,
          "self_id": 123456,
          "user_id": 111222,
          "message_id": 778,
          "font": 14,
          "raw_message": "/sid",
          "sender": {
            "user_id": 111222,
            "nickname": "tester"
          },
          "message": [
            {"type": "text", "data": {"text": "/sid"}}
          ]
        }
        """
    )

    await asyncio.wait_for(action_started.wait(), timeout=1.0)
    assert len(fake_socket.sent_payloads) == 1

    echo = str(fake_socket.sent_payloads[0]["echo"])
    await adapter.client._handle_ws_payload(
        json.dumps(
            {
                "status": "ok",
                "retcode": 0,
                "data": {"done": True},
                "echo": echo,
            }
        )
    )

    await asyncio.wait_for(action_finished.wait(), timeout=1.0)
    if adapter.client._payload_tasks:
        await asyncio.gather(
            *list(adapter.client._payload_tasks), return_exceptions=True
        )


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_ignores_extra_event_fields():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message",
          "message_type": "private",
          "sub_type": "friend",
          "time": 1720000000,
          "self_id": 123456,
          "user_id": 111222,
          "message_id": 778,
          "font": 14,
          "raw_message": "/sid",
          "sender": {
            "user_id": 111222,
            "nickname": "tester"
          },
          "message": [
            {"type": "text", "data": {"text": "/sid"}}
          ],
          "unexpected_top_level": "ignored"
        }
        """
    )

    queued = queue.get_nowait()
    assert queued.get_message_str() == "/sid"


@pytest.mark.asyncio
async def test_napcat_unknown_array_segment_degrades_without_dropping_message():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message",
          "message_type": "private",
          "sub_type": "friend",
          "time": 1720000000,
          "self_id": 123456,
          "user_id": 111222,
          "message_id": 779,
          "font": 14,
          "raw_message": "before unknown after",
          "sender": {"user_id": 111222, "nickname": "tester"},
          "message": [
            {"type": "text", "data": {"text": "before "}},
            {"type": "future_segment", "data": {"value": "mock"}},
            {"type": "text", "data": {"text": " after"}}
          ]
        }
        """
    )

    queued = queue.get_nowait()
    assert queued.get_message_str() == (
        "before [Unsupported NapCat segment: future_segment] after"
    )
    assert [type(component).__name__ for component in queued.get_messages()] == [
        "Plain",
        "Plain",
        "Plain",
    ]


@pytest.mark.asyncio
async def test_napcat_unknown_notice_is_queued_as_generic_event():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "notice",
          "notice_type": "future_notice",
          "sub_type": "mock",
          "time": 1720000000,
          "self_id": 123456,
          "user_id": 111222,
          "future_value": "preserved"
        }
        """
    )

    queued = queue.get_nowait()
    assert queued.get_message_str() == "[notice:future_notice:mock] user 111222"
    assert queued.get_extra("onebot_notice_type") == "future_notice"
    assert queued.get_extra("napcat_event")["future_value"] == "preserved"


@pytest.mark.asyncio
async def test_napcat_unknown_request_is_queued_as_generic_event():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "request",
          "request_type": "future_request",
          "sub_type": "mock",
          "time": 1720000000,
          "self_id": 123456,
          "user_id": 111222,
          "comment": "mock request",
          "flag": "mock-flag"
        }
        """
    )

    queued = queue.get_nowait()
    assert queued.get_message_str() == (
        "[request:future_request:mock] user 111222 comment mock request flag mock-flag"
    )
    assert queued.get_extra("onebot_request_type") == "future_request"


@pytest.mark.asyncio
async def test_napcat_unknown_meta_event_is_ignored():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "meta_event",
          "meta_event_type": "future_meta",
          "time": 1720000000,
          "self_id": 123456
        }
        """
    )

    assert queue.empty()


@pytest.mark.asyncio
async def test_napcat_forward_ws_only_ignores_message_sent_events():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message_sent",
          "message_type": "private",
          "sub_type": "friend",
          "time": 1720000000,
          "self_id": 123456,
          "user_id": 123456,
          "target_id": 123456,
          "message_id": 779,
          "font": 14,
          "raw_message": "echo",
          "sender": {
            "user_id": 123456,
            "nickname": "bot-self"
          },
          "message": [
            {"type": "text", "data": {"text": "echo"}}
          ]
        }
        """
    )

    assert queue.empty()


@pytest.mark.asyncio
async def test_napcat_forward_ws_only_ignores_self_sent_message_events():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message",
          "message_type": "private",
          "sub_type": "friend",
          "time": 1720000000,
          "self_id": 123456,
          "user_id": 123456,
          "target_id": 123456,
          "message_id": 780,
          "font": 14,
          "raw_message": "self-echo",
          "sender": {
            "user_id": 123456,
            "nickname": "bot-self"
          },
          "message": [
            {"type": "text", "data": {"text": "self-echo"}}
          ]
        }
        """
    )

    assert queue.empty()


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_accepts_heartbeat_meta_event(caplog):
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    with caplog.at_level("WARNING"):
        await adapter.client._handle_ws_payload(
            """
            {
              "time": 1782950187,
              "self_id": 1507533037,
              "post_type": "meta_event",
              "meta_event_type": "heartbeat",
              "status": {
                "online": true,
                "good": true
              },
              "interval": 30000
            }
            """
        )

    assert queue.empty()
    assert not any("rejected event payload" in message for message in caplog.messages)


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_defaults_missing_group_sender_role(caplog):
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    with caplog.at_level("INFO"):
        await adapter.client._handle_ws_payload(
            """
            {
              "post_type": "message",
              "message_type": "group",
              "sub_type": "normal",
              "time": 1720000000,
              "self_id": 123456,
              "group_id": 654321,
              "user_id": 111222,
              "message_id": 781,
              "font": 14,
              "raw_message": "hello",
              "sender": {
                "user_id": 111222,
                "nickname": "tester-card"
              },
              "message": [
                {"type": "text", "data": {"text": "hello"}}
              ]
            }
            """
        )

    queued = queue.get_nowait()
    assert queued.get_message_str() == "hello"
    assert queued.platform_member_role == "member"
    assert any(
        "defaulted sender.role to member" in message for message in caplog.messages
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["owner", "admin"])
async def test_napcat_private_sender_role_cannot_grant_group_privilege(role):
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        json.dumps(
            {
                "post_type": "message",
                "message_type": "private",
                "sub_type": "friend",
                "time": 1720000000,
                "self_id": 123456,
                "user_id": 111222,
                "message_id": 784,
                "font": 14,
                "raw_message": "hello",
                "sender": {
                    "user_id": 111222,
                    "nickname": "tester",
                    "role": role,
                },
                "message": [{"type": "text", "data": {"text": "hello"}}],
            }
        )
    )

    queued = queue.get_nowait()
    assert queued.is_private_chat()
    assert queued.platform_member_role == "member"


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_drops_sender_extra_fields(caplog):
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    with caplog.at_level("INFO"):
        await adapter.client._handle_ws_payload(
            """
            {
              "post_type": "message",
              "message_type": "private",
              "sub_type": "friend",
              "time": 1720000000,
              "self_id": 123456,
              "user_id": 111222,
              "message_id": 781,
              "font": 14,
              "raw_message": "hello",
              "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "uid": "unexpected-uid",
                "tiny_id": "unexpected-tiny-id"
              },
              "message": [
                {"type": "text", "data": {"text": "hello"}}
              ]
            }
            """
        )

    queued = queue.get_nowait()
    assert queued.get_message_str() == "hello"
    assert any(
        "dropped sender extra fields: tiny_id, uid" in message
        for message in caplog.messages
    )


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_preserves_temp_private_payload_fields(
    caplog,
):
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    with caplog.at_level("INFO"):
        await adapter.client._handle_ws_payload(
            """
            {
              "post_type": "message",
              "message_type": "private",
              "sub_type": "group",
              "time": 1720000000,
              "self_id": 123456,
              "group_id": 654321,
              "group_name": "temp-group",
              "user_id": 111222,
              "message_id": 782,
              "font": 14,
              "raw_message": "temp hello",
              "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "temp-card"
              },
              "message": [
                {"type": "text", "data": {"text": "temp hello"}}
              ]
            }
            """
        )

    queued = queue.get_nowait()
    assert queued.get_message_type() == MessageType.FRIEND_MESSAGE
    assert queued.get_message_str() == "temp hello"
    assert queued.get_sender_name() == "temp-card"
    assert queued.get_group_id() == "654321"
    assert queued.session.session_id == "111222"
    assert queued.get_extra("onebot_sub_type") == "group"
    assert queued.get_extra("napcat_group_id") == 654321
    assert queued.get_extra("napcat_event")["group_name"] == "temp-group"
    assert not any(
        "coerced private sub_type to friend" in message for message in caplog.messages
    )


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_accepts_private_string_message_payload():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message",
          "message_type": "private",
          "sub_type": "friend",
          "time": 1720000000,
          "self_id": 123456,
          "user_id": 111222,
          "target_id": 123456,
          "message_id": 783,
          "message_seq": 783,
          "real_id": 783,
          "real_seq": "783",
          "font": 14,
          "message_format": "string",
          "message_sent_type": "self",
          "raw_message": "hello string",
          "sender": {
            "user_id": 111222,
            "nickname": "tester"
          },
          "message": "hello string"
        }
        """
    )

    queued = queue.get_nowait()
    assert queued.get_message_str() == "hello string"
    assert [type(component).__name__ for component in queued.get_messages()] == [
        "Plain"
    ]
    assert queued.get_messages()[0].text == "hello string"
    assert queued.get_extra("napcat_event")["message_format"] == "string"
    assert queued.get_extra("napcat_notice_message") is None


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_accepts_group_string_message_payload():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message",
          "message_type": "group",
          "sub_type": "normal",
          "time": 1720000000,
          "self_id": 123456,
          "group_id": 654321,
          "group_name": "napcat-group",
          "user_id": 111222,
          "message_id": 784,
          "message_seq": 784,
          "real_id": 784,
          "real_seq": "784",
          "font": 14,
          "message_format": "string",
          "raw_message": "@bot hello group string",
          "sender": {
            "user_id": 111222,
            "nickname": "tester",
            "role": "member"
          },
          "message": "@bot hello group string"
        }
        """
    )

    queued = queue.get_nowait()
    assert queued.get_message_type() == MessageType.GROUP_MESSAGE
    assert queued.get_group_id() == "654321"
    assert queued.get_message_str() == "@bot hello group string"
    assert [type(component).__name__ for component in queued.get_messages()] == [
        "Plain"
    ]
    assert queued.get_extra("napcat_event")["group_name"] == "napcat-group"
    assert queued.get_extra("napcat_event")["message_format"] == "string"


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_parses_group_string_cq_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message",
          "message_type": "group",
          "sub_type": "normal",
          "time": 1720000000,
          "self_id": 123456,
          "group_id": 654321,
          "group_name": "napcat-group",
          "user_id": 111222,
          "message_id": 785,
          "message_seq": 785,
          "real_id": 785,
          "real_seq": "785",
          "font": 14,
          "message_format": "string",
          "raw_message": "[CQ:at,qq=123456,name=bot] hello [CQ:reply,id=9004]",
          "sender": {
            "user_id": 111222,
            "nickname": "tester",
            "role": "member"
          },
          "message": "[CQ:at,qq=123456,name=bot] hello [CQ:reply,id=9004]"
        }
        """
    )

    queued = queue.get_nowait()
    assert queued.get_message_str() == "hello"
    assert [type(component).__name__ for component in queued.get_messages()] == [
        "At",
        "Plain",
        "Reply",
    ]
    reply = queued.get_messages()[-1]
    assert reply.id == "9004"
    assert reply.sender_id == 0
    assert reply.sender_nickname == ""
    assert reply.message_str == ""
    assert not reply.chain
    adapter.client.get_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_keeps_group_string_at_targets_without_lookup():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()
    adapter.client.get_group_member_info = AsyncMock()
    adapter.client.get_stranger_info = AsyncMock()

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message",
          "message_type": "group",
          "sub_type": "normal",
          "time": 1720000000,
          "self_id": 123456,
          "group_id": 654321,
          "user_id": 111222,
          "message_id": 785,
          "message_seq": 785,
          "real_id": 785,
          "real_seq": "785",
          "font": 14,
          "message_format": "string",
          "raw_message": "[CQ:at,qq=999999] hi [CQ:at,qq=888888][CQ:at,qq=all][CQ:at,qq=777777,name=inline-name]",
          "sender": {
            "user_id": 111222,
            "nickname": "tester",
            "role": "member"
          },
          "message": "[CQ:at,qq=999999] hi [CQ:at,qq=888888][CQ:at,qq=all][CQ:at,qq=777777,name=inline-name]"
        }
        """
    )

    queued = queue.get_nowait()
    assert queued.get_message_str() == "@999999  hi  @888888  @all  @inline-name"
    messages = queued.get_messages()
    assert [type(component).__name__ for component in messages] == [
        "At",
        "Plain",
        "At",
        "AtAll",
        "At",
    ]
    assert messages[0].name == ""
    assert messages[2].name == ""
    assert messages[4].name == "inline-name"
    adapter.client.get_group_member_info.assert_not_awaited()
    adapter.client.get_stranger_info.assert_not_awaited()


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_keeps_group_string_at_targets_from_raw_message_fallback():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()
    adapter.client.get_group_member_info = AsyncMock()
    adapter.client.get_stranger_info = AsyncMock()

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message",
          "message_type": "group",
          "sub_type": "normal",
          "time": 1720000000,
          "self_id": 123456,
          "group_id": 654321,
          "user_id": 111222,
          "message_id": 786,
          "message_seq": 786,
          "real_id": 786,
          "real_seq": "786",
          "font": 14,
          "message_format": "string",
          "raw_message": "[CQ:at,qq=999999] hello",
          "sender": {
            "user_id": 111222,
            "nickname": "tester",
            "role": "member"
          },
          "message": ""
        }
        """
    )

    queued = queue.get_nowait()
    assert queued.get_message_str() == "@999999  hello"
    messages = queued.get_messages()
    assert [type(component).__name__ for component in messages] == ["At", "Plain"]
    assert messages[0].name == ""
    adapter.client.get_group_member_info.assert_not_awaited()
    adapter.client.get_stranger_info.assert_not_awaited()


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_parses_string_nonstandard_and_forward_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message",
          "message_type": "private",
          "sub_type": "friend",
          "time": 1720000000,
          "self_id": 123456,
          "user_id": 111222,
          "message_id": 786,
          "message_seq": 786,
          "real_id": 786,
          "real_seq": "786",
          "font": 14,
          "message_format": "string",
          "raw_message": "[CQ:mface,emoji_package_id=1152,emoji_id=987654321,key=market-face-key,summary=&#91;HappyFace&#93;][CQ:onlinefile,msgId=msg-1,elementId=element-1,fileName=demo.zip,fileSize=2048,isDir=false][CQ:flashtransfer,fileSetId=flash-set-1][CQ:forward,id=forward-1]",
          "sender": {
            "user_id": 111222,
            "nickname": "tester"
          },
          "message": "[CQ:mface,emoji_package_id=1152,emoji_id=987654321,key=market-face-key,summary=&#91;HappyFace&#93;][CQ:onlinefile,msgId=msg-1,elementId=element-1,fileName=demo.zip,fileSize=2048,isDir=false][CQ:flashtransfer,fileSetId=flash-set-1][CQ:forward,id=forward-1]"
        }
        """
    )

    queued = queue.get_nowait()
    assert queued.get_message_str() == ""
    assert [type(component).__name__ for component in queued.get_messages()] == [
        "MFace",
        "OnlineFile",
        "FlashTransfer",
        "Forward",
    ]
    assert queued.get_messages()[0].summary == "[HappyFace]"
    assert queued.get_messages()[1].file_name == "demo.zip"
    assert queued.get_messages()[1].is_dir is False
    assert queued.get_messages()[2].file_set_id == "flash-set-1"
    assert queued.get_messages()[3].id == "forward-1"


@pytest.mark.asyncio
async def test_napcat_unknown_string_segment_becomes_unknown_component():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message",
          "message_type": "private",
          "sub_type": "friend",
          "time": 1720000000,
          "self_id": 123456,
          "user_id": 111222,
          "message_id": 790,
          "font": 14,
          "message_format": "string",
          "raw_message": "[CQ:future_segment,value=mock]tail",
          "sender": {"user_id": 111222, "nickname": "tester"},
          "message": "[CQ:future_segment,value=mock]tail"
        }
        """
    )

    queued = queue.get_nowait()
    assert queued.get_message_str() == (
        "[Unsupported NapCat segment: future_segment]tail"
    )
    assert isinstance(queued.get_messages()[0], Unknown)
    assert queued.get_messages()[0].segment_type == "future_segment"
    assert isinstance(queued.get_messages()[1], Plain)


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_parses_string_file_like_and_rich_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message",
          "message_type": "private",
          "sub_type": "friend",
          "time": 1720000000,
          "self_id": 123456,
          "user_id": 111222,
          "message_id": 787,
          "message_seq": 787,
          "real_id": 787,
          "real_seq": "787",
          "font": 14,
          "message_format": "string",
          "raw_message": "[CQ:image,file=napcat-image.png,url=https://example.com/napcat-image.png,sub_type=1][CQ:record,file=napcat-record.amr,path=C:/NapCat/cache/napcat-record.amr,url=file:///C:/NapCat/cache/napcat-record.amr][CQ:video,file=encoded-video-token,url=file:///C:/NapCat/cache/napcat-video.mp4][CQ:file,file=napcat-doc.zip,url=https://example.com/napcat-doc.zip][CQ:json,data={\\\"app\\\":\\\"demo\\\"}][CQ:xml,data=<msg serviceID='1'>demo</msg>]",
          "sender": {
            "user_id": 111222,
            "nickname": "tester"
          },
          "message": "[CQ:image,file=napcat-image.png,url=https://example.com/napcat-image.png,sub_type=1][CQ:record,file=napcat-record.amr,path=C:/NapCat/cache/napcat-record.amr,url=file:///C:/NapCat/cache/napcat-record.amr][CQ:video,file=encoded-video-token,url=file:///C:/NapCat/cache/napcat-video.mp4][CQ:file,file=napcat-doc.zip,url=https://example.com/napcat-doc.zip][CQ:json,data={\\\"app\\\":\\\"demo\\\"}][CQ:xml,data=<msg serviceID='1'>demo</msg>]"
        }
        """
    )

    queued = queue.get_nowait()
    assert queued.get_message_str() == ""
    assert [type(component).__name__ for component in queued.get_messages()] == [
        "Image",
        "Record",
        "Video",
        "File",
        "Json",
        "Xml",
    ]
    assert queued.get_messages()[0].file == "napcat-image.png"
    assert queued.get_messages()[0].url == "https://example.com/napcat-image.png"
    assert queued.get_messages()[0].sub_type == "1"
    assert queued.get_messages()[1].path == "C:/NapCat/cache/napcat-record.amr"
    assert queued.get_messages()[2].url == "file:///C:/NapCat/cache/napcat-video.mp4"
    assert queued.get_messages()[3].name == "napcat-doc.zip"
    assert queued.get_messages()[4].data == {"app": "demo"}
    assert queued.get_messages()[5].data == "<msg serviceID='1'>demo</msg>"


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_unescapes_commas_in_string_rich_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message",
          "message_type": "private",
          "sub_type": "friend",
          "time": 1720000000,
          "self_id": 123456,
          "user_id": 111222,
          "message_id": 788,
          "message_seq": 788,
          "real_id": 788,
          "real_seq": "788",
          "font": 14,
          "message_format": "string",
          "raw_message": "[CQ:json,data={\\\"app\\\":\\\"demo\\\"&#44;\\\"text\\\":\\\"hello&#44;world\\\"}][CQ:xml,data=<msg serviceID='1' brief='a&#44;b'>demo</msg>]",
          "sender": {
            "user_id": 111222,
            "nickname": "tester"
          },
          "message": "[CQ:json,data={\\\"app\\\":\\\"demo\\\"&#44;\\\"text\\\":\\\"hello&#44;world\\\"}][CQ:xml,data=<msg serviceID='1' brief='a&#44;b'>demo</msg>]"
        }
        """
    )

    queued = queue.get_nowait()
    assert [type(component).__name__ for component in queued.get_messages()] == [
        "Json",
        "Xml",
    ]
    assert queued.get_messages()[0].data == {"app": "demo", "text": "hello,world"}
    assert queued.get_messages()[1].data == "<msg serviceID='1' brief='a,b'>demo</msg>"


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_parses_string_misc_segments_including_custom_music():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message",
          "message_type": "private",
          "sub_type": "friend",
          "time": 1720000000,
          "self_id": 123456,
          "user_id": 111222,
          "message_id": 789,
          "message_seq": 789,
          "real_id": 789,
          "real_seq": "789",
          "font": 14,
          "message_format": "string",
          "raw_message": "[CQ:music,type=qq,id=12345][CQ:music,type=custom,url=https://example.com/song,image=https://example.com/cover.jpg,content=hello][CQ:contact,type=qq,id=10001][CQ:location,lat=30.123,lon=120.456,title=Hangzhou,content=West Lake][CQ:poke,type=2000,id=10001][CQ:dice][CQ:rps]",
          "sender": {
            "user_id": 111222,
            "nickname": "tester"
          },
          "message": "[CQ:music,type=qq,id=12345][CQ:music,type=custom,url=https://example.com/song,image=https://example.com/cover.jpg,content=hello][CQ:contact,type=qq,id=10001][CQ:location,lat=30.123,lon=120.456,title=Hangzhou,content=West Lake][CQ:poke,type=2000,id=10001][CQ:dice][CQ:rps]"
        }
        """
    )

    queued = queue.get_nowait()
    assert queued.get_message_str() == ""
    assert [type(component).__name__ for component in queued.get_messages()] == [
        "Music",
        "Music",
        "Contact",
        "Location",
        "Poke",
        "Dice",
        "RPS",
    ]
    assert queued.get_messages()[0].sub_type == "qq"
    assert queued.get_messages()[0].id == 12345
    assert queued.get_messages()[1].sub_type == "custom"
    assert queued.get_messages()[1].url == "https://example.com/song"
    assert queued.get_messages()[1].image == "https://example.com/cover.jpg"
    assert queued.get_messages()[1].audio is None
    assert queued.get_messages()[1].title is None
    assert queued.get_messages()[2].sub_type == "qq"
    assert queued.get_messages()[2].id == 10001
    assert queued.get_messages()[3].lat == 30.123
    assert queued.get_messages()[3].lon == 120.456
    assert queued.get_messages()[3].title == "Hangzhou"
    assert queued.get_messages()[3].content == "West Lake"
    assert str(queued.get_messages()[4].id) == "10001"
    assert queued.get_messages()[4].poke_type == "2000"


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_supports_nonstandard_live_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    await adapter.client._handle_ws_payload(
        """
        {
          "post_type": "message",
          "message_type": "private",
          "sub_type": "friend",
          "time": 1720000000,
          "self_id": 123456,
          "user_id": 111222,
          "message_id": 783,
          "font": 14,
          "raw_message": "nonstandard payload",
          "sender": {
            "user_id": 111222,
            "nickname": "tester"
          },
          "message": [
            {
              "type": "mface",
              "data": {
                "emoji_package_id": 1152,
                "emoji_id": "987654321",
                "key": "market-face-key",
                "summary": "[HappyFace]"
              }
            },
            {
              "type": "markdown",
              "data": {
                "content": "# Demo"
              }
            },
            {
              "type": "miniapp",
              "data": {
                "data": "{\\\"app\\\":\\\"demo\\\"}"
              }
            },
            {
              "type": "onlinefile",
              "data": {
                "msgId": "msg-1",
                "elementId": "element-1",
                "fileName": "demo.zip",
                "fileSize": "2048",
                "isDir": false
              }
            },
            {
              "type": "flashtransfer",
              "data": {
                "fileSetId": "flash-set-1"
              }
            }
          ]
        }
        """
    )

    queued = queue.get_nowait()
    assert queued.get_message_str() == ""
    assert [type(component).__name__ for component in queued.get_messages()] == [
        "MFace",
        "Markdown",
        "MiniApp",
        "OnlineFile",
        "FlashTransfer",
    ]
    assert queued.get_messages()[0].summary == "[HappyFace]"
    assert queued.get_messages()[1].content == "# Demo"
    assert queued.get_messages()[2].data == '{"app":"demo"}'
    assert queued.get_messages()[3].file_name == "demo.zip"
    assert queued.get_messages()[4].file_set_id == "flash-set-1"


@pytest.mark.asyncio
async def test_napcat_group_message_event_is_queued_with_expected_components():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock(
        return_value=NapCatFetchedMessage(
            message_id=9001,
            sender_id=333444,
            sender_nickname="quoted-user",
            time=1719999999,
            message_str="quoted text",
            raw_message="quoted text",
            message_payload=[
                {"type": "text", "data": {"text": "quoted text"}},
                {
                    "type": "image",
                    "data": {
                        "file": "https://example.com/quoted.jpg",
                        "url": "https://example.com/quoted.jpg",
                    },
                },
            ],
        )
    )
    adapter.client.delete_message = AsyncMock()
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 777,
            "font": 14,
            "raw_message": "@bot hello",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "admin",
            },
            "message": [
                {"type": "at", "data": {"qq": "123456", "name": "bot"}},
                {"type": "text", "data": {"text": " hello"}},
                {
                    "type": "image",
                    "data": {
                        "file": "https://example.com/a.jpg",
                        "url": "https://example.com/a.jpg",
                    },
                },
                {"type": "reply", "data": {"id": "9001"}},
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_str() == "hello"
    assert queued.platform_member_role == "admin"
    assert queued.get_message_type() == MessageType.GROUP_MESSAGE
    assert queued.session.session_id == "654321"
    assert [type(component).__name__ for component in queued.get_messages()] == [
        "At",
        "Plain",
        "Image",
        "Reply",
    ]
    reply = queued.get_messages()[-1]
    assert reply.id == "9001"
    assert reply.sender_id == 0
    assert reply.sender_nickname == ""
    assert reply.message_str == ""
    assert not reply.chain
    adapter.client.get_message.assert_not_awaited()
    await queued.delete()
    adapter.client.delete_message.assert_awaited_once_with("777")


@pytest.mark.asyncio
async def test_napcat_group_message_reply_accepts_string_quoted_payload():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 778,
            "font": 14,
            "raw_message": "hello [CQ:reply,id=9003]",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "member",
            },
            "message": [
                {"type": "text", "data": {"text": "hello"}},
                {"type": "reply", "data": {"id": "9003"}},
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    reply = queued.get_messages()[-1]
    assert reply.id == "9003"
    assert reply.sender_id == 0
    assert reply.sender_nickname == ""
    assert reply.message_str == ""
    assert not reply.chain
    adapter.client.get_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_napcat_group_message_reply_prefers_decoded_text_for_array_payload():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 779,
            "font": 14,
            "raw_message": "hello [CQ:reply,id=9004]",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "member",
            },
            "message": [
                {"type": "text", "data": {"text": "hello"}},
                {"type": "reply", "data": {"id": "9004"}},
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    reply = queued.get_messages()[-1]
    assert reply.id == "9004"
    assert reply.message_str == ""
    assert not reply.chain
    adapter.client.get_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_napcat_group_message_reply_uses_decoded_text_for_runtime_string_payload():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 779,
            "font": 14,
            "raw_message": "hello [CQ:reply,id=9005]",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "member",
            },
            "message": [
                {"type": "text", "data": {"text": "hello"}},
                {"type": "reply", "data": {"id": "9005"}},
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    reply = queued.get_messages()[-1]
    assert reply.id == "9005"
    assert reply.message_str == ""
    assert not reply.chain
    adapter.client.get_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_napcat_group_message_reply_keeps_missing_at_targets_without_group_lookup():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_group_member_info = AsyncMock()
    adapter.client.get_stranger_info = AsyncMock()
    adapter.client.get_message = AsyncMock()
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 779,
            "font": 14,
            "raw_message": "hello [CQ:reply,id=9005]",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "member",
            },
            "message": [
                {"type": "text", "data": {"text": "hello"}},
                {"type": "reply", "data": {"id": "9005"}},
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    reply = queued.get_messages()[-1]
    assert reply.id == "9005"
    assert reply.message_str == ""
    assert not reply.chain
    adapter.client.get_group_member_info.assert_not_awaited()
    adapter.client.get_stranger_info.assert_not_awaited()
    adapter.client.get_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_napcat_group_message_reply_keeps_nontext_runtime_string_payload_empty():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 780,
            "font": 14,
            "raw_message": "hello [CQ:reply,id=9006]",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "member",
            },
            "message": [
                {"type": "text", "data": {"text": "hello"}},
                {"type": "reply", "data": {"id": "9006"}},
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    reply = queued.get_messages()[-1]
    assert reply.id == "9006"
    assert reply.message_str == ""
    assert not reply.chain
    adapter.client.get_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_napcat_group_message_event_logs_inbound_summary(caplog):
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "private",
            "sub_type": "friend",
            "time": 1720000000,
            "self_id": 123456,
            "user_id": 111222,
            "message_id": 778,
            "font": 14,
            "raw_message": "/sid",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
            },
            "message": [
                {"type": "text", "data": {"text": "/sid"}},
            ],
        }
    )

    with caplog.at_level("INFO"):
        await adapter.handle_forward_ws_event(event)

    assert any(
        "[NapCat] Received private message:" in message and "outline=/sid" in message
        for message in caplog.messages
    )


@pytest.mark.asyncio
async def test_napcat_group_message_at_segment_keeps_targets_without_client_lookup():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()
    adapter.client.get_group_member_info = AsyncMock()
    adapter.client.get_stranger_info = AsyncMock()
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 778,
            "font": 14,
            "raw_message": "@member @stranger hello",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "member",
            },
            "message": [
                {"type": "at", "data": {"qq": "999999"}},
                {"type": "text", "data": {"text": " hi "}},
                {"type": "at", "data": {"qq": "888888"}},
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_str() == "@999999  hi  @888888"
    messages = queued.get_messages()
    assert messages[0].name == ""
    assert messages[2].name == ""
    adapter.client.get_group_member_info.assert_not_awaited()
    adapter.client.get_stranger_info.assert_not_awaited()


@pytest.mark.asyncio
async def test_napcat_group_message_event_supports_dice_rps_and_shake_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 779,
            "font": 14,
            "raw_message": "",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "member",
            },
            "message": [
                {"type": "dice"},
                {"type": "rps"},
                {"type": "shake", "data": {}},
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_str() == ""
    assert [type(component).__name__ for component in queued.get_messages()] == [
        "Dice",
        "RPS",
        "Shake",
    ]


@pytest.mark.asyncio
async def test_napcat_group_message_event_supports_anonymous_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 7791,
            "font": 14,
            "raw_message": "",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "member",
            },
            "message": [
                {"type": "anonymous", "data": {"ignore": 1}},
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_str() == ""
    assert len(queued.get_messages()) == 1
    assert isinstance(queued.get_messages()[0], Anonymous)
    assert queued.get_messages()[0].ignore == 1


@pytest.mark.asyncio
async def test_napcat_group_message_event_supports_xml_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 780,
            "font": 14,
            "raw_message": "",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "member",
            },
            "message": [
                {"type": "xml", "data": {"data": "<msg serviceID='1'>demo</msg>"}},
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_str() == ""
    assert len(queued.get_messages()) == 1
    assert isinstance(queued.get_messages()[0], Xml)
    assert queued.get_messages()[0].data == "<msg serviceID='1'>demo</msg>"


@pytest.mark.asyncio
async def test_napcat_group_message_event_supports_custom_node_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 781,
            "font": 14,
            "raw_message": "",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "member",
            },
            "message": [
                {
                    "type": "node",
                    "data": {
                        "user_id": "10001",
                        "nickname": "forwarded-user",
                        "content": [
                            {"type": "text", "data": {"text": "nested text"}},
                            {"type": "face", "data": {"id": "123"}},
                        ],
                        "summary": "forward summary",
                    },
                }
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_str() == "nested text"
    assert len(queued.get_messages()) == 1
    assert isinstance(queued.get_messages()[0], Node)
    assert queued.get_messages()[0].uin == "10001"
    assert queued.get_messages()[0].name == "forwarded-user"
    assert [
        type(component).__name__ for component in queued.get_messages()[0].content
    ] == [
        "Plain",
        "Face",
    ]


@pytest.mark.asyncio
async def test_napcat_custom_node_recursively_preserves_reply_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 782,
            "font": 14,
            "raw_message": "",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "role": "member",
            },
            "message": [
                {
                    "type": "node",
                    "data": {
                        "user_id": "10001",
                        "nickname": "Mock Node Sender",
                        "source": "Mock Source",
                        "summary": "Mock Summary",
                        "prompt": "Mock Prompt",
                        "news": [{"text": "Mock Preview"}],
                        "time": "1720000001",
                        "content": [
                            {"type": "reply", "data": {"id": "9001"}},
                            {"type": "text", "data": {"text": "nested"}},
                        ],
                    },
                }
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    node = queue.get_nowait().get_messages()[0]
    assert isinstance(node, Node)
    assert isinstance(node.content[0], Reply)
    assert node.content[0].id == "9001"
    assert node.source == "Mock Source"
    assert node.summary == "Mock Summary"
    assert node.prompt == "Mock Prompt"
    assert node.news == [{"text": "Mock Preview"}]
    assert node.time == 1720000001


@pytest.mark.asyncio
async def test_napcat_embedded_forward_content_becomes_structured_nodes():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 783,
            "font": 14,
            "raw_message": "[CQ:forward,id=9000000000000000001]",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "role": "member",
            },
            "message": [
                {
                    "type": "forward",
                    "data": {
                        "id": "9000000000000000001",
                        "content": [
                            {
                                "user_id": 10001,
                                "sender": {
                                    "user_id": 10001,
                                    "nickname": "Mock Forward Sender",
                                },
                                "message": [
                                    {
                                        "type": "text",
                                        "data": {"text": "forwarded text"},
                                    },
                                    {"type": "reply", "data": {"id": "9002"}},
                                ],
                            }
                        ],
                    },
                }
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    forward = queue.get_nowait().get_messages()[0]
    assert isinstance(forward, Forward)
    assert forward.id == "9000000000000000001"
    assert forward.content
    assert isinstance(forward.content[0], Node)
    assert forward.content[0].name == "Mock Forward Sender"
    assert isinstance(forward.content[0].content[1], Reply)


@pytest.mark.asyncio
async def test_napcat_forward_ws_group_message_accepts_real_image_payload():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 781,
            "font": 14,
            "raw_message": "",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "member",
            },
            "message": [
                {
                    "type": "image",
                    "data": {
                        "file": "napcat-image.png",
                        "url": "https://example.com/napcat-image.png",
                        "summary": "[Image]",
                        "sub_type": 1,
                        "file_size": 2048,
                    },
                }
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_str() == ""
    assert len(queued.get_messages()) == 1
    assert isinstance(queued.get_messages()[0], Image)
    assert queued.get_messages()[0].file == "napcat-image.png"
    assert queued.get_messages()[0].url == "https://example.com/napcat-image.png"
    assert queued.get_messages()[0].sub_type == "1"


@pytest.mark.asyncio
async def test_napcat_forward_ws_group_message_accepts_real_file_like_payloads():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 782,
            "font": 14,
            "raw_message": "",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "member",
            },
            "message": [
                {
                    "type": "record",
                    "data": {
                        "file": "napcat-record.amr",
                        "path": "C:/NapCat/cache/napcat-record.amr",
                        "url": "file:///C:/NapCat/cache/napcat-record.amr",
                        "file_size": 1024,
                    },
                },
                {
                    "type": "video",
                    "data": {
                        "file": "encoded-video-token",
                        "url": "file:///C:/NapCat/cache/napcat-video.mp4",
                        "file_size": 4096,
                    },
                },
                {
                    "type": "file",
                    "data": {
                        "file": "napcat-doc.zip",
                        "file_id": "file-uuid-1",
                        "file_size": 8192,
                        "url": "https://example.com/napcat-doc.zip",
                    },
                },
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert [type(component).__name__ for component in queued.get_messages()] == [
        "Record",
        "Video",
        "File",
    ]
    assert queued.get_messages()[0].path == "C:/NapCat/cache/napcat-record.amr"
    assert queued.get_messages()[0].url == "file:///C:/NapCat/cache/napcat-record.amr"
    assert queued.get_messages()[1].url == "file:///C:/NapCat/cache/napcat-video.mp4"
    assert queued.get_messages()[2].name == "napcat-doc.zip"
    assert queued.get_messages()[2].url == "https://example.com/napcat-doc.zip"


@pytest.mark.asyncio
async def test_napcat_group_message_reply_preserves_nonstandard_quoted_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock()
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 782,
            "font": 14,
            "raw_message": "",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "member",
            },
            "message": [
                {"type": "reply", "data": {"id": "9002"}},
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    reply = queued.get_messages()[0]
    assert reply.id == "9002"
    assert not reply.chain
    adapter.client.get_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_napcat_forward_ws_bot_offline_notice_is_queued_as_friend_message():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "bot_offline",
            "time": 1720000000,
            "self_id": 123456,
            "user_id": 123456,
            "tag": "gateway_disconnect",
            "message": "socket closed by remote peer",
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_type() == MessageType.FRIEND_MESSAGE
    assert queued.session.session_id == "123456"
    assert (
        queued.get_message_str()
        == "[notice:bot_offline] user 123456 tag gateway_disconnect message socket closed by remote peer"
    )
    assert queued.get_extra("onebot_notice_type") == "bot_offline"
    assert queued.get_extra("napcat_tag") == "gateway_disconnect"
    assert queued.get_extra("napcat_notice_message") == "socket closed by remote peer"
    assert queued.get_extra("skip_private_wake") is True


@pytest.mark.asyncio
async def test_napcat_private_notice_events_do_not_auto_wake_pipeline(monkeypatch):
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "bot_offline",
            "time": 1720000000,
            "self_id": 123456,
            "user_id": 123456,
            "tag": "gateway_disconnect",
            "message": "socket closed by remote peer",
        }
    )

    await adapter.handle_forward_ws_event(event)
    queued = queue.get_nowait()

    stage = WakingCheckStage()
    catalogs = RuntimeCatalogs()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config={
                "wake_prefix": ["/"],
                "platform_settings": {
                    "no_permission_reply": True,
                    "friend_message_needs_wake_prefix": False,
                    "ignore_bot_self_message": False,
                    "ignore_at_all": False,
                    "unique_session": False,
                    "group_wake_policy": {
                        "mention_bot": True,
                        "reply_to_bot": True,
                    },
                },
                "plugin_set": ["*"],
            },
            astrbot_config_id="default",
            plugin_catalog=SimpleNamespace(
                get_command_catalog=lambda *_args: CommandCatalogStore(),
            ),
            preferences=SimpleNamespace(get_async=AsyncMock(return_value={})),
            handlers=catalogs.handlers,
            plugins=catalogs.plugins,
        )
    )

    await stage.process(queued)

    assert queued.is_private_chat() is True
    assert queued.is_at_or_wake_command is False
    assert queued.is_wake is False


@pytest.mark.asyncio
async def test_napcat_notice_poke_event_is_queued_as_group_message():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "notify",
            "sub_type": "poke",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "target_id": 123456,
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert (
        queued.get_message_str()
        == "[notice:notify:poke] user 111222 target 123456 group 654321"
    )
    assert queued.get_message_type() == MessageType.GROUP_MESSAGE
    assert queued.session.session_id == "654321"
    assert queued.get_extra("platform_event") == "napcat"
    assert queued.get_extra("onebot_post_type") == "notice"
    assert queued.get_extra("onebot_notice_type") == "notify"
    assert queued.get_extra("onebot_sub_type") == "poke"
    assert queued.get_extra("napcat_self_id") == 123456
    assert queued.get_extra("napcat_user_id") == 111222
    assert queued.get_extra("napcat_group_id") == 654321
    assert queued.get_extra("napcat_target_id") == 123456
    assert queued.get_extra("napcat_time") == 1720000000
    assert queued.is_notice_type("notify", sub_type="poke")
    assert queued.get_notify_info() == {
        "notice_type": "notify",
        "sub_type": "poke",
        "user_id": 111222,
        "group_id": 654321,
        "target_id": 123456,
    }
    assert (
        queued.get_extra("napcat_event").items()
        >= {
            "group_id": 654321,
            "notice_type": "notify",
            "post_type": "notice",
            "self_id": 123456,
            "sub_type": "poke",
            "target_id": 123456,
            "time": 1720000000,
            "user_id": 111222,
        }.items()
    )
    assert len(queued.get_messages()) == 1
    assert isinstance(queued.get_messages()[0], Poke)
    assert str(queued.get_messages()[0].id) == "123456"


@pytest.mark.asyncio
async def test_napcat_group_notice_keeps_group_session_when_unique_session_enabled(
    monkeypatch,
):
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "group_recall",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "operator_id": 333444,
            "message_id": 777888,
        }
    )

    await adapter.handle_forward_ws_event(event)
    queued = queue.get_nowait()

    stage = WakingCheckStage()
    catalogs = RuntimeCatalogs()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config={
                "wake_prefix": ["/"],
                "platform_settings": {
                    "no_permission_reply": True,
                    "friend_message_needs_wake_prefix": False,
                    "ignore_bot_self_message": False,
                    "ignore_at_all": False,
                    "unique_session": True,
                },
                "plugin_set": ["*"],
            },
            astrbot_config_id="default",
            plugin_catalog=SimpleNamespace(
                get_command_catalog=lambda *_args: CommandCatalogStore(),
            ),
            preferences=SimpleNamespace(get_async=AsyncMock(return_value={})),
            handlers=catalogs.handlers,
            plugins=catalogs.plugins,
        )
    )

    await stage.process(queued)

    assert queued.session.session_id == "654321"


@pytest.mark.asyncio
async def test_napcat_group_message_route_identity_keeps_original_group_target_after_unique_session(
    monkeypatch,
):
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    queued = _make_manual_event(
        adapter,
        sender_id="111222",
        message_type=MessageType.GROUP_MESSAGE,
        group_id="654321",
        message=[Plain("hello")],
    )
    queued.message_str = "hello"

    stage = WakingCheckStage()
    catalogs = RuntimeCatalogs()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config={
                "wake_prefix": ["/"],
                "platform_settings": {
                    "no_permission_reply": True,
                    "friend_message_needs_wake_prefix": False,
                    "ignore_bot_self_message": False,
                    "ignore_at_all": False,
                    "unique_session": True,
                },
                "plugin_set": ["*"],
            },
            astrbot_config_id="default",
            plugin_catalog=SimpleNamespace(
                get_command_catalog=lambda *_args: CommandCatalogStore(),
            ),
            preferences=SimpleNamespace(get_async=AsyncMock(return_value={})),
            handlers=catalogs.handlers,
            plugins=catalogs.plugins,
        )
    )

    assert queued.route_origin == "napcat-test:GroupMessage:654321"

    await stage.process(queued)

    assert queued.session.session_id == "111222_654321"
    assert queued.route_identity.target_id == "654321"
    assert queued.route_origin == "napcat-test:GroupMessage:654321"


@pytest.mark.asyncio
async def test_napcat_reply_only_wake_resolves_sender_lazily_in_waking_stage(
    monkeypatch,
):
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock(
        return_value=NapCatFetchedMessage(message_id=9001, sender_id=123456)
    )
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 781,
            "font": 14,
            "raw_message": "[CQ:reply,id=9001] hello",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "member",
            },
            "message": [
                {"type": "reply", "data": {"id": "9001"}},
                {"type": "text", "data": {"text": " hello"}},
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)
    queued = queue.get_nowait()
    reply = queued.get_messages()[0]
    assert reply.sender_id == 0
    adapter.client.get_message.assert_not_awaited()

    stage = WakingCheckStage()
    catalogs = RuntimeCatalogs()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config={
                "wake_prefix": ["/"],
                "platform_settings": {
                    "no_permission_reply": True,
                    "friend_message_needs_wake_prefix": False,
                    "ignore_bot_self_message": False,
                    "ignore_at_all": False,
                    "unique_session": False,
                    "group_wake_policy": {
                        "mention_bot": True,
                        "reply_to_bot": True,
                    },
                },
                "plugin_set": ["*"],
            },
            astrbot_config_id="default",
            plugin_catalog=SimpleNamespace(
                get_command_catalog=lambda *_args: CommandCatalogStore(),
            ),
            preferences=SimpleNamespace(get_async=AsyncMock(return_value={})),
            handlers=catalogs.handlers,
            plugins=catalogs.plugins,
        )
    )

    await stage.process(queued)

    assert queued.is_wake is True
    assert queued.is_at_or_wake_command is True
    assert reply.sender_id == "123456"
    adapter.client.get_message.assert_awaited_once_with("9001")


@pytest.mark.asyncio
async def test_napcat_event_send_uses_route_identity_after_unique_session_mutation():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.send_group_message = AsyncMock()
    event = _make_manual_event(
        adapter,
        sender_id="111222",
        message_type=MessageType.GROUP_MESSAGE,
        group_id="654321",
    )
    event.session_id = "111222_654321"

    await event.send(MessageChain([Plain("reply")]))

    adapter.client.send_group_message.assert_awaited_once()
    call = adapter.client.send_group_message.await_args.kwargs
    assert call["group_id"] == "654321"
    assert event.route_identity.target_id == "654321"
    assert event.session.session_id == "111222_654321"


@pytest.mark.asyncio
async def test_napcat_forward_ws_accepts_private_poke_payload_with_sender_id_and_raw_info():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "notify",
            "sub_type": "poke",
            "time": 1720000000,
            "self_id": 123456,
            "user_id": 445566,
            "sender_id": 123456,
            "target_id": 445566,
            "raw_info": [{"uid": "u_1"}, {"uid": "u_2"}],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_type() == MessageType.FRIEND_MESSAGE
    assert queued.get_sender_id() == "123456"
    assert queued.session.session_id == "445566"
    assert queued.get_extra("napcat_sender_id") == 123456
    assert queued.get_notify_info() == {
        "notice_type": "notify",
        "sub_type": "poke",
        "user_id": 445566,
        "sender_id": 123456,
        "target_id": 445566,
    }
    assert (
        queued.get_extra("napcat_event").items()
        >= {
            "notice_type": "notify",
            "post_type": "notice",
            "raw_info": [{"uid": "u_1"}, {"uid": "u_2"}],
            "self_id": 123456,
            "sender_id": 123456,
            "sub_type": "poke",
            "target_id": 445566,
            "time": 1720000000,
            "user_id": 445566,
        }.items()
    )


@pytest.mark.asyncio
async def test_napcat_forward_ws_ignores_ephemeral_input_status_notice():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "notify",
            "sub_type": "input_status",
            "time": 1720000000,
            "self_id": 123456,
            "user_id": 3013138453,
            "group_id": 0,
            "event_type": 1,
            "status_text": "对方正在输入...",
        }
    )

    await adapter.handle_forward_ws_event(event)

    assert queue.empty()


@pytest.mark.asyncio
async def test_napcat_private_event_typing_helpers_use_input_status():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.set_input_status = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    event = _make_manual_event(adapter, sender_id="445566")

    await event.send_typing()
    adapter.client.set_input_status.assert_awaited_once_with(
        user_id="445566",
        event_type=1,
    )

    adapter.client.set_input_status.reset_mock()
    await event.stop_typing()
    adapter.client.set_input_status.assert_awaited_once_with(
        user_id="445566",
        event_type=2,
    )


@pytest.mark.asyncio
async def test_napcat_group_event_typing_helpers_are_noops():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.set_input_status = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    event = _make_manual_event(
        adapter,
        sender_id="445566",
        message_type=MessageType.GROUP_MESSAGE,
        group_id="654321",
    )

    await event.send_typing()
    await event.stop_typing()

    adapter.client.set_input_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_group_history_fetches_recent_messages():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.call_action = AsyncMock(
        side_effect=[
            {
                "status": "ok",
                "retcode": 0,
                "messages": [
                    {"message_id": 100, "raw_message": "m100"},
                    {"message_id": 101, "raw_message": "m101"},
                ],
            },
            {
                "status": "ok",
                "retcode": 0,
                "messages": [
                    {"message_id": 101, "raw_message": "m101"},
                ],
            },
            {
                "status": "ok",
                "retcode": 0,
                "messages": [
                    {"message_id": 99, "raw_message": "m99"},
                    {"message_id": 98, "raw_message": "m98"},
                    {"message_id": 100, "raw_message": "m100"},
                ],
            },
        ]
    )

    history = await adapter.client.get_group_msg_history(group_id="654321", count=4)

    assert [item["message_id"] for item in history] == [98, 99, 100, 101]
    assert adapter.client.call_action.await_count == 3


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_friend_history_honors_explicit_message_seq():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.call_action = AsyncMock(
        return_value={
            "status": "ok",
            "retcode": 0,
            "messages": [
                {"message_id": 501, "raw_message": "m501"},
                {"message_id": 502, "raw_message": "m502"},
            ],
        }
    )

    history = await adapter.client.get_friend_msg_history(
        user_id="445566",
        count=2,
        message_seq=500,
    )

    assert [item["message_id"] for item in history] == [501, 502]
    adapter.client.call_action.assert_awaited_once()


@pytest.mark.asyncio
async def test_napcat_forward_ws_client_ai_actions_match_napcat_payload_schema():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.call_action = AsyncMock(
        side_effect=[
            {
                "status": "ok",
                "retcode": 0,
                "data": [{"type": "default", "characters": []}],
            },
            {
                "status": "ok",
                "retcode": 0,
                "data": {"message_id": 0},
            },
        ]
    )

    characters = await adapter.client.get_ai_characters(group_id="654321", chat_type=2)
    assert characters == [{"type": "default", "characters": []}]

    await adapter.client.send_group_ai_record(
        group_id="654321",
        character="voice-1",
        text="你好",
        chat_type=2,
        timeout_seconds=30,
    )

    assert adapter.client.call_action.await_args_list[0].args == ("get_ai_characters",)
    assert adapter.client.call_action.await_args_list[0].kwargs == {
        "group_id": "654321",
        "chat_type": 2,
    }
    assert adapter.client.call_action.await_args_list[1].args == (
        "send_group_ai_record",
    )
    assert adapter.client.call_action.await_args_list[1].kwargs == {
        "group_id": "654321",
        "character": "voice-1",
        "text": "你好",
    }


@pytest.mark.asyncio
async def test_napcat_notify_group_name_event_is_queued_with_notify_info():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "notify",
            "sub_type": "group_name",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "name_new": "NapCat New Name",
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert (
        queued.get_message_str()
        == "[notice:notify:group_name] user 111222 group 654321 name NapCat New Name"
    )
    assert queued.get_message_type() == MessageType.GROUP_MESSAGE
    assert queued.session.session_id == "654321"
    assert queued.get_notify_info() == {
        "notice_type": "notify",
        "sub_type": "group_name",
        "user_id": 111222,
        "group_id": 654321,
        "name_new": "NapCat New Name",
    }


@pytest.mark.asyncio
async def test_napcat_notify_profile_like_event_is_queued_with_notify_info():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "notify",
            "sub_type": "profile_like",
            "time": 1720000000,
            "self_id": 123456,
            "operator_id": 111222,
            "operator_nick": "tester",
            "times": 3,
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_type() == MessageType.FRIEND_MESSAGE
    assert queued.get_sender_id() == "111222"
    assert queued.session.session_id == "111222"
    assert (
        queued.get_message_str()
        == "[notice:notify:profile_like] operator 111222 operator_nick tester times 3"
    )
    assert queued.get_notify_info() == {
        "notice_type": "notify",
        "sub_type": "profile_like",
        "operator_id": 111222,
        "operator_nick": "tester",
        "times": 3,
    }


@pytest.mark.asyncio
async def test_napcat_notify_group_title_event_is_queued_with_notify_info():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "notify",
            "sub_type": "title",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "title": "NapCat Title",
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_type() == MessageType.GROUP_MESSAGE
    assert queued.session.session_id == "654321"
    assert (
        queued.get_message_str()
        == "[notice:notify:title] user 111222 group 654321 title NapCat Title"
    )
    assert queued.get_notify_info() == {
        "notice_type": "notify",
        "sub_type": "title",
        "user_id": 111222,
        "group_id": 654321,
        "title": "NapCat Title",
    }


@pytest.mark.asyncio
async def test_napcat_notify_gray_tip_event_is_queued_with_notify_info():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "notify",
            "sub_type": "gray_tip",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 777888,
            "busi_id": "tip-1",
            "content": "gray tip content",
            "raw_info": {"kind": "gray-tip"},
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_type() == MessageType.GROUP_MESSAGE
    assert queued.session.session_id == "654321"
    assert (
        queued.get_message_str()
        == "[notice:notify:gray_tip] user 111222 message 777888 group 654321 busi tip-1 content gray tip content"
    )
    assert queued.get_notify_info() == {
        "notice_type": "notify",
        "sub_type": "gray_tip",
        "user_id": 111222,
        "group_id": 654321,
        "busi_id": "tip-1",
        "content": "gray tip content",
    }


@pytest.mark.asyncio
async def test_napcat_online_file_send_notice_uses_peer_id_for_friend_session():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "online_file_send",
            "sub_type": "receive",
            "time": 1720000000,
            "self_id": 123456,
            "peer_id": 445566,
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_type() == MessageType.FRIEND_MESSAGE
    assert queued.get_sender_id() == "445566"
    assert queued.session.session_id == "445566"
    assert queued.get_message_str() == "[notice:online_file_send:receive] peer 445566"
    assert queued.get_extra("napcat_peer_id") == 445566


@pytest.mark.asyncio
async def test_napcat_online_file_notice_actions_use_peer_id_without_sender_id():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_online_file_messages = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {"items": []}}
    )
    adapter.client.receive_online_file = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    event = _make_manual_event(
        adapter,
        sender_id="",
        message=[
            OnlineFile(
                msg_id="msg-1",
                element_id="element-1",
                file_name="demo.zip",
                file_size="1024",
                is_dir=False,
            )
        ],
    )
    event.set_extra("napcat_peer_id", "445566")

    await event.get_online_file_messages()
    adapter.client.get_online_file_messages.assert_awaited_once_with(user_id="445566")

    await event.receive_online_file()
    adapter.client.receive_online_file.assert_awaited_once_with(
        user_id="445566",
        msg_id="msg-1",
        element_id="element-1",
    )


@pytest.mark.asyncio
async def test_napcat_group_recall_notice_exposes_recall_helper():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "group_recall",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "operator_id": 333444,
            "message_id": 777888,
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.is_notice_type("group_recall")
    assert queued.get_recall_info() == {
        "notice_type": "group_recall",
        "message_id": 777888,
        "user_id": 111222,
        "group_id": 654321,
        "operator_id": 333444,
    }


@pytest.mark.asyncio
async def test_napcat_group_upload_notice_exposes_upload_helper():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "group_upload",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "file": {
                "id": "file-id",
                "name": "demo.zip",
                "size": 2048,
                "busid": 102,
            },
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.is_notice_type("group_upload")
    assert queued.get_message_str() == (
        "[notice:group_upload] user 111222 group 654321 file demo.zip "
        "file_id file-id file_size 2048 busid 102"
    )
    assert queued.get_upload_info() == {
        "notice_type": "group_upload",
        "group_id": 654321,
        "user_id": 111222,
        "file": {
            "id": "file-id",
            "name": "demo.zip",
            "size": 2048,
            "busid": 102,
        },
    }


@pytest.mark.asyncio
async def test_napcat_group_request_accepts_nonstandard_sub_type_strings():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "request",
            "request_type": "group",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "sub_type": "join_request",
            "comment": "please approve",
            "flag": "flag-1",
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_request_info() == {
        "request_type": "group",
        "sub_type": "join_request",
        "user_id": 111222,
        "flag": "flag-1",
        "comment": "please approve",
        "group_id": 654321,
    }


@pytest.mark.asyncio
async def test_napcat_group_reaction_notice_exposes_reaction_helper():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "group_msg_emoji_like",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 777,
            "is_add": True,
            "likes": [
                {"emoji_id": 128077, "count": 2},
                {"emoji_id": 128293, "count": 1},
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_str() == (
        "[notice:group_msg_emoji_like] user 111222 message 777 group 654321 "
        "likes 128077=2,128293=1 action add"
    )
    assert queued.get_reaction_info() == {
        "notice_type": "group_msg_emoji_like",
        "group_id": 654321,
        "message_id": 777,
        "user_id": 111222,
        "is_add": True,
        "likes": [
            {"emoji_id": 128077, "count": 2},
            {"emoji_id": 128293, "count": 1},
        ],
    }


@pytest.mark.asyncio
async def test_napcat_lagrange_reaction_notice_exposes_reaction_helper():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "reaction",
            "sub_type": "add",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "operator_id": 111222,
            "message_id": 777,
            "code": "128077",
            "count": 3,
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_reaction_info() == {
        "notice_type": "reaction",
        "group_id": 654321,
        "message_id": 777,
        "operator_id": 111222,
        "code": "128077",
        "count": 3,
        "sub_type": "add",
    }


@pytest.mark.asyncio
async def test_napcat_group_admin_notice_exposes_helper():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "group_admin",
            "sub_type": "set",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.is_notice_type("group_admin", sub_type="set")
    assert queued.get_group_admin_info() == {
        "notice_type": "group_admin",
        "sub_type": "set",
        "group_id": 654321,
        "user_id": 111222,
    }


@pytest.mark.asyncio
async def test_napcat_group_ban_notice_exposes_helper():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "group_ban",
            "sub_type": "ban",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "operator_id": 333444,
            "duration": 600,
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.is_notice_type("group_ban", sub_type="ban")
    assert queued.get_group_ban_info() == {
        "notice_type": "group_ban",
        "sub_type": "ban",
        "group_id": 654321,
        "user_id": 111222,
        "operator_id": 333444,
        "duration": 600,
    }


@pytest.mark.asyncio
async def test_napcat_group_card_notice_exposes_helper():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "group_card",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "card_old": "old-card",
            "card_new": "new-card",
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.is_notice_type("group_card")
    assert queued.get_group_card_info() == {
        "notice_type": "group_card",
        "group_id": 654321,
        "user_id": 111222,
        "card_old": "old-card",
        "card_new": "new-card",
    }


@pytest.mark.asyncio
async def test_napcat_group_increase_notice_exposes_helper():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "group_increase",
            "sub_type": "invite",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "operator_id": 333444,
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.is_notice_type("group_increase", sub_type="invite")
    assert queued.get_group_increase_info() == {
        "notice_type": "group_increase",
        "sub_type": "invite",
        "group_id": 654321,
        "user_id": 111222,
        "operator_id": 333444,
    }


@pytest.mark.asyncio
async def test_napcat_group_decrease_notice_exposes_helper():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "group_decrease",
            "sub_type": "kick",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "operator_id": 333444,
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.is_notice_type("group_decrease", sub_type="kick")
    assert queued.get_group_decrease_info() == {
        "notice_type": "group_decrease",
        "sub_type": "kick",
        "group_id": 654321,
        "user_id": 111222,
        "operator_id": 333444,
    }


@pytest.mark.asyncio
async def test_napcat_group_essence_notice_exposes_helper():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = OB11AllEvent.model_validate(
        {
            "post_type": "notice",
            "notice_type": "essence",
            "sub_type": "add",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "message_id": 777888,
            "operator_id": 333444,
            "sender_id": 111222,
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.is_notice_type("essence", sub_type="add")
    assert queued.get_group_essence_info() == {
        "notice_type": "essence",
        "sub_type": "add",
        "group_id": 654321,
        "message_id": 777888,
        "operator_id": 333444,
        "sender_id": 111222,
    }


@pytest.mark.asyncio
async def test_napcat_group_request_event_is_queued_with_group_session():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.set_group_add_request = AsyncMock()
    event = OB11AllEvent.model_validate(
        {
            "post_type": "request",
            "request_type": "group",
            "sub_type": "add",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "comment": "let me in",
            "flag": "request-flag",
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert (
        queued.get_message_str()
        == "[request:group:add] user 111222 group 654321 comment let me in "
        "flag request-flag"
    )
    assert queued.get_message_type() == MessageType.GROUP_MESSAGE
    assert queued.session.session_id == "654321"
    assert queued.get_sender_id() == "111222"
    assert queued.get_extra("onebot_post_type") == "request"
    assert queued.get_extra("onebot_request_type") == "group"
    assert queued.get_extra("onebot_sub_type") == "add"
    assert queued.get_extra("napcat_self_id") == 123456
    assert queued.get_extra("napcat_user_id") == 111222
    assert queued.get_extra("napcat_group_id") == 654321
    assert queued.get_extra("napcat_comment") == "let me in"
    assert queued.get_extra("napcat_flag") == "request-flag"
    assert queued.get_extra("napcat_time") == 1720000000
    assert queued.get_request_info() == {
        "request_type": "group",
        "sub_type": "add",
        "user_id": 111222,
        "flag": "request-flag",
        "comment": "let me in",
        "group_id": 654321,
    }
    assert queued.get_extra("napcat_event") == {
        "comment": "let me in",
        "flag": "request-flag",
        "group_id": 654321,
        "post_type": "request",
        "request_type": "group",
        "self_id": 123456,
        "sub_type": "add",
        "time": 1720000000,
        "user_id": 111222,
    }
    assert queued.get_messages() == []
    await queued.approve_request()
    adapter.client.set_group_add_request.assert_awaited_with(
        flag="request-flag",
        approve=True,
        reason=None,
    )
    await queued.reject_request(reason="denied")
    adapter.client.set_group_add_request.assert_awaited_with(
        flag="request-flag",
        approve=False,
        reason="denied",
    )


@pytest.mark.asyncio
async def test_napcat_friend_request_event_can_be_approved_or_rejected():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.set_friend_add_request = AsyncMock()
    event = OB11AllEvent.model_validate(
        {
            "post_type": "request",
            "request_type": "friend",
            "time": 1720000000,
            "self_id": 123456,
            "user_id": 111222,
            "comment": "hello",
            "flag": "friend-request-flag",
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    assert queued.get_message_type() == MessageType.FRIEND_MESSAGE
    assert queued.get_message_str() == (
        "[request:friend] user 111222 comment hello flag friend-request-flag"
    )
    assert queued.get_request_info() == {
        "request_type": "friend",
        "user_id": 111222,
        "flag": "friend-request-flag",
        "comment": "hello",
    }
    await queued.approve_request(remark="new-friend")
    adapter.client.set_friend_add_request.assert_awaited_with(
        flag="friend-request-flag",
        approve=True,
        remark="new-friend",
    )
    await queued.reject_request()
    adapter.client.set_friend_add_request.assert_awaited_with(
        flag="friend-request-flag",
        approve=False,
        remark=None,
    )


@pytest.mark.asyncio
async def test_napcat_outbound_builder_supports_record_video_and_file_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    payload = await adapter._build_outbound_message(
        MessageChain(
            [
                Record(file="https://example.com/demo.wav"),
                Video(file="https://example.com/demo.mp4", cover="thumb://cover"),
                File(name="demo.txt", url="https://example.com/demo.txt"),
            ]
        )
    )

    assert isinstance(payload, list)
    assert [segment.to_dict()["type"] for segment in payload] == [
        "record",
        "video",
        "file",
    ]
    assert payload[0].to_dict()["data"]["file"] == "https://example.com/demo.wav"
    assert payload[1].to_dict()["data"]["thumb"] == "thumb://cover"
    assert payload[2].to_dict()["data"]["name"] == "demo.txt"


@pytest.mark.asyncio
async def test_napcat_outbound_builder_supports_face_contact_location_poke_and_json():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    payload = await adapter._build_outbound_message(
        MessageChain(
            [
                Face(id=123),
                Contact(_type="qq", id=456789),
                Location(
                    lat=31.2304,
                    lon=121.4737,
                    title="Shanghai",
                    content="The Bund",
                ),
                Poke(id=10001, poke_type="2000"),
                Json(data={"app": "com.tencent.test", "desc": "demo"}),
            ]
        )
    )

    assert isinstance(payload, list)
    assert [segment.to_dict()["type"] for segment in payload] == [
        "face",
        "contact",
        "location",
        "poke",
        "json",
    ]
    assert payload[0].to_dict()["data"]["id"] == "123"
    assert payload[1].to_dict()["data"] == {"type": "qq", "id": "456789"}
    assert payload[2].to_dict()["data"]["title"] == "Shanghai"
    assert payload[3].to_dict()["data"] == {"type": "2000", "id": "10001"}
    assert payload[4].to_dict()["data"]["data"] == {
        "app": "com.tencent.test",
        "desc": "demo",
    }


@pytest.mark.asyncio
async def test_napcat_outbound_builder_supports_mface_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    payload = await adapter._build_outbound_message(
        MessageChain(
            [
                MFace(
                    emoji_package_id=1152,
                    emoji_id="987654321",
                    key="market-face-key",
                    summary="[HappyFace]",
                )
            ]
        )
    )

    assert isinstance(payload, list)
    assert len(payload) == 1
    assert payload[0].to_dict() == {
        "type": "mface",
        "data": {
            "emoji_package_id": 1152.0,
            "emoji_id": "987654321",
            "key": "market-face-key",
            "summary": "[HappyFace]",
        },
    }


@pytest.mark.asyncio
async def test_napcat_outbound_builder_supports_id_and_custom_music():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    payload = await adapter._build_outbound_message(
        MessageChain(
            [
                Music(_type="qq", id=12345),
                Music(
                    _type="custom",
                    url="https://example.com/page",
                    audio="https://example.com/audio.mp3",
                    title="Custom Song",
                    image="https://example.com/cover.jpg",
                    content="Custom intro",
                ),
            ]
        )
    )

    assert isinstance(payload, list)
    assert [segment.to_dict()["type"] for segment in payload] == ["music", "music"]
    assert payload[0].to_dict()["data"] == {"type": "qq", "id": "12345"}
    assert payload[1].to_dict()["data"] == {
        "type": "custom",
        "id": None,
        "url": "https://example.com/page",
        "image": "https://example.com/cover.jpg",
        "audio": "https://example.com/audio.mp3",
        "title": "Custom Song",
        "content": "Custom intro",
    }


@pytest.mark.asyncio
async def test_napcat_outbound_builder_supports_share_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    payload = await adapter._build_outbound_message(
        MessageChain(
            [
                Share(
                    url="https://example.com/article",
                    title="Example Article",
                    content="A short summary",
                    image="https://example.com/cover.png",
                )
            ]
        )
    )

    assert isinstance(payload, list)
    assert len(payload) == 1
    assert payload[0].to_dict() == {
        "type": "share",
        "data": {
            "url": "https://example.com/article",
            "title": "Example Article",
            "content": "A short summary",
            "image": "https://example.com/cover.png",
        },
    }


@pytest.mark.asyncio
async def test_napcat_outbound_builder_supports_dice_rps_and_shake():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    payload = await adapter._build_outbound_message(
        MessageChain([Dice(), RPS(), Shake()])
    )

    assert isinstance(payload, list)
    assert [segment.to_dict() for segment in payload] == [
        {"type": "dice", "data": {}},
        {"type": "rps", "data": {}},
        {"type": "shake", "data": {}},
    ]


@pytest.mark.asyncio
async def test_napcat_outbound_builder_supports_xml_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    payload = await adapter._build_outbound_message(
        MessageChain([Xml(data="<msg template='123'>demo</msg>")])
    )

    assert isinstance(payload, list)
    assert len(payload) == 1
    assert payload[0].to_dict() == {
        "type": "xml",
        "data": {"data": "<msg template='123'>demo</msg>"},
    }


@pytest.mark.asyncio
async def test_napcat_outbound_builder_supports_markdown_and_miniapp_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    payload = await adapter._build_outbound_message(
        MessageChain(
            [
                Markdown(content="# Demo\ncontent"),
                MiniApp(data='{"app":"demo","page":"/index"}'),
            ]
        )
    )

    assert isinstance(payload, list)
    assert [segment.to_dict()["type"] for segment in payload] == [
        "markdown",
        "miniapp",
    ]
    assert payload[0].to_dict()["data"] == {"content": "# Demo\ncontent"}
    assert payload[1].to_dict()["data"] == {"data": '{"app":"demo","page":"/index"}'}


@pytest.mark.asyncio
async def test_napcat_outbound_builder_supports_onlinefile_and_flashtransfer():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    payload = await adapter._build_outbound_message(
        MessageChain(
            [
                OnlineFile(
                    msg_id="msg-1",
                    element_id="element-1",
                    file_name="demo.zip",
                    file_size="1024",
                    is_dir=False,
                ),
                FlashTransfer(file_set_id="flash-set-1"),
            ]
        )
    )

    assert isinstance(payload, list)
    assert [segment.to_dict()["type"] for segment in payload] == [
        "onlinefile",
        "flashtransfer",
    ]
    assert payload[0].to_dict()["data"] == {
        "msgId": "msg-1",
        "elementId": "element-1",
        "fileName": "demo.zip",
        "fileSize": "1024",
        "isDir": False,
    }
    assert payload[1].to_dict()["data"] == {"fileSetId": "flash-set-1"}


@pytest.mark.asyncio
async def test_napcat_outbound_builder_supports_forward_segments():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    payload = await adapter._build_outbound_message(
        MessageChain([Forward(id="forward-res-id")])
    )

    assert isinstance(payload, list)
    assert len(payload) == 1
    assert payload[0].to_dict() == {
        "type": "forward",
        "data": {"id": "forward-res-id"},
    }


@pytest.mark.asyncio
async def test_napcat_send_by_session_supports_forward_nodes():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.send_group_message = AsyncMock()
    adapter.client.send_group_forward_message = AsyncMock()
    session = MessageSession(
        platform_name="napcat-test",
        message_type=MessageType.GROUP_MESSAGE,
        session_id="654321",
    )

    await adapter.send_by_session(
        session,
        MessageChain(
            [
                Plain("before"),
                Nodes(
                    [
                        Node(
                            uin="1001",
                            name="alice",
                            content=[Plain("first node")],
                        ),
                        Node(
                            uin="1002",
                            name="bob",
                            content=[Plain("second node")],
                        ),
                    ]
                ),
                Plain("after"),
            ]
        ),
    )

    assert adapter.client.send_group_message.await_count == 2
    first_standard = adapter.client.send_group_message.await_args_list[0].kwargs
    second_standard = adapter.client.send_group_message.await_args_list[1].kwargs
    assert first_standard["group_id"] == "654321"
    assert second_standard["group_id"] == "654321"
    assert [
        segment.to_dict()["data"]["text"] for segment in first_standard["message"]
    ] == ["before"]
    assert [
        segment.to_dict()["data"]["text"] for segment in second_standard["message"]
    ] == ["after"]

    adapter.client.send_group_forward_message.assert_awaited_once()
    forward_call = adapter.client.send_group_forward_message.await_args.kwargs
    assert forward_call["group_id"] == "654321"
    assert len(forward_call["messages"]) == 2
    assert forward_call["messages"][0]["type"] == "node"
    assert forward_call["messages"][0]["data"]["nickname"] == "alice"
    assert (
        forward_call["messages"][0]["data"]["content"][0]["data"]["text"]
        == "first node"
    )
    assert forward_call["messages"][1]["data"]["nickname"] == "bob"


@pytest.mark.asyncio
async def test_napcat_get_group_returns_group_details():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_message = AsyncMock(
        return_value=NapCatFetchedMessage(message_id=9001)
    )
    adapter.client.get_group_info = AsyncMock(
        return_value=SimpleNamespace(
            group_id=654321.0,
            group_name="NapCat Group",
        )
    )
    adapter.client.get_group_member_list = AsyncMock(
        return_value=[
            SimpleNamespace(
                user_id=1.0,
                nickname="owner-nick",
                card="owner-card",
                role="owner",
            ),
            SimpleNamespace(
                user_id=2.0,
                nickname="admin-nick",
                card="",
                role="admin",
            ),
            SimpleNamespace(
                user_id=3.0,
                nickname="member-nick",
                card="member-card",
                role="member",
            ),
        ]
    )
    event = OB11AllEvent.model_validate(
        {
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "time": 1720000000,
            "self_id": 123456,
            "group_id": 654321,
            "user_id": 111222,
            "message_id": 777,
            "font": 14,
            "raw_message": "hello",
            "sender": {
                "user_id": 111222,
                "nickname": "tester",
                "card": "tester-card",
                "role": "admin",
            },
            "message": [
                {"type": "text", "data": {"text": "hello"}},
            ],
        }
    )

    await adapter.handle_forward_ws_event(event)

    queued = queue.get_nowait()
    group = await queued.get_group()
    assert group is not None
    assert group.group_id == "654321"
    assert group.group_name == "NapCat Group"
    assert group.group_owner == "1"
    assert group.group_admins == ["2"]
    assert [member.user_id for member in group.members] == ["1", "2", "3"]
    assert [member.nickname for member in group.members] == [
        "owner-card",
        "admin-nick",
        "member-card",
    ]


@pytest.mark.asyncio
async def test_napcat_get_group_returns_none_without_group_context():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = _make_manual_event(adapter, sender_id="445566")

    assert await event.get_group() is None


@pytest.mark.asyncio
async def test_napcat_get_group_supports_explicit_group_id_no_cache_and_mapping_data():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_group_info = AsyncMock(
        return_value={"group_id": "777888", "group_name": "Mapped Group"}
    )
    adapter.client.get_group_member_list = AsyncMock(
        return_value=[
            {"user_id": 11, "nickname": "owner-nick", "card": "", "role": "owner"},
            {"user_id": 12, "nickname": "admin-nick", "role": "admin"},
            {"user_id": 13, "card": "member-card", "role": "member"},
            {"user_id": None, "nickname": "ignored"},
        ]
    )
    event = _make_manual_event(adapter, sender_id="445566")

    group = await event.get_group(group_id="777888", no_cache=True)

    adapter.client.get_group_info.assert_awaited_once_with(group_id="777888")
    adapter.client.get_group_member_list.assert_awaited_once_with(
        "777888",
        no_cache=True,
    )
    assert group is not None
    assert group.group_id == "777888"
    assert group.group_name == "Mapped Group"
    assert group.group_owner == "11"
    assert group.group_admins == ["12"]
    assert [member.user_id for member in group.members] == ["11", "12", "13"]
    assert [member.nickname for member in group.members] == [
        "owner-nick",
        "admin-nick",
        "member-card",
    ]


@pytest.mark.asyncio
async def test_napcat_event_get_forward_msg_resolves_component_or_returns_none():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_forward_message = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {"messages": []}}
    )
    event = _make_manual_event(
        adapter,
        sender_id="445566",
        message=[Forward(id="forward-123")],
    )

    payload = await event.get_forward_msg()
    assert payload["data"] == {"messages": []}
    adapter.client.get_forward_message.assert_awaited_once_with("forward-123")

    adapter.client.get_forward_message.reset_mock()
    explicit_payload = await event.get_forward_msg(" forward-456 ")
    assert explicit_payload["status"] == "ok"
    adapter.client.get_forward_message.assert_awaited_once_with("forward-456")

    empty_event = _make_manual_event(adapter, sender_id="445566", message=[])
    assert await empty_event.get_forward_msg() is None


def test_napcat_event_notice_and_request_helpers_return_none_when_unrelated():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = _make_manual_event(adapter, sender_id="445566")

    assert event.get_notify_info() is None
    assert event.get_group_admin_info() is None
    assert event.get_group_ban_info() is None
    assert event.get_group_card_info() is None
    assert event.get_group_increase_info() is None
    assert event.get_group_decrease_info() is None
    assert event.get_group_essence_info() is None
    assert event.get_request_info() is None


def test_napcat_event_notice_and_request_helpers_omit_optional_fields_when_missing():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)

    notify_event = _make_manual_event(adapter, sender_id="445566")
    notify_event.set_extra("onebot_post_type", "notice")
    notify_event.set_extra("onebot_notice_type", "notify")
    notify_event.set_extra("onebot_sub_type", "poke")
    notify_event.set_extra("napcat_user_id", "445566")
    assert notify_event.get_notify_info() == {
        "notice_type": "notify",
        "sub_type": "poke",
        "user_id": "445566",
    }

    request_event = _make_manual_event(adapter, sender_id="445566")
    request_event.set_extra("onebot_post_type", "request")
    request_event.set_extra("onebot_request_type", "friend")
    request_event.set_extra("onebot_sub_type", "add")
    request_event.set_extra("napcat_user_id", "445566")
    request_event.set_extra("napcat_flag", "flag-1")
    assert request_event.get_request_info() == {
        "request_type": "friend",
        "sub_type": "add",
        "user_id": "445566",
        "flag": "flag-1",
    }

    essence_event = _make_manual_event(adapter, sender_id="445566")
    essence_event.message_obj.raw_message = SimpleNamespace()
    essence_event.set_extra("onebot_post_type", "notice")
    essence_event.set_extra("onebot_notice_type", "essence")
    essence_event.set_extra("onebot_sub_type", "add")
    essence_event.set_extra("napcat_group_id", "654321")
    essence_event.set_extra("napcat_message_id", "9001")
    essence_event.set_extra("napcat_operator_id", "10001")
    assert essence_event.get_group_essence_info() == {
        "notice_type": "essence",
        "sub_type": "add",
        "group_id": "654321",
        "message_id": "9001",
        "operator_id": "10001",
    }


@pytest.mark.asyncio
async def test_napcat_event_delete_validates_message_event_and_message_id():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.delete_message = AsyncMock()

    notice_event = _make_manual_event(adapter, sender_id="445566")
    notice_event.set_extra("onebot_post_type", "notice")
    with pytest.raises(ValueError, match="delete\\(\\) is only available"):
        await notice_event.delete()

    missing_id_event = _make_manual_event(adapter, sender_id="445566")
    missing_id_event.set_extra("onebot_post_type", "message")
    missing_id_event.message_obj.message_id = ""
    with pytest.raises(
        ValueError, match="current NapCat event does not contain a message_id"
    ):
        await missing_id_event.delete()


@pytest.mark.asyncio
async def test_napcat_event_send_streaming_batches_without_fallback():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = _make_manual_event(adapter, sender_id="445566")
    event.send = AsyncMock()

    async def _generator():
        yield MessageChain([Plain("hello")])
        yield MessageChain([Plain(" world"), Face(id="123")])

    result = await event.send_streaming(_generator())

    assert isinstance(result, PlatformSendResult)
    assert result.status == "unknown"
    assert result.success is False
    event.send.assert_awaited_once()
    sent_chain = event.send.await_args.args[0]
    assert isinstance(sent_chain, MessageChain)
    assert [type(component).__name__ for component in sent_chain.chain] == [
        "Plain",
        "Face",
    ]
    assert sent_chain.chain[0].text == "hello world"
    assert sent_chain.chain[1].id == 123
    assert event._has_send_oper is True


@pytest.mark.asyncio
async def test_napcat_event_send_streaming_fallback_sends_components_incrementally(
    monkeypatch: pytest.MonkeyPatch,
):
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = _make_manual_event(adapter, sender_id="445566")
    event.send = AsyncMock()
    sleep_mock = AsyncMock()
    monkeypatch.setattr(
        "astrbot.core.platform.sources.napcat.message_event.asyncio.sleep", sleep_mock
    )

    async def _generator():
        yield MessageChain([Plain("hello "), Face(id="1")])
        yield "ignored"
        yield MessageChain([Plain("world"), Face(id="2")])

    result = await event.send_streaming(_generator(), use_fallback=True)

    assert isinstance(result, PlatformSendResult)
    assert result.status == "unknown"
    assert result.success is False
    assert event.send.await_count == 3
    first_chain = event.send.await_args_list[0].args[0]
    second_chain = event.send.await_args_list[1].args[0]
    third_chain = event.send.await_args_list[2].args[0]
    assert [type(component).__name__ for component in first_chain.chain] == ["Face"]
    assert [type(component).__name__ for component in second_chain.chain] == ["Face"]
    assert [type(component).__name__ for component in third_chain.chain] == ["Plain"]
    assert first_chain.chain[0].id == 1
    assert second_chain.chain[0].id == 2
    assert third_chain.chain[0].text == "hello world"
    assert sleep_mock.await_count == 2
    assert event._has_send_oper is True


@pytest.mark.asyncio
async def test_napcat_event_send_streaming_ignores_empty_non_fallback_stream():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = _make_manual_event(adapter, sender_id="445566")
    event.send = AsyncMock()

    async def _generator():
        if False:
            yield MessageChain([])

    result = await event.send_streaming(_generator())

    assert result is None
    event.send.assert_not_called()


@pytest.mark.asyncio
async def test_napcat_event_send_streaming_ignores_empty_fallback_stream():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = _make_manual_event(adapter, sender_id="445566")
    event.send = AsyncMock()

    async def _generator():
        if False:
            yield MessageChain([])

    result = await event.send_streaming(_generator(), use_fallback=True)

    assert result is None
    event.send.assert_not_called()
    assert event._has_send_oper is False


@pytest.mark.asyncio
async def test_napcat_event_online_file_actions_resolve_current_component():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.get_online_file_messages = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {"items": []}}
    )
    adapter.client.receive_online_file = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.refuse_online_file = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.cancel_online_file = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    event = _make_manual_event(
        adapter,
        sender_id="445566",
        message=[
            OnlineFile(
                msg_id="msg-1",
                element_id="element-1",
                file_name="demo.zip",
                file_size="1024",
                is_dir=False,
            )
        ],
    )

    payload = await event.get_online_file_messages()
    assert payload["status"] == "ok"
    adapter.client.get_online_file_messages.assert_awaited_once_with(user_id="445566")

    await event.receive_online_file()
    adapter.client.receive_online_file.assert_awaited_once_with(
        user_id="445566",
        msg_id="msg-1",
        element_id="element-1",
    )

    await event.refuse_online_file()
    adapter.client.refuse_online_file.assert_awaited_once_with(
        user_id="445566",
        msg_id="msg-1",
        element_id="element-1",
    )

    await event.cancel_online_file()
    adapter.client.cancel_online_file.assert_awaited_once_with(
        user_id="445566",
        msg_id="msg-1",
    )


@pytest.mark.asyncio
async def test_napcat_event_online_file_actions_validate_required_fields():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = _make_manual_event(adapter, sender_id="445566", message=[])

    with pytest.raises(ValueError, match="msg_id is required"):
        await event.cancel_online_file()

    with pytest.raises(ValueError, match="element_id is required"):
        await event.receive_online_file(user_id="445566", msg_id="msg-1")


@pytest.mark.asyncio
async def test_napcat_event_online_file_actions_allow_explicit_overrides():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.receive_online_file = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.refuse_online_file = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.cancel_online_file = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    event = _make_manual_event(
        adapter,
        sender_id="445566",
        message=[
            OnlineFile(
                msg_id="embedded-msg",
                element_id="embedded-element",
                file_name="demo.zip",
                file_size="1024",
                is_dir=False,
            )
        ],
    )

    await event.receive_online_file(
        user_id="778899",
        msg_id="explicit-msg",
        element_id="explicit-element",
    )
    adapter.client.receive_online_file.assert_awaited_once_with(
        user_id="778899",
        msg_id="explicit-msg",
        element_id="explicit-element",
    )

    await event.refuse_online_file(
        user_id="778899",
        msg_id="explicit-msg-2",
        element_id="explicit-element-2",
    )
    adapter.client.refuse_online_file.assert_awaited_once_with(
        user_id="778899",
        msg_id="explicit-msg-2",
        element_id="explicit-element-2",
    )

    await event.cancel_online_file(user_id="778899", msg_id="explicit-msg-3")
    adapter.client.cancel_online_file.assert_awaited_once_with(
        user_id="778899",
        msg_id="explicit-msg-3",
    )


@pytest.mark.asyncio
async def test_napcat_online_file_actions_do_not_infer_private_peer_from_group_events():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    group_event = _make_manual_event(
        adapter,
        sender_id="445566",
        message_type=MessageType.GROUP_MESSAGE,
        group_id="654321",
        message=[
            OnlineFile(
                msg_id="group-msg-1",
                element_id="group-element-1",
                file_name="demo.zip",
                file_size="1024",
                is_dir=False,
            )
        ],
    )

    with pytest.raises(ValueError, match="outside private chats"):
        await group_event.get_online_file_messages()

    with pytest.raises(ValueError, match="outside private chats"):
        await group_event.receive_online_file()

    with pytest.raises(ValueError, match="outside private chats"):
        await group_event.send_online_file("C:\\tmp\\demo.zip")


@pytest.mark.asyncio
async def test_napcat_event_send_platform_specific_file_actions():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.send_online_file = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.send_online_folder = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.send_flash_message = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )

    private_event = _make_manual_event(adapter, sender_id="445566")
    await private_event.send_online_file("C:\\tmp\\demo.zip", file_name="demo.zip")
    adapter.client.send_online_file.assert_awaited_once_with(
        user_id="445566",
        file_path="C:\\tmp\\demo.zip",
        file_name="demo.zip",
    )

    await private_event.send_online_folder(
        "C:\\tmp\\demo-folder",
        folder_name="demo-folder",
    )
    adapter.client.send_online_folder.assert_awaited_once_with(
        user_id="445566",
        folder_path="C:\\tmp\\demo-folder",
        folder_name="demo-folder",
    )

    await private_event.send_flash_message("flash-set-1")
    adapter.client.send_flash_message.assert_awaited_with(
        fileset_id="flash-set-1",
        user_id="445566",
    )

    group_event = _make_manual_event(
        adapter,
        sender_id="445566",
        message_type=MessageType.GROUP_MESSAGE,
        group_id="654321",
    )
    await group_event.send_flash_message("flash-set-2")
    adapter.client.send_flash_message.assert_awaited_with(
        fileset_id="flash-set-2",
        group_id="654321",
    )


@pytest.mark.asyncio
async def test_napcat_event_flash_file_management_helpers():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.create_flash_task = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {"fileset_id": "flash-1"}}
    )
    adapter.client.get_flash_file_list = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {"files": ["a.png"]}}
    )
    adapter.client.get_flash_file_url = AsyncMock(
        return_value={
            "status": "ok",
            "retcode": 0,
            "data": {"url": "https://example.com/a.png"},
        }
    )
    event = _make_manual_event(adapter, sender_id="445566")

    created = await event.create_flash_task(
        ["C:\\tmp\\a.png"],
        name="flash-task",
        thumb_path="C:\\tmp\\thumb.png",
    )
    assert created["data"]["fileset_id"] == "flash-1"
    adapter.client.create_flash_task.assert_awaited_once_with(
        files=["C:\\tmp\\a.png"],
        name="flash-task",
        thumb_path="C:\\tmp\\thumb.png",
    )

    listed = await event.get_flash_file_list("flash-1")
    assert listed["data"]["files"] == ["a.png"]
    adapter.client.get_flash_file_list.assert_awaited_once_with(fileset_id="flash-1")

    resolved = await event.get_flash_file_url("flash-1", file_index=0)
    assert resolved["data"]["url"] == "https://example.com/a.png"
    adapter.client.get_flash_file_url.assert_awaited_once_with(
        fileset_id="flash-1",
        file_name=None,
        file_index=0,
    )


@pytest.mark.asyncio
async def test_napcat_event_request_helpers_validate_request_specific_rules():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.set_friend_add_request = AsyncMock()
    adapter.client.set_group_add_request = AsyncMock()

    non_request_event = _make_manual_event(adapter, sender_id="445566")
    with pytest.raises(
        ValueError,
        match="approve_request\\(\\)/reject_request\\(\\) are only available",
    ):
        await non_request_event.approve_request()

    friend_message = AstrBotMessage()
    friend_message.type = MessageType.FRIEND_MESSAGE
    friend_message.self_id = "123456"
    friend_message.session_id = "445566"
    friend_message.message_id = "friend-request-msg"
    friend_message.sender = MessageMember("445566", "friend-user")
    friend_message.message = []
    friend_message.message_str = ""
    friend_message.group_id = None
    friend_message.raw_message = SimpleNamespace(flag="friend-flag")
    friend_event = adapter.create_event(friend_message)
    friend_event.set_extra("onebot_request_type", "friend")

    with pytest.raises(
        ValueError, match="friend add requests do not support a reject reason"
    ):
        await friend_event.reject_request(reason="nope")

    group_message = AstrBotMessage()
    group_message.type = MessageType.GROUP_MESSAGE
    group_message.self_id = "123456"
    group_message.session_id = "654321"
    group_message.group_id = "654321"
    group_message.message_id = "group-request-msg"
    group_message.sender = MessageMember("445566", "group-user")
    group_message.message = []
    group_message.message_str = ""
    group_message.raw_message = SimpleNamespace(flag="group-flag")
    group_event = adapter.create_event(group_message)
    group_event.set_extra("onebot_request_type", "group")

    with pytest.raises(ValueError, match="group add requests do not support a remark"):
        await group_event.approve_request(remark="hello")

    missing_flag_message = AstrBotMessage()
    missing_flag_message.type = MessageType.FRIEND_MESSAGE
    missing_flag_message.self_id = "123456"
    missing_flag_message.session_id = "445566"
    missing_flag_message.message_id = "missing-flag-msg"
    missing_flag_message.sender = MessageMember("445566", "friend-user")
    missing_flag_message.message = []
    missing_flag_message.message_str = ""
    missing_flag_message.group_id = None
    missing_flag_message.raw_message = SimpleNamespace(flag=" ")
    missing_flag_event = adapter.create_event(missing_flag_message)
    missing_flag_event.set_extra("onebot_request_type", "friend")

    with pytest.raises(
        ValueError, match="current NapCat request event does not contain a flag"
    ):
        await missing_flag_event.approve_request()


@pytest.mark.asyncio
async def test_napcat_event_group_management_helpers_route_to_forward_ws_client():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.set_group_admin = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_group_ban = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_group_card = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_group_kick = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_group_kick_members = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_group_leave = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_group_whole_ban = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_essence_message = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.delete_essence_message = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.send_group_notice = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.group_poke = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.get_group_msg_history = AsyncMock(
        return_value=[{"message_id": 1001, "message": []}]
    )
    adapter.client.get_ai_characters = AsyncMock(
        return_value=[
            {
                "type": "default",
                "characters": [
                    {"character_id": "voice-1", "character_name": "Demo Voice"}
                ],
            }
        ]
    )
    adapter.client.send_group_ai_record = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    event = _make_manual_event(
        adapter,
        sender_id="445566",
        message_type=MessageType.GROUP_MESSAGE,
        group_id="654321",
    )

    await event.set_group_admin(enable=False)
    adapter.client.set_group_admin.assert_awaited_once_with(
        group_id="654321",
        user_id="445566",
        enable=False,
    )

    await event.set_group_ban(duration=600)
    adapter.client.set_group_ban.assert_awaited_once_with(
        group_id="654321",
        user_id="445566",
        duration=600,
    )

    await event.set_group_card("new-card")
    adapter.client.set_group_card.assert_awaited_once_with(
        group_id="654321",
        user_id="445566",
        card="new-card",
    )

    await event.kick_group_member(reject_add_request=True)
    adapter.client.set_group_kick.assert_awaited_once_with(
        group_id="654321",
        user_id="445566",
        reject_add_request=True,
    )

    await event.kick_group_members(["10001", 10002], reject_add_request=False)
    adapter.client.set_group_kick_members.assert_awaited_once_with(
        group_id="654321",
        user_ids=["10001", 10002],
        reject_add_request=False,
    )

    await event.leave_group(is_dismiss=True)
    adapter.client.set_group_leave.assert_awaited_once_with(
        group_id="654321",
        is_dismiss=True,
    )

    await event.set_group_whole_ban(enable=True)
    adapter.client.set_group_whole_ban.assert_awaited_once_with(
        group_id="654321",
        enable=True,
    )

    await event.set_essence_message()
    adapter.client.set_essence_message.assert_awaited_once_with(
        message_id="local-message-id",
    )

    await event.delete_essence_message()
    adapter.client.delete_essence_message.assert_awaited_once_with(
        message_id="local-message-id",
        msg_seq=None,
        msg_random=None,
        group_id="654321",
    )

    await event.send_group_notice("hello", pinned=1)
    adapter.client.send_group_notice.assert_awaited_once_with(
        group_id="654321",
        content="hello",
        pinned=1,
        type_=None,
        confirm_required=None,
        is_show_edit_card=None,
        tip_window_type=None,
        image=None,
    )

    await event.send_poke(target_id="123456")
    adapter.client.group_poke.assert_awaited_once_with(
        user_id="445566",
        group_id="654321",
        target_id="123456",
    )

    history = await event.get_group_msg_history(count=50)
    assert history == [{"message_id": 1001, "message": []}]
    adapter.client.get_group_msg_history.assert_awaited_once_with(
        group_id="654321",
        count=50,
        message_seq=None,
    )

    characters = await event.get_ai_characters()
    assert characters[0]["characters"][0]["character_id"] == "voice-1"
    adapter.client.get_ai_characters.assert_awaited_once_with(
        group_id="654321",
        chat_type=1,
    )

    await event.send_group_ai_record("你好", character="voice-1")
    adapter.client.send_group_ai_record.assert_awaited_once_with(
        group_id="654321",
        character="voice-1",
        text="你好",
        chat_type=1,
        timeout_seconds=10.0,
    )


@pytest.mark.asyncio
async def test_napcat_event_social_helpers_and_group_validation():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.send_like = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.friend_poke = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_input_status = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.get_friend_msg_history = AsyncMock(
        return_value=[{"message_id": 2001, "message": []}]
    )
    adapter.client.fetch_custom_face = AsyncMock(
        return_value=["https://example.com/face-1.png"]
    )

    private_event = _make_manual_event(adapter, sender_id="445566")
    await private_event.send_like(times=3)
    adapter.client.send_like.assert_awaited_once_with(user_id="445566", times=3)

    await private_event.send_poke(target_id="123456")
    adapter.client.friend_poke.assert_awaited_once_with(
        user_id="445566",
        target_id="123456",
    )

    await private_event.set_input_status(event_type=1)
    adapter.client.set_input_status.assert_awaited_once_with(
        user_id="445566",
        event_type=1,
    )

    history = await private_event.get_friend_msg_history(count=5)
    assert history == [{"message_id": 2001, "message": []}]
    adapter.client.get_friend_msg_history.assert_awaited_once_with(
        user_id="445566",
        count=5,
        message_seq=None,
    )

    faces = await private_event.fetch_custom_face(count=1)
    assert faces == ["https://example.com/face-1.png"]
    adapter.client.fetch_custom_face.assert_awaited_once_with(count=1)

    with pytest.raises(ValueError, match="group_id is required"):
        await private_event.set_group_admin()

    with pytest.raises(ValueError, match="user_ids is required"):
        await private_event.kick_group_members([])


@pytest.mark.asyncio
async def test_napcat_adapter_proactive_management_helpers_proxy_to_forward_ws_client():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    adapter.client.set_group_admin = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_group_ban = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_group_card = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_group_kick = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_group_kick_members = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_group_leave = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_group_whole_ban = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_essence_message = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.delete_essence_message = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.send_group_notice = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.send_like = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.group_poke = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.friend_poke = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.set_input_status = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )
    adapter.client.get_group_msg_history = AsyncMock(
        return_value=[{"message_id": 3001}]
    )
    adapter.client.get_friend_msg_history = AsyncMock(
        return_value=[{"message_id": 3002}]
    )
    adapter.client.fetch_custom_face = AsyncMock(
        return_value=["https://example.com/face-2.png"]
    )
    adapter.client.get_ai_characters = AsyncMock(
        return_value=[{"type": "default", "characters": []}]
    )
    adapter.client.send_group_ai_record = AsyncMock(
        return_value={"status": "ok", "retcode": 0, "data": {}}
    )

    await adapter.set_group_admin(group_id="654321", user_id="445566", enable=True)
    adapter.client.set_group_admin.assert_awaited_once_with(
        group_id="654321",
        user_id="445566",
        enable=True,
    )

    await adapter.set_group_ban(group_id="654321", user_id="445566", duration=60)
    adapter.client.set_group_ban.assert_awaited_once_with(
        group_id="654321",
        user_id="445566",
        duration=60,
    )

    await adapter.set_group_card(group_id="654321", user_id="445566", card="new-card")
    adapter.client.set_group_card.assert_awaited_once_with(
        group_id="654321",
        user_id="445566",
        card="new-card",
    )

    await adapter.kick_group_member(
        group_id="654321",
        user_id="445566",
        reject_add_request=True,
    )
    adapter.client.set_group_kick.assert_awaited_once_with(
        group_id="654321",
        user_id="445566",
        reject_add_request=True,
    )

    await adapter.kick_group_members(group_id="654321", user_ids=["1", "2"])
    adapter.client.set_group_kick_members.assert_awaited_once_with(
        group_id="654321",
        user_ids=["1", "2"],
        reject_add_request=None,
    )

    await adapter.leave_group(group_id="654321", is_dismiss=True)
    adapter.client.set_group_leave.assert_awaited_once_with(
        group_id="654321",
        is_dismiss=True,
    )

    await adapter.set_group_whole_ban(group_id="654321", enable=False)
    adapter.client.set_group_whole_ban.assert_awaited_once_with(
        group_id="654321",
        enable=False,
    )

    await adapter.set_essence_message(message_id="9001")
    adapter.client.set_essence_message.assert_awaited_once_with(message_id="9001")

    await adapter.delete_essence_message(
        message_id="9001",
        msg_seq="seq-1",
        msg_random="rand-1",
        group_id="654321",
    )
    adapter.client.delete_essence_message.assert_awaited_once_with(
        message_id="9001",
        msg_seq="seq-1",
        msg_random="rand-1",
        group_id="654321",
    )

    await adapter.send_group_notice(group_id="654321", content="notice")
    adapter.client.send_group_notice.assert_awaited_once_with(
        group_id="654321",
        content="notice",
        pinned=None,
        type_=None,
        confirm_required=None,
        is_show_edit_card=None,
        tip_window_type=None,
        image=None,
    )

    await adapter.send_like(user_id="445566", times=2)
    adapter.client.send_like.assert_awaited_once_with(user_id="445566", times=2)

    await adapter.send_poke(user_id="445566", group_id="654321", target_id="123456")
    adapter.client.group_poke.assert_awaited_once_with(
        user_id="445566",
        group_id="654321",
        target_id="123456",
    )

    await adapter.send_poke(user_id="445566", target_id="123456")
    adapter.client.friend_poke.assert_awaited_once_with(
        user_id="445566",
        target_id="123456",
    )

    await adapter.set_input_status(user_id="445566", event_type=2)
    adapter.client.set_input_status.assert_awaited_once_with(
        user_id="445566",
        event_type=2,
    )

    assert await adapter.get_group_msg_history(group_id="654321", count=10) == [
        {"message_id": 3001}
    ]
    adapter.client.get_group_msg_history.assert_awaited_once_with(
        group_id="654321",
        count=10,
        message_seq=None,
    )

    assert await adapter.get_friend_msg_history(user_id="445566", count=8) == [
        {"message_id": 3002}
    ]
    adapter.client.get_friend_msg_history.assert_awaited_once_with(
        user_id="445566",
        count=8,
        message_seq=None,
    )

    assert await adapter.fetch_custom_face(count=2) == [
        "https://example.com/face-2.png"
    ]
    adapter.client.fetch_custom_face.assert_awaited_once_with(count=2)

    assert await adapter.get_ai_characters(group_id="654321") == [
        {"type": "default", "characters": []}
    ]
    adapter.client.get_ai_characters.assert_awaited_once_with(
        group_id="654321",
        chat_type=1,
    )

    await adapter.send_group_ai_record(
        group_id="654321",
        character="voice-1",
        text="你好",
    )
    adapter.client.send_group_ai_record.assert_awaited_once_with(
        group_id="654321",
        character="voice-1",
        text="你好",
        chat_type=1,
        timeout_seconds=10.0,
    )


def test_napcat_event_outline_includes_new_component_placeholders():
    queue: asyncio.Queue = asyncio.Queue()
    adapter = _make_adapter(queue)
    event = _make_manual_event(
        adapter,
        message=[
            Anonymous(ignore=1),
            MFace(
                emoji_package_id=1152,
                emoji_id="987654321",
                key="market-face-key",
                summary="[HappyFace]",
            ),
            OnlineFile(
                msg_id="msg-1",
                element_id="element-1",
                file_name="demo.zip",
                file_size="1024",
                is_dir=False,
            ),
            FlashTransfer(file_set_id="flash-set-1"),
            Markdown(content="# Demo"),
            MiniApp(data='{"app":"demo"}'),
        ],
    )

    outline = event.get_message_outline()
    assert "[匿名]" in outline
    assert "[商城表情:[HappyFace]]" in outline
    assert "[在线文件:demo.zip]" in outline
    assert "[闪传]" in outline
    assert "[Markdown]" in outline
    assert "[小程序]" in outline
