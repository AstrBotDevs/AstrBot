"""Smoke tests for GeminiEmbeddingProvider."""
from unittest.mock import patch

from astrbot.core.provider.sources.gemini_embedding_source import (
    GeminiEmbeddingProvider,
)


def test_gemini_embedding_import():
    assert GeminiEmbeddingProvider is not None


@patch("astrbot.core.provider.sources.gemini_embedding_source.genai")
def test_gemini_embedding_construction(mock_genai):
    provider = GeminiEmbeddingProvider(
        provider_config={
            "embedding_api_key": "test-key",
            "embedding_api_base": "https://generativelanguage.googleapis.com",
            "embedding_model": "gemini-embedding-exp-03-07",
        },
        provider_settings={},
    )
    assert provider is not None
    assert provider.model == "gemini-embedding-exp-03-07"
    mock_genai.Client.assert_called_once()


@patch("astrbot.core.provider.sources.gemini_embedding_source.genai")
def test_gemini_embedding_default_model(mock_genai):
    provider = GeminiEmbeddingProvider(
        provider_config={
            "embedding_api_key": "test-key",
            "embedding_api_base": "https://generativelanguage.googleapis.com",
        },
        provider_settings={},
    )
    assert provider.model == "gemini-embedding-exp-03-07"


@patch("astrbot.core.provider.sources.gemini_embedding_source.genai")
def test_gemini_embedding_get_dim(mock_genai):
    provider = GeminiEmbeddingProvider(
        provider_config={
            "embedding_api_key": "test-key",
            "embedding_api_base": "https://generativelanguage.googleapis.com",
            "embedding_dimensions": 512,
        },
        provider_settings={},
    )
    assert provider.get_dim() == 512


@patch("astrbot.core.provider.sources.gemini_embedding_source.genai")
def test_gemini_embedding_get_dim_default(mock_genai):
    provider = GeminiEmbeddingProvider(
        provider_config={
            "embedding_api_key": "test-key",
            "embedding_api_base": "https://generativelanguage.googleapis.com",
        },
        provider_settings={},
    )
    assert provider.get_dim() == 768
