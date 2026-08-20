from astrbot.core.provider.sources.openai_embedding_source import (
    OpenAIEmbeddingProvider,
    _normalize_api_base,
)


def test_openai_embedding_api_base_keeps_version_suffixes():
    assert (
        _normalize_api_base("https://ark.cn-beijing.volces.com/api/plan/v3")
        == "https://ark.cn-beijing.volces.com/api/plan/v3"
    )
    assert _normalize_api_base("https://example.test/v4") == "https://example.test/v4"


def test_openai_embedding_api_base_adds_default_version():
    assert _normalize_api_base("https://example.test/openai") == (
        "https://example.test/openai/v1"
    )
    assert _normalize_api_base("https://example.test/v1/embeddings") == (
        "https://example.test/v1"
    )


def test_embedding_dimensions_auto_mode_only_targets_known_apis():
    provider = OpenAIEmbeddingProvider.__new__(OpenAIEmbeddingProvider)
    provider.provider_config = {
        "embedding_api_base": "https://example.test/v1",
        "embedding_model": "text-embedding-3-small",
        "embedding_dimensions": 1024,
    }
    provider.model = "text-embedding-3-small"

    assert provider._embedding_kwargs() == {}


def test_embedding_dimensions_auto_mode_supports_openai_and_siliconflow_qwen():
    provider = OpenAIEmbeddingProvider.__new__(OpenAIEmbeddingProvider)
    provider.provider_config = {
        "embedding_api_base": "https://api.openai.com/v1",
        "embedding_model": "text-embedding-3-small",
        "embedding_dimensions": "1024",
    }
    provider.model = "text-embedding-3-small"

    assert provider._embedding_kwargs() == {"dimensions": 1024}

    provider.provider_config["embedding_api_base"] = "https://api.siliconflow.cn/v1"
    provider.model = "Qwen/Qwen3-Embedding-8B"
    assert provider._embedding_kwargs() == {"dimensions": 1024}


def test_embedding_dimensions_mode_can_force_or_disable_parameter():
    provider = OpenAIEmbeddingProvider.__new__(OpenAIEmbeddingProvider)
    provider.provider_config = {
        "embedding_api_base": "https://example.test/v1",
        "embedding_model": "custom-embedding",
        "embedding_dimensions": 768,
        "embedding_dimensions_mode": "always",
    }
    provider.model = "custom-embedding"

    assert provider._embedding_kwargs() == {"dimensions": 768}

    provider.provider_config["embedding_dimensions_mode"] = "never"
    assert provider._embedding_kwargs() == {}
