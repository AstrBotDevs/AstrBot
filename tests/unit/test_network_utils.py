import ssl

import pytest

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


def test_create_proxy_client_shares_http_ssl_singleton_and_optional_kwargs(
    monkeypatch: pytest.MonkeyPatch,
):
    from astrbot.core.utils import http_ssl

    captured_calls: list[dict] = []

    class _FakeAsyncClient:
        def __init__(self, **kwargs):
            captured_calls.append(kwargs)

    monkeypatch.setattr(network_utils.httpx, "AsyncClient", _FakeAsyncClient)

    network_utils.create_proxy_client(
        "Gemini",
        timeout=30,
        trust_env=True,
        follow_redirects=True,
        base_url="https://example.com",
    )

    assert len(captured_calls) == 1
    assert captured_calls[0]["verify"] is http_ssl.build_ssl_context_with_certifi()
    assert captured_calls[0]["timeout"] == 30
    assert captured_calls[0]["trust_env"] is True
    assert captured_calls[0]["follow_redirects"] is True
    assert captured_calls[0]["base_url"] == "https://example.com"


def test_create_proxy_client_preserves_explicit_none_timeout_and_redacts_log(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    captured_calls: list[dict] = []

    class _FakeAsyncClient:
        def __init__(self, **kwargs):
            captured_calls.append(kwargs)

    monkeypatch.setattr(network_utils.httpx, "AsyncClient", _FakeAsyncClient)

    with caplog.at_level("INFO"):
        network_utils.create_proxy_client(
            "DeepSeek STT",
            proxy="http://user:secret-pass@127.0.0.1:7890",
            timeout=None,
        )

    assert len(captured_calls) == 1
    assert "timeout" in captured_calls[0]
    assert captured_calls[0]["timeout"] is None
    assert captured_calls[0]["proxy"] == "http://user:secret-pass@127.0.0.1:7890"
    assert "secret-pass" not in caplog.text
    assert "127.0.0.1:7890" in caplog.text
