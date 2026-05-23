from unittest.mock import AsyncMock, patch

import pytest

from astrbot.core.platform.sources.misskey.misskey_api import StreamingClient
from astrbot.core.platform.sources.websocket_security import (
    require_secure_transport_url,
    to_websocket_url,
)


def test_require_secure_transport_url_allows_local_ws() -> None:
    parsed = require_secure_transport_url(
        "ws://localhost:5140/satori/v1/events",
        label="Satori WebSocket URL",
        allowed_schemes={"ws", "wss"},
    )

    assert parsed.scheme == "ws"


def test_require_secure_transport_url_rejects_public_ws() -> None:
    with pytest.raises(
        ValueError,
        match=r"must use secure transport \(https or wss\) for non-local endpoints",
    ):
        require_secure_transport_url(
            "ws://example.com/events",
            label="Satori WebSocket URL",
            allowed_schemes={"ws", "wss"},
        )


def test_require_secure_transport_url_rejects_bare_hostname_ws() -> None:
    with pytest.raises(
        ValueError,
        match=r"must use secure transport \(https or wss\) for non-local endpoints",
    ):
        require_secure_transport_url(
            "ws://prod/events",
            label="Satori WebSocket URL",
            allowed_schemes={"ws", "wss"},
        )


def test_to_websocket_url_converts_https_to_wss() -> None:
    assert to_websocket_url("https://example.com") == "wss://example.com"
    assert (
        to_websocket_url("http://localhost:5140/satori/v1")
        == "ws://localhost:5140/satori/v1"
    )


def test_to_websocket_url_rejects_unsupported_scheme() -> None:
    with pytest.raises(
        ValueError,
        match="Misskey instance URL must use the http, https, ws, or wss scheme",
    ):
        to_websocket_url("ftp://example.com", label="Misskey instance URL")


@pytest.mark.asyncio
async def test_streaming_client_connects_with_secure_websocket_url() -> None:
    client = StreamingClient("https://example.com", "token")
    websocket = AsyncMock()

    with patch(
        "astrbot.core.platform.sources.misskey.misskey_api.websockets.connect",
        new_callable=AsyncMock,
    ) as mock_connect:
        mock_connect.return_value = websocket

        assert await client.connect() is True

    mock_connect.assert_awaited_once_with(
        "wss://example.com/streaming?i=token",
        ping_interval=30,
        ping_timeout=10,
    )


@pytest.mark.asyncio
async def test_streaming_client_rejects_remote_http_instance() -> None:
    client = StreamingClient("http://example.com", "token")

    with patch(
        "astrbot.core.platform.sources.misskey.misskey_api.websockets.connect",
        new_callable=AsyncMock,
    ) as mock_connect:
        assert await client.connect() is False

    mock_connect.assert_not_awaited()
