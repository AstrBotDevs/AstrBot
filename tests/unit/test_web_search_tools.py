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
    """每次 post() 调用返回列表中的下一个响应，支持多 key 轮询的测试"""

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
    """模拟 Tavily API 的 HTTP 响应"""

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
    """重置所有 KeyRotator 的索引，避免测试间状态干扰"""
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
# Issue #8886: Tavily 多 Key 轮询不会在失败时切换到下一个 Key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tavily_search_raises_value_error_when_no_key_configured():
    """未配置 Tavily API Key 时，应抛出 ValueError"""
    with pytest.raises(
        ValueError,
        match="Error: Tavily API key is not configured in AstrBot.",
    ):
        await tools._tavily_search({}, {"query": "test"})


@pytest.mark.asyncio
async def test_tavily_search_key_failover_on_quota_exceeded_432(
    monkeypatch,
):
    """第一个 key 返回 432（额度耗尽），应自动切换到第二个 key 并成功"""
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
    assert len(session.calls) == 2  # 确认两个 key 都被尝试过


@pytest.mark.asyncio
async def test_tavily_search_key_failover_on_rate_limited_429(
    monkeypatch,
):
    """第一个 key 返回 429（限流），应自动切换到第二个 key 并成功"""
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
    assert len(session.calls) == 2  # 确认两个 key 都被尝试过


@pytest.mark.asyncio
async def test_tavily_search_fails_when_all_keys_exhausted_8886(
    monkeypatch,
):
    """所有 key 都失败时，应该抛出最后一个错误"""
    # 两个响应都返回 432
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

    assert len(session.calls) == 2  # 确认两个 key 都被尝试过


@pytest.mark.asyncio
async def test_tavily_search_does_not_failover_on_server_error_500(
    monkeypatch,
):
    """非 key 相关错误（500）不应触发 key 切换，应直接抛出"""
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

    # 只尝试了 1 个 key（500 不是可重试状态码，不会切换到第二个 key）
    assert len(session.calls) == 1


def _context_with_provider_settings(provider_settings):
    config = {"provider_settings": provider_settings}
    agent_context = SimpleNamespace(
        context=SimpleNamespace(get_config=lambda umo: config),
        event=SimpleNamespace(unified_msg_origin="test:private:session"),
    )
    return SimpleNamespace(context=agent_context)
