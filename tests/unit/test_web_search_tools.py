import json
from types import SimpleNamespace

import pytest

from astrbot.core.tools import web_search_tools as tools


class _FakeConfig(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.saved = False

    def save_config(self):
        self.saved = True


def test_normalize_legacy_web_search_config_migrates_firecrawl_key():
    config = _FakeConfig(
        {"provider_settings": {"websearch_firecrawl_key": "firecrawl-key"}}
    )

    tools.normalize_legacy_web_search_config(config)

    assert config["provider_settings"]["websearch_firecrawl_key"] == ["firecrawl-key"]
    assert config.saved is True


@pytest.mark.asyncio
async def test_firecrawl_search_maps_web_results(monkeypatch):
    async def fake_firecrawl_search(provider_settings, payload):
        assert provider_settings["websearch_firecrawl_key"] == ["firecrawl-key"]
        assert payload == {
            "query": "AstrBot",
            "limit": 3,
            "sources": ["web"],
            "country": "US",
        }
        return [
            tools.SearchResult(
                title="AstrBot",
                url="https://example.com",
                snippet="Search result",
            )
        ]

    monkeypatch.setattr(tools, "_firecrawl_search", fake_firecrawl_search)
    tool = tools.FirecrawlWebSearchTool()
    context = _context_with_provider_settings(
        {"websearch_firecrawl_key": ["firecrawl-key"]}
    )

    result = await tool.call(context, query="AstrBot", limit=3, country="US")

    assert json.loads(result)["results"] == [
        {
            "title": "AstrBot",
            "url": "https://example.com",
            "snippet": "Search result",
            "index": json.loads(result)["results"][0]["index"],
        }
    ]


@pytest.mark.asyncio
async def test_firecrawl_search_maps_v2_data_list(monkeypatch):
    session = _FakeFirecrawlSession(
        _FakeFirecrawlResponse(
            status=200,
            json_data={
                "success": True,
                "data": [
                    {
                        "title": "AstrBot",
                        "url": "https://example.com",
                        "description": "Search result",
                    }
                ],
            },
        )
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    results = await tools._firecrawl_search(
        {"websearch_firecrawl_key": ["firecrawl-key"]},
        {"query": "AstrBot", "limit": 5, "sources": ["web"]},
    )

    assert session.posted == {
        "url": "https://api.firecrawl.dev/v2/search",
        "json": {"query": "AstrBot", "limit": 5, "sources": ["web"]},
        "headers": {
            "Authorization": "Bearer firecrawl-key",
            "Content-Type": "application/json",
        },
    }
    assert results == [
        tools.SearchResult(
            title="AstrBot", url="https://example.com", snippet="Search result"
        )
    ]


@pytest.mark.asyncio
async def test_firecrawl_search_maps_v2_grouped_web_data(monkeypatch):
    session = _FakeFirecrawlSession(
        _FakeFirecrawlResponse(
            status=200,
            json_data={
                "success": True,
                "data": {
                    "web": [
                        {
                            "title": "AstrBot",
                            "url": "https://example.com",
                            "description": "Search result",
                        }
                    ]
                },
            },
        )
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    results = await tools._firecrawl_search(
        {"websearch_firecrawl_key": ["firecrawl-key"]},
        {"query": "AstrBot", "limit": 5, "sources": ["web"]},
    )

    assert results == [
        tools.SearchResult(
            title="AstrBot", url="https://example.com", snippet="Search result"
        )
    ]


@pytest.mark.asyncio
async def test_firecrawl_search_payload_omits_tbs_and_uses_default_limit(monkeypatch):
    async def fake_firecrawl_search(provider_settings, payload):
        assert payload == {
            "query": "AstrBot",
            "limit": 5,
            "sources": ["web"],
            "country": "US",
        }
        return [
            tools.SearchResult(
                title="AstrBot",
                url="https://example.com",
                snippet="Search result",
            )
        ]

    monkeypatch.setattr(tools, "_firecrawl_search", fake_firecrawl_search)
    tool = tools.FirecrawlWebSearchTool()
    context = _context_with_provider_settings(
        {"websearch_firecrawl_key": ["firecrawl-key"]}
    )

    result = await tool.call(
        context,
        query="AstrBot",
        tbs="qdr:d",
        country="US",
    )

    assert json.loads(result)["results"][0]["url"] == "https://example.com"
    assert "tbs" not in tool.parameters["properties"]


@pytest.mark.asyncio
async def test_firecrawl_extract_returns_scraped_markdown(monkeypatch):
    async def fake_firecrawl_scrape(provider_settings, payload):
        assert provider_settings["websearch_firecrawl_key"] == ["firecrawl-key"]
        assert payload == {
            "url": "https://example.com",
            "formats": ["markdown"],
            "onlyMainContent": True,
        }
        return {"url": "https://example.com", "markdown": "# Example"}

    monkeypatch.setattr(tools, "_firecrawl_scrape", fake_firecrawl_scrape)
    tool = tools.FirecrawlExtractWebPageTool()
    context = _context_with_provider_settings(
        {"websearch_firecrawl_key": ["firecrawl-key"]}
    )

    result = await tool.call(context, url="https://example.com")

    assert result == "URL: https://example.com\nContent: # Example"


@pytest.mark.asyncio
async def test_firecrawl_search_uses_session_context(monkeypatch):
    session = _FakeFirecrawlSession(
        _FakeFirecrawlResponse(
            status=200,
            json_data={
                "success": True,
                "data": [
                    {
                        "title": "AstrBot",
                        "url": "https://example.com",
                        "description": "Search result",
                    }
                ],
            },
        )
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    await tools._firecrawl_search(
        {"websearch_firecrawl_key": ["firecrawl-key"]},
        {"query": "AstrBot"},
    )

    assert session.trust_env is True
    assert session.entered is True
    assert session.exited is True
    assert session.posted == {
        "url": "https://api.firecrawl.dev/v2/search",
        "json": {"query": "AstrBot"},
        "headers": {
            "Authorization": "Bearer firecrawl-key",
            "Content-Type": "application/json",
        },
    }


@pytest.mark.asyncio
async def test_firecrawl_search_raises_error_for_http_errors(monkeypatch):
    session = _FakeFirecrawlSession(
        _FakeFirecrawlResponse(status=401, text_data="Unauthorized")
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    with pytest.raises(
        Exception,
        match="Firecrawl web search failed: Unauthorized, status: 401",
    ):
        await tools._firecrawl_search(
            {"websearch_firecrawl_key": ["firecrawl-key"]},
            {"query": "AstrBot"},
        )

    assert session.trust_env is True
    assert session.entered is True
    assert session.exited is True


@pytest.mark.asyncio
async def test_firecrawl_scrape_uses_request_setup(monkeypatch):
    session = _FakeFirecrawlSession(
        _FakeFirecrawlResponse(
            status=200,
            json_data={
                "success": True,
                "data": {"url": "https://example.com", "markdown": "# Example"},
            },
        )
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    result = await tools._firecrawl_scrape(
        {"websearch_firecrawl_key": ["firecrawl-key"]},
        {"url": "https://example.com", "formats": ["markdown"]},
    )

    assert result == {"url": "https://example.com", "markdown": "# Example"}
    assert session.trust_env is True
    assert session.entered is True
    assert session.exited is True
    assert session.posted == {
        "url": "https://api.firecrawl.dev/v2/scrape",
        "json": {"url": "https://example.com", "formats": ["markdown"]},
        "headers": {
            "Authorization": "Bearer firecrawl-key",
            "Content-Type": "application/json",
        },
    }


@pytest.mark.asyncio
async def test_firecrawl_scrape_raises_error_for_http_errors(monkeypatch):
    session = _FakeFirecrawlSession(
        _FakeFirecrawlResponse(status=401, text_data="Unauthorized")
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    with pytest.raises(
        Exception,
        match="Firecrawl web scraper failed: Unauthorized, status: 401",
    ):
        await tools._firecrawl_scrape(
            {"websearch_firecrawl_key": ["firecrawl-key"]},
            {"url": "https://example.com", "formats": ["markdown"]},
        )

    assert session.trust_env is True
    assert session.entered is True
    assert session.exited is True


class _FakeFirecrawlResponse:
    def __init__(self, status=200, json_data=None, text_data=""):
        self.status = status
        self.json_data = json_data or {}
        self.text_data = text_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def json(self):
        return self.json_data

    async def text(self):
        return self.text_data


class _FakeFirecrawlSession:
    def __init__(self, response):
        self.response = response
        self.trust_env = None
        self.entered = False
        self.exited = False
        self.posted = None

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.exited = True
        return None

    def post(self, url, json, headers):
        self.posted = {"url": url, "json": json, "headers": headers}
        return self.response


class _CycleSession:
    """Return the next response for each post() call in key rotation tests."""

    def __init__(self, responses: list):
        self.responses = responses
        self.cursor = 0
        self.trust_env = None
        self.entered = False
        self.exited = False
        self.calls: list[dict] = []

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.exited = True
        return None

    def post(self, url, json, headers):
        resp = self.responses[self.cursor]
        self.cursor = (self.cursor + 1) % len(self.responses)
        self.calls.append({"url": url, "json": json, "headers": headers})
        return resp


class _TavilyResponse:
    """Fake HTTP response for Tavily API tests."""

    def __init__(self, status=200, jsonData=None, textData=""):
        self.status = status
        self.jsonData = jsonData or {}
        self.textData = textData

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def json(self):
        return self.jsonData

    async def text(self):
        return self.textData


@pytest.fixture(autouse=True)
def _resetKeyRotators():
    """Reset KeyRotator indexes to avoid state leakage between tests."""
    tools._TAVILY_KEY_ROTATOR.index = 0
    tools._BOCHA_KEY_ROTATOR.index = 0
    tools._BRAVE_KEY_ROTATOR.index = 0
    tools._FIRECRAWL_KEY_ROTATOR.index = 0
    yield
    tools._TAVILY_KEY_ROTATOR.index = 0
    tools._BOCHA_KEY_ROTATOR.index = 0
    tools._BRAVE_KEY_ROTATOR.index = 0
    tools._FIRECRAWL_KEY_ROTATOR.index = 0


# ---------------------------------------------------------------------------
# Issue #8886: Tavily key rotation did not fail over to the next key.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tavily_search_raises_value_error_when_no_key_configured():
    """Raise ValueError when no Tavily API key is configured."""
    with pytest.raises(
        ValueError,
        match="Error: Tavily API key is not configured in AstrBot.",
    ):
        await tools._tavily_search({}, {"query": "test"})


@pytest.mark.asyncio
async def test_tavily_search_key_failover_on_quota_exceeded_432(
    monkeypatch,
):
    """Fail over to the second key when the first key returns 432."""
    session = _CycleSession(
        [
            _TavilyResponse(
                status=432,
                textData='{"detail":{"error":"quota exceeded"}}',
            ),
            _TavilyResponse(
                status=200,
                jsonData={
                    "results": [
                        {"title": "AstrBot", "url": "https://example.com", "content": "OK"}
                    ]
                },
            ),
        ]
    )

    def fakeClientSession(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fakeClientSession)

    providerSettings = {"websearch_tavily_key": ["bad-key", "good-key"]}

    results = await tools._tavily_search(providerSettings, {"query": "test"})

    assert len(results) == 1
    assert results[0].title == "AstrBot"
    assert results[0].url == "https://example.com"
    assert len(session.calls) == 2  # Both keys were attempted.


@pytest.mark.asyncio
async def test_tavily_search_key_failover_on_rate_limited_429(
    monkeypatch,
):
    """Fail over to the second key when the first key returns 429."""
    session = _CycleSession(
        [
            _TavilyResponse(
                status=429,
                textData='{"detail":{"error":"rate limited"}}',
            ),
            _TavilyResponse(
                status=200,
                jsonData={
                    "results": [
                        {"title": "RateLimitOK", "url": "https://example2.com", "content": "OK"}
                    ]
                },
            ),
        ]
    )

    def fakeClientSession(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fakeClientSession)

    providerSettings = {"websearch_tavily_key": ["rate-limited-key", "good-key"]}

    results = await tools._tavily_search(providerSettings, {"query": "test"})

    assert len(results) == 1
    assert results[0].title == "RateLimitOK"
    assert len(session.calls) == 2  # Both keys were attempted.


@pytest.mark.asyncio
async def test_tavily_search_fails_when_all_keys_exhausted_8886(
    monkeypatch,
):
    """Raise the last error when all keys are exhausted."""
    # Both responses are retryable failures.
    session = _CycleSession(
        [
            _TavilyResponse(
                status=432,
                textData='{"detail":{"error":"quota exceeded"}}',
            ),
            _TavilyResponse(
                status=429,
                textData='{"detail":{"error":"rate limited"}}',
            ),
        ]
    )

    def fakeClientSession(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fakeClientSession)

    providerSettings = {"websearch_tavily_key": ["bad-key-1", "bad-key-2"]}

    with pytest.raises(
        Exception,
        match="Tavily web search failed",
    ):
        await tools._tavily_search(providerSettings, {"query": "test"})

    assert len(session.calls) == 2  # Both keys were attempted.


@pytest.mark.asyncio
async def test_tavily_search_does_not_failover_on_server_error_500(
    monkeypatch,
):
    """Raise immediately for non-key-related errors such as 500 responses."""
    session = _CycleSession(
        [
            _TavilyResponse(
                status=500,
                textData='{"error":"internal server error"}',
            ),
            _TavilyResponse(
                status=200,
                jsonData={
                    "results": [
                        {"title": "OK", "url": "https://example.com", "content": "OK"}
                    ]
                },
            ),
        ]
    )

    def fakeClientSession(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fakeClientSession)

    providerSettings = {"websearch_tavily_key": ["key-1", "key-2"]}

    with pytest.raises(
        Exception,
        match="Tavily web search failed.*status: 500",
    ):
        await tools._tavily_search(providerSettings, {"query": "test"})

    # Only one key is attempted because 500 is not retryable.
    assert len(session.calls) == 1


def _context_with_provider_settings(provider_settings):
    config = {"provider_settings": provider_settings}
    agent_context = SimpleNamespace(
        context=SimpleNamespace(get_config=lambda umo: config),
        event=SimpleNamespace(unified_msg_origin="test:private:session"),
    )
    return SimpleNamespace(context=agent_context)


# --- Exa tests ---


def test_normalize_legacy_web_search_config_migrates_exa_key():
    config = _FakeConfig({"provider_settings": {"websearch_exa_key": "exa-key"}})

    tools.normalize_legacy_web_search_config(config)

    assert config["provider_settings"]["websearch_exa_key"] == ["exa-key"]
    assert config.saved is True


@pytest.mark.asyncio
async def test_exa_search_maps_results(monkeypatch):
    async def fake_exa_search(provider_settings, payload):
        assert provider_settings["websearch_exa_key"] == ["exa-key"]
        assert payload["query"] == "AstrBot"
        assert payload["numResults"] == 5
        return [
            tools.SearchResult(
                title="AstrBot",
                url="https://example.com",
                snippet="AI Agent Assistant",
            )
        ]

    monkeypatch.setattr(tools, "_exa_search", fake_exa_search)
    tool = tools.ExaWebSearchTool()
    context = _context_with_provider_settings({"websearch_exa_key": ["exa-key"]})

    result = await tool.call(context, query="AstrBot", num_results=5)

    parsed = json.loads(result)
    assert parsed["results"][0]["title"] == "AstrBot"
    assert parsed["results"][0]["url"] == "https://example.com"
    assert parsed["results"][0]["snippet"] == "AI Agent Assistant"


@pytest.mark.asyncio
async def test_exa_search_raw_api_call(monkeypatch):
    session = _FakeFirecrawlSession(
        _FakeFirecrawlResponse(
            status=200,
            json_data={
                "results": [
                    {
                        "title": "AstrBot",
                        "url": "https://example.com",
                        "text": "AI Agent Assistant",
                    }
                ],
            },
        )
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    results = await tools._exa_search(
        {"websearch_exa_key": ["exa-key"]},
        {"query": "AstrBot", "numResults": 10, "type": "auto"},
    )

    assert session.posted["url"] == "https://api.exa.ai/search"
    assert session.posted["headers"]["x-api-key"] == "exa-key"
    assert results == [
        tools.SearchResult(
            title="AstrBot", url="https://example.com", snippet="AI Agent Assistant"
        )
    ]


@pytest.mark.asyncio
async def test_exa_search_raises_on_http_error(monkeypatch):
    session = _FakeFirecrawlSession(
        _FakeFirecrawlResponse(status=401, text_data="Unauthorized")
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    with pytest.raises(
        Exception,
        match="Exa web search failed: Unauthorized, status: 401",
    ):
        await tools._exa_search(
            {"websearch_exa_key": ["exa-key"]},
            {"query": "AstrBot"},
        )


@pytest.mark.asyncio
async def test_exa_get_contents_returns_text(monkeypatch):
    async def fake_exa_get_contents(provider_settings, payload):
        assert provider_settings["websearch_exa_key"] == ["exa-key"]
        assert payload["ids"] == ["https://example.com"]
        return [{"url": "https://example.com", "text": "# Example Content"}]

    monkeypatch.setattr(tools, "_exa_get_contents", fake_exa_get_contents)
    tool = tools.ExaGetContentsTool()
    context = _context_with_provider_settings({"websearch_exa_key": ["exa-key"]})

    result = await tool.call(context, url="https://example.com")

    assert result == "URL: https://example.com\nContent: # Example Content"


@pytest.mark.asyncio
async def test_exa_get_contents_raises_on_http_error(monkeypatch):
    session = _FakeFirecrawlSession(
        _FakeFirecrawlResponse(status=403, text_data="Forbidden")
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    with pytest.raises(
        Exception,
        match="Exa get contents failed: Forbidden, status: 403",
    ):
        await tools._exa_get_contents(
            {"websearch_exa_key": ["exa-key"]},
            {"ids": ["https://example.com"]},
        )
