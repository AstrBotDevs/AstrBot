import ssl

import httpx
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


# --- x-stainless-* telemetry header stripping (#8531) ---------------------------


CHAT_COMPLETION_BODY = {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "created": 0,
    "model": "gpt-test",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "ok"},
            "finish_reason": "stop",
        }
    ],
}

ANTHROPIC_MESSAGE_BODY = {
    "id": "msg_test",
    "type": "message",
    "role": "assistant",
    "model": "claude-test",
    "content": [{"type": "text", "text": "ok"}],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 1, "output_tokens": 1},
}


def _stainless_headers(sent: dict[str, str]) -> list[str]:
    return sorted(key for key in sent if key.lower().startswith("x-stainless-"))


def _mock_httpx_module(sent: dict[str, str], body: dict, **client_kwargs):
    """A stand-in for the ``httpx`` module whose clients answer from a mock transport.

    ``create_proxy_client`` builds its client from the module it is handed, so this
    lets the test exercise the real client construction (event hooks included)
    without opening a socket. ``verify``/``proxy`` are dropped because a
    ``MockTransport`` handles neither.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        sent.clear()
        sent.update(dict(request.headers))
        return httpx.Response(200, json=body)

    class _Module:
        @staticmethod
        def AsyncClient(**kwargs):
            kwargs.pop("verify", None)
            kwargs.pop("proxy", None)
            return httpx.AsyncClient(
                transport=httpx.MockTransport(handler), **kwargs, **client_kwargs
            )

    return _Module


@pytest.mark.asyncio
async def test_openai_sdk_sends_stainless_headers_without_the_hook():
    """Guards the premise of #8531: the SDK really does stamp these headers on."""
    import openai

    sent: dict[str, str] = {}
    module = _mock_httpx_module(sent, CHAT_COMPLETION_BODY)

    async with module.AsyncClient() as http_client:
        client = openai.AsyncOpenAI(
            api_key="sk-test", base_url="https://relay.test/v1", http_client=http_client
        )
        await client.chat.completions.create(
            model="gpt-test", messages=[{"role": "user", "content": "hi"}]
        )

    assert _stainless_headers(sent) == [
        "x-stainless-arch",
        "x-stainless-async",
        "x-stainless-lang",
        "x-stainless-os",
        "x-stainless-package-version",
        "x-stainless-read-timeout",
        "x-stainless-retry-count",
        "x-stainless-runtime",
        "x-stainless-runtime-version",
    ]


@pytest.mark.asyncio
async def test_openai_sdk_sends_no_stainless_headers_through_create_proxy_client():
    import openai

    sent: dict[str, str] = {}
    http_client = network_utils.create_proxy_client(
        "OpenAI", httpx_module=_mock_httpx_module(sent, CHAT_COMPLETION_BODY)
    )

    async with http_client:
        client = openai.AsyncOpenAI(
            api_key="sk-test", base_url="https://relay.test/v1", http_client=http_client
        )
        await client.chat.completions.create(
            model="gpt-test", messages=[{"role": "user", "content": "hi"}]
        )

    assert _stainless_headers(sent) == []
    # Everything the request actually needs must survive.
    assert sent["authorization"] == "Bearer sk-test"
    assert sent["content-type"] == "application/json"


@pytest.mark.asyncio
async def test_anthropic_sdk_sends_no_stainless_headers_through_create_proxy_client():
    """The Anthropic SDK is Stainless-generated too, and adds x-stainless-timeout."""
    import anthropic

    sent: dict[str, str] = {}
    http_client = network_utils.create_proxy_client(
        "Anthropic", httpx_module=_mock_httpx_module(sent, ANTHROPIC_MESSAGE_BODY)
    )

    async with http_client:
        client = anthropic.AsyncAnthropic(
            api_key="sk-test", base_url="https://relay.test", http_client=http_client
        )
        await client.messages.create(
            model="claude-test",
            max_tokens=16,
            messages=[{"role": "user", "content": "hi"}],
        )

    assert _stainless_headers(sent) == []
    assert sent["x-api-key"] == "sk-test"


@pytest.mark.asyncio
async def test_stripping_survives_the_proxy_transport():
    """A proxy makes httpx route through ``mounts``, which outrank ``transport=``.

    This is why the stripping is an event hook and not an ``AsyncHTTPTransport``
    subclass: a custom transport would be bypassed here, silently leaving the
    headers on for every user who configured a proxy.
    """
    sent: dict[str, str] = {}
    reached_proxy = False

    def proxy_handler(request: httpx.Request) -> httpx.Response:
        nonlocal reached_proxy
        reached_proxy = True
        sent.clear()
        sent.update(dict(request.headers))
        return httpx.Response(200, json=CHAT_COMPLETION_BODY)

    http_client = network_utils.create_proxy_client(
        "OpenAI",
        proxy="http://127.0.0.1:7890",
        httpx_module=_mock_httpx_module(
            sent,
            CHAT_COMPLETION_BODY,
            mounts={"all://": httpx.MockTransport(proxy_handler)},
        ),
    )

    async with http_client:
        request = http_client.build_request(
            "POST", "https://relay.test/v1/chat/completions", json={}
        )
        request.headers["x-stainless-lang"] = "python"
        request.headers["x-stainless-os"] = "Linux"
        response = await http_client.send(request)

    assert response.status_code == 200
    # The mounted (proxy) transport received the request, and it was still cleaned.
    assert reached_proxy
    assert _stainless_headers(sent) == []


@pytest.mark.asyncio
async def test_strip_sdk_telemetry_headers_leaves_everything_else_alone():
    request = httpx.Request(
        "POST",
        "https://relay.test/v1/chat/completions",
        headers={
            "Authorization": "Bearer sk-test",
            "X-Stainless-Lang": "python",
            "x-stainless-retry-count": "0",
            "X-Custom-Header": "keep-me",
            "x-stainless": "no-trailing-dash-stays",
        },
    )

    await network_utils.strip_sdk_telemetry_headers(request)

    assert _stainless_headers(dict(request.headers)) == []
    assert request.headers["authorization"] == "Bearer sk-test"
    assert request.headers["x-custom-header"] == "keep-me"
    # Only the ``x-stainless-`` prefix is telemetry; a bare ``x-stainless`` is not.
    assert request.headers["x-stainless"] == "no-trailing-dash-stays"


def test_create_proxy_client_registers_the_hook_with_and_without_proxy(
    monkeypatch: pytest.MonkeyPatch,
):
    captured_calls: list[dict] = []

    class _FakeAsyncClient:
        def __init__(self, **kwargs):
            captured_calls.append(kwargs)

    monkeypatch.setattr(network_utils.httpx, "AsyncClient", _FakeAsyncClient)

    network_utils.create_proxy_client("OpenAI")
    network_utils.create_proxy_client("OpenAI", proxy="http://127.0.0.1:7890")

    for call in captured_calls:
        assert call["event_hooks"]["request"] == [
            network_utils.strip_sdk_telemetry_headers
        ]


def test_resolve_sdk_httpx_modules_prefer_the_sdk_import():
    from anthropic import _base_client as anthropic_base_client
    from openai import _base_client as openai_base_client

    assert network_utils.resolve_openai_httpx_module() is openai_base_client.httpx
    assert network_utils.resolve_anthropic_httpx_module() is anthropic_base_client.httpx


def test_resolve_sdk_httpx_modules_fall_back_to_global_httpx(
    monkeypatch: pytest.MonkeyPatch,
):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {"openai", "anthropic"} and fromlist:
            raise ImportError(f"missing {name}._base_client")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert network_utils.resolve_openai_httpx_module() is httpx
    assert network_utils.resolve_anthropic_httpx_module() is httpx
