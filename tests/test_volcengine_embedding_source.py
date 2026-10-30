"""Verify Ark multimodal requests through the real OpenAI HTTP transport."""

from typing import TypedDict

import pytest
import pytest_asyncio
from aiohttp import web
from openai import AuthenticationError

from astrbot.core.provider.headers import DEFAULT_USER_AGENT
from astrbot.core.provider.sources.volcengine_embedding_source import (
    VolcengineEmbeddingProvider,
)


class _ResponseConfig(TypedDict):
    """Mutable HTTP status and JSON body returned by the test server."""

    status: int
    body: dict | None


@pytest_asyncio.fixture
async def ark_provider(monkeypatch, request, unused_tcp_port):
    """Create a provider whose actual HTTP requests are captured locally.

    Args:
        monkeypatch: Fixture for bypassing proxies for the local test server.
        request: Fixture carrying optional provider configuration.
        unused_tcp_port: Available port for the local test server.

    Yields:
        A provider, captured requests and a mutable response configuration.
    """
    requests: list[tuple[web.Request, dict]] = []
    response: _ResponseConfig = {"status": 200, "body": None}
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")

    async def handle(http_request: web.Request) -> web.Response:
        payload = await http_request.json()
        requests.append((http_request, payload))
        body = response["body"]
        if body is None:
            text = payload["input"][0]["text"]
            vector = [0.3, 0.4] if text == "second" else [0.1, 0.2]
            body = {"data": {"embedding": vector}}
        return web.json_response(body, status=response["status"])

    config = {"embedding_api_key": "test-key", **getattr(request, "param", {})}
    config["embedding_api_base"] = config.get(
        "embedding_api_base", "https://ark.cn-beijing.volces.com/api/v3"
    ).replace(
        "https://ark.cn-beijing.volces.com", f"http://127.0.0.1:{unused_tcp_port}"
    )
    provider = VolcengineEmbeddingProvider(config, {})
    app = web.Application()
    app.router.add_post("/{path:.*}", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    try:
        await web.TCPSite(runner, "127.0.0.1", unused_tcp_port).start()
        yield provider, requests, response
    finally:
        await provider.terminate()
        await runner.cleanup()
        assert provider.client.is_closed()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ark_provider, expected_path, expected_model",
    [
        ({}, "/api/v3/embeddings/multimodal", "doubao-embedding-vision-251215"),
        (
            {
                "embedding_api_base": " https://ark.cn-beijing.volces.com/api/plan/v3/ ",
                "embedding_model": "doubao-embedding-vision",
            },
            "/api/plan/v3/embeddings/multimodal",
            "doubao-embedding-vision",
        ),
        (
            {
                "embedding_api_base": "https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal",
                "embedding_model": "ep-test-endpoint",
            },
            "/api/v3/embeddings/multimodal",
            "ep-test-endpoint",
        ),
    ],
    indirect=["ark_provider"],
)
async def test_texts_receive_independent_vectors(
    ark_provider, expected_path, expected_model
):
    provider, requests, response = ark_provider
    assert await provider.get_embeddings([]) == []
    assert requests == []
    assert await provider.get_embeddings(["first", "second"]) == [
        [0.1, 0.2],
        [0.3, 0.4],
    ]
    assert len(requests) == 2
    for (http_request, payload), text in zip(
        requests, ["first", "second"], strict=True
    ):
        assert http_request.path == expected_path
        assert http_request.headers["Authorization"] == "Bearer test-key"
        assert http_request.headers["User-Agent"] == DEFAULT_USER_AGENT
        assert payload == {
            "model": expected_model,
            "input": [{"type": "text", "text": text}],
            "dimensions": 1024,
            "encoding_format": "float",
        }
    assert provider.get_dim() == 1024
    assert provider.get_model() == expected_model
    response["body"] = {"data": {"embedding": [0.3, 0.4]}}
    assert await provider.get_embedding("third") == [0.3, 0.4]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ark_provider",
    [{"embedding_dimensions": 2048, "custom_headers": {"User-Agent": "custom/1.0"}}],
    indirect=True,
)
async def test_configured_dimensions_and_headers(ark_provider):
    provider, requests, _ = ark_provider
    await provider.get_embedding("hello")
    http_request, payload = requests[0]
    assert payload["dimensions"] == 2048
    assert http_request.headers["User-Agent"] == "custom/1.0"
    assert provider.get_dim() == 2048


@pytest.mark.asyncio
async def test_authentication_error_is_preserved(ark_provider):
    provider, _, response = ark_provider
    response.update(status=401, body={"error": {"message": "Invalid API key"}})
    with pytest.raises(AuthenticationError, match="Invalid API key"):
        await provider.get_embedding("hello")


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{}, {"data": None}, {"data": {"embedding": []}}])
async def test_missing_vectors_are_rejected(ark_provider, body):
    provider, _, response = ark_provider
    response["body"] = body
    with pytest.raises(ValueError, match="no dense vector"):
        await provider.get_embedding("hello")
