from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.sources.nvidia_rerank_source import NvidiaRerankProvider

NEW_MODEL = "nvidia/llama-nemotron-rerank-vl-1b-v2"
OLD_MODEL = "nv-rerank-qa-mistral-4b:1"


def test_nvidia_rerank_config_template_uses_new_model():
    templates = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]

    assert templates["NVIDIA Rerank"]["nvidia_rerank_model"] == NEW_MODEL


def test_nvidia_rerank_provider_uses_new_fallback_model():
    provider = NvidiaRerankProvider({}, {})

    assert provider.model == NEW_MODEL
    assert provider.get_model() == NEW_MODEL


def test_nvidia_rerank_provider_preserves_explicit_old_model():
    provider = NvidiaRerankProvider({"nvidia_rerank_model": OLD_MODEL}, {})

    assert provider.model == OLD_MODEL
    assert provider._get_endpoint() == (
        "https://ai.api.nvidia.com/v1/retrieval/nvidia/reranking"
    )


def test_nvidia_rerank_new_model_uses_existing_api_contract():
    provider = NvidiaRerankProvider(
        {
            "nvidia_rerank_model": NEW_MODEL,
            "nvidia_rerank_truncate": "END",
        },
        {},
    )

    assert provider._get_endpoint() == (
        "https://ai.api.nvidia.com/v1/retrieval/nvidia/"
        "llama-nemotron-rerank-vl-1b-v2/reranking"
    )
    assert provider._build_payload("query", ["first", "second"]) == {
        "model": NEW_MODEL,
        "query": {"text": "query"},
        "passages": [{"text": "first"}, {"text": "second"}],
        "truncate": "END",
    }


def test_nvidia_rerank_parses_official_rankings_response():
    provider = NvidiaRerankProvider({}, {})

    results = provider._parse_results(
        {
            "rankings": [
                {"index": 1, "logit": -0.25},
                {"index": 0, "logit": 0.75},
            ]
        },
        top_n=None,
    )

    assert [(result.index, result.relevance_score) for result in results] == [
        (0, 0.75),
        (1, -0.25),
    ]
