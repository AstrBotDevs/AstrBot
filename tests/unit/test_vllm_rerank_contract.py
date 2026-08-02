"""Offline lifecycle and error-boundary contracts for VLLM reranking."""

import asyncio
import logging

import aiohttp
import pytest

from astrbot.core.provider.entities import RerankResult
from astrbot.core.provider.sources.vllm_rerank_source import VLLMRerankProvider

pytestmark = pytest.mark.provider

_SENSITIVE_ERROR = (
    "api_key=vllm-api-key "
    "Bearer vllm-bearer-token "
    "password=vllm-password "
    "https://internal.example/rerank "
    "C:\\private\\rerank.txt "
    "/srv/astrbot/rerank.json"
)
_SENSITIVE_VALUES = (
    "vllm-api-key",
    "vllm-bearer-token",
    "vllm-password",
    "https://internal.example/rerank",
    "C:\\private\\rerank.txt",
    "/srv/astrbot/rerank.json",
)
_REQUEST_ERROR = "VLLM rerank request failed"


def _assert_no_sensitive_values(*texts: object) -> None:
    for text in texts:
        rendered = str(text)
        for value in _SENSITIVE_VALUES:
            assert value not in rendered


class _Response:
    def __init__(
        self,
        status: object,
        payload: object,
        json_error: BaseException | None = None,
    ) -> None:
        self.status = status
        self.payload = payload
        self.json_error = json_error

    async def json(self) -> object:
        if self.json_error is not None:
            raise self.json_error
        return self.payload


class _Request:
    def __init__(self, response: _Response | BaseException) -> None:
        self.response = response

    async def __aenter__(self) -> _Response:
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response

    async def __aexit__(self, *_args: object) -> None:
        return None


class _Client:
    def __init__(
        self, response: _Response | BaseException, *, closed: bool = False
    ) -> None:
        self.response = response
        self.closed = closed
        self.close_error: BaseException | None = None
        self.close_calls = 0
        self.posts: list[tuple[str, dict]] = []

    def post(self, url: str, *, json: dict) -> _Request:
        self.posts.append((url, json))
        return _Request(self.response)

    async def close(self) -> None:
        self.close_calls += 1
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


def _provider(client: _Client) -> VLLMRerankProvider:
    provider = VLLMRerankProvider.__new__(VLLMRerankProvider)
    provider.client = client
    provider.base_url = "https://rerank.example.test"
    provider.api_suffix = "/v1/rerank"
    provider.model = "test-reranker"
    return provider


@pytest.mark.asyncio
async def test_rerank_keeps_payload_and_returns_valid_results() -> None:
    client = _Client(
        _Response(200, {"results": [{"index": 1, "relevance_score": 0.9}]})
    )
    provider = _provider(client)

    result = await provider.rerank("query", ["a", "b"], top_n=1)

    assert result == [RerankResult(index=1, relevance_score=0.9)]
    assert client.posts == [
        (
            "https://rerank.example.test/v1/rerank",
            {
                "query": "query",
                "documents": ["a", "b"],
                "model": "test-reranker",
                "top_n": 1,
            },
        )
    ]


@pytest.mark.asyncio
async def test_rerank_hides_http_error_body_from_exception_and_logs(caplog) -> None:
    provider = _provider(_Client(_Response(500, {"detail": _SENSITIVE_ERROR})))

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        with pytest.raises(RuntimeError, match=_REQUEST_ERROR) as caught:
            await provider.rerank("query", ["document"])

    _assert_no_sensitive_values(caught.value, caplog.text)


@pytest.mark.asyncio
async def test_rerank_hides_network_error_from_exception_and_logs(caplog) -> None:
    provider = _provider(_Client(aiohttp.ClientError(_SENSITIVE_ERROR)))

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        with pytest.raises(RuntimeError, match=_REQUEST_ERROR) as caught:
            await provider.rerank("query", ["document"])

    _assert_no_sensitive_values(caught.value, caplog.text)


@pytest.mark.asyncio
async def test_rerank_hides_json_error_from_exception_and_logs(caplog) -> None:
    provider = _provider(
        _Client(_Response(200, {}, json_error=RuntimeError(_SENSITIVE_ERROR)))
    )

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        with pytest.raises(RuntimeError, match=_REQUEST_ERROR) as caught:
            await provider.rerank("query", ["document"])

    _assert_no_sensitive_values(caught.value, caplog.text)


@pytest.mark.asyncio
async def test_rerank_hides_invalid_status_value_from_logs(caplog) -> None:
    provider = _provider(_Client(_Response(_SENSITIVE_ERROR, {})))

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        with pytest.raises(RuntimeError, match=_REQUEST_ERROR) as caught:
            await provider.rerank("query", ["document"])

    _assert_no_sensitive_values(caught.value, caplog.text)


@pytest.mark.asyncio
async def test_rerank_skips_malformed_results_without_logging_contents(caplog) -> None:
    provider = _provider(
        _Client(
            _Response(
                200,
                {
                    "results": [
                        {"index": 0, "relevance_score": 0.8},
                        {"index": 1, "relevance_score": _SENSITIVE_ERROR},
                        _SENSITIVE_ERROR,
                    ]
                },
            )
        )
    )

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        result = await provider.rerank("query", ["document"])

    assert result == [RerankResult(index=0, relevance_score=0.8)]
    _assert_no_sensitive_values(caplog.text)


@pytest.mark.asyncio
async def test_rerank_rejects_non_object_response_without_leaking_contents(
    caplog,
) -> None:
    provider = _provider(_Client(_Response(200, [_SENSITIVE_ERROR])))

    with caplog.at_level(logging.ERROR, logger="astrbot"):
        with pytest.raises(RuntimeError, match=_REQUEST_ERROR) as caught:
            await provider.rerank("query", ["document"])

    _assert_no_sensitive_values(caught.value, caplog.text)


@pytest.mark.asyncio
async def test_rerank_skips_request_for_empty_documents() -> None:
    client = _Client(_Response(200, {"results": []}))
    provider = _provider(client)

    assert await provider.rerank("query", []) == []
    assert client.posts == []


@pytest.mark.asyncio
async def test_rerank_propagates_cancellation() -> None:
    provider = _provider(_Client(asyncio.CancelledError()))

    with pytest.raises(asyncio.CancelledError):
        await provider.rerank("query", ["document"])


@pytest.mark.asyncio
async def test_terminate_sanitizes_close_failure_and_drops_client(caplog) -> None:
    client = _Client(_Response(200, {}))
    client.close_error = RuntimeError(_SENSITIVE_ERROR)
    provider = _provider(client)

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        await provider.terminate()

    assert client.close_calls == 1
    assert provider.client is None
    _assert_no_sensitive_values(caplog.text)


@pytest.mark.asyncio
async def test_terminate_drops_an_already_closed_client() -> None:
    client = _Client(_Response(200, {}), closed=True)
    provider = _provider(client)

    await provider.terminate()

    assert client.close_calls == 0
    assert provider.client is None


@pytest.mark.asyncio
async def test_terminate_propagates_cancellation_after_dropping_client() -> None:
    client = _Client(_Response(200, {}))
    client.close_error = asyncio.CancelledError()
    provider = _provider(client)

    with pytest.raises(asyncio.CancelledError):
        await provider.terminate()

    assert client.close_calls == 1
    assert provider.client is None
