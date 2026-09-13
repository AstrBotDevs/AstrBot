"""Regression tests for optional OAuth image WebSocket requests."""

import asyncio
import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import pytest
import pytest_asyncio

import astrbot.core.provider.sources.openai_oauth_source as source

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j6S8AAAAASUVORK5CYII="
)


def image_events():
    return [
        {"type": "response.created", "response": {"id": "response-test"}},
        {"type": "response.image_generation_call.generating"},
        {
            "type": "response.output_item.done",
            "item": {
                "id": "image-test",
                "type": "image_generation_call",
                "result": base64.b64encode(PNG).decode(),
            },
        },
        {
            "type": "response.completed",
            "response": {
                "id": "response-test",
                "output": [],
                "usage": {"input_tokens": 1, "output_tokens": 2},
            },
        },
    ]


class Socket:
    def __init__(self, events=(), *, send_error=None, wait_forever=False):
        self.events = list(events)
        self.send_error = send_error
        self.wait_forever = wait_forever
        self.sent = []
        self.reading = asyncio.Event()
        self.closed = False
        self.wake = asyncio.Event()
        self.close_code = 1000

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()

    async def close(self):
        self.closed = True
        self.wake.set()

    async def send_json(self, value):
        self.sent.append(value)
        if self.send_error:
            raise self.send_error

    def __aiter__(self):
        return self

    async def __anext__(self):
        self.reading.set()
        if self.closed:
            raise StopAsyncIteration
        if self.events:
            event = self.events.pop(0)
            return SimpleNamespace(type=aiohttp.WSMsgType.TEXT, data=json.dumps(event))
        if self.wait_forever:
            await self.wake.wait()
        raise StopAsyncIteration

    def exception(self):
        return None


class Handshake:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        self.session.handshaking.set()
        if self.session.gate:
            await self.session.gate.wait()
        if self.session.error:
            raise self.session.error
        return self.session.socket

    async def __aexit__(self, *_):
        await self.session.socket.close()


class Session:
    def __init__(self, socket, *, error=None, gate=None):
        self.socket = socket
        self.error = error
        self.gate = gate
        self.closed = False
        self.handshaking = asyncio.Event()
        self.connect_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()

    async def close(self):
        self.closed = True
        await self.socket.close()

    def ws_connect(self, url, **kwargs):
        self.connect_calls.append((url, kwargs))
        return Handshake(self)


@pytest_asyncio.fixture
async def provider(monkeypatch, tmp_path):
    monkeypatch.setattr(
        source, "db_helper", SimpleNamespace(insert_provider_stat=AsyncMock())
    )
    provider = source.ProviderOpenAIOAuth(
        {
            "id": "test-openai-oauth",
            "type": "openai_oauth_chat_completion",
            "model": "gpt-5.6-sol",
            "oauth_access_token": "test-secret-token",
            "oauth_refresh_token": "test-refresh",
            "oauth_account_id": "test-account",
            "generated_image_dir": str(tmp_path),
            "timeout": 300,
        },
        {},
    )
    provider._ensure_fresh_oauth_token = AsyncMock()
    provider._refresh_after_auth_failure = AsyncMock(return_value=True)
    yield provider
    await provider.terminate()


def install_sessions(monkeypatch, sessions):
    calls = []
    pending = list(sessions)

    def factory(**kwargs):
        calls.append(kwargs)
        return pending.pop(0)

    monkeypatch.setattr(source, "aiohttp", aiohttp, raising=False)
    monkeypatch.setattr(source.aiohttp, "ClientSession", factory)
    return calls


@pytest.mark.asyncio
async def test_default_http_and_explicit_websocket_preserve_images(
    provider, monkeypatch
):
    http_response = {"output": [image_events()[2]["item"]]}
    provider._request_image_backend = AsyncMock(return_value=http_response)
    normal = await provider.generate_image("cat")
    assert normal[0].path
    assert provider._request_image_backend.await_count == 1
    socket = Socket(image_events())
    session = Session(socket)
    install_sessions(monkeypatch, [session])
    result = await provider.generate_image("cat", transport="websocket", timeout=90)
    assert len(result) == 1
    from pathlib import Path

    assert Path(result[0].path).read_bytes() == PNG
    assert provider._request_image_backend.await_count == 1
    assert source.ProviderOpenAIOAuth.capabilities["image_websocket"] is True
    assert len(socket.sent) == 1
    request = socket.sent[0]
    assert request["type"] == "response.create"
    assert "stream" not in request and "background" not in request
    assert request["tools"][0]["action"] == "generate"
    assert session.closed and socket.closed
    assert not provider._oauth_stream_clients


@pytest.mark.asyncio
async def test_websocket_preserves_edit_references(provider, monkeypatch):
    socket = Socket(image_events())
    install_sessions(monkeypatch, [Session(socket)])
    refs = ["data:image/png;base64," + base64.b64encode(PNG).decode()] * 2
    await provider.generate_image(
        "edit cat", reference_images=refs, action="edit", transport="websocket"
    )
    request = socket.sent[0]
    assert request["tools"][0]["action"] == "edit"
    assert [
        p["image_url"]
        for p in request["input"][0]["content"]
        if p["type"] == "input_image"
    ] == refs


@pytest.mark.asyncio
async def test_handshake_401_refreshes_once_before_any_send(provider, monkeypatch):
    denied = Socket()
    first = Session(
        denied,
        error=aiohttp.WSServerHandshakeError(
            SimpleNamespace(real_url="wss://test"), (), status=401
        ),
    )
    accepted = Socket(image_events())
    second = Session(accepted)
    install_sessions(monkeypatch, [first, second])

    def headers():
        version = provider._refresh_after_auth_failure.await_count
        return {"Authorization": f"Bearer test-token-{version}"}, version

    provider._build_backend_headers_with_version = headers
    await provider.generate_image("cat", transport="websocket")
    assert denied.sent == [] and len(accepted.sent) == 1
    assert provider._refresh_after_auth_failure.await_count == 1
    assert first.connect_calls[0][1]["headers"] != second.connect_calls[0][1]["headers"]
    assert first.closed and second.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_handshake_rejection_never_sends_images(provider, monkeypatch, status):
    sessions = [
        Session(
            Socket(),
            error=aiohttp.WSServerHandshakeError(
                SimpleNamespace(real_url="wss://test"), (), status=status
            ),
        )
        for _ in range(2)
    ]
    install_sessions(monkeypatch, sessions)
    with pytest.raises(Exception) as caught:
        await provider.generate_image("cat", transport="websocket")
    assert getattr(caught.value, "status_code", None) == status
    assert all(not session.socket.sent for session in sessions)
    assert provider._refresh_after_auth_failure.await_count == (
        1 if status == 401 else 0
    )
    assert not provider._oauth_stream_clients


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["send", "closed", "server503", "server429"])
async def test_after_submission_never_resends_or_falls_back(
    provider, monkeypatch, scenario
):
    events = []
    if scenario.startswith("server"):
        events = [
            {
                "type": "response.failed",
                "response": {
                    "error": {
                        "status_code": int(scenario[6:]),
                        "message": "test-secret-token",
                    }
                },
            }
        ]
    socket = Socket(
        events,
        send_error=ConnectionError("test-secret-token") if scenario == "send" else None,
    )
    session = Session(socket)
    install_sessions(monkeypatch, [session])
    provider._request_image_backend = AsyncMock()
    with pytest.raises(Exception) as caught:
        await provider.generate_image("cat", transport="websocket")
    assert getattr(caught.value, "retryable", None) is False
    assert "test-secret-token" not in str(caught.value)
    assert len(socket.sent) == 1
    assert provider._request_image_backend.await_count == 0
    assert session.closed and not provider._oauth_stream_clients


@pytest.mark.asyncio
async def test_websocket_total_deadline_does_not_reset_on_keepalive(
    provider, monkeypatch
):
    socket = Socket([{"type": "keepalive"}], wait_forever=True)
    session = Session(socket)
    install_sessions(monkeypatch, [session])
    with pytest.raises(Exception) as caught:
        await provider.generate_image("cat", transport="websocket", timeout=0.02)
    assert getattr(caught.value, "reason_code", None) == "outcome_unknown"
    assert getattr(caught.value, "retryable", None) is False
    assert len(socket.sent) == 1 and session.closed
    assert not provider._oauth_stream_clients


@pytest.mark.asyncio
async def test_cancellation_closes_pending_image_socket(provider, monkeypatch):
    socket = Socket(wait_forever=True)
    session = Session(socket)
    install_sessions(monkeypatch, [session])
    task = asyncio.create_task(provider.generate_image("cat", transport="websocket"))
    await asyncio.wait_for(socket.reading.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert session.closed and not provider._oauth_stream_clients


@pytest.mark.asyncio
async def test_terminate_during_handshake_prevents_send(provider, monkeypatch):
    gate = asyncio.Event()
    socket = Socket(image_events())
    session = Session(socket, gate=gate)
    install_sessions(monkeypatch, [session])
    task = asyncio.create_task(provider.generate_image("cat", transport="websocket"))
    await asyncio.wait_for(session.handshaking.wait(), 1)
    await provider.terminate()
    gate.set()
    with pytest.raises(Exception):
        await task
    assert socket.sent == []
    assert session.closed and not provider._oauth_stream_clients


@pytest.mark.asyncio
async def test_terminate_during_generation_closes_pending_socket(provider, monkeypatch):
    socket = Socket(wait_forever=True)
    session = Session(socket)
    install_sessions(monkeypatch, [session])
    task = asyncio.create_task(provider.generate_image("cat", transport="websocket"))
    await asyncio.wait_for(socket.reading.wait(), 1)
    await provider.terminate()
    with pytest.raises(Exception) as caught:
        await task
    assert getattr(caught.value, "reason_code", None) == "outcome_unknown"
    assert len(socket.sent) == 1 and not provider._oauth_stream_clients


@pytest.mark.asyncio
async def test_cancelled_handshake_closes_owned_session(provider, monkeypatch):
    gate = asyncio.Event()
    session = Session(Socket(), gate=gate)
    install_sessions(monkeypatch, [session])
    task = asyncio.create_task(provider.generate_image("cat", transport="websocket"))
    await asyncio.wait_for(session.handshaking.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert session.closed and session.socket.sent == []
    assert not provider._oauth_stream_clients


@pytest.mark.asyncio
async def test_cancelled_send_closes_owned_session(provider, monkeypatch):
    class SendingSocket(Socket):
        async def send_json(self, value):
            self.sent.append(value)
            self.reading.set()
            await asyncio.Event().wait()

    socket = SendingSocket()
    session = Session(socket)
    install_sessions(monkeypatch, [session])
    task = asyncio.create_task(provider.generate_image("cat", transport="websocket"))
    await asyncio.wait_for(socket.reading.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(socket.sent) == 1 and session.closed
    assert not provider._oauth_stream_clients


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", ["bytes", "events"])
async def test_websocket_transcript_limits_stop_without_resubmission(
    provider, monkeypatch, limit
):
    if limit == "bytes":
        monkeypatch.setattr(source, "IMAGE_WEBSOCKET_MAX_TRANSCRIPT_BYTES", 32)
        events = [{"type": "keepalive", "padding": "a" * 64}]
    else:
        monkeypatch.setattr(source, "IMAGE_WEBSOCKET_MAX_EVENTS", 2)
        events = [{"type": "keepalive"}] * 3
    socket = Socket(events)
    session = Session(socket)
    install_sessions(monkeypatch, [session])
    with pytest.raises(Exception) as caught:
        await provider.generate_image("cat", transport="websocket")
    assert caught.value.reason_code == "outcome_unknown"
    assert not caught.value.retryable
    assert len(socket.sent) == 1 and session.closed


@pytest.mark.asyncio
async def test_repeated_keepalive_cannot_extend_total_deadline(provider, monkeypatch):
    class HeartbeatSocket(Socket):
        async def __anext__(self):
            await asyncio.sleep(0.001)
            return SimpleNamespace(
                type=aiohttp.WSMsgType.TEXT, data='{"type":"keepalive"}'
            )

    socket = HeartbeatSocket()
    session = Session(socket)
    install_sessions(monkeypatch, [session])
    with pytest.raises(Exception) as caught:
        await asyncio.wait_for(
            provider.generate_image("cat", transport="websocket", timeout=0.02), 0.3
        )
    assert caught.value.reason_code == "outcome_unknown"
    assert len(socket.sent) == 1 and session.closed


@pytest_asyncio.fixture
async def http_server():
    from aiohttp import web

    runners = []

    async def start(routes):
        app = web.Application()
        for path, handler in routes.items():
            app.router.add_get(path, handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        runners.append(runner)
        port = site._server.sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}"

    yield start
    for runner in runners:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_real_handshake_redirect_is_rejected_before_following(
    provider, http_server
):
    from aiohttp import web

    calls = {"first": 0, "redirected": 0}

    async def redirect(_request):
        calls["first"] += 1
        raise web.HTTPFound("/sink")

    async def sink(_request):
        calls["redirected"] += 1
        return web.Response()

    provider.base_url = await http_server({"/responses": redirect, "/sink": sink})
    with pytest.raises(Exception) as caught:
        await provider.generate_image("cat", transport="websocket")
    assert caught.value.status_code == 302
    assert caught.value.reason_code == "request_rejected"
    assert calls == {"first": 1, "redirected": 0}
    assert not provider._oauth_stream_clients


@pytest.mark.asyncio
async def test_real_pending_handshake_ends_when_provider_terminates(
    provider, http_server
):
    from aiohttp import web

    entered = asyncio.Event()
    release = asyncio.Event()

    async def handshake(_request):
        entered.set()
        await release.wait()
        return web.Response(status=503)

    provider.base_url = await http_server({"/responses": handshake})
    task = asyncio.create_task(provider.generate_image("cat", transport="websocket"))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await provider.terminate()
        done, _pending = await asyncio.wait({task}, timeout=0.5)
        assert task in done, "terminate() must finish the pending handshake"
        with pytest.raises(source.OpenAIOAuthImageStreamError):
            await task
        assert not provider._oauth_stream_clients
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_real_oversized_websocket_message_is_bounded(
    provider, monkeypatch, http_server
):
    from aiohttp import web

    monkeypatch.setattr(source, "IMAGE_WEBSOCKET_MAX_MESSAGE_BYTES", 64)
    received = []

    async def oversized(request):
        websocket = web.WebSocketResponse()
        await websocket.prepare(request)
        received.append(await websocket.receive_json())
        await websocket.send_json({"type": "keepalive", "padding": "x" * 128})
        await websocket.close()
        return websocket

    provider.base_url = await http_server({"/responses": oversized})
    with pytest.raises(Exception) as caught:
        await provider.generate_image("cat", transport="websocket")
    assert caught.value.reason_code == "outcome_unknown"
    assert len(received) == 1 and not provider._oauth_stream_clients


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["http", "websocket"])
@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), True])
async def test_invalid_image_deadlines_fail_before_any_request(
    provider, transport, timeout
):
    provider._request_image_backend = AsyncMock(
        return_value={"output": [image_events()[2]["item"]]}
    )
    with pytest.raises(ValueError):
        await provider.generate_image("cat", transport=transport, timeout=timeout)
    assert provider._request_image_backend.await_count == 0
