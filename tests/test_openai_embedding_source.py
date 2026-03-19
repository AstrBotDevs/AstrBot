import pytest

from astrbot.core.provider.sources.openai_embedding_source import (
    OpenAIEmbeddingProvider,
)
from astrbot.core.provider.utils import resolve_openai_compatible_base_url


def _make_provider(overrides: dict | None = None) -> OpenAIEmbeddingProvider:
    provider_config = {
        "id": "test-openai-embedding",
        "type": "openai_embedding",
        "embedding_api_key": "test-key",
        "embedding_model": "text-embedding-3-small",
    }
    if overrides:
        provider_config.update(overrides)
    return OpenAIEmbeddingProvider(
        provider_config=provider_config,
        provider_settings={},
    )


class TestResolveOpenAICompatibleBaseUrl:
    """Test the resolve_openai_compatible_base_url helper function."""

    def test_auto_mode_adds_v1_when_missing(self):
        """Test that auto mode adds /v1 suffix when not present."""
        result = resolve_openai_compatible_base_url(
            "https://api.example.com",
            mode="auto",
        )
        assert result == "https://api.example.com/v1"

    def test_auto_mode_keeps_v1_when_present(self):
        """Test that auto mode keeps /v1 suffix when already present."""
        result = resolve_openai_compatible_base_url(
            "https://api.example.com/v1",
            mode="auto",
        )
        assert result == "https://api.example.com/v1"

    def test_force_v1_mode_always_adds_v1(self):
        """Test that force_v1 mode always adds /v1 suffix."""
        result = resolve_openai_compatible_base_url(
            "https://api.example.com/v1",
            mode="force_v1",
        )
        assert result == "https://api.example.com/v1"

    def test_force_v1_mode_adds_v1_when_missing(self):
        """Test that force_v1 mode adds /v1 suffix when missing."""
        result = resolve_openai_compatible_base_url(
            "https://api.example.com",
            mode="force_v1",
        )
        assert result == "https://api.example.com/v1"

    def test_as_is_mode_keeps_url_unchanged(self):
        """Test that as_is mode keeps URL unchanged."""
        result = resolve_openai_compatible_base_url(
            "https://api.example.com/custom/path",
            mode="as_is",
        )
        assert result == "https://api.example.com/custom/path"

    def test_as_is_mode_removes_trailing_slash(self):
        """Test that as_is mode removes trailing slash."""
        result = resolve_openai_compatible_base_url(
            "https://api.example.com/",
            mode="as_is",
        )
        assert result == "https://api.example.com"

    def test_empty_url_returns_default(self):
        """Test that empty URL returns the default base URL."""
        result = resolve_openai_compatible_base_url(
            "",
            mode="auto",
        )
        assert result == "https://api.openai.com/v1"


@pytest.mark.asyncio
async def test_openai_embedding_provider_auto_mode():
    """Test OpenAI Embedding provider with auto mode (default)."""
    provider = _make_provider(
        {"embedding_api_base": "https://api.example.com", "embedding_api_base_mode": "auto"}
    )
    try:
        assert str(provider.client.base_url) == "https://api.example.com/v1/"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_openai_embedding_provider_force_v1_mode():
    """Test OpenAI Embedding provider with force_v1 mode."""
    provider = _make_provider(
        {
            "embedding_api_base": "https://api.example.com",
            "embedding_api_base_mode": "force_v1",
        }
    )
    try:
        assert str(provider.client.base_url) == "https://api.example.com/v1/"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_openai_embedding_provider_as_is_mode():
    """Test OpenAI Embedding provider with as_is mode."""
    provider = _make_provider(
        {
            "embedding_api_base": "https://api.example.com/v2/embeddings",
            "embedding_api_base_mode": "as_is",
        }
    )
    try:
        assert str(provider.client.base_url) == "https://api.example.com/v2/embeddings/"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_openai_embedding_provider_default_base_when_empty():
    """Test OpenAI Embedding provider with empty base URL uses default."""
    provider = _make_provider({"embedding_api_base": ""})
    try:
        assert str(provider.client.base_url) == "https://api.openai.com/v1/"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_openai_embedding_provider_with_v1_already_present():
    """Test OpenAI Embedding provider when URL already has /v1."""
    provider = _make_provider(
        {"embedding_api_base": "https://api.example.com/v1", "embedding_api_base_mode": "auto"}
    )
    try:
        assert str(provider.client.base_url) == "https://api.example.com/v1/"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_openai_embedding_provider_with_trailing_slash():
    """Test OpenAI Embedding provider keeps URL unchanged in as_is mode."""
    provider = _make_provider(
        {"embedding_api_base": "https://api.example.com/", "embedding_api_base_mode": "as_is"}
    )
    try:
        # The provider returns URL unchanged, OpenAI client adds trailing slash
        assert str(provider.client.base_url) == "https://api.example.com/"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_openai_embedding_provider_auto_mode_default():
    """Test OpenAI Embedding provider auto mode is default when not specified."""
    provider = _make_provider({"embedding_api_base": "https://api.example.com"})
    try:
        # Should default to auto mode
        assert str(provider.client.base_url) == "https://api.example.com/v1/"
    finally:
        await provider.terminate()
