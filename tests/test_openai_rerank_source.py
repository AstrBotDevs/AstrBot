import pytest

from astrbot.core.provider.sources.openai_rerank_source import OpenAIRerankProvider


class _MockResponse:
    def __init__(self, payload: dict, status: int = 200, text: str = ""):
        self._payload = payload
        self.status = status
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self, content_type=None):
        return self._payload

    async def text(self):
        return self._text


class _MockClient:
    def __init__(self, response: _MockResponse):
        self.response = response
        self.calls: list[tuple[str, dict]] = []
        self.closed = False

    def post(self, url: str, json: dict):
        self.calls.append((url, json))
        return self.response

    async def close(self):
        self.closed = True


def _make_provider(overrides: dict | None = None) -> OpenAIRerankProvider:
    provider_config = {
        "id": "test-openai-rerank",
        "type": "openai_rerank",
        "rerank_api_key": "test-key",
        "rerank_api_url": "https://api.example.com/v1/rerank",
        "rerank_model": "test-model",
        "timeout": 30,
    }
    if overrides:
        provider_config.update(overrides)
    return OpenAIRerankProvider(provider_config=provider_config, provider_settings={})


def test_init_requires_api_key_and_url():
    with pytest.raises(ValueError, match="API Key"):
        _make_provider({"rerank_api_key": ""})

    with pytest.raises(ValueError, match="API URL"):
        _make_provider({"rerank_api_url": ""})


@pytest.mark.asyncio
async def test_rerank_maps_top_n_to_top_k_and_accepts_object_documents():
    provider = _make_provider()
    mock_client = _MockClient(
        _MockResponse(
            {
                "results": [
                    {"index": 1, "relevance_score": 0.95},
                    {"index": 0, "relevance_score": "0.52"},
                ]
            }
        )
    )
    provider.client = mock_client

    try:
        results = await provider.rerank(
            query="astrbot rerank",
            documents=[
                "plain text document",
                {"id": "doc-2", "title": "Title", "content": "Body"},
            ],
            top_n=120,
        )
    finally:
        await provider.terminate()

    assert mock_client.calls == [
        (
            "https://api.example.com/v1/rerank",
            {
                "query": "astrbot rerank",
                "documents": [
                    "plain text document",
                    {"id": "doc-2", "title": "Title", "content": "Body"},
                ],
                "model": "test-model",
                "top_k": 100,
            },
        )
    ]
    assert [result.index for result in results] == [1, 0]
    assert [result.relevance_score for result in results] == pytest.approx([0.95, 0.52])


@pytest.mark.asyncio
async def test_rerank_rejects_unsupported_document_types():
    provider = _make_provider()

    try:
        with pytest.raises(TypeError, match=r"documents\[0\]"):
            await provider.rerank(
                query="astrbot rerank",
                documents=[123],
            )
    finally:
        await provider.terminate()
