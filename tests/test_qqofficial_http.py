import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import botpy.errors
import pytest
from botpy import Intents

from astrbot.core.platform.sources.qqofficial import (
    qqofficial_http,
    qqofficial_message_event,
)
from astrbot.core.platform.sources.qqofficial.qqofficial_http import (
    QQOfficialHttp,
    QQOfficialHttpClosedError,
    QQOfficialHttpOverloadedError,
    _parse_response,
)
from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
    APIReturnNoneError,
    QQOfficialMessageEvent,
)
from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
    botClient,
)
from astrbot.core.platform.sources.qqofficial_webhook.qo_webhook_server import (
    QQOfficialWebhook,
)


class _FakeToken:
    app_id = "app-id"

    async def check_token(self) -> None:
        """Pretend that the cached QQ token is valid."""

    def get_string(self) -> str:
        """Return a deterministic authorization header.

        Returns:
            Fake authorization token.
        """
        return "QQBot fake-token"


class _FakeSession:
    def __init__(self, connector=None, request_context=None) -> None:
        self.closed = False
        self.connector = connector
        self.request_context = request_context
        self.request_count = 0

    def request(self, **kwargs):
        """Return the configured async request context.

        Args:
            **kwargs: Ignored aiohttp request arguments.

        Returns:
            Configured async request context.
        """
        del kwargs
        self.request_count += 1
        return self.request_context

    async def close(self) -> None:
        """Close the fake session and its real connector."""
        self.closed = True
        if self.connector is not None:
            await self.connector.close()


@pytest.mark.asyncio
async def test_response_parser_preserves_qq_error_mapping():
    """Return JSON success payloads and map HTTP failures to botpy errors."""
    success = SimpleNamespace(
        status=200,
        headers={"content-type": "application/json; charset=utf-8"},
        json=AsyncMock(return_value={"id": "message-id"}),
        text=AsyncMock(),
    )
    failure = SimpleNamespace(
        status=500,
        headers={"content-type": "application/json"},
        json=AsyncMock(return_value={"message": "temporary failure"}),
        text=AsyncMock(),
    )

    assert await _parse_response(success) == {"id": "message-id"}
    with pytest.raises(botpy.errors.ServerError, match="temporary failure"):
        await _parse_response(failure)


def _immediate_retry(max_attempts: int = 3, retry_errors=None):
    """Build a no-delay retry decorator for deterministic tests.

    Args:
        max_attempts: Maximum function attempts.
        retry_errors: Ignored exception filter for production signature compatibility.

    Returns:
        Async retry decorator.
    """
    del retry_errors

    def decorate(function):
        async def wrapped(*args, **kwargs):
            last_error = None
            for _ in range(max_attempts):
                try:
                    return await function(*args, **kwargs)
                except APIReturnNoneError as exc:
                    last_error = exc
            assert last_error is not None
            raise last_error

        return wrapped

    return decorate


@pytest.fixture
def immediate_retries(monkeypatch) -> None:
    """Disable retry waits while preserving attempt counts in tests."""
    monkeypatch.setattr(
        qqofficial_message_event,
        "_qqofficial_retry",
        _immediate_retry,
    )


@pytest.mark.asyncio
async def test_http_session_reuses_keepalive_connector_and_stays_closed(monkeypatch):
    """Reuse one keep-alive pool and never recreate it after shutdown."""
    sessions: list[_FakeSession] = []

    def create_session(**kwargs) -> _FakeSession:
        session = _FakeSession(connector=kwargs["connector"])
        sessions.append(session)
        return session

    monkeypatch.setattr(qqofficial_http.aiohttp, "ClientSession", create_session)
    http = QQOfficialHttp(timeout=20)
    http._token = _FakeToken()

    await http.check_session()
    await http.check_session()

    assert len(sessions) == 1
    assert sessions[0].connector.force_close is False
    assert sessions[0].connector.limit == 32
    assert sessions[0].connector.limit_per_host == 16

    await http.close()

    with pytest.raises(QQOfficialHttpClosedError):
        await http.check_session()
    assert len(sessions) == 1


@pytest.mark.asyncio
async def test_close_during_token_refresh_does_not_create_session(monkeypatch):
    """Prevent direct session checks from reopening transport during shutdown."""
    refresh_started = asyncio.Event()
    finish_refresh = asyncio.Event()
    sessions: list[_FakeSession] = []

    class BlockingToken(_FakeToken):
        async def check_token(self) -> None:
            refresh_started.set()
            await finish_refresh.wait()

    def create_session(**kwargs) -> _FakeSession:
        session = _FakeSession(connector=kwargs["connector"])
        sessions.append(session)
        return session

    monkeypatch.setattr(qqofficial_http.aiohttp, "ClientSession", create_session)
    http = QQOfficialHttp(timeout=20)
    http._token = BlockingToken()
    check_task = asyncio.create_task(http.check_session())
    await refresh_started.wait()
    close_task = asyncio.create_task(http.close())
    await asyncio.sleep(0)
    finish_refresh.set()

    with pytest.raises(QQOfficialHttpClosedError):
        await check_task
    await close_task
    assert sessions == []


@pytest.mark.asyncio
async def test_websocket_and_webhook_adapters_share_bounded_http_transport():
    """Use the same managed HTTP transport for both QQ adapter modes."""
    websocket_client = botClient(intents=Intents(public_messages=True), bot_log=False)
    webhook = QQOfficialWebhook(
        {
            "appid": "app-id",
            "secret": "secret",
            "is_sandbox": False,
        },
        asyncio.Queue(),
        SimpleNamespace(),
    )

    assert isinstance(websocket_client.http, QQOfficialHttp)
    assert isinstance(webhook.http, QQOfficialHttp)

    await websocket_client.close()
    await webhook.http.close()


@pytest.mark.asyncio
async def test_request_queue_is_bounded_and_close_cancels_owned_tasks():
    """Reject excess work and cancel active or queued requests during shutdown."""
    http = QQOfficialHttp(
        timeout=20,
        max_concurrent_requests=1,
        max_pending_requests=2,
        queue_timeout=1,
    )
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    queued_started = asyncio.Event()

    async def hold_first_slot() -> None:
        async with http.request_slot():
            first_started.set()
            await release_first.wait()

    async def wait_for_slot() -> None:
        queued_started.set()
        async with http.request_slot():
            return

    first_task = asyncio.create_task(hold_first_slot())
    await first_started.wait()
    queued_task = asyncio.create_task(wait_for_slot())
    await queued_started.wait()
    await asyncio.sleep(0)

    with pytest.raises(QQOfficialHttpOverloadedError):
        async with http.request_slot():
            pass

    await http.close()

    assert first_task.cancelled()
    assert queued_task.cancelled()
    assert http._pending_requests == 0


@pytest.mark.asyncio
async def test_transport_does_not_retry_connection_resets(monkeypatch):
    """Leave retries to AstrBot's single bounded retry policy."""

    class ResetRequestContext:
        async def __aenter__(self):
            raise ConnectionResetError("connection reset")

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            del exc_type, exc, traceback

    session = _FakeSession(request_context=ResetRequestContext())
    monkeypatch.setattr(
        qqofficial_http.aiohttp,
        "ClientSession",
        lambda **kwargs: setattr(session, "connector", kwargs["connector"]) or session,
    )
    http = QQOfficialHttp(timeout=20)
    http._token = _FakeToken()

    with pytest.raises(ConnectionResetError):
        await http.request(SimpleNamespace(method="POST", path="/test", url="url"))

    assert session.request_count == 1
    await http.close()


@pytest.mark.asyncio
async def test_send_retry_policy_has_one_owner_and_three_attempts(immediate_retries):
    """Retry an empty QQ send response exactly three times in the send layer."""
    send = AsyncMock(return_value=None)
    event = object.__new__(QQOfficialMessageEvent)

    with pytest.raises(APIReturnNoneError):
        await event._send_with_markdown_fallback(
            send_func=send,
            payload={"content": "hello"},
            plain_text="hello",
        )

    assert send.await_count == 3


@pytest.mark.asyncio
async def test_semantic_fallbacks_share_the_three_attempt_retry_budget(
    immediate_retries,
):
    """Keep proactive and stream fallbacks inside one logical send budget."""
    event = object.__new__(QQOfficialMessageEvent)
    send = AsyncMock(
        side_effect=[
            botpy.errors.ForbiddenError("passive reply rejected"),
            botpy.errors.ServerError(event.STREAM_MARKDOWN_NEWLINE_ERROR),
            None,
        ]
    )

    with pytest.raises(APIReturnNoneError):
        await event._send_with_markdown_fallback(
            send_func=send,
            payload={"content": "hello", "msg_id": "message-id"},
            plain_text="hello",
            stream={"state": 10},
        )

    assert send.await_count == 3


@pytest.mark.asyncio
async def test_failed_image_upload_log_omits_base64_payload(
    monkeypatch,
    immediate_retries,
):
    """Log only image size when all upload attempts return no response."""
    warning = Mock()
    monkeypatch.setattr(qqofficial_message_event.logger, "warning", warning)
    event = object.__new__(QQOfficialMessageEvent)
    request = AsyncMock(return_value=None)
    event.bot = SimpleNamespace(
        api=SimpleNamespace(_http=SimpleNamespace(request=request))
    )
    image_base64 = "sensitive-base64-payload"

    with pytest.raises(APIReturnNoneError):
        await event.upload_group_and_c2c_image(
            image_base64,
            event.IMAGE_FILE_TYPE,
            openid="user-id",
        )

    assert request.await_count == 3
    assert image_base64 not in str(warning.call_args)
    assert warning.call_args.args[-1] == len(image_base64)
