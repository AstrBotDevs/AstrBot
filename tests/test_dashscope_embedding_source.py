"""Unit tests for the DashScope embedding provider."""

import pytest

from astrbot.core.provider.sources.dashscope_embedding_source import (
    DashScopeEmbeddingProvider,
)


class _FakeResponse:
    """Minimal stand-in for dashscope.DashScopeAPIResponse."""

    def __init__(
        self,
        status_code=200,
        output=None,
        code="",
        message="",
        request_id="",
    ):
        self.status_code = status_code
        self.output = output
        self.code = code
        self.message = message
        self.request_id = request_id


def _make_provider(config: dict | None = None) -> DashScopeEmbeddingProvider:
    config = config or {}
    config.setdefault("embedding_api_key", "sk-test")
    return DashScopeEmbeddingProvider(config, {})


def _patch_sdk(monkeypatch, *, text=None, multimodal=None):
    """Patch TextEmbedding.call / MultiModalEmbedding.call in the source module."""
    import astrbot.core.provider.sources.dashscope_embedding_source as mod

    if text is not None:
        monkeypatch.setattr(mod.TextEmbedding, "call", text)
    if multimodal is not None:
        monkeypatch.setattr(mod.MultiModalEmbedding, "call", multimodal)


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


def test_requires_api_key():
    with pytest.raises(ValueError, match="API Key"):
        DashScopeEmbeddingProvider({"embedding_api_key": ""}, {})


def test_env_var_fallback(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-from-env")
    provider = DashScopeEmbeddingProvider({"embedding_api_key": ""}, {})
    assert provider.api_key == "sk-from-env"


def test_api_key_takes_precedence_over_env(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-from-env")
    provider = DashScopeEmbeddingProvider({"embedding_api_key": "sk-config"}, {})
    assert provider.api_key == "sk-config"


def test_defaults():
    provider = _make_provider()
    assert provider.model == "text-embedding-v4"
    assert provider.base_url == "https://dashscope.aliyuncs.com/api/v1"


def test_user_values_preserved():
    provider = _make_provider(
        {
            "embedding_model": "qwen3-vl-embedding",
            "embedding_api_base": "https://dashscope-intl.aliyuncs.com/api/v1",
        }
    )
    assert provider.model == "qwen3-vl-embedding"
    assert provider.base_url == "https://dashscope-intl.aliyuncs.com/api/v1"


# ---------------------------------------------------------------------------
# get_embeddings — text models
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_text_model_routes_to_text_embedding(monkeypatch):
    provider = _make_provider(
        {
            "embedding_api_base": "https://custom.example.com/api/v1",
            "embedding_dimensions": 1024,
        }
    )
    captured: dict = {}

    def fake_call(**kwargs):
        captured["kwargs"] = kwargs
        return _FakeResponse(
            output={
                # Intentionally out of order to verify text_index sorting.
                "embeddings": [
                    {"embedding": [0.4, 0.5], "text_index": 1},
                    {"embedding": [0.1, 0.2], "text_index": 0},
                ]
            }
        )

    _patch_sdk(
        monkeypatch,
        text=fake_call,
        multimodal=lambda **kw: pytest.fail(
            "should not call MultiModalEmbedding for text models"
        ),
    )

    result = await provider.get_embeddings(["a", "b"])

    assert result == [[0.1, 0.2], [0.4, 0.5]]
    assert captured["kwargs"]["model"] == "text-embedding-v4"
    assert captured["kwargs"]["input"] == ["a", "b"]
    assert captured["kwargs"]["api_key"] == "sk-test"
    assert captured["kwargs"]["dimension"] == 1024
    # base_address is passed per-call instead of mutating the module global.
    assert captured["kwargs"]["base_address"] == "https://custom.example.com/api/v1"


# ---------------------------------------------------------------------------
# get_embeddings — multimodal models
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multimodal_model_routes_to_multimodal_embedding(monkeypatch):
    provider = _make_provider(
        {"embedding_model": "qwen3-vl-embedding", "embedding_dimensions": 1024}
    )
    captured: dict = {}

    def fake_call(**kwargs):
        captured["kwargs"] = kwargs
        # Multimodal response uses "index" instead of "text_index".
        return _FakeResponse(
            output={
                "embeddings": [
                    {"embedding": [0.7, 0.8], "index": 1},
                    {"embedding": [0.1, 0.2], "index": 0},
                ]
            }
        )

    _patch_sdk(
        monkeypatch,
        multimodal=fake_call,
        text=lambda **kw: pytest.fail(
            "should not call TextEmbedding for multimodal models"
        ),
    )

    result = await provider.get_embeddings(["hello", "world"])

    assert result == [[0.1, 0.2], [0.7, 0.8]]
    assert captured["kwargs"]["model"] == "qwen3-vl-embedding"
    # Multimodal input wraps each text in a content dict.
    assert captured["kwargs"]["input"] == [{"text": "hello"}, {"text": "world"}]
    assert captured["kwargs"]["api_key"] == "sk-test"
    assert captured["kwargs"]["dimension"] == 1024
    assert captured["kwargs"]["base_address"] == (
        "https://dashscope.aliyuncs.com/api/v1"
    )


@pytest.mark.asyncio
async def test_tongyi_vision_model_routes_to_multimodal(monkeypatch):
    """tongyi-embedding-vision-* models also use the multimodal endpoint."""
    provider = _make_provider({"embedding_model": "tongyi-embedding-vision-plus"})
    captured: dict = {}

    def fake_call(**kwargs):
        captured["kwargs"] = kwargs
        return _FakeResponse(
            output={"embeddings": [{"embedding": [0.1, 0.2], "index": 0}]}
        )

    _patch_sdk(monkeypatch, multimodal=fake_call)

    result = await provider.get_embeddings(["hi"])
    assert result == [[0.1, 0.2]]


# ---------------------------------------------------------------------------
# get_embeddings — edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_input_returns_early(monkeypatch):
    """An empty input list must not invoke the SDK at all."""
    provider = _make_provider()

    _patch_sdk(
        monkeypatch,
        text=lambda **kw: pytest.fail("should not call SDK for empty input"),
        multimodal=lambda **kw: pytest.fail("should not call SDK for empty input"),
    )

    result = await provider.get_embeddings([])
    assert result == []


@pytest.mark.asyncio
async def test_zero_embedding_dimension_omitted(monkeypatch):
    """A zero dimension is invalid and must be omitted from the SDK call."""
    provider = _make_provider({"embedding_dimensions": 0})
    captured: dict = {}

    def fake_call(**kwargs):
        captured["kwargs"] = kwargs
        return _FakeResponse(
            output={"embeddings": [{"embedding": [0.1], "text_index": 0}]}
        )

    _patch_sdk(monkeypatch, text=fake_call)

    await provider.get_embeddings(["hi"])
    assert "dimension" not in captured["kwargs"]


@pytest.mark.asyncio
async def test_non_int_embedding_dimension_omitted(monkeypatch):
    """A non-integer dimension is invalid and must be omitted from the SDK call."""
    provider = _make_provider({"embedding_dimensions": "abc"})
    captured: dict = {}

    def fake_call(**kwargs):
        captured["kwargs"] = kwargs
        return _FakeResponse(
            output={"embeddings": [{"embedding": [0.1], "text_index": 0}]}
        )

    _patch_sdk(monkeypatch, text=fake_call)

    await provider.get_embeddings(["hi"])
    assert "dimension" not in captured["kwargs"]


# ---------------------------------------------------------------------------
# get_embedding (single text convenience wrapper)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_embedding_single(monkeypatch):
    provider = _make_provider()

    async def fake_get_embeddings(texts):
        return [[0.5, 0.6]]

    monkeypatch.setattr(provider, "get_embeddings", fake_get_embeddings)
    result = await provider.get_embedding("hello")
    assert result == [0.5, 0.6]


# ---------------------------------------------------------------------------
# error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_error_surfaces_status_code_and_request_id(monkeypatch):
    provider = _make_provider()

    def fake_call(**kwargs):
        return _FakeResponse(
            status_code=400,
            code="InvalidParameter",
            message="bad input",
            request_id="req-123",
        )

    _patch_sdk(monkeypatch, text=fake_call)

    with pytest.raises(
        Exception,
        match=r"HTTP 400.*InvalidParameter.*bad input"
        r".*url=https://dashscope\.aliyuncs\.com/api/v1/services/embeddings/text-embedding/text-embedding"
        r".*request_id=req-123",
    ):
        await provider.get_embeddings(["hi"])


@pytest.mark.asyncio
async def test_multimodal_error_url_uses_multimodal_path(monkeypatch):
    provider = _make_provider({"embedding_model": "qwen3-vl-embedding"})

    def fake_call(**kwargs):
        return _FakeResponse(status_code=404, code="Unkonwn", message="")

    _patch_sdk(monkeypatch, multimodal=fake_call)

    with pytest.raises(
        Exception,
        match=r"HTTP 404.*url=https://dashscope\.aliyuncs\.com/api/v1/services/embeddings/multimodal-embedding/multimodal-embedding",
    ):
        await provider.get_embeddings(["hi"])


@pytest.mark.asyncio
async def test_no_embeddings_raises(monkeypatch):
    provider = _make_provider()
    _patch_sdk(monkeypatch, text=lambda **kw: _FakeResponse(output={}))
    with pytest.raises(Exception, match="No embeddings"):
        await provider.get_embeddings(["hi"])


# ---------------------------------------------------------------------------
# get_dim
# ---------------------------------------------------------------------------


def test_get_dim_returns_configured():
    provider = _make_provider({"embedding_dimensions": 768})
    assert provider.get_dim() == 768


def test_get_dim_returns_zero_when_not_set():
    provider = _make_provider()
    assert provider.get_dim() == 0


def test_get_dim_returns_zero_when_invalid():
    provider = _make_provider({"embedding_dimensions": "abc"})
    assert provider.get_dim() == 0
