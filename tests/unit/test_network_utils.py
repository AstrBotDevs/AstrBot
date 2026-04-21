import ssl

import pytest

from astrbot.core.utils import network_utils


def test_create_proxy_client_reuses_shared_ssl_context(
    monkeypatch: pytest.MonkeyPatch,
):
    captured_calls: list[dict] = []

    class _FakeAsyncClient:
        def __init__(self, **kwargs):
            captured_calls.append(kwargs)

    monkeypatch.setattr(network_utils.httpx, "AsyncClient", _FakeAsyncClient)

    network_utils.create_proxy_client("OpenAI")
    network_utils.create_proxy_client("OpenAI", proxy="http://127.0.0.1:7890")

    assert len(captured_calls) == 2
    assert isinstance(captured_calls[0]["verify"], ssl.SSLContext)
    assert captured_calls[0]["verify"] is captured_calls[1]["verify"]
