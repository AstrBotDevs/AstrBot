from unittest.mock import MagicMock

import pytest

from astrbot.core.provider.sources import gemini_embedding_source


def test_gemini_embedding_reuses_provider_source_key(monkeypatch) -> None:
    client = MagicMock()
    client.aio = MagicMock()
    factory = MagicMock(return_value=client)
    monkeypatch.setattr(gemini_embedding_source.genai, "Client", factory)

    provider = gemini_embedding_source.GeminiEmbeddingProvider(
        {
            "id": "gemini_embedding",
            "key": ["source-key"],
            "api_base": "https://example.invalid/",
            "embedding_model": "gemini-embedding-001",
            "embedding_dimensions": 768,
        },
        {},
    )

    assert provider.model == "gemini-embedding-001"
    factory.assert_called_once()
    assert factory.call_args.kwargs["api_key"] == "source-key"
    assert factory.call_args.kwargs["http_options"].base_url == (
        "https://example.invalid"
    )


def test_gemini_embedding_requires_key() -> None:
    with pytest.raises(ValueError, match="configured API key"):
        gemini_embedding_source.GeminiEmbeddingProvider(
            {
                "id": "gemini_embedding",
                "embedding_api_key": "",
                "embedding_api_base": "",
            },
            {},
        )
