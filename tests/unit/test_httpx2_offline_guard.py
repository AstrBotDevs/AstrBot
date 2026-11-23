"""Keep optional HTTPX2 real transports offline without blocking local fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import import_module
from importlib.util import find_spec
from threading import Thread
from types import ModuleType
from unittest.mock import AsyncMock, Mock

import pytest

EXTERNAL_URL = "https://no-network.invalid/private"
OFFLINE_ERROR = "External network access is disabled in tests: no-network.invalid"


@pytest.fixture
def httpx2_module() -> ModuleType:
    if find_spec("httpx2") is None:
        pytest.skip("Optional httpx2 is not installed")
    # An installed package with a broken dependency must fail, rather than skip.
    return import_module("httpx2")


@pytest.fixture
def local_server() -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", EXTERNAL_URL)
                body = b""
            else:
                self.send_response(200)
                body = b"local fixture response"
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            """Keep the fixture server's request log out of test output."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


@pytest.mark.parametrize("proxy", [None, "http://127.0.0.1:9"])
def test_httpx2_sync_rejects_external_target_before_direct_or_proxy_pool(
    httpx2_module: ModuleType, monkeypatch: pytest.MonkeyPatch, proxy: str | None
) -> None:
    transport = httpx2_module.HTTPTransport(proxy=proxy, trust_env=False)
    pool_call = Mock(side_effect=AssertionError("Unexpected HTTP pool I/O"))
    monkeypatch.setattr(transport._pool, "handle_request", pool_call)
    with httpx2_module.Client(transport=transport, trust_env=False) as client:
        with pytest.raises(RuntimeError, match=OFFLINE_ERROR):
            client.get(EXTERNAL_URL)
    pool_call.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("proxy", [None, "http://127.0.0.1:9"])
async def test_httpx2_async_rejects_external_target_before_direct_or_proxy_pool(
    httpx2_module: ModuleType, monkeypatch: pytest.MonkeyPatch, proxy: str | None
) -> None:
    transport = httpx2_module.AsyncHTTPTransport(proxy=proxy, trust_env=False)
    pool_call = AsyncMock(side_effect=AssertionError("Unexpected HTTP pool I/O"))
    monkeypatch.setattr(transport._pool, "handle_async_request", pool_call)
    async with httpx2_module.AsyncClient(
        transport=transport, trust_env=False
    ) as client:
        with pytest.raises(RuntimeError, match=OFFLINE_ERROR):
            await client.get(EXTERNAL_URL)
    pool_call.assert_not_awaited()


def test_httpx2_sync_allows_local_server_but_blocks_external_redirect(
    httpx2_module: ModuleType, monkeypatch: pytest.MonkeyPatch, local_server: str
) -> None:
    transport = httpx2_module.HTTPTransport(trust_env=False)
    real_pool_request = transport._pool.handle_request

    def local_pool_request(request):
        assert request.url.host == b"127.0.0.1", "External redirect reached the pool"
        return real_pool_request(request)

    pool_call = Mock(side_effect=local_pool_request)
    monkeypatch.setattr(transport._pool, "handle_request", pool_call)
    with httpx2_module.Client(
        transport=transport, trust_env=False, follow_redirects=True, timeout=2
    ) as client:
        response = client.get(f"{local_server}/ok")
        assert response.status_code == 200
        assert response.text == "local fixture response"
        with pytest.raises(RuntimeError, match=OFFLINE_ERROR):
            client.get(f"{local_server}/redirect")
    assert pool_call.call_count == 2


@pytest.mark.asyncio
async def test_httpx2_async_allows_local_server_but_blocks_external_redirect(
    httpx2_module: ModuleType, monkeypatch: pytest.MonkeyPatch, local_server: str
) -> None:
    transport = httpx2_module.AsyncHTTPTransport(trust_env=False)
    real_pool_request = transport._pool.handle_async_request

    async def local_pool_request(request):
        assert request.url.host == b"127.0.0.1", "External redirect reached the pool"
        return await real_pool_request(request)

    pool_call = AsyncMock(side_effect=local_pool_request)
    monkeypatch.setattr(transport._pool, "handle_async_request", pool_call)
    async with httpx2_module.AsyncClient(
        transport=transport, trust_env=False, follow_redirects=True, timeout=2
    ) as client:
        response = await client.get(f"{local_server}/ok")
        assert response.status_code == 200
        assert response.text == "local fixture response"
        with pytest.raises(RuntimeError, match=OFFLINE_ERROR):
            await client.get(f"{local_server}/redirect")
    assert pool_call.await_count == 2


def test_httpx2_sync_mock_transport_remains_available(
    httpx2_module: ModuleType,
) -> None:
    handler = Mock(return_value=httpx2_module.Response(200, text="in-process fixture"))
    with httpx2_module.Client(
        transport=httpx2_module.MockTransport(handler), trust_env=False
    ) as client:
        response = client.get(EXTERNAL_URL)
    assert response.text == "in-process fixture"
    handler.assert_called_once()


@pytest.mark.asyncio
async def test_httpx2_async_mock_transport_remains_available(
    httpx2_module: ModuleType,
) -> None:
    handler = AsyncMock(
        return_value=httpx2_module.Response(200, text="in-process fixture")
    )
    async with httpx2_module.AsyncClient(
        transport=httpx2_module.MockTransport(handler), trust_env=False
    ) as client:
        response = await client.get(EXTERNAL_URL)
    assert response.text == "in-process fixture"
    handler.assert_awaited_once()
