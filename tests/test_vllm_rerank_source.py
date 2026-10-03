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
