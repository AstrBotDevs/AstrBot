import pytest

import astrbot.core.provider.sources.bailian_rerank_source as bailian_rerank_module
from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.sources.bailian_rerank_source import BailianRerankProvider

CHINA_COMPATIBLE_URL = "https://dashscope.aliyuncs.com/compatible-api/v1/reranks"
SINGAPORE_COMPATIBLE_URL = (
    "https://example.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1/reranks"
)
NATIVE_URL = (
    "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
)


@pytest.fixture
def provider() -> BailianRerankProvider:
    instance = BailianRerankProvider.__new__(BailianRerankProvider)
    instance.model = "qwen3-rerank"
    instance.return_documents = False
    instance.instruct = ""
    return instance


def test_bailian_rerank_provider_preserves_native_default_endpoint(monkeypatch):
    monkeypatch.setattr(
        bailian_rerank_module.aiohttp,
        "ClientSession",
        lambda **_kwargs: object(),
    )

    provider = BailianRerankProvider(
        provider_config={"rerank_api_key": "test-key"},
        provider_settings={},
    )

    assert provider.base_url == NATIVE_URL


def test_bailian_rerank_config_template_preserves_native_default_endpoint():
    templates = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]

    assert templates["阿里云百炼重排序"]["rerank_api_base"] == NATIVE_URL


def test_bailian_rerank_provider_preserves_explicit_endpoint(monkeypatch):
    monkeypatch.setattr(
        bailian_rerank_module.aiohttp,
        "ClientSession",
        lambda **_kwargs: object(),
    )
    custom_url = "https://rerank.example.test/custom"

    provider = BailianRerankProvider(
        provider_config={
            "rerank_api_key": "test-key",
            "rerank_api_base": custom_url,
        },
        provider_settings={},
    )

    assert provider.base_url == custom_url


@pytest.mark.parametrize(
    "base_url",
    [CHINA_COMPATIBLE_URL, SINGAPORE_COMPATIBLE_URL],
)
def test_qwen3_compatible_endpoints_use_flat_payload(provider, base_url):
    provider.base_url = base_url

    assert provider._build_payload("query", ["document"], top_n=1) == {
        "model": "qwen3-rerank",
        "query": "query",
        "documents": ["document"],
        "top_n": 1,
    }


def test_qwen3_native_endpoint_uses_wrapped_payload(provider):
    provider.base_url = NATIVE_URL
    provider.instruct = "Focus on technical relevance."

    assert provider._build_payload("query", ["document"], top_n=1) == {
        "model": "qwen3-rerank",
        "input": {"query": "query", "documents": ["document"]},
        "parameters": {
            "top_n": 1,
            "instruct": "Focus on technical relevance.",
        },
    }


def test_protocol_detection_ignores_compatible_text_outside_url_path(provider):
    provider.base_url = f"{NATIVE_URL}?redirect=/compatible-api/v1/reranks"

    assert provider._build_payload("query", ["document"], top_n=1) == {
        "model": "qwen3-rerank",
        "input": {"query": "query", "documents": ["document"]},
        "parameters": {"top_n": 1},
    }


def test_protocol_detection_accepts_compatible_endpoint_suffix(provider):
    provider.base_url = f"{CHINA_COMPATIBLE_URL}/?workspace=test"

    assert provider._build_payload("query", ["document"], top_n=1) == {
        "model": "qwen3-rerank",
        "query": "query",
        "documents": ["document"],
        "top_n": 1,
    }


@pytest.mark.parametrize(
    "base_url",
    [CHINA_COMPATIBLE_URL, SINGAPORE_COMPATIBLE_URL],
)
def test_compatible_endpoints_parse_top_level_results(provider, base_url):
    provider.base_url = base_url

    results = provider._parse_results(
        {"results": [{"index": 0, "relevance_score": 0.75}]}
    )

    assert len(results) == 1
    assert results[0].index == 0
    assert results[0].relevance_score == 0.75


def test_native_endpoint_parses_nested_results(provider):
    provider.base_url = NATIVE_URL

    results = provider._parse_results(
        {"output": {"results": [{"index": 0, "relevance_score": 0.75}]}}
    )

    assert len(results) == 1
    assert results[0].index == 0
    assert results[0].relevance_score == 0.75


# ---------- qwen3-rerank additional cases ----------


def test_qwen3_native_endpoint_ignores_return_documents(provider):
    provider.base_url = NATIVE_URL
    provider.return_documents = True

    payload = provider._build_payload("q", ["d1"], None)

    assert "parameters" not in payload


def test_qwen3_native_endpoint_no_params_when_top_n_zero(provider):
    provider.base_url = NATIVE_URL

    payload = provider._build_payload("q", ["d1"], 0)

    assert "parameters" not in payload


def test_qwen3_compatible_endpoint_ignores_return_documents(provider):
    provider.base_url = CHINA_COMPATIBLE_URL
    provider.return_documents = True

    payload = provider._build_payload("q", ["d1"], None)

    assert "return_documents" not in payload


def test_qwen3_compatible_endpoint_no_optional_fields(provider):
    provider.base_url = CHINA_COMPATIBLE_URL

    payload = provider._build_payload("q", ["d1"], None)

    assert payload == {
        "model": "qwen3-rerank",
        "query": "q",
        "documents": ["d1"],
    }


def test_qwen3_compatible_endpoint_includes_instruct(provider):
    provider.base_url = CHINA_COMPATIBLE_URL
    provider.instruct = "focus on facts"

    payload = provider._build_payload("q", ["d1", "d2"], 3)

    assert payload == {
        "model": "qwen3-rerank",
        "query": "q",
        "documents": ["d1", "d2"],
        "top_n": 3,
        "instruct": "focus on facts",
    }


# ---------- non-qwen3 model (gte-rerank) ----------


def test_gte_rerank_native_endpoint_uses_wrapped_format_with_return_documents(provider):
    provider.model = "gte-rerank-v2"
    provider.base_url = NATIVE_URL
    provider.return_documents = True

    payload = provider._build_payload("q", ["d1"], 2)

    assert payload == {
        "model": "gte-rerank-v2",
        "input": {"query": "q", "documents": ["d1"]},
        "parameters": {"top_n": 2, "return_documents": True},
    }


def test_gte_rerank_native_endpoint_no_instruct(provider):
    provider.model = "gte-rerank-v2"
    provider.base_url = NATIVE_URL
    provider.instruct = "ignored"

    payload = provider._build_payload("q", ["d1"], None)

    assert payload["input"] == {"query": "q", "documents": ["d1"]}
    assert "parameters" not in payload


def test_gte_rerank_compatible_endpoint_uses_flat_format(provider):
    provider.model = "gte-rerank-v2"
    provider.base_url = CHINA_COMPATIBLE_URL
    provider.return_documents = True

    payload = provider._build_payload("q", ["d1"], 2)

    assert payload == {
        "model": "gte-rerank-v2",
        "query": "q",
        "documents": ["d1"],
        "top_n": 2,
        "return_documents": True,
    }


def test_gte_rerank_compatible_endpoint_no_instruct(provider):
    provider.model = "gte-rerank-v2"
    provider.base_url = CHINA_COMPATIBLE_URL
    provider.instruct = "ignored"

    payload = provider._build_payload("q", ["d1"], None)

    assert "instruct" not in payload


def test_gte_rerank_compatible_endpoint_no_optional_fields(provider):
    provider.model = "gte-rerank-v2"
    provider.base_url = SINGAPORE_COMPATIBLE_URL

    payload = provider._build_payload("q", ["d1"], None)

    assert payload == {
        "model": "gte-rerank-v2",
        "query": "q",
        "documents": ["d1"],
    }
