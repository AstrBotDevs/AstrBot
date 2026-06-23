import pytest

from astrbot.core.knowledge_base.parsers import url_parser


class _FakeResponse:
    def __init__(self, status: int, json_data: dict):
        self.status = status
        self._json_data = json_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        return self._json_data

    async def text(self):
        return "error body"


class _FakeSession:
    """Captures the request and returns a canned response."""

    def __init__(self, response: _FakeResponse, recorder: dict):
        self._response = response
        self._recorder = recorder

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def post(self, url, json=None, headers=None, timeout=None):
        self._recorder["url"] = url
        self._recorder["json"] = json
        self._recorder["headers"] = headers
        return self._response


def _patch_session(monkeypatch, response: _FakeResponse) -> dict:
    recorder: dict = {}

    def fake_client_session(*args, **kwargs):
        return _FakeSession(response, recorder)

    monkeypatch.setattr(url_parser.aiohttp, "ClientSession", fake_client_session)
    return recorder


def test_unsupported_provider_raises():
    with pytest.raises(ValueError):
        url_parser.URLExtractor(["k"], provider="bocha")


def test_missing_keys_for_selected_provider_raises():
    # Firecrawl selected but only Tavily keys supplied.
    with pytest.raises(ValueError):
        url_parser.URLExtractor(["tavily-key"], provider="firecrawl")


@pytest.mark.asyncio
async def test_tavily_extraction_hits_tavily(monkeypatch):
    response = _FakeResponse(200, {"results": [{"raw_content": "tavily body"}]})
    recorder = _patch_session(monkeypatch, response)

    content = await url_parser.extract_text_from_url(
        "https://example.com", ["tavily-key"], provider="tavily"
    )

    assert content == "tavily body"
    assert recorder["url"] == "https://api.tavily.com/extract"
    assert recorder["headers"]["Authorization"] == "Bearer tavily-key"
    assert recorder["json"]["urls"] == ["https://example.com"]


@pytest.mark.asyncio
async def test_firecrawl_extraction_hits_firecrawl(monkeypatch):
    response = _FakeResponse(200, {"data": {"markdown": "# firecrawl body"}})
    recorder = _patch_session(monkeypatch, response)

    content = await url_parser.extract_text_from_url(
        "https://example.com",
        tavily_keys=[],
        provider="firecrawl",
        firecrawl_keys=["firecrawl-key"],
    )

    assert content == "# firecrawl body"
    assert recorder["url"] == "https://api.firecrawl.dev/v2/scrape"
    assert recorder["headers"]["Authorization"] == "Bearer firecrawl-key"
    assert recorder["json"] == {
        "url": "https://example.com",
        "formats": ["markdown"],
        "onlyMainContent": True,
    }


@pytest.mark.asyncio
async def test_firecrawl_empty_content_raises(monkeypatch):
    response = _FakeResponse(200, {"data": {"markdown": ""}})
    _patch_session(monkeypatch, response)

    with pytest.raises(ValueError):
        await url_parser.extract_text_from_url(
            "https://example.com",
            provider="firecrawl",
            firecrawl_keys=["firecrawl-key"],
        )


@pytest.mark.asyncio
async def test_default_provider_is_tavily_backward_compatible(monkeypatch):
    response = _FakeResponse(200, {"results": [{"raw_content": "legacy body"}]})
    recorder = _patch_session(monkeypatch, response)

    # Legacy positional call signature must keep working.
    content = await url_parser.extract_text_from_url(
        "https://example.com", ["tavily-key"]
    )

    assert content == "legacy body"
    assert recorder["url"] == "https://api.tavily.com/extract"
