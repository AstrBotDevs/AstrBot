from astrbot.core.provider.sources.openai_embedding_source import _normalize_api_base


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
