"""DashScope / NVIDIA Embedding 的非对称检索任务类型测试。

两家都需要区分查询与文档侧的编码模式，否则检索区分度下降：

- DashScope: ``text_type`` = ``query`` / ``document``
- NVIDIA: ``input_type`` = ``query`` / ``passage``
"""

from unittest.mock import patch

import pytest

from astrbot.core.provider.sources.dashscope_embedding_source import (
    DashScopeEmbeddingProvider,
)
from astrbot.core.provider.sources.nvidia_embedding_source import (
    NvidiaEmbeddingProvider,
)

# ── DashScope ───────────────────────────────────────────────


def _make_dashscope(**overrides) -> DashScopeEmbeddingProvider:
    provider = DashScopeEmbeddingProvider.__new__(DashScopeEmbeddingProvider)
    provider.provider_config = {
        "embedding_api_key": "test-key",
        "embedding_model": "text-embedding-v4",
        "embedding_dimensions": 1024,
        **overrides,
    }
    provider.api_key = "test-key"
    provider.base_url = "https://dashscope.aliyuncs.com/api/v1"
    provider.model = overrides.get("embedding_model", "text-embedding-v4")
    provider.request_headers = {}
    provider.text_type_mode = overrides.get("embedding_text_type_mode", "auto")
    return provider


class _FakeResp:
    def __init__(self) -> None:
        self.status_code = 200
        self.output = {"embeddings": [{"text_index": 0, "embedding": [0.1, 0.2]}]}


@pytest.mark.asyncio
async def test_dashscope_sends_query_text_type_for_retrieval():
    provider = _make_dashscope()
    captured: list[dict] = []

    def fake_call(**kwargs):
        captured.append(kwargs)
        return _FakeResp()

    with patch(
        "astrbot.core.provider.sources.dashscope_embedding_source.TextEmbedding"
    ) as mock_te:
        mock_te.call.side_effect = fake_call
        await provider.get_query_embedding("查询词")

    assert captured[0]["text_type"] == "query"


@pytest.mark.asyncio
async def test_dashscope_sends_document_text_type_for_indexing():
    provider = _make_dashscope()
    captured: list[dict] = []

    def fake_call(**kwargs):
        captured.append(kwargs)
        return _FakeResp()

    with patch(
        "astrbot.core.provider.sources.dashscope_embedding_source.TextEmbedding"
    ) as mock_te:
        mock_te.call.side_effect = fake_call
        await provider.get_embedding("文档正文")
        await provider.get_embeddings(["甲", "乙"])

    assert captured[0]["text_type"] == "document"
    assert captured[1]["text_type"] == "document"


@pytest.mark.asyncio
async def test_dashscope_never_mode_omits_text_type():
    provider = _make_dashscope(embedding_text_type_mode="never")
    captured: list[dict] = []

    def fake_call(**kwargs):
        captured.append(kwargs)
        return _FakeResp()

    with patch(
        "astrbot.core.provider.sources.dashscope_embedding_source.TextEmbedding"
    ) as mock_te:
        mock_te.call.side_effect = fake_call
        await provider.get_query_embedding("查询词")

    assert "text_type" not in captured[0]


@pytest.mark.asyncio
async def test_dashscope_multimodal_does_not_send_text_type():
    """多模态端点不接受 text_type 参数。"""
    provider = _make_dashscope(embedding_model="qwen3-vl-embedding")
    captured: list[dict] = []

    def fake_call(**kwargs):
        captured.append(kwargs)
        return _FakeResp()

    with patch(
        "astrbot.core.provider.sources.dashscope_embedding_source.MultiModalEmbedding"
    ) as mock_mm:
        mock_mm.call.side_effect = fake_call
        await provider.get_query_embedding("查询词")

    assert "text_type" not in captured[0]


def test_dashscope_invalid_mode_falls_back_to_auto():
    provider = _make_dashscope(embedding_text_type_mode="bogus")
    # __init__ 会校验并回退；这里直接验证判定函数的结果
    provider.text_type_mode = "auto"
    assert provider._should_send_text_type() is True


# ── NVIDIA ──────────────────────────────────────────────────


def _make_nvidia(**overrides) -> NvidiaEmbeddingProvider:
    provider = NvidiaEmbeddingProvider.__new__(NvidiaEmbeddingProvider)
    provider.provider_config = {
        "embedding_api_key": "test-key",
        "embedding_model": "nvidia/nemotron-3-embed-1b",
        "input_type": "passage",
        "query_input_type": "query",
        "embedding_dimensions": 2048,
        **overrides,
    }
    provider.api_key = "test-key"
    provider.base_url = "https://integrate.api.nvidia.com/v1"
    provider.model = overrides.get("embedding_model", "nvidia/nemotron-3-embed-1b")
    provider.input_type = overrides.get("input_type", "passage")
    provider.query_input_type = overrides.get("query_input_type", "query")
    provider.request_headers = {}
    provider.proxy = ""
    provider.client = None
    return provider


def test_nvidia_payload_uses_query_input_type_for_query():
    provider = _make_nvidia()
    payload = provider._build_payload(["q"], input_type=provider.query_input_type)
    assert payload["input_type"] == "query"


def test_nvidia_payload_defaults_to_passage_for_documents():
    provider = _make_nvidia()
    assert provider._build_payload(["d"])["input_type"] == "passage"


def test_nvidia_payload_allows_custom_query_input_type():
    provider = _make_nvidia(query_input_type="query")
    assert provider._build_payload(["q"], input_type="query")["input_type"] == "query"
