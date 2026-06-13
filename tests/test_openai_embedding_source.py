import pytest

from astrbot.core.provider.sources.openai_embedding_source import (
    _normalize_embedding_api_base,
)


@pytest.mark.parametrize(
    ("api_base", "expected"),
    [
        ("https://api.openai.com/v1", "https://api.openai.com/v1"),
        (
            "https://ark.cn-beijing.volces.com/api/plan/v3",
            "https://ark.cn-beijing.volces.com/api/plan/v3",
        ),
        ("https://example.com/openai/v12/", "https://example.com/openai/v12"),
        ("https://example.com/openai", "https://example.com/openai/v1"),
        ("https://example.com/openai/embeddings", "https://example.com/openai/v1"),
        (
            " https://example.com/openai/v3/embeddings/ ",
            "https://example.com/openai/v3",
        ),
        (None, ""),
        ("", ""),
    ],
)
def test_normalize_embedding_api_base(api_base, expected):
    assert _normalize_embedding_api_base(api_base) == expected
