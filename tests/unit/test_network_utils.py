import ssl

import pytest

from astrbot.core.platform import proxy as platform_proxy
from astrbot.core.utils import network_utils


def test_create_proxy_client_reuses_shared_ssl_context(
    monkeypatch: pytest.MonkeyPatch,
):
    captured_calls: list[dict] = []
    headers = {"X-Test-Header": "value"}

    class _FakeAsyncClient:
        def __init__(self, **kwargs):
            captured_calls.append(kwargs)

    monkeypatch.setattr(network_utils.httpx, "AsyncClient", _FakeAsyncClient)

    network_utils.create_proxy_client("OpenAI")
    network_utils.create_proxy_client("OpenAI", proxy="http://127.0.0.1:7890")
    network_utils.create_proxy_client("OpenAI", headers=headers)
    network_utils.create_proxy_client("OpenAI", proxy="")

    assert len(captured_calls) == 4
    assert "proxy" not in captured_calls[0]
    assert captured_calls[1]["proxy"] == "http://127.0.0.1:7890"
    assert captured_calls[2]["headers"] is headers
    assert "proxy" not in captured_calls[3]
    assert isinstance(captured_calls[0]["verify"], ssl.SSLContext)
    assert captured_calls[0]["verify"] is captured_calls[1]["verify"]
    assert captured_calls[1]["verify"] is captured_calls[2]["verify"]
    assert captured_calls[2]["verify"] is captured_calls[3]["verify"]


def test_create_proxy_client_allows_verify_override(
    monkeypatch: pytest.MonkeyPatch,
):
    captured_calls: list[dict] = []
    custom_verify = ssl.create_default_context()

    class _FakeAsyncClient:
        def __init__(self, **kwargs):
            captured_calls.append(kwargs)

    monkeypatch.setattr(network_utils.httpx, "AsyncClient", _FakeAsyncClient)

    network_utils.create_proxy_client("OpenAI", verify=custom_verify)

    assert len(captured_calls) == 1
    assert captured_calls[0]["verify"] is custom_verify


def test_create_platform_client_session_uses_socks_connector(
    monkeypatch: pytest.MonkeyPatch,
):
    captured_session_kwargs: list[dict] = []
    captured_connector_kwargs: list[dict] = []
    connector = object()

    def fake_from_url(url, **kwargs):
        captured_connector_kwargs.append({"url": url, **kwargs})
        return connector

    def fake_client_session(**kwargs):
        captured_session_kwargs.append(kwargs)
        return object()

    monkeypatch.setattr(
        platform_proxy.ProxyConnector,
        "from_url",
        staticmethod(fake_from_url),
    )
    monkeypatch.setattr(platform_proxy.aiohttp, "ClientSession", fake_client_session)

    platform_proxy.create_platform_client_session(
        "socks5://127.0.0.1:1080",
        trust_env=True,
    )

    assert captured_connector_kwargs == [{"url": "socks5://127.0.0.1:1080"}]
    assert captured_session_kwargs == [{"trust_env": True, "connector": connector}]
