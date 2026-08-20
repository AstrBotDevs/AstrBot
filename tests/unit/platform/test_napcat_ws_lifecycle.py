from __future__ import annotations

import pytest

from tests.unit.platform.napcat_adapter_support import *  # noqa: F403

pytestmark = pytest.mark.platform


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
