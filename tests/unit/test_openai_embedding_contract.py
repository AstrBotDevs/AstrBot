"""Offline error and lifecycle contracts for the OpenAI embedding adapter."""

import asyncio
import logging

import pytest

from astrbot.core.provider.sources import openai_embedding_source
from astrbot.core.provider.sources.openai_embedding_source import (
    OpenAIEmbeddingProvider,
)

pytestmark = pytest.mark.provider

_SENSITIVE_ERROR = (
    "api_key=openai-embedding-api-key "
    "Bearer openai-embedding-bearer "
    "password=openai-embedding-password "
    "https://internal.example/openai-embedding "
    "C:\\private\\openai-embedding.txt "
    "/srv/astrbot/openai-embedding.json"
)
_SENSITIVE_VALUES = (
    "openai-embedding-api-key",
    "openai-embedding-bearer",
    "openai-embedding-password",
    "https://internal.example/openai-embedding",
    "C:\\private\\openai-embedding.txt",
    "/srv/astrbot/openai-embedding.json",
)


def _assert_no_sensitive_values(*texts: object) -> None:
    for text in texts:
        for value in _SENSITIVE_VALUES:
            assert value not in str(text)


class _EmbeddingItem:
    def __init__(self, embedding: object) -> None:
        self.embedding = embedding


class _Response:
    def __init__(self, data: object) -> None:
        self.data = data


class _Embeddings:
    def __init__(self, response: _Response | BaseException) -> None:
        self.response = response

    async def create(self, **_kwargs: object) -> _Response:
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


class _Client:
    def __init__(
        self,
        response: _Response | BaseException,
        *,
        close_error: BaseException | None = None,
    ) -> None:
        self.embeddings = _Embeddings(response)
        self.close_error = close_error
        self.closed = False

    async def close(self) -> None:
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


def _provider(client: _Client) -> OpenAIEmbeddingProvider:
    provider = OpenAIEmbeddingProvider.__new__(OpenAIEmbeddingProvider)
    provider.client = client
    provider.model = "test-embedding"
    provider.provider_config = {"embedding_dimensions_mode": "never"}
    return provider


def test_openai_embedding_does_not_log_proxy_or_api_base_credentials(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    class _HTTPClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

    class _OpenAIClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

    monkeypatch.setattr(openai_embedding_source.httpx2, "AsyncClient", _HTTPClient)
    monkeypatch.setattr(openai_embedding_source, "AsyncOpenAI", _OpenAIClient)

    with caplog.at_level(logging.INFO, logger="astrbot"):
        OpenAIEmbeddingProvider(
            {
                "type": "openai_embedding",
                "proxy": _SENSITIVE_ERROR,
                "embedding_api_base": "https://internal.example/openai-embedding",
            },
            {},
        )

    _assert_no_sensitive_values(caplog.text)


@pytest.mark.asyncio
async def test_openai_embedding_hides_sdk_error_from_logs_and_exception(caplog) -> None:
    provider = _provider(_Client(RuntimeError(_SENSITIVE_ERROR)))

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        with pytest.raises(
            RuntimeError, match="OpenAI embedding request failed"
        ) as caught:
            await provider.get_embedding("text")

    assert caught.value.__cause__ is None
    _assert_no_sensitive_values(caught.value, caplog.text)


@pytest.mark.asyncio
async def test_openai_embedding_rejects_malformed_response_shape() -> None:
    provider = _provider(_Client(_Response([_EmbeddingItem(_SENSITIVE_ERROR)])))

    with pytest.raises(RuntimeError, match="OpenAI embedding request failed") as caught:
        await provider.get_embeddings(["text"])

    assert caught.value.__cause__ is None
    _assert_no_sensitive_values(caught.value)


@pytest.mark.asyncio
async def test_openai_embedding_propagates_cancellation() -> None:
    provider = _provider(_Client(asyncio.CancelledError()))

    with pytest.raises(asyncio.CancelledError):
        await provider.get_embeddings(["text"])


@pytest.mark.asyncio
async def test_openai_embedding_terminate_drops_client_and_hides_close_error(
    caplog,
) -> None:
    client = _Client(_Response([]), close_error=RuntimeError(_SENSITIVE_ERROR))
    provider = _provider(client)

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        await provider.terminate()

    assert client.closed is True
    assert provider.client is None
    _assert_no_sensitive_values(caplog.text)


def test_openai_embedding_hides_invalid_dimension_value_in_logs(caplog) -> None:
    provider = OpenAIEmbeddingProvider.__new__(OpenAIEmbeddingProvider)
    provider.model = "test-embedding"
    provider.provider_config = {
        "embedding_dimensions_mode": "always",
        "embedding_dimensions": _SENSITIVE_ERROR,
    }

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        assert provider._embedding_kwargs() == {}

    _assert_no_sensitive_values(caplog.text)
