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


def _context_with_provider_settings(provider_settings):
    config = {"provider_settings": provider_settings}
    agent_context = SimpleNamespace(
        context=SimpleNamespace(get_config=lambda umo: config),
        event=SimpleNamespace(unified_msg_origin="test:private:session"),
    )
    return SimpleNamespace(context=agent_context)


class _FakeMetasoResponse:
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


class _FakeMetasoSession:
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


@pytest.mark.asyncio
async def test_metaso_search_maps_web_results(monkeypatch):
    async def fake_metaso_search(provider_settings, payload):
        assert payload == {"q": "test", "scope": "webpage", "size": 5}
        return [
            tools.SearchResult(
                title="Result A",
                url="https://example.com/a",
                snippet="Snippet A",
            )
        ]

    monkeypatch.setattr(tools, "_metaso_search", fake_metaso_search)
    tool = tools.MetasoWebSearchTool()
    context = _context_with_provider_settings({"websearch_metaso_key": ["my-key"]})

    result = await tool.call(context, query="test", size=5)

    assert json.loads(result)["results"] == [
        {
            "title": "Result A",
            "url": "https://example.com/a",
            "snippet": "Snippet A",
            "index": json.loads(result)["results"][0]["index"],
        }
    ]


@pytest.mark.asyncio
async def test_metaso_search_uses_default_key_when_empty(monkeypatch):
    async def fake_metaso_search(provider_settings, payload):
        assert payload == {"q": "test", "scope": "webpage", "size": 5}
        return [
            tools.SearchResult(
                title="Result A",
                url="https://example.com/a",
                snippet="Snippet A",
            )
        ]

    monkeypatch.setattr(tools, "_metaso_search", fake_metaso_search)
    tool = tools.MetasoWebSearchTool()
    context = _context_with_provider_settings({"websearch_metaso_key": []})

    result = await tool.call(context, query="test", size=5)
    assert json.loads(result)["results"][0]["title"] == "Result A"


@pytest.mark.asyncio
async def test_metaso_search_payload_defaults(monkeypatch):
    captured = {}

    async def fake_metaso_search(provider_settings, payload):
        captured["payload"] = payload
        return [tools.SearchResult(title="X", url="https://x.com", snippet="x")]

    monkeypatch.setattr(tools, "_metaso_search", fake_metaso_search)
    tool = tools.MetasoWebSearchTool()
    context = _context_with_provider_settings({"websearch_metaso_key": ["k"]})

    await tool.call(context, query="hello")

    assert captured["payload"] == {"q": "hello", "scope": "webpage", "size": 10}


@pytest.mark.asyncio
async def test_metaso_search_caps_size_low(monkeypatch):
    captured = {}

    async def fake_metaso_search(provider_settings, payload):
        captured["payload"] = payload
        return [tools.SearchResult(title="X", url="https://x.com", snippet="x")]

    monkeypatch.setattr(tools, "_metaso_search", fake_metaso_search)
    tool = tools.MetasoWebSearchTool()
    context = _context_with_provider_settings({"websearch_metaso_key": ["k"]})

    await tool.call(context, query="hello", size=0)
    assert captured["payload"]["size"] == 1


@pytest.mark.asyncio
async def test_metaso_search_caps_size_high(monkeypatch):
    captured = {}

    async def fake_metaso_search(provider_settings, payload):
        captured["payload"] = payload
        return [tools.SearchResult(title="X", url="https://x.com", snippet="x")]

    monkeypatch.setattr(tools, "_metaso_search", fake_metaso_search)
    tool = tools.MetasoWebSearchTool()
    context = _context_with_provider_settings({"websearch_metaso_key": ["k"]})

    await tool.call(context, query="hello", size=999)
    assert captured["payload"]["size"] == 100


@pytest.mark.asyncio
async def test_metaso_search_no_results_returns_error(monkeypatch):
    async def fake_metaso_search(provider_settings, payload):
        return []

    monkeypatch.setattr(tools, "_metaso_search", fake_metaso_search)
    tool = tools.MetasoWebSearchTool()
    context = _context_with_provider_settings({"websearch_metaso_key": ["k"]})

    result = await tool.call(context, query="test")
    assert result == "Error: Metaso searcher did not return any results."


@pytest.mark.asyncio
async def test_metaso_search_returns_results_from_api(monkeypatch):
    session = _FakeMetasoSession(
        _FakeMetasoResponse(
            status=200,
            json_data={
                "webpages": [
                    {
                        "title": "Result One",
                        "link": "https://example.com/1",
                        "snippet": "Snippet one.",
                    },
                    {
                        "title": "Result Two",
                        "link": "https://example.com/2",
                        "summary": "Summary two.",
                    },
                ],
            },
        )
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    results = await tools._metaso_search(
        {"websearch_metaso_key": ["metaso-key"]},
        {"q": "test", "scope": "webpage", "size": 5},
    )

    assert session.posted == {
        "url": "https://metaso.cn/api/v1/search",
        "json": {"q": "test", "scope": "webpage", "size": 5},
        "headers": {
            "Authorization": "Bearer metaso-key",
            "Content-Type": "application/json",
        },
    }
    assert results == [
        tools.SearchResult(
            title="Result One",
            url="https://example.com/1",
            snippet="Snippet one.",
        ),
        tools.SearchResult(
            title="Result Two",
            url="https://example.com/2",
            snippet="Summary two.",
        ),
    ]


@pytest.mark.asyncio
async def test_metaso_search_uses_default_key_when_no_keys_configured(monkeypatch):
    session = _FakeMetasoSession(
        _FakeMetasoResponse(
            status=200,
            json_data={
                "webpages": [
                    {
                        "title": "Result",
                        "link": "https://example.com",
                        "snippet": "Snippet.",
                    },
                ],
            },
        )
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    results = await tools._metaso_search(
        {"websearch_metaso_key": []},
        {"q": "test", "scope": "webpage", "size": 5},
    )

    assert session.posted["headers"]["Authorization"] == f"Bearer {tools._METASO_DEFAULT_API_KEY}"
    assert results[0].title == "Result"


@pytest.mark.asyncio
async def test_metaso_search_uses_configured_keys_when_present(monkeypatch):
    session = _FakeMetasoSession(
        _FakeMetasoResponse(
            status=200,
            json_data={
                "webpages": [
                    {
                        "title": "Result",
                        "link": "https://example.com",
                        "snippet": "Snippet.",
                    },
                ],
            },
        )
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    results = await tools._metaso_search(
        {"websearch_metaso_key": ["custom-key"]},
        {"q": "test", "scope": "webpage", "size": 5},
    )

    assert session.posted["headers"]["Authorization"] == "Bearer custom-key"
    assert results[0].title == "Result"


@pytest.mark.asyncio
async def test_metaso_search_http_401(monkeypatch):
    session = _FakeMetasoSession(
        _FakeMetasoResponse(status=401, text_data="Unauthorized")
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    with pytest.raises(Exception, match="unauthorized"):
        await tools._metaso_search(
            {"websearch_metaso_key": ["bad-key"]},
            {"q": "test", "scope": "webpage", "size": 5},
        )


@pytest.mark.asyncio
async def test_metaso_search_http_403(monkeypatch):
    session = _FakeMetasoSession(
        _FakeMetasoResponse(status=403, text_data="Forbidden")
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    with pytest.raises(Exception, match="unauthorized"):
        await tools._metaso_search(
            {"websearch_metaso_key": ["bad-key"]},
            {"q": "test", "scope": "webpage", "size": 5},
        )


@pytest.mark.asyncio
async def test_metaso_search_http_429(monkeypatch):
    session = _FakeMetasoSession(
        _FakeMetasoResponse(status=429, text_data="Rate limited")
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    with pytest.raises(Exception, match="rate-limited"):
        await tools._metaso_search(
            {"websearch_metaso_key": ["key"]},
            {"q": "test", "scope": "webpage", "size": 5},
        )


@pytest.mark.asyncio
async def test_metaso_search_code_3003_daily_limit(monkeypatch):
    session = _FakeMetasoSession(
        _FakeMetasoResponse(
            status=200,
            json_data={"code": 3003, "message": "今日调用次数已达上限"},
        )
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    with pytest.raises(Exception, match="daily search limit"):
        await tools._metaso_search(
            {"websearch_metaso_key": ["key"]},
            {"q": "test", "scope": "webpage", "size": 5},
        )


@pytest.mark.asyncio
async def test_metaso_search_code_2005_invalid_key(monkeypatch):
    session = _FakeMetasoSession(
        _FakeMetasoResponse(
            status=200,
            json_data={"code": 2005, "message": "API密钥无效"},
        )
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    with pytest.raises(Exception, match="API key rejected"):
        await tools._metaso_search(
            {"websearch_metaso_key": ["bad-key"]},
            {"q": "test", "scope": "webpage", "size": 5},
        )


@pytest.mark.asyncio
async def test_metaso_search_non_zero_code(monkeypatch):
    session = _FakeMetasoSession(
        _FakeMetasoResponse(
            status=200,
            json_data={"code": 9999, "message": "Unknown error"},
        )
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    with pytest.raises(Exception, match="code=9999"):
        await tools._metaso_search(
            {"websearch_metaso_key": ["key"]},
            {"q": "test", "scope": "webpage", "size": 5},
        )


@pytest.mark.asyncio
async def test_metaso_search_empty_webpages(monkeypatch):
    session = _FakeMetasoSession(
        _FakeMetasoResponse(
            status=200,
            json_data={"webpages": []},
        )
    )

    def fake_client_session(*, trust_env):
        session.trust_env = trust_env
        return session

    monkeypatch.setattr(tools.aiohttp, "ClientSession", fake_client_session)

    results = await tools._metaso_search(
        {"websearch_metaso_key": ["key"]},
        {"q": "test", "scope": "webpage", "size": 5},
    )

    assert results == []
