"""Protocol contracts for Bailian rerank endpoints."""

from astrbot.core.provider.sources.bailian_rerank_source import (
    BailianRerankProvider,
)

CHINA_COMPATIBLE_URL = "https://dashscope.aliyuncs.com/compatible-api/v1/reranks"
OVERSEAS_COMPATIBLE_URL = (
    "https://example.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1/reranks"
)
NATIVE_URL = (
    "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
)


def _provider(base_url: str) -> BailianRerankProvider:
    provider = BailianRerankProvider.__new__(BailianRerankProvider)
    provider.base_url = base_url
    provider.model = "qwen3-rerank"
    provider.return_documents = False
    provider.instruct = ""
    return provider


def test_compatible_endpoints_use_flat_qwen3_payload():
    """Both regional compatible endpoints use the OpenAI-like request shape."""
    for base_url in (CHINA_COMPATIBLE_URL, OVERSEAS_COMPATIBLE_URL):
        provider = _provider(base_url)

        assert provider._build_payload("query", ["document"], top_n=1) == {
            "model": "qwen3-rerank",
            "query": "query",
            "documents": ["document"],
            "top_n": 1,
        }


def test_native_endpoint_uses_wrapped_qwen3_payload():
    """The native endpoint expects input and parameters containers."""
    provider = _provider(NATIVE_URL)
    provider.instruct = "Focus on technical relevance."

    assert provider._build_payload("query", ["document"], top_n=1) == {
        "model": "qwen3-rerank",
        "input": {"query": "query", "documents": ["document"]},
        "parameters": {"top_n": 1, "instruct": "Focus on technical relevance."},
    }


def test_protocol_detection_uses_url_path_not_query_text():
    """A query parameter must not accidentally change the endpoint protocol."""
    provider = _provider(f"{NATIVE_URL}?redirect=/compatible-api/v1/reranks")

    assert provider._uses_compatible_api() is False
    assert provider._build_payload("query", ["document"], top_n=1) == {
        "model": "qwen3-rerank",
        "input": {"query": "query", "documents": ["document"]},
        "parameters": {"top_n": 1},
    }


def test_compatible_response_uses_top_level_results():
    """Compatible responses put rerank results directly at the top level."""
    provider = _provider(f"{CHINA_COMPATIBLE_URL}/?workspace=test")

    results = provider._parse_results(
        {"results": [{"index": 0, "relevance_score": 0.75}]}
    )

    assert [(result.index, result.relevance_score) for result in results] == [(0, 0.75)]


def test_native_response_uses_nested_results():
    """Native responses retain the output container."""
    provider = _provider(NATIVE_URL)

    results = provider._parse_results(
        {"output": {"results": [{"index": 0, "relevance_score": 0.75}]}}
    )

    assert [(result.index, result.relevance_score) for result in results] == [(0, 0.75)]
