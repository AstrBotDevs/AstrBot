import asyncio
import json
from unittest.mock import Mock

import pytest

import astrbot.core.utils.llm_metadata as llm_metadata

METADATA = {
    "test-provider": {
        "models": {
            "test-model": {
                "id": "test-model",
                "limit": {"context": 4096, "output": 1024},
            }
        }
    }
}


class _AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        if isinstance(self.value, BaseException):
            raise self.value
        return self.value

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _Response:
    def __init__(self, data, json_error=None):
        self.data = data
        self.json_error = json_error

    def raise_for_status(self):
        return None

    async def json(self):
        if self.json_error is not None:
            raise self.json_error
        return self.data


class _Session:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.requested_urls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def get(self, url):
        self.requested_urls.append(url)
        return _AsyncContext(self.outcomes.pop(0))


@pytest.mark.asyncio
async def test_update_llm_metadata_uses_primary_url(monkeypatch):
    session = _Session([_Response(METADATA)])
    monkeypatch.setattr(
        llm_metadata.aiohttp,
        "ClientSession",
        lambda **_kwargs: session,
    )
    monkeypatch.setattr(llm_metadata, "build_tls_connector", lambda: None)
    info = Mock()
    monkeypatch.setattr(llm_metadata.logger, "info", info)
    cache = llm_metadata.LLM_METADATAS
    cache.clear()

    await llm_metadata.update_llm_metadata()

    assert session.requested_urls == [llm_metadata.LLM_METADATA_URLS[0]]
    assert llm_metadata.LLM_METADATAS is cache
    assert llm_metadata.LLM_METADATAS["test-model"]["limit"]["context"] == 4096
    assert info.call_count == 1
    assert llm_metadata.LLM_METADATA_URLS[0] in info.call_args.args[0]


@pytest.mark.asyncio
async def test_update_llm_metadata_falls_back_to_opencode_domain(monkeypatch):
    session = _Session(
        [llm_metadata.aiohttp.ClientError("primary unavailable"), _Response(METADATA)]
    )
    monkeypatch.setattr(
        llm_metadata.aiohttp,
        "ClientSession",
        lambda **_kwargs: session,
    )
    monkeypatch.setattr(llm_metadata, "build_tls_connector", lambda: None)
    warning = Mock()
    info = Mock()
    monkeypatch.setattr(llm_metadata.logger, "warning", warning)
    monkeypatch.setattr(llm_metadata.logger, "info", info)
    llm_metadata.LLM_METADATAS.clear()

    await llm_metadata.update_llm_metadata()

    assert session.requested_urls == list(llm_metadata.LLM_METADATA_URLS)
    assert "test-model" in llm_metadata.LLM_METADATAS
    assert warning.call_count == 1
    assert llm_metadata.LLM_METADATA_URLS[0] in warning.call_args.args[0]
    assert "primary unavailable" in warning.call_args.args[0]
    assert info.call_count == 1
    assert llm_metadata.LLM_METADATA_URLS[1] in info.call_args.args[0]


@pytest.mark.parametrize(
    "primary_outcome",
    [
        asyncio.TimeoutError(),
        _Response(
            None,
            json_error=json.JSONDecodeError("invalid JSON", "", 0),
        ),
        _Response(
            None,
            json_error=UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"),
        ),
        _Response(None),
    ],
    ids=["timeout", "invalid-json", "invalid-encoding", "empty-response"],
)
@pytest.mark.asyncio
async def test_update_llm_metadata_falls_back_for_recoverable_response_errors(
    monkeypatch, primary_outcome
):
    session = _Session([primary_outcome, _Response(METADATA)])
    monkeypatch.setattr(
        llm_metadata.aiohttp,
        "ClientSession",
        lambda **_kwargs: session,
    )
    monkeypatch.setattr(llm_metadata, "build_tls_connector", lambda: None)
    warning = Mock()
    monkeypatch.setattr(llm_metadata.logger, "warning", warning)
    llm_metadata.LLM_METADATAS.clear()

    await llm_metadata.update_llm_metadata()

    assert session.requested_urls == list(llm_metadata.LLM_METADATA_URLS)
    assert "test-model" in llm_metadata.LLM_METADATAS
    assert warning.call_count == 1
    assert llm_metadata.LLM_METADATA_URLS[0] in warning.call_args.args[0]


@pytest.mark.asyncio
async def test_update_llm_metadata_preserves_cache_when_all_endpoints_fail(monkeypatch):
    session = _Session(
        [
            llm_metadata.aiohttp.ClientError("primary unavailable"),
            asyncio.TimeoutError("fallback timed out"),
        ]
    )
    monkeypatch.setattr(
        llm_metadata.aiohttp,
        "ClientSession",
        lambda **_kwargs: session,
    )
    monkeypatch.setattr(llm_metadata, "build_tls_connector", lambda: None)
    warning = Mock()
    error = Mock()
    monkeypatch.setattr(llm_metadata.logger, "warning", warning)
    monkeypatch.setattr(llm_metadata.logger, "error", error)
    cache = llm_metadata.LLM_METADATAS
    cache.clear()
    cache["existing-model"] = {"id": "existing-model"}

    await llm_metadata.update_llm_metadata()

    assert session.requested_urls == list(llm_metadata.LLM_METADATA_URLS)
    assert cache == {"existing-model": {"id": "existing-model"}}
    assert warning.call_count == 2
    warning_messages = [call.args[0] for call in warning.call_args_list]
    assert all(
        url in message
        for url, message in zip(llm_metadata.LLM_METADATA_URLS, warning_messages)
    )
    assert error.call_count == 1
    assert "fallback timed out" in error.call_args.args[0]
