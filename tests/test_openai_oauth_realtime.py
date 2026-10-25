import asyncio
import json

import httpx
import pytest

from astrbot.core.provider.oauth.openai_oauth_realtime import (
    REALTIME_CALL_URL,
    OpenAIOAuthRealtimeClient,
    _NoRedirectConnect,
)

SDP = "v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"


class FakeProvider:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.provider_config = {"proxy": "http://proxy.invalid"}
        self.timeout = 30
        self.responses = responses
        self.requests: list[dict] = []
        self.version = 2
        self.refreshes = 0

    async def _ensure_fresh_oauth_token(self) -> None:
        return None

    def _build_backend_headers_with_version(self):
        return (
            {
                "Authorization": f"Bearer token-{self.version}",
                "chatgpt-account-id": "account-id",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "version": "0.153.4",
                "User-Agent": "codex_cli_rs/0.153.4",
            },
            self.version,
        )

    async def _refresh_after_auth_failure(self, attempted_version: int) -> bool:
        assert attempted_version == self.version
        self.refreshes += 1
        self.version += 1
        return True


class FakeHttpClient:
    provider: FakeProvider
    init_kwargs: list[dict] = []

    def __init__(self, **kwargs) -> None:
        self.init_kwargs.append(kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def post(self, url: str, **kwargs):
        self.provider.requests.append({"url": url, **kwargs})
        return self.provider.responses.pop(0)


class FakeWebSocket:
    def __init__(self, early_messages: list[str | bytes] | None = None) -> None:
        self.incoming: asyncio.Queue[str | bytes | None] = asyncio.Queue()
        for message in early_messages or []:
            self.incoming.put_nowait(message)
        self.sent: list[dict] = []
        self.closed = False

    async def recv(self):
        value = await self.incoming.get()
        if value is None:
            raise RuntimeError("socket closed")
        return value

    async def send(self, data: str) -> None:
        self.sent.append(json.loads(data))

    async def close(self, *args, **kwargs) -> None:
        self.closed = True


def _install_fakes(monkeypatch, provider: FakeProvider, sockets: list[FakeWebSocket]):
    FakeHttpClient.provider = provider
    FakeHttpClient.init_kwargs = []
    connections: list[dict] = []

    async def fake_connect(url: str, **kwargs):
        connections.append({"url": url, **kwargs})
        return sockets.pop(0)

    monkeypatch.setattr(
        "astrbot.core.provider.oauth.openai_oauth_realtime.httpx.AsyncClient",
        FakeHttpClient,
    )
    monkeypatch.setattr(
        "astrbot.core.provider.oauth.openai_oauth_realtime.websocket_connect",
        fake_connect,
    )
    return connections


def test_sideband_connector_never_follows_redirects():
    connector = _NoRedirectConnect("wss://api.openai.com/v1/live/rtc_test")

    result = connector.process_redirect(Exception("redirect-like failure"))

    assert isinstance(result, RuntimeError)
    assert not isinstance(result, str)


@pytest.mark.asyncio
async def test_create_session_uses_fixed_endpoints_and_returns_after_sideband_ready(
    monkeypatch: pytest.MonkeyPatch,
):
    provider = FakeProvider(
        [
            httpx.Response(
                200,
                text=SDP,
                headers={"Location": "/v1/realtime/calls/rtc_test-call"},
            )
        ]
    )
    socket = FakeWebSocket()
    connections = _install_fakes(monkeypatch, provider, [socket])
    client = OpenAIOAuthRealtimeClient(provider)

    session = await client.create_session(SDP, instructions="help", voice="cove")

    assert session.id == "rtc_test-call"
    assert session.answer_sdp == SDP
    request = provider.requests[0]
    assert request["url"] == REALTIME_CALL_URL
    assert request["json"]["sdp"] == SDP
    assert request["json"]["session"] == {
        "model": "gpt-live-1-codex",
        "instructions": "help",
        "audio": {"output": {"voice": "cove"}},
        "delegation": {"type": "client"},
    }
    assert request["headers"]["OpenAI-Alpha"] == "quicksilver=v2"
    assert connections[0]["url"] == "wss://api.openai.com/v1/live/rtc_test-call"
    assert connections[0]["additional_headers"]["Authorization"] == ("Bearer token-2")
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sdp", "model", "voice"),
    [
        ("", "gpt-live-1-codex", "cove"),
        (SDP, "gpt-6-astra", "cove"),
        (SDP, "gpt-live-1-codex", "invalid"),
        ("v=0\r\nm=video 9 RTP/AVP 96", "gpt-live-1-codex", "cove"),
    ],
)
async def test_invalid_offer_model_and_voice_fail_before_auth(
    monkeypatch: pytest.MonkeyPatch, sdp: str, model: str, voice: str
):
    provider = FakeProvider([])
    _install_fakes(monkeypatch, provider, [])
    client = OpenAIOAuthRealtimeClient(provider)

    with pytest.raises(ValueError):
        await client.create_session(sdp, model=model, voice=voice)

    assert provider.requests == []


@pytest.mark.asyncio
async def test_create_session_refreshes_once_after_401(monkeypatch):
    provider = FakeProvider(
        [
            httpx.Response(401, text="secret body"),
            httpx.Response(
                200,
                text=SDP,
                headers={"openai-session-id": "rtc_after-refresh"},
            ),
        ]
    )
    _install_fakes(monkeypatch, provider, [FakeWebSocket()])
    client = OpenAIOAuthRealtimeClient(provider)

    session = await client.create_session(SDP)

    assert session.id == "rtc_after-refresh"
    assert provider.refreshes == 1
    assert [r["headers"]["Authorization"] for r in provider.requests] == [
        "Bearer token-2",
        "Bearer token-3",
    ]
    await client.close()


@pytest.mark.asyncio
async def test_sideband_failure_does_not_create_a_second_call(monkeypatch):
    provider = FakeProvider(
        [
            httpx.Response(
                200,
                text=SDP,
                headers={"Location": "/v1/realtime/calls/rtc_orphan"},
            )
        ]
    )

    async def fail_connect(*args, **kwargs):
        raise OSError("secret network detail")

    FakeHttpClient.provider = provider
    monkeypatch.setattr(
        "astrbot.core.provider.oauth.openai_oauth_realtime.httpx.AsyncClient",
        FakeHttpClient,
    )
    monkeypatch.setattr(
        "astrbot.core.provider.oauth.openai_oauth_realtime.websocket_connect",
        fail_connect,
    )
    client = OpenAIOAuthRealtimeClient(provider, sideband_connect_attempts=2)

    with pytest.raises(RuntimeError, match="远端清理状态未知") as exc_info:
        await client.create_session(SDP)

    assert "secret" not in str(exc_info.value)
    assert len(provider.requests) == 1


@pytest.mark.asyncio
async def test_untrusted_absolute_location_is_rejected_without_websocket(monkeypatch):
    provider = FakeProvider(
        [
            httpx.Response(
                200,
                text=SDP,
                headers={"Location": "https://evil.invalid/live/rtc_stolen"},
            )
        ]
    )
    connections = _install_fakes(monkeypatch, provider, [])
    client = OpenAIOAuthRealtimeClient(provider)

    with pytest.raises(RuntimeError, match="Location 来源无效"):
        await client.create_session(SDP)

    assert connections == []
    assert client.session_count == 0


@pytest.mark.asyncio
async def test_transcript_delegation_chunking_and_single_final_result(monkeypatch):
    early = [
        json.dumps({"type": "input_transcript.added", "item": {"text": "hi"}}),
        json.dumps(
            {
                "type": "delegation.created",
                "item": {
                    "type": "delegation",
                    "target": "client",
                    "id": "delegate-1",
                    "content": [{"type": "input_text", "text": "search"}],
                },
            }
        ),
    ]
    provider = FakeProvider(
        [
            httpx.Response(
                200,
                text=SDP,
                headers={"Location": "/v1/realtime/calls/rtc_events"},
            )
        ]
    )
    socket = FakeWebSocket(early)
    _install_fakes(monkeypatch, provider, [socket])
    client = OpenAIOAuthRealtimeClient(provider)
    session = await client.create_session(SDP)
    events = session.events()

    transcript = await anext(events)
    delegation = await anext(events)
    assert (transcript.type, transcript.text) == ("input_transcript", "hi")
    assert (delegation.type, delegation.delegation_id, delegation.text) == (
        "delegation",
        "delegate-1",
        "search",
    )

    result = "你" * 400
    await session.submit_delegation_result("delegate-1", result)
    chunks = [
        message["content"][0]["text"]
        for message in socket.sent
        if message["type"] == "delegation.context.append"
    ]
    assert "".join(chunks) == result
    assert all(len(chunk.encode("utf-8")) <= 500 for chunk in chunks)
    with pytest.raises(ValueError, match="已完成"):
        await session.submit_delegation_result("delegate-1", "again")
    await session.close()


@pytest.mark.asyncio
async def test_concurrent_delegation_results_allow_only_one_final_reply(monkeypatch):
    delegation = json.dumps(
        {
            "type": "delegation.created",
            "item": {
                "type": "delegation",
                "target": "client",
                "id": "delegate-race",
                "content": [{"type": "input_text", "text": "work"}],
            },
        }
    )
    provider = FakeProvider(
        [
            httpx.Response(
                200,
                text=SDP,
                headers={"Location": "/v1/realtime/calls/rtc_race"},
            )
        ]
    )
    socket = FakeWebSocket([delegation])
    send_started = asyncio.Event()
    release_send = asyncio.Event()
    original_send = socket.send

    async def blocking_send(data: str) -> None:
        if json.loads(data).get("type") == "delegation.context.append":
            send_started.set()
            await release_send.wait()
        await original_send(data)

    socket.send = blocking_send
    _install_fakes(monkeypatch, provider, [socket])
    client = OpenAIOAuthRealtimeClient(provider)
    session = await client.create_session(SDP)
    event = await anext(session.events())
    assert event.delegation_id == "delegate-race"

    first = asyncio.create_task(
        session.submit_delegation_result("delegate-race", "first")
    )
    await send_started.wait()
    second = asyncio.create_task(
        session.submit_delegation_result("delegate-race", "second")
    )
    await asyncio.sleep(0)
    release_send.set()
    results = await asyncio.gather(first, second, return_exceptions=True)

    assert sum(result is None for result in results) == 1
    assert sum(isinstance(result, ValueError) for result in results) == 1
    await session.close()


@pytest.mark.asyncio
async def test_new_delegation_during_send_remains_active(monkeypatch):
    def delegation(identifier: str) -> str:
        return json.dumps(
            {
                "type": "delegation.created",
                "item": {
                    "type": "delegation",
                    "target": "client",
                    "id": identifier,
                    "content": [{"type": "input_text", "text": identifier}],
                },
            }
        )

    provider = FakeProvider(
        [
            httpx.Response(
                200,
                text=SDP,
                headers={"Location": "/v1/realtime/calls/rtc_new-delegation"},
            )
        ]
    )
    socket = FakeWebSocket([delegation("delegate-old")])
    send_started = asyncio.Event()
    release_send = asyncio.Event()
    original_send = socket.send

    async def blocking_send(data: str) -> None:
        if json.loads(data).get("delegation_item_id") == "delegate-old":
            send_started.set()
            await release_send.wait()
        await original_send(data)

    socket.send = blocking_send
    _install_fakes(monkeypatch, provider, [socket])
    client = OpenAIOAuthRealtimeClient(provider)
    session = await client.create_session(SDP)
    assert (await anext(session.events())).delegation_id == "delegate-old"
    old_submit = asyncio.create_task(
        session.submit_delegation_result("delegate-old", "old result")
    )
    await send_started.wait()
    socket.incoming.put_nowait(delegation("delegate-new"))
    cancelled = await anext(session.events())
    new_event = await anext(session.events())
    assert (cancelled.type, new_event.delegation_id) == (
        "delegation_cancelled",
        "delegate-new",
    )
    release_send.set()
    await old_submit

    await session.submit_delegation_result("delegate-new", "new result")

    assert any(
        message.get("delegation_item_id") == "delegate-new" for message in socket.sent
    )
    await session.close()


@pytest.mark.asyncio
async def test_concurrency_limit_counts_pending_and_recovers_after_failure(monkeypatch):
    provider = FakeProvider([])
    started = asyncio.Event()
    release = asyncio.Event()

    class BlockingHttpClient(FakeHttpClient):
        async def post(self, url: str, **kwargs):
            started.set()
            await release.wait()
            raise httpx.ConnectError("lost")

    FakeHttpClient.provider = provider
    monkeypatch.setattr(
        "astrbot.core.provider.oauth.openai_oauth_realtime.httpx.AsyncClient",
        BlockingHttpClient,
    )
    client = OpenAIOAuthRealtimeClient(provider, max_sessions=1)
    first = asyncio.create_task(client.create_session(SDP))
    await started.wait()

    with pytest.raises(RuntimeError, match="并发上限"):
        await client.create_session(SDP)
    release.set()
    with pytest.raises(RuntimeError):
        await first

    assert client.session_count == 0


@pytest.mark.asyncio
async def test_binary_frame_before_ready_fails_create_and_releases_session(monkeypatch):
    provider = FakeProvider(
        [
            httpx.Response(
                200,
                text=SDP,
                headers={"Location": "/v1/realtime/calls/rtc_binary"},
            )
        ]
    )
    socket = FakeWebSocket([b"unexpected"])
    _install_fakes(monkeypatch, provider, [socket])
    client = OpenAIOAuthRealtimeClient(provider, event_queue_size=1)
    with pytest.raises(RuntimeError, match="就绪前关闭"):
        await client.create_session(SDP)

    assert socket.closed
    assert client.session_count == 0
    await client.close()


@pytest.mark.asyncio
async def test_event_queue_overflow_closes_session(monkeypatch):
    provider = FakeProvider(
        [
            httpx.Response(
                200,
                text=SDP,
                headers={"Location": "/v1/realtime/calls/rtc_overflow"},
            )
        ]
    )
    socket = FakeWebSocket()
    _install_fakes(monkeypatch, provider, [socket])
    client = OpenAIOAuthRealtimeClient(provider, event_queue_size=1)
    session = await client.create_session(SDP)
    event = json.dumps({"type": "input_transcript.added", "item": {"text": "x"}})

    socket.incoming.put_nowait(event)
    socket.incoming.put_nowait(event)
    await asyncio.wait_for(session.wait_closed(), timeout=1)

    assert socket.closed
    assert client.session_count == 0
    assert (await anext(session.events())).type == "closed"
    await client.close()


@pytest.mark.asyncio
async def test_session_ttl_closes_verified_sideband(monkeypatch):
    provider = FakeProvider(
        [
            httpx.Response(
                200,
                text=SDP,
                headers={"Location": "/v1/realtime/calls/rtc_ttl"},
            )
        ]
    )
    socket = FakeWebSocket()
    _install_fakes(monkeypatch, provider, [socket])
    client = OpenAIOAuthRealtimeClient(provider, session_ttl=0.02, idle_timeout=10)
    session = await client.create_session(SDP)

    await asyncio.wait_for(session.wait_closed(), timeout=1)

    assert {"type": "session.close"} in socket.sent
    assert client.session_count == 0


@pytest.mark.asyncio
async def test_client_close_cancels_pending_creation_and_rejects_new_work(monkeypatch):
    provider = FakeProvider([])
    started = asyncio.Event()

    class BlockingHttpClient(FakeHttpClient):
        async def post(self, url: str, **kwargs):
            started.set()
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

    FakeHttpClient.provider = provider
    monkeypatch.setattr(
        "astrbot.core.provider.oauth.openai_oauth_realtime.httpx.AsyncClient",
        BlockingHttpClient,
    )
    client = OpenAIOAuthRealtimeClient(provider)
    pending = asyncio.create_task(client.create_session(SDP))
    await started.wait()

    await client.close()

    with pytest.raises(asyncio.CancelledError):
        await pending
    assert client.session_count == 0
    with pytest.raises(RuntimeError, match="正在关闭"):
        await client.create_session(SDP)


@pytest.mark.asyncio
async def test_close_is_idempotent_sends_only_verified_ws_close(monkeypatch):
    provider = FakeProvider(
        [
            httpx.Response(
                200,
                text=SDP,
                headers={"Location": "/v1/realtime/calls/rtc_close"},
            )
        ]
    )
    socket = FakeWebSocket()
    _install_fakes(monkeypatch, provider, [socket])
    client = OpenAIOAuthRealtimeClient(provider)
    session = await client.create_session(SDP)

    await asyncio.gather(session.close(), session.close())

    assert [
        message for message in socket.sent if message["type"] == "session.close"
    ] == [{"type": "session.close"}]
    assert client.session_count == 0
    await client.close()


@pytest.mark.asyncio
async def test_cancelled_close_continues_cleanup_and_releases_slot(monkeypatch):
    provider = FakeProvider(
        [
            httpx.Response(
                200,
                text=SDP,
                headers={"Location": "/v1/realtime/calls/rtc_cancel-close"},
            )
        ]
    )
    socket = FakeWebSocket()
    close_send_started = asyncio.Event()

    async def blocking_send(data: str) -> None:
        if json.loads(data).get("type") == "session.close":
            close_send_started.set()
            await asyncio.Event().wait()

    socket.send = blocking_send
    _install_fakes(monkeypatch, provider, [socket])
    client = OpenAIOAuthRealtimeClient(provider, close_timeout=0.01, send_timeout=10)
    session = await client.create_session(SDP)
    close_task = asyncio.create_task(session.close())
    await close_send_started.wait()

    close_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await close_task
    await asyncio.wait_for(session.wait_closed(), timeout=1)
    await asyncio.wait_for(session.close(), timeout=1)

    assert session.closed
    assert client.session_count == 0
