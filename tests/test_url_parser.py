"""URL extraction validates inputs and isolates the HTTP boundary."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock

import aiohttp
import pytest

from astrbot.core.knowledge_base.parsers import url_parser


@pytest.fixture
def transport(monkeypatch):
    response = MagicMock()
    response.status = 200
    response.json = AsyncMock(return_value={"results": [{"raw_content": "page text"}]})
    response.text = AsyncMock(return_value="service unavailable")
    response.__aenter__.return_value = response
    session = MagicMock()
    session.__aenter__.return_value = session
    session.post.return_value = response
    factory = Mock(return_value=session)
    monkeypatch.setattr(url_parser.aiohttp, "ClientSession", factory)
    return factory, session, response


def test_missing_keys_are_rejected_before_transport(transport):
    factory, _, _ = transport
    with pytest.raises(ValueError, match="keys are not configured"):
        url_parser.URLExtractor([])
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_empty_url_does_not_consume_a_key_or_open_transport(transport):
    factory, _, _ = transport
    extractor = url_parser.URLExtractor(["key-a", "key-b"])
    with pytest.raises(ValueError, match="non-empty"):
        await extractor.extract_text_from_url("")
    assert extractor.tavily_key_index == 0
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_key_rotation_is_ordered_for_concurrent_callers():
    extractor = url_parser.URLExtractor(["key-a", "key-b"])
    keys = await asyncio.gather(*(extractor._get_tavily_key() for _ in range(6)))
    assert keys == ["key-a", "key-b"] * 3
    assert extractor.tavily_key_index == 0


@pytest.mark.asyncio
async def test_extract_passes_url_authorization_and_bounded_timeout(transport):
    factory, session, response = transport
    assert (
        await url_parser.extract_text_from_url(
            "https://example.invalid/manual", ["key-a"]
        )
        == "page text"
    )
    factory.assert_called_once_with(trust_env=True)
    session.post.assert_called_once()
    call = session.post.call_args
    assert call.args == ("https://api.tavily.com/extract",)
    assert call.kwargs["json"] == {
        "urls": ["https://example.invalid/manual"],
        "extract_depth": "basic",
    }
    assert call.kwargs["headers"]["Authorization"] == "Bearer key-a"
    assert call.kwargs["timeout"].total == 30
    response.__aexit__.assert_awaited_once()
    session.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 429, 503])
async def test_http_errors_include_status_and_close_transport(transport, status):
    _, session, response = transport
    response.status = status
    with pytest.raises(OSError, match=f"status: {status}"):
        await url_parser.URLExtractor(["key"]).extract_text_from_url(
            "https://example.invalid"
        )
    response.json.assert_not_awaited()
    response.__aexit__.assert_awaited_once()
    session.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_result_reports_extraction_failure(transport):
    _, _, response = transport
    response.json.return_value = {"results": []}
    with pytest.raises(OSError, match="No content extracted"):
        await url_parser.URLExtractor(["key"]).extract_text_from_url(
            "https://example.invalid"
        )


@pytest.mark.asyncio
async def test_transport_error_preserves_its_cause(transport):
    _, session, _ = transport
    failure = aiohttp.ClientConnectionError("disconnected")
    session.post.side_effect = failure
    with pytest.raises(OSError, match="Failed to fetch URL") as caught:
        await url_parser.URLExtractor(["key"]).extract_text_from_url(
            "https://example.invalid"
        )
    assert caught.value.__cause__ is failure
    session.__aexit__.assert_awaited_once()
