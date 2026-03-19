from types import SimpleNamespace

import pytest

from astrbot.core.provider.sources import openai_compatible_embedding_source as source


class _FakeEmbeddingsAPI:
    def __init__(self, create_calls: list[dict]) -> None:
        self._create_calls = create_calls

    async def create(self, **kwargs):
        self._create_calls.append(kwargs)
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])],
        )


class _FakeAsyncOpenAI:
    instances: list["_FakeAsyncOpenAI"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.create_calls: list[dict] = []
        self.embeddings = _FakeEmbeddingsAPI(self.create_calls)
        self.closed = False
        self.__class__.instances.append(self)

    async def close(self):
        self.closed = True


class _FakeHTTPClient:
    instances: list["_FakeHTTPClient"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.closed = False
        self.__class__.instances.append(self)

    async def aclose(self):
        self.closed = True


def _make_provider_config(**overrides) -> dict:
    provider_config = {
        "id": "test-openai-compatible-embedding",
        "type": "openai_compatible_embedding",
        "embedding_api_key": "test-key",
        "embedding_api_base": "",
        "embedding_model": "text-embedding-3-small",
        "embedding_dimensions": 1024,
        "send_dimensions_param": False,
        "timeout": 20,
        "proxy": "",
    }
    provider_config.update(overrides)
    return provider_config


@pytest.mark.parametrize(
    ("api_base", "expected_base_url"),
    [
        ("", "https://api.openai.com/v1"),
        ("api.openai.com", "https://api.openai.com/v1"),
        ("https://example.com", "https://example.com/v1"),
        ("https://example.com/", "https://example.com/v1"),
        (
            "https://open.bigmodel.cn/api/paas/v4",
            "https://open.bigmodel.cn/api/paas/v4",
        ),
        (
            "https://ark.cn-beijing.volces.com/api/v3",
            "https://ark.cn-beijing.volces.com/api/v3",
        ),
    ],
)
def test_normalize_openai_compatible_embedding_api_base(api_base, expected_base_url):
    assert (
        source.normalize_openai_compatible_embedding_api_base(api_base)
        == expected_base_url
    )


@pytest.mark.asyncio
async def test_openai_compatible_embedding_provider_appends_v1_only_for_host_url(
    monkeypatch: pytest.MonkeyPatch,
):
    _FakeAsyncOpenAI.instances.clear()
    monkeypatch.setattr(source, "AsyncOpenAI", _FakeAsyncOpenAI)

    provider = source.OpenAICompatibleEmbeddingProvider(
        _make_provider_config(embedding_api_base="https://example.com"),
        {},
    )

    try:
        assert _FakeAsyncOpenAI.instances[-1].kwargs["base_url"] == (
            "https://example.com/v1"
        )
    finally:
        await provider.terminate()
        assert provider.client.closed is True


@pytest.mark.asyncio
async def test_openai_compatible_embedding_provider_preserves_existing_api_path(
    monkeypatch: pytest.MonkeyPatch,
):
    _FakeAsyncOpenAI.instances.clear()
    monkeypatch.setattr(source, "AsyncOpenAI", _FakeAsyncOpenAI)

    provider = source.OpenAICompatibleEmbeddingProvider(
        _make_provider_config(
            embedding_api_base="https://open.bigmodel.cn/api/paas/v4",
        ),
        {},
    )

    try:
        assert _FakeAsyncOpenAI.instances[-1].kwargs["base_url"] == (
            "https://open.bigmodel.cn/api/paas/v4"
        )
    finally:
        await provider.terminate()
        assert provider.client.closed is True


@pytest.mark.asyncio
async def test_openai_compatible_embedding_provider_sends_dimensions_only_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
):
    _FakeAsyncOpenAI.instances.clear()
    monkeypatch.setattr(source, "AsyncOpenAI", _FakeAsyncOpenAI)

    provider_without_dimensions = source.OpenAICompatibleEmbeddingProvider(
        _make_provider_config(send_dimensions_param=False),
        {},
    )
    provider_with_dimensions = source.OpenAICompatibleEmbeddingProvider(
        _make_provider_config(send_dimensions_param=True, embedding_dimensions=2048),
        {},
    )

    try:
        await provider_without_dimensions.get_embedding("hello")
        await provider_with_dimensions.get_embedding("hello")

        assert "dimensions" not in _FakeAsyncOpenAI.instances[0].create_calls[0]
        assert _FakeAsyncOpenAI.instances[1].create_calls[0]["dimensions"] == 2048
    finally:
        await provider_without_dimensions.terminate()
        await provider_with_dimensions.terminate()
        assert provider_without_dimensions.client.closed is True
        assert provider_with_dimensions.client.closed is True


@pytest.mark.asyncio
async def test_openai_compatible_embedding_provider_closes_proxy_http_client(
    monkeypatch: pytest.MonkeyPatch,
):
    _FakeAsyncOpenAI.instances.clear()
    _FakeHTTPClient.instances.clear()
    monkeypatch.setattr(source, "AsyncOpenAI", _FakeAsyncOpenAI)
    monkeypatch.setattr(source.httpx, "AsyncClient", _FakeHTTPClient)

    provider = source.OpenAICompatibleEmbeddingProvider(
        _make_provider_config(proxy="http://127.0.0.1:7890"),
        {},
    )

    try:
        assert _FakeHTTPClient.instances[-1].kwargs["proxy"] == "http://127.0.0.1:7890"
    finally:
        await provider.terminate()
        assert provider.client.closed is True
        assert provider._http_client.closed is True


def test_should_send_dimensions_param_requires_boolean(
    monkeypatch: pytest.MonkeyPatch,
):
    warnings: list[str] = []

    def _capture_warning(message, *args):
        warnings.append(message % args)

    monkeypatch.setattr(source.logger, "warning", _capture_warning)

    assert (
        source.should_send_dimensions_param({"send_dimensions_param": "true"}) is False
    )
    assert "send_dimensions_param should be a boolean" in warnings[0]
