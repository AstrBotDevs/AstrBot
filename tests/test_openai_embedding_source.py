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


def test_openai_embedding_dimensions_auto_sends_for_official_openai_embedding_3():
    provider = OpenAIEmbeddingProvider.__new__(OpenAIEmbeddingProvider)
    provider.provider_config = {"embedding_dimensions": 1024}
    provider.model = "text-embedding-3-small"

    assert provider.get_dim() == 1024
    assert provider._embedding_kwargs() == {"dimensions": 1024}


def test_openai_embedding_dimensions_auto_skips_custom_api_base():
    provider = OpenAIEmbeddingProvider.__new__(OpenAIEmbeddingProvider)
    provider.provider_config = {
        "embedding_api_base": "https://api.siliconflow.cn/v1",
        "embedding_dimensions": 1024,
        "embedding_dimensions_mode": "auto",
    }
    provider.model = "BAAI/bge-m3"

    assert provider._embedding_kwargs() == {}


def test_openai_embedding_dimensions_auto_sends_for_siliconflow_qwen():
    provider = OpenAIEmbeddingProvider.__new__(OpenAIEmbeddingProvider)
    provider.provider_config = {
        "embedding_api_base": "https://api.siliconflow.cn/v1",
        "embedding_dimensions": 1024,
        "embedding_dimensions_mode": "auto",
    }
    provider.model = "Qwen/Qwen3-Embedding-4B"

    assert provider._embedding_kwargs() == {"dimensions": 1024}


def test_openai_embedding_dimensions_are_sent_when_mode_is_always():
    provider = OpenAIEmbeddingProvider.__new__(OpenAIEmbeddingProvider)
    provider.provider_config = {
        "embedding_dimensions": 1024,
        "embedding_dimensions_mode": "always",
    }

    assert provider.get_dim() == 1024
    assert provider._embedding_kwargs() == {"dimensions": 1024}


def test_openai_embedding_dimensions_are_local_when_mode_is_never():
    provider = OpenAIEmbeddingProvider.__new__(OpenAIEmbeddingProvider)
    provider.provider_config = {
        "embedding_dimensions": 1024,
        "embedding_dimensions_mode": "never",
    }
    provider.model = "text-embedding-3-small"

    assert provider.get_dim() == 1024
    assert provider._embedding_kwargs() == {}
