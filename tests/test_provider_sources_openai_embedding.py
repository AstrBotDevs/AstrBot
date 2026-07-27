"""Smoke tests for OpenAIEmbeddingProvider."""
from unittest.mock import patch

from astrbot.core.provider.sources.openai_embedding_source import (
    OpenAIEmbeddingProvider,
)


@patch("astrbot.core.provider.sources.openai_embedding_source.AsyncOpenAI")
def test_openai_embedding_import_and_construction(mock_async_openai):
    provider = OpenAIEmbeddingProvider(
        provider_config={
            "embedding_api_key": "test-key",
            "embedding_api_base": "https://api.openai.com/v1",
            "embedding_model": "text-embedding-3-small",
        },
        provider_settings={},
    )
    assert provider is not None
    assert provider.model == "text-embedding-3-small"


@patch("astrbot.core.provider.sources.openai_embedding_source.AsyncOpenAI")
def test_openai_embedding_default_model(mock_async_openai):
    provider = OpenAIEmbeddingProvider(
        provider_config={
            "embedding_api_key": "test-key",
        },
        provider_settings={},
    )
    assert provider.model == "text-embedding-3-small"


@patch("astrbot.core.provider.sources.openai_embedding_source.AsyncOpenAI")
def test_openai_embedding_api_base_convention(mock_async_openai):
    OpenAIEmbeddingProvider(
        provider_config={
            "embedding_api_key": "test-key",
            "embedding_api_base": "https://custom.api.com",
        },
        provider_settings={},
    )
    # Should automatically append /v1
    mock_async_openai.assert_called_once()
    _call_kwargs = mock_async_openai.call_args.kwargs
    assert _call_kwargs["base_url"] == "https://custom.api.com/v1"


@patch("astrbot.core.provider.sources.openai_embedding_source.AsyncOpenAI")
def test_openai_embedding_get_dim(mock_async_openai):
    provider = OpenAIEmbeddingProvider(
        provider_config={
            "embedding_api_key": "test-key",
            "embedding_dimensions": 256,
        },
        provider_settings={},
    )
    assert provider.get_dim() == 256
