from unittest.mock import AsyncMock, patch

import pytest

from astrbot.core.provider.sources.openai_embedding_source import (
    OpenAIEmbeddingProvider,
)


def _make_provider(overrides: dict | None = None) -> OpenAIEmbeddingProvider:
    provider_config = {
        "id": "test-openai-embedding",
        "embedding_api_key": "test-key",
        "embedding_model": "text-embedding-3-small",
    }
    if overrides:
        provider_config.update(overrides)
    return OpenAIEmbeddingProvider(
        provider_config=provider_config,
        provider_settings={},
    )


class TestOpenAIEmbeddingProviderApiBaseV1Suffix:
    """Test that /v1 suffix is auto-appended to embedding_api_base.

    Regression test for: https://github.com/AstrBotDevs/AstrBot/issues/6887
    PR #6669 removed automatic /v1 suffix because some providers don't use
    standard /v1/embeddings endpoint, but this broke OpenAI-compatible
    providers. PR #6863 reintroduces the auto-append logic.
    """

    def test_api_base_without_v1_gets_v1_appended(self) -> None:
        """api_base like 'https://api.openai.com' should become 'https://api.openai.com/v1'."""
        provider = _make_provider({"embedding_api_base": "https://api.openai.com"})
        # The provider should auto-append /v1
        assert provider.client.base_url == "https://api.openai.com/v1"

    def test_api_base_with_trailing_slash_gets_v1_appended(self) -> None:
        """api_base like 'https://api.openai.com/' should become 'https://api.openai.com/v1'."""
        provider = _make_provider({"embedding_api_base": "https://api.openai.com/"})
        assert provider.client.base_url == "https://api.openai.com/v1"

    def test_api_base_already_with_v1_is_unchanged(self) -> None:
        """api_base already ending with /v1 should not double-append."""
        provider = _make_provider({"embedding_api_base": "https://api.openai.com/v1"})
        assert provider.client.base_url == "https://api.openai.com/v1"

    def test_api_base_with_v1_trailing_slash_is_unchanged(self) -> None:
        """api_base already ending with /v1/ should not double-append."""
        provider = _make_provider({"embedding_api_base": "https://api.openai.com/v1/"})
        assert provider.client.base_url == "https://api.openai.com/v1/"

    def test_api_base_custom_endpoint_without_v1_gets_v1_appended(self) -> None:
        """Custom API base like 'https://openai.example.com' should become 'https://openai.example.com/v1'."""
        provider = _make_provider({"embedding_api_base": "https://openai.example.com"})
        assert provider.client.base_url == "https://openai.example.com/v1"

    def test_api_base_custom_endpoint_already_with_v1_is_unchanged(self) -> None:
        """Custom API base already with /v1 should not change."""
        provider = _make_provider({"embedding_api_base": "https://openai.example.com/v1"})
        assert provider.client.base_url == "https://openai.example.com/v1"

    def test_empty_api_base_uses_default(self) -> None:
        """Empty api_base should use the default OpenAI endpoint."""
        provider = _make_provider({"embedding_api_base": ""})
        assert provider.client.base_url == "https://api.openai.com/v1"

    def test_default_api_base_is_unchanged(self) -> None:
        """Default api_base (not set) should be the standard OpenAI endpoint."""
        provider = _make_provider()
        assert provider.client.base_url == "https://api.openai.com/v1"
