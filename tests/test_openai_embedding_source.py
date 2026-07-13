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


def test_openai_embedding_dimensions_are_local_by_default():
    provider = OpenAIEmbeddingProvider.__new__(OpenAIEmbeddingProvider)
    provider.provider_config = {"embedding_dimensions": 1024}

    assert provider.get_dim() == 1024
    assert provider._embedding_kwargs() == {}


def test_openai_embedding_dimensions_are_sent_when_enabled():
    provider = OpenAIEmbeddingProvider.__new__(OpenAIEmbeddingProvider)
    provider.provider_config = {
        "embedding_dimensions": 1024,
        "send_embedding_dimensions": True,
    }

    assert provider.get_dim() == 1024
    assert provider._embedding_kwargs() == {"dimensions": 1024}
