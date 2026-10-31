from unittest.mock import Mock

import aiohttp
import pytest

from astrbot.core.provider.sources.vllm_rerank_source import VLLMRerankProvider


class FakeResponse:
    def __init__(self, response_data, status: int = 200) -> None:
        self.response_data = response_data
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise aiohttp.ClientResponseError(
                request_info=Mock(),
                history=(),
                status=self.status,
            )

    async def json(self):
        return self.response_data


class FakeClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.closed = False
        self.requests = []

    def post(self, url: str, json: dict) -> FakeResponse:
        if self.closed:
            # Mirrors aiohttp: a closed session refuses to send requests.
            raise RuntimeError("Session is closed")
        self.requests.append((url, json))
        return self.response

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def provider() -> VLLMRerankProvider:
    instance = VLLMRerankProvider.__new__(VLLMRerankProvider)
    instance.base_url = "https://rerank.example.test"
    instance.api_suffix = "/v1/rerank"
    instance.model = "test-model"
    instance.client = None
    return instance


@pytest.mark.asyncio
async def test_vllm_rerank_maps_successful_response(provider):
    provider.client = FakeClient(
        FakeResponse(
            {
                "results": [
                    {"index": 1, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.7},
                ]
            }
        )
    )

    results = await provider.rerank("query", ["first", "second"], top_n=2)

    assert [(result.index, result.relevance_score) for result in results] == [
        (1, 0.9),
        (0, 0.7),
    ]
    assert provider.client.requests == [
        (
            "https://rerank.example.test/v1/rerank",
            {
                "query": "query",
                "documents": ["first", "second"],
                "model": "test-model",
                "top_n": 2,
            },
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 429])
async def test_vllm_rerank_raises_for_http_errors(provider, status):
    provider.client = FakeClient(FakeResponse({"error": "request failed"}, status))

    with pytest.raises(aiohttp.ClientResponseError) as exc_info:
        await provider.rerank("query", ["document"])

    assert exc_info.value.status == status


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response_data",
    [None, {}, {"results": None}, {"results": []}, {"results": [{}]}],
)
async def test_vllm_rerank_raises_for_invalid_responses(provider, response_data):
    provider.client = FakeClient(FakeResponse(response_data))

    with pytest.raises(ValueError):
        await provider.rerank("query", ["document"])


@pytest.mark.asyncio
async def test_vllm_rerank_skips_request_for_empty_documents(provider):
    provider.client = FakeClient(FakeResponse({"results": []}))

    results = await provider.rerank("query", [])

    assert results == []
    assert provider.client.requests == []


@pytest.mark.asyncio
async def test_vllm_rerank_terminate_closes_session(provider):
    client = FakeClient(FakeResponse({"results": []}))
    provider.client = client

    await provider.terminate()

    assert client.closed is True
    assert provider.client is None


@pytest.mark.asyncio
async def test_vllm_rerank_does_not_recreate_session_after_terminate(
    provider, monkeypatch
):
    """terminate() clears the session and rerank must not build a new one.

    Knowledge base vector stores cache the provider instance they were built
    with, so a reload can leave retrieval holding a terminated instance.
    Resolving the provider by ID on every retrieval is what recovers from a
    reload; this instance must not rebuild the session here, because that would
    silently keep using the endpoint, key and model from before the reload.
    """
    await provider.terminate()
    assert provider.client is None

    created_sessions = []

    def fake_client_session(**kwargs):
        created_sessions.append(kwargs)
        return FakeClient(
            FakeResponse({"results": [{"index": 0, "relevance_score": 0.5}]})
        )

    monkeypatch.setattr(aiohttp, "ClientSession", fake_client_session)

    with pytest.raises(RuntimeError, match="session is terminated"):
        await provider.rerank("query", ["document"])

    assert created_sessions == []


@pytest.mark.asyncio
async def test_vllm_rerank_terminate_then_reload_uses_the_new_instance(provider):
    """After terminate() only a freshly loaded provider may rerank again."""
    await provider.terminate()
    assert provider.client is None

    reloaded = VLLMRerankProvider.__new__(VLLMRerankProvider)
    reloaded.base_url = "https://rerank-reloaded.example.test"
    reloaded.api_suffix = "/v1/rerank"
    reloaded.model = "reloaded-model"
    reloaded.client = FakeClient(
        FakeResponse({"results": [{"index": 0, "relevance_score": 0.25}]})
    )

    results = await reloaded.rerank("query", ["document"])

    assert [(result.index, result.relevance_score) for result in results] == [
        (0, 0.25),
    ]
    assert reloaded.client.requests == [
        (
            "https://rerank-reloaded.example.test/v1/rerank",
            {
                "query": "query",
                "documents": ["document"],
                "model": "reloaded-model",
            },
        )
    ]


@pytest.mark.asyncio
async def test_vllm_rerank_reports_closed_session_without_rebuilding(provider):
    """A closed session fails with a diagnosable error instead of an empty one."""
    client = FakeClient(
        FakeResponse({"results": [{"index": 0, "relevance_score": 0.5}]})
    )
    await client.close()
    provider.client = client

    with pytest.raises(RuntimeError, match="Session is closed"):
        await provider.rerank("query", ["document"])

    assert client.requests == []
