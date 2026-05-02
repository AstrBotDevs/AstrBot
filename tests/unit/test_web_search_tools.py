import json
from types import SimpleNamespace

import pytest

import astrbot.core.tools.registry as tool_registry
from astrbot.core.knowledge_base.parsers.url_parser import URLExtractor
from astrbot.core.tools import web_search_tools as tools


class _FakeConfig(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.saved = False

    def save_config(self):
        self.saved = True


class _FakeExaResponse:
    def __init__(self, payload: dict):
        self.status = 200
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._payload

    async def text(self):
        return ""


class _FakeExaSession:
    def __init__(self, payload: dict, captured: dict[str, object]):
        self._payload = payload
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def post(self, url: str, **kwargs):
        self._captured["url"] = url
        self._captured["kwargs"] = kwargs
        return _FakeExaResponse(self._payload)


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


def test_normalize_legacy_web_search_config_migrates_firecrawl_and_exa_keys():
    config = _FakeConfig(
        {
            "provider_settings": {
                "websearch_firecrawl_key": "firecrawl-key",
                "websearch_exa_key": "exa-key",
            }
        }
    )

    tools.normalize_legacy_web_search_config(config)

    assert config["provider_settings"]["websearch_firecrawl_key"] == ["firecrawl-key"]
    assert config["provider_settings"]["websearch_exa_key"] == ["exa-key"]
    assert config.saved is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("search_type", "expected"),
    [
        ("auto", "auto"),
        ("neural", "neural"),
        ("fast", "fast"),
        ("deep-lite", "deep-lite"),
        ("deep", "deep"),
        ("deep-reasoning", "deep-reasoning"),
        ("instant", "instant"),
        (" INSTANT ", "instant"),
        ("unsupported", "auto"),
    ],
)
async def test_exa_web_search_tool_normalizes_search_type(
    monkeypatch: pytest.MonkeyPatch,
    search_type: str,
    expected: str,
):
    captured: dict[str, object] = {}

    async def fake_exa_search(provider_settings: dict, payload: dict, timeout: int):
        captured["provider_settings"] = provider_settings
        captured["payload"] = payload
        captured["timeout"] = timeout
        return []

    monkeypatch.setattr(tools, "_exa_search", fake_exa_search)

    tool = tools.ExaWebSearchTool()
    result = await tool.call(
        _context_with_provider_settings({"websearch_exa_key": ["test-key"]}),
        query="AstrBot",
        search_type=search_type,
    )

    assert result == "Error: Exa web searcher does not return any results."
    assert captured["payload"]["type"] == expected


@pytest.mark.asyncio
async def test_exa_web_search_tool_uses_default_for_invalid_max_results(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, object] = {}

    async def fake_exa_search(provider_settings: dict, payload: dict, timeout: int):
        captured["payload"] = payload
        return []

    monkeypatch.setattr(tools, "_exa_search", fake_exa_search)

    tool = tools.ExaWebSearchTool()
    result = await tool.call(
        _context_with_provider_settings({"websearch_exa_key": ["test-key"]}),
        query="AstrBot",
        max_results="not-a-number",
    )

    assert result == "Error: Exa web searcher does not return any results."
    assert captured["payload"]["numResults"] == 10


@pytest.mark.asyncio
async def test_exa_find_similar_uses_default_for_invalid_max_results(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, object] = {}

    async def fake_exa_find_similar(
        provider_settings: dict,
        payload: dict,
        timeout: int,
    ):
        captured["payload"] = payload
        return []

    monkeypatch.setattr(tools, "_exa_find_similar", fake_exa_find_similar)

    tool = tools.ExaFindSimilarTool()
    result = await tool.call(
        _context_with_provider_settings({"websearch_exa_key": ["test-key"]}),
        url="https://example.com",
        max_results="not-a-number",
    )

    assert result == "Error: Exa find similar does not return any results."
    assert captured["payload"]["numResults"] == 10


def test_get_exa_base_url_rejects_endpoint_path():
    with pytest.raises(ValueError) as exc_info:
        tools._get_exa_base_url({"websearch_exa_base_url": "https://api.exa.ai/search"})

    assert str(exc_info.value) == (
        "Error: Exa API Base URL must be a base URL or proxy prefix, "
        "not a specific endpoint path. Received: 'https://api.exa.ai/search'."
    )


def test_url_extractor_rejects_endpoint_base_url():
    with pytest.raises(ValueError) as exc_info:
        URLExtractor(
            ["test-key"],
            tavily_base_url="https://api.tavily.com/extract",
        )

    assert str(exc_info.value) == (
        "Error: Tavily API Base URL must be a base URL or proxy prefix, "
        "not a specific endpoint path. Received: 'https://api.tavily.com/extract'."
    )


def test_bocha_builtin_config_statuses_are_registered():
    rule = tool_registry._BUILTIN_TOOL_CONFIG_RULES.get("web_search_bocha")

    assert rule is not None
    statuses = rule.evaluate(
        {
            "provider_settings": {
                "web_search": True,
                "websearch_provider": "bocha",
            }
        }
    )

    assert statuses == [
        {
            "key": "provider_settings.web_search",
            "operator": "equals",
            "expected": True,
            "actual": True,
            "matched": True,
            "message": None,
        },
        {
            "key": "provider_settings.websearch_provider",
            "operator": "equals",
            "expected": "bocha",
            "actual": "bocha",
            "matched": True,
            "message": None,
        },
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("helper_name", "payload"),
    [
        ("_exa_search", {"query": "AstrBot"}),
        ("_exa_find_similar", {"url": "https://example.com"}),
    ],
)
async def test_exa_helpers_preserve_favicon(
    monkeypatch: pytest.MonkeyPatch,
    helper_name: str,
    payload: dict,
):
    captured: dict[str, object] = {}
    response_payload = {
        "results": [
            {
                "title": "Example",
                "url": "https://example.com",
                "text": "Snippet",
                "favicon": "https://example.com/favicon.ico",
            }
        ]
    }

    async def fake_get(provider_settings: dict) -> str:
        return "test-key"

    monkeypatch.setattr(tools._EXA_KEY_ROTATOR, "get", fake_get)
    monkeypatch.setattr(
        tools.aiohttp,
        "ClientSession",
        lambda **kwargs: _FakeExaSession(response_payload, captured),
    )

    helper = getattr(tools, helper_name)
    results = await helper(
        {"websearch_exa_key": ["test-key"]},
        payload,
    )

    assert captured["url"]
    assert results[0].favicon == "https://example.com/favicon.ico"


@pytest.mark.asyncio
async def test_exa_extract_raises_status_error(monkeypatch: pytest.MonkeyPatch):
    response_payload = {
        "results": [],
        "statuses": [
            {
                "id": "https://example.com/missing",
                "status": "error",
                "error": {
                    "tag": "CRAWL_NOT_FOUND",
                    "httpStatusCode": 404,
                },
            }
        ],
    }
    captured: dict[str, object] = {}

    async def fake_get(provider_settings: dict) -> str:
        return "test-key"

    monkeypatch.setattr(tools._EXA_KEY_ROTATOR, "get", fake_get)
    monkeypatch.setattr(
        tools.aiohttp,
        "ClientSession",
        lambda **kwargs: _FakeExaSession(response_payload, captured),
    )

    with pytest.raises(ValueError) as exc_info:
        await tools._exa_extract(
            {"websearch_exa_key": ["test-key"]},
            {"urls": ["https://example.com/missing"], "text": True},
        )

    assert str(exc_info.value) == (
        "Error: Exa content extraction failed: "
        "https://example.com/missing: CRAWL_NOT_FOUND (HTTP 404)"
    )


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
    parsed = json.loads(result)

    assert parsed["results"] == [
        {
            "title": "AstrBot",
            "url": "https://example.com",
            "snippet": "Search result",
            "index": parsed["results"][0]["index"],
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
