import ssl

import pytest

from astrbot.core.utils import network_utils
from astrbot.core.utils.proxy_route import set_global_network_config


@pytest.fixture(autouse=True)
def _reset_global_network_config():
    set_global_network_config(http_proxy="", no_proxy=[])
    yield
    set_global_network_config(http_proxy="", no_proxy=[])


def test_create_proxy_client_reuses_shared_ssl_context(
    monkeypatch: pytest.MonkeyPatch,
):
    captured_calls: list[dict] = []
    headers = {"X-Test-Header": "value"}

    class _FakeAsyncClient:
        def __init__(self, **kwargs):
            captured_calls.append(kwargs)

    monkeypatch.setattr(network_utils.httpx, "AsyncClient", _FakeAsyncClient)

    network_utils.create_proxy_client("OpenAI", {"proxy_mode": "direct"})
    network_utils.create_proxy_client(
        "OpenAI",
        {"proxy_mode": "custom", "proxy_url": "http://127.0.0.1:7890"},
    )
    network_utils.create_proxy_client(
        "OpenAI", {"proxy_mode": "direct"}, headers=headers
    )
    network_utils.create_proxy_client("OpenAI", {"proxy_mode": "inherit"})

    assert len(captured_calls) == 4
    assert "proxy" not in captured_calls[0]
    assert captured_calls[1]["proxy"] == "http://127.0.0.1:7890"
    assert captured_calls[2]["headers"] is headers
    assert "proxy" not in captured_calls[3]
    assert captured_calls[0]["trust_env"] is False
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
