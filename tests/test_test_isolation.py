"""Verify that the test process is offline while local fixtures remain usable."""

import http.client
import json
import os
import socket
from pathlib import Path

import aiohttp
import httpx
import pytest


@pytest.mark.parametrize("host", ["example.com", "192.0.2.1", "2001:db8::1"])
def test_external_resolution_is_rejected(host):
    with pytest.raises(RuntimeError, match="External network access is disabled"):
        socket.getaddrinfo(host, 443)


@pytest.mark.parametrize("method", ["connect", "connect_ex"])
def test_external_connection_is_rejected_before_io(method):
    with socket.socket() as client:
        with pytest.raises(RuntimeError, match="External network access is disabled"):
            getattr(client, method)(("192.0.2.1", 443))


def test_external_datagram_is_rejected_before_io():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        with pytest.raises(RuntimeError, match="External network access is disabled"):
            client.sendto(b"test", ("192.0.2.1", 443))


def test_loopback_fixture_can_exchange_data():
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        server.settimeout(1)
        with socket.create_connection(server.getsockname(), timeout=1) as client:
            connection, _ = server.accept()
            with connection:
                connection.settimeout(1)
                client.sendall(b"local fixture")
                assert connection.recv(32) == b"local fixture"


def test_shared_config_saves_only_inside_current_test_root():
    from astrbot.core import astrbot_config

    path = Path(astrbot_config.config_path).resolve()
    assert path.is_relative_to(Path(os.environ["ASTRBOT_ROOT"]).resolve())
    astrbot_config["isolation_probe"] = "current test"
    astrbot_config.save_config()
    assert (
        json.loads(path.read_text(encoding="utf-8-sig"))["isolation_probe"]
        == "current test"
    )
    assert "_config_path" not in astrbot_config


@pytest.mark.parametrize("proxy", [None, "http://127.0.0.1:9"])
def test_real_http_transport_rejects_external_targets_before_proxy_io(proxy):
    with httpx.Client(proxy=proxy) as client:
        with pytest.raises(RuntimeError, match="External network access is disabled"):
            client.get("https://example.com/isolation-probe")


@pytest.mark.asyncio
async def test_async_http_transport_rejects_external_proxy_targets():
    async with httpx.AsyncClient(proxy="http://127.0.0.1:9") as client:
        with pytest.raises(RuntimeError, match="External network access is disabled"):
            await client.get("https://example.com/isolation-probe")


@pytest.mark.asyncio
async def test_aiohttp_rejects_external_proxy_targets_before_connecting():
    async with aiohttp.ClientSession() as client:
        with pytest.raises(RuntimeError, match="External network access is disabled"):
            await client.get(
                "https://example.com/isolation-probe", proxy="http://127.0.0.1:9"
            )


def test_stdlib_tunnel_checks_destination_before_connecting():
    connection = http.client.HTTPConnection("127.0.0.1", 9)
    connection.set_tunnel("example.com", 443)
    try:
        with pytest.raises(RuntimeError, match="External network access is disabled"):
            connection.connect()
    finally:
        connection.close()


def test_explicit_mock_transport_can_test_external_url_semantics():
    seen = []

    def respond(request):
        seen.append(str(request.url))
        return httpx.Response(200, json={"offline": True})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert client.get("https://example.com/fake").json() == {"offline": True}
    assert seen == ["https://example.com/fake"]
