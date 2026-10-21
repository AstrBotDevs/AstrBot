import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from astrbot.core.tools import registry
from astrbot.core.tools import web_search_tools as tools


def _response(status=200, data=None, reason=""):
    """Build a mock aiohttp response.

    Args:
        status: HTTP status code.
        data: JSON response body.
        reason: Text response body for HTTP errors.

    Returns:
        An asynchronous response context manager.
    """
    response = MagicMock(status=status)
    response.__aenter__.return_value = response
    response.json = AsyncMock(return_value=data or {})
    response.text = AsyncMock(return_value=reason)
    return response


@pytest.fixture
def serpapi_http(monkeypatch):
    """Mock the SerpApi transport and reset key rotation.

    Args:
        monkeypatch: Pytest patch fixture.

    Returns:
        The session and session factory mocks.
    """
    session = MagicMock()
    session.__aenter__.return_value = session
    factory = MagicMock(return_value=session)
    monkeypatch.setattr(tools.aiohttp, "ClientSession", factory)
    monkeypatch.setattr(
        tools,
        "_SERPAPI_KEY_ROTATOR",
        tools._KeyRotator("websearch_serpapi_key", "SerpApi"),
    )
    return SimpleNamespace(session=session, factory=factory)


@pytest.fixture
def serpapi_context():
    """Create an agent context with a configured SerpApi key.

    Returns:
        A context wrapper for search tool calls.
    """
    config = {"provider_settings": {"websearch_serpapi_key": ["test-key"]}}
    return SimpleNamespace(
        context=SimpleNamespace(
            context=SimpleNamespace(get_config=lambda umo: config),
            event=SimpleNamespace(unified_msg_origin="test:private:session"),
        )
    )


@pytest.mark.asyncio
async def test_serpapi_finance_preserves_quotes_fundamentals_and_sources(
    serpapi_http, serpapi_context
):
    data = {
        "search_metadata": {
            "google_finance_url": "https://www.google.com/finance/quote/AAPL:NASDAQ?hl=en",
            "json_endpoint": "https://serpapi.com/private-search",
        },
        "summary": {
            "title": "Apple Inc",
            "stock": "AAPL",
            "exchange": "NASDAQ",
            "price": "$230.00",
            "extracted_price": 230.0,
            "currency": "USD",
            "date": "Oct 16 2026, 04:00 PM UTC-04:00",
            "price_movement": {"percentage": 1.2, "value": 2.76, "movement": "Up"},
        },
        "knowledge_graph": {
            "key_stats": {"stats": [{"label": "Open", "value": "$228"}]}
        },
        "financials": [
            {"title": "Income Statement", "results": [{"date": "Jun 2026"}]}
        ],
        "news_results": [
            {"link": "https://example.com/news", "snippet": "Company news"}
        ],
        "graph": [{"price": 229.0, "date": "Oct 16 2026, 09:30 AM UTC-04:00"}],
    }
    serpapi_http.session.get.return_value = _response(data=data)

    result = json.loads(
        await tools.SerpApiFinanceSearchTool().call(
            serpapi_context, query="AAPL:NASDAQ", search_lang="en"
        )
    )

    assert serpapi_http.session.get.call_args.kwargs["params"] == {
        "engine": "google_finance",
        "api_key": "test-key",
        "q": "AAPL:NASDAQ",
        "hl": "en",
    }
    for key in ("summary", "knowledge_graph", "financials", "news_results"):
        assert result[key] == data[key]
    assert result["results"][0]["url"] == data["search_metadata"]["google_finance_url"]
    assert json.loads(result["results"][0]["snippet"]) == data["summary"]
    assert result["results"][0]["index"].endswith(".1")
    assert "search_metadata" not in result
    assert "graph" not in result


@pytest.mark.asyncio
async def test_serpapi_finance_returns_requested_history(serpapi_http, serpapi_context):
    graph = [{"price": i, "currency": "USD", "date": f"Day {i}"} for i in range(120)]
    serpapi_http.session.get.return_value = _response(
        data={
            "summary": {"title": "Apple Inc", "price": "$230.00"},
            "graph": graph,
            "key_events": [{"title": "Earnings", "date": "Day 100"}],
        }
    )

    result = json.loads(
        await tools.SerpApiFinanceSearchTool().call(
            serpapi_context, query="AAPL:NASDAQ", window="1Y"
        )
    )

    assert serpapi_http.session.get.call_args.kwargs["params"]["window"] == "1Y"
    assert result["graph"] == graph
    assert result["key_events"] == [{"title": "Earnings", "date": "Day 100"}]
    assert (
        result["results"][0]["url"]
        == "https://www.google.com/finance/quote/AAPL:NASDAQ"
    )


@pytest.mark.asyncio
async def test_serpapi_finance_preserves_suggestions_for_unknown_symbol(
    serpapi_http, serpapi_context
):
    suggestions = [
        {
            "stock": "MSFT:NASDAQ",
            "link": "https://www.google.com/finance/quote/MSFT:NASDAQ",
        }
    ]
    serpapi_http.session.get.return_value = _response(data={"suggestions": suggestions})

    result = json.loads(
        await tools.SerpApiFinanceSearchTool().call(serpapi_context, query="MSFTR:")
    )

    assert result["results"] == []
    assert result["suggestions"] == suggestions


@pytest.mark.asyncio
@pytest.mark.parametrize("query,window", [("", None), ("AAPL:NASDAQ", "invalid")])
async def test_serpapi_finance_validates_input_before_request(
    serpapi_http, serpapi_context, query, window
):
    result = await tools.SerpApiFinanceSearchTool().call(
        serpapi_context, query=query, window=window
    )

    assert result.startswith("Error:")
    serpapi_http.factory.assert_not_called()


@pytest.mark.asyncio
async def test_serpapi_scholar_preserves_publication_metadata_and_filters(
    serpapi_http, serpapi_context
):
    publication_info = {
        "summary": "A Author - Example Journal, 2024",
        "authors": [{"name": "A Author"}],
    }
    resources = [
        {
            "title": "Full text",
            "link": "https://example.com/paper.pdf",
            "file_format": "PDF",
        }
    ]
    serpapi_http.session.get.return_value = _response(
        data={
            "organic_results": [
                {
                    "title": "A research paper",
                    "link": "https://example.com/paper",
                    "snippet": "Abstract excerpt",
                    "publication_info": publication_info,
                    "resources": resources,
                    "inline_links": {
                        "cited_by": {
                            "total": 42,
                            "link": "https://scholar.google.com/scholar?cites=123",
                        },
                        "serpapi_cite_link": "https://serpapi.com/private-cite",
                    },
                }
            ]
        }
    )

    result = json.loads(
        await tools.SerpApiScholarSearchTool().call(
            serpapi_context,
            query="retrieval augmented generation",
            max_results=3,
            search_lang="en",
            year_from=2020,
            year_to=2026,
        )
    )["results"]

    assert serpapi_http.session.get.call_args.kwargs["params"] == {
        "engine": "google_scholar",
        "api_key": "test-key",
        "q": "retrieval augmented generation",
        "num": 3,
        "hl": "en",
        "as_ylo": 2020,
        "as_yhi": 2026,
    }
    assert result[0] == {
        "title": "A research paper",
        "url": "https://example.com/paper",
        "snippet": "Abstract excerpt",
        "publication_info": publication_info,
        "cited_by_count": 42,
        "cited_by_url": "https://scholar.google.com/scholar?cites=123",
        "resources": resources,
        "index": result[0]["index"],
    }
    assert result[0]["index"].endswith(".1")


@pytest.mark.asyncio
@pytest.mark.parametrize("limit,expected", [(None, 5), (-3, 1), (7, 7), (100, 20)])
async def test_serpapi_scholar_limits_results_and_handles_citation_only_entries(
    serpapi_http, serpapi_context, limit, expected
):
    serpapi_http.session.get.return_value = _response(
        data={"organic_results": [{"title": f"Paper {i}"} for i in range(22)]}
    )
    kwargs = {} if limit is None else {"max_results": limit}

    results = json.loads(
        await tools.SerpApiScholarSearchTool().call(
            serpapi_context, query="papers", **kwargs
        )
    )["results"]

    assert len(results) == expected
    assert serpapi_http.session.get.call_args.kwargs["params"]["num"] == expected
    assert results[0]["url"] == "https://scholar.google.com/scholar?q=Paper%200"
    assert results[0]["cited_by_count"] is None


@pytest.mark.asyncio
async def test_serpapi_scholar_uses_full_text_link_if_publisher_link_is_missing(
    serpapi_http, serpapi_context
):
    serpapi_http.session.get.return_value = _response(
        data={
            "organic_results": [
                {
                    "title": "Paper",
                    "resources": [{"link": "https://example.com/paper.pdf"}],
                }
            ]
        }
    )

    result = json.loads(
        await tools.SerpApiScholarSearchTool().call(
            serpapi_context, query="papers", year_from=2024
        )
    )["results"]

    assert result[0]["url"] == "https://example.com/paper.pdf"
    assert serpapi_http.session.get.call_args.kwargs["params"]["as_ylo"] == 2024
    assert "as_yhi" not in serpapi_http.session.get.call_args.kwargs["params"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"query": ""},
        {"year_from": 2026, "year_to": 2020},
        {"year_from": 0},
        {"year_to": 10000},
    ],
)
async def test_serpapi_scholar_validates_query_and_years(
    serpapi_http, serpapi_context, kwargs
):
    result = await tools.SerpApiScholarSearchTool().call(
        serpapi_context, **{"query": "papers", **kwargs}
    )

    assert result.startswith("Error:")
    serpapi_http.factory.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_class", [tools.SerpApiFinanceSearchTool, tools.SerpApiScholarSearchTool]
)
async def test_serpapi_specialized_search_handles_empty_and_failed_responses(
    serpapi_http, serpapi_context, tool_class
):
    serpapi_http.session.get.side_effect = [
        _response(),
        _response(503, reason="API unavailable"),
    ]

    result = json.loads(await tool_class().call(serpapi_context, query="example"))

    assert result["results"] == []
    with pytest.raises(RuntimeError, match="status: 503"):
        await tool_class().call(serpapi_context, query="example")


@pytest.mark.asyncio
async def test_serpapi_images_light_maps_images_and_sources(
    serpapi_http, serpapi_context, monkeypatch
):
    cache = {}
    monkeypatch.setitem(tools.sp.temporary_cache, "_ws_favicon", cache)
    serpapi_http.session.get.return_value = _response(
        data={
            "images_results": [
                {"title": "Missing image"},
                {
                    "title": "AstrBot 标志",
                    "source": "Example",
                    "link": "https://example.com/article",
                    "original": "https://example.com/image.png",
                    "thumbnail": "https://example.com/thumb.png",
                    "original_width": 1200,
                    "original_height": 800,
                    "source_logo": "https://example.com/favicon.ico",
                },
                {
                    "original": "x-raw-image:///pdf-image",
                    "thumbnail": "https://example.com/pdf-thumb.png",
                    "original_width": 500,
                    "original_height": 300,
                },
                {"serpapi_thumbnail": "https://example.com/serpapi-thumb.png"},
                {"original": "data:image/png;base64,invalid"},
            ]
        }
    )

    result = json.loads(
        await tools.SerpApiImageSearchTool().call(
            serpapi_context, query="AstrBot logo", country="us", search_lang="en"
        )
    )["results"]

    assert serpapi_http.session.get.call_args.kwargs["params"] == {
        "engine": "google_images_light",
        "api_key": "test-key",
        "q": "AstrBot logo",
        "gl": "us",
        "hl": "en",
    }
    assert len(result) == 3
    assert result[0] == {
        "title": "AstrBot 标志",
        "url": "https://example.com/article",
        "snippet": "Example",
        "image_url": "https://example.com/image.png",
        "thumbnail_url": "https://example.com/thumb.png",
        "width": 1200,
        "height": 800,
        "index": result[0]["index"],
    }
    assert result[1]["image_url"] == "https://example.com/pdf-thumb.png"
    assert result[1]["url"] == result[1]["image_url"]
    assert result[1]["width"] is result[1]["height"] is None
    assert result[2]["image_url"] == "https://example.com/serpapi-thumb.png"
    assert [item["index"] for item in result] == [
        f"{result[0]['index'].split('.')[0]}.{i}" for i in range(1, 4)
    ]
    assert cache == {"https://example.com/article": "https://example.com/favicon.ico"}


@pytest.mark.asyncio
@pytest.mark.parametrize("limit,expected", [(None, 5), (-2, 1), (3, 3), (100, 10)])
async def test_serpapi_images_light_limits_results(
    serpapi_http, serpapi_context, limit, expected
):
    serpapi_http.session.get.return_value = _response(
        data={
            "images_results": [
                {"original": f"https://example.com/{i}.png"} for i in range(12)
            ]
        }
    )
    kwargs = {} if limit is None else {"max_results": limit}

    result = json.loads(
        await tools.SerpApiImageSearchTool().call(
            serpapi_context, query="AstrBot", **kwargs
        )
    )

    assert len(result["results"]) == expected
    assert serpapi_http.session.get.call_args.kwargs["params"] == {
        "engine": "google_images_light",
        "api_key": "test-key",
        "q": "AstrBot",
    }


@pytest.mark.asyncio
async def test_serpapi_images_light_handles_empty_success(
    serpapi_http, serpapi_context
):
    serpapi_http.session.get.return_value = _response(
        data={
            "search_metadata": {"status": "Success"},
            "error": "No image results found.",
        }
    )

    result = await tools.SerpApiImageSearchTool().call(serpapi_context, query="AstrBot")

    assert json.loads(result) == {"results": []}


@pytest.mark.asyncio
async def test_serpapi_images_light_surfaces_api_errors(serpapi_http, serpapi_context):
    serpapi_http.session.get.return_value = _response(503, reason="Search failed")

    with pytest.raises(RuntimeError, match="status: 503"):
        await tools.SerpApiImageSearchTool().call(serpapi_context, query="AstrBot")


@pytest.mark.asyncio
async def test_serpapi_tool_maps_query_results_and_citations(serpapi_http, monkeypatch):
    serpapi_http.session.get.return_value = _response(
        data={
            "search_metadata": {"status": "Success"},
            "organic_results": [
                {"title": "Missing link"},
                {
                    "title": "AstrBot 搜索",
                    "link": "https://example.com",
                    "snippet": "Search result",
                    "favicon": "https://example.com/favicon.ico",
                },
                {"link": "https://example.org", "title": None, "snippet": None},
            ],
        }
    )
    cache = {}
    monkeypatch.setattr(tools.sp, "temporary_cache", {"_ws_favicon": cache})
    config = {"provider_settings": {"websearch_serpapi_key": ["test-key"]}}
    get_config = MagicMock(return_value=config)
    context = SimpleNamespace(
        context=SimpleNamespace(
            context=SimpleNamespace(get_config=get_config),
            event=SimpleNamespace(unified_msg_origin="test:private:session"),
        )
    )

    result = json.loads(
        await tools.SerpApiWebSearchTool().call(
            context,
            query="AstrBot 搜索",
            country="cn",
            search_lang="zh-cn",
            location="Shanghai, China",
        )
    )["results"]

    get_config.assert_called_once_with(umo="test:private:session")
    serpapi_http.factory.assert_called_once_with(trust_env=True)
    call = serpapi_http.session.get.call_args
    assert call.args == ("https://serpapi.com/search.json",)
    assert call.kwargs["params"] == {
        "engine": "google",
        "api_key": "test-key",
        "q": "AstrBot 搜索",
        "gl": "cn",
        "hl": "zh-cn",
        "location": "Shanghai, China",
    }
    assert call.kwargs["timeout"].total == 60
    assert result[0] == {
        "title": "AstrBot 搜索",
        "url": "https://example.com",
        "snippet": "Search result",
        "index": result[0]["index"],
    }
    assert result[0]["index"].endswith(".1")
    assert result[1]["title"] == result[1]["snippet"] == ""
    assert cache == {"https://example.com": "https://example.com/favicon.ico"}


@pytest.mark.asyncio
@pytest.mark.parametrize("limit,expected", [(None, 5), (-2, 1), (3, 3), (100, 10)])
async def test_serpapi_tool_limits_first_page_results(serpapi_http, limit, expected):
    serpapi_http.session.get.return_value = _response(
        data={
            "organic_results": [{"link": f"https://example.com/{i}"} for i in range(12)]
        }
    )
    config = {"provider_settings": {"websearch_serpapi_key": ["test-key"]}}
    context = SimpleNamespace(
        context=SimpleNamespace(
            context=SimpleNamespace(get_config=lambda umo: config),
            event=SimpleNamespace(unified_msg_origin="test:private:session"),
        )
    )
    kwargs = {} if limit is None else {"max_results": limit}

    result = await tools.SerpApiWebSearchTool().call(context, query="AstrBot", **kwargs)

    assert len(json.loads(result)["results"]) == expected
    assert serpapi_http.session.get.call_args.kwargs["params"] == {
        "engine": "google",
        "api_key": "test-key",
        "q": "AstrBot",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403, 429])
@pytest.mark.parametrize(
    "engine", ["google", "google_images_light", "google_finance", "google_scholar"]
)
async def test_serpapi_rotates_and_retries_key_errors(serpapi_http, status, engine):
    serpapi_http.session.get.side_effect = [
        _response(status, reason="Key rejected"),
        _response(),
        _response(),
    ]
    settings = {"websearch_serpapi_key": ["first-key", "second-key"]}
    payload = {"q": "AstrBot"}

    assert await tools._serpapi_request(settings, payload, engine=engine) == {}
    assert await tools._serpapi_request(settings, payload, engine=engine) == {}

    assert [
        call.kwargs["params"]["api_key"]
        for call in serpapi_http.session.get.call_args_list
    ] == ["first-key", "second-key", "first-key"]
    assert all(
        call.kwargs["params"]["engine"] == engine
        for call in serpapi_http.session.get.call_args_list
    )
    assert payload == {"q": "AstrBot"}


@pytest.mark.asyncio
async def test_serpapi_exhausts_keys_and_redacts_error(serpapi_http):
    serpapi_http.session.get.side_effect = [
        _response(401, reason="Invalid first-key"),
        _response(429, reason="Quota for second-key"),
    ]

    with pytest.raises(RuntimeError, match="Quota for \\[redacted\\], status: 429"):
        await tools._serpapi_search(
            {"websearch_serpapi_key": ["first-key", "second-key"]}, {"q": "AstrBot"}
        )

    assert serpapi_http.session.get.call_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 500, 503])
async def test_serpapi_does_not_retry_other_http_errors(serpapi_http, status):
    serpapi_http.session.get.return_value = _response(status, reason="Request failed")

    with pytest.raises(RuntimeError, match=f"status: {status}"):
        await tools._serpapi_search(
            {"websearch_serpapi_key": ["first-key", "second-key"]}, {"q": "AstrBot"}
        )

    assert serpapi_http.session.get.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("metadata", [{}, {"status": "Error"}])
async def test_serpapi_surfaces_json_errors(serpapi_http, metadata):
    serpapi_http.session.get.return_value = _response(
        data={"search_metadata": metadata, "error": "Failed for test-key"}
    )

    with pytest.raises(RuntimeError, match="Failed for \\[redacted\\]"):
        await tools._serpapi_search(
            {"websearch_serpapi_key": ["test-key"]}, {"q": "AstrBot"}
        )


@pytest.mark.asyncio
async def test_serpapi_success_with_empty_results_is_not_an_error(serpapi_http):
    serpapi_http.session.get.return_value = _response(
        data={
            "search_metadata": {"status": "Success"},
            "search_information": {"organic_results_state": "Fully empty"},
            "error": "Google hasn't returned any results for this query.",
        }
    )

    assert (
        await tools._serpapi_search(
            {"websearch_serpapi_key": ["test-key"]}, {"q": "AstrBot"}
        )
        == []
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [aiohttp.ClientError, asyncio.TimeoutError])
async def test_serpapi_transport_errors_do_not_expose_credentials(
    serpapi_http, error_type
):
    serpapi_http.session.get.side_effect = error_type(
        "Request failed: https://serpapi.com/search.json?api_key=secret-key"
    )

    with pytest.raises(RuntimeError, match="request failed or timed out") as error:
        await tools._serpapi_search(
            {"websearch_serpapi_key": ["secret-key"]}, {"q": "AstrBot"}
        )

    assert "secret-key" not in str(error.value)
    assert error.value.__suppress_context__


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_class",
    [
        tools.SerpApiWebSearchTool,
        tools.SerpApiImageSearchTool,
        tools.SerpApiFinanceSearchTool,
        tools.SerpApiScholarSearchTool,
    ],
)
async def test_serpapi_requires_credentials_before_request(serpapi_http, tool_class):
    with pytest.raises(ValueError, match="SerpApi API key is not configured"):
        await tools._serpapi_search({}, {"q": "AstrBot"})

    config = {"provider_settings": {}}
    context = SimpleNamespace(
        context=SimpleNamespace(
            context=SimpleNamespace(get_config=lambda umo: config),
            event=SimpleNamespace(unified_msg_origin="test:private:session"),
        )
    )
    result = await tool_class().call(context, query="AstrBot")

    assert "SerpApi API key is not configured" in result
    serpapi_http.factory.assert_not_called()


@pytest.mark.parametrize(
    "enabled,provider,expected",
    [(True, "serpapi", True), (False, "serpapi", False), (True, "tavily", False)],
)
@pytest.mark.parametrize(
    "tool_class",
    [
        tools.SerpApiWebSearchTool,
        tools.SerpApiImageSearchTool,
        tools.SerpApiFinanceSearchTool,
        tools.SerpApiScholarSearchTool,
    ],
)
def test_serpapi_tool_is_registered_and_gated(enabled, provider, expected, tool_class):
    name = tool_class().name
    rule = registry.get_builtin_tool_config_rule(name)
    conditions = rule.evaluate(
        {"provider_settings": {"web_search": enabled, "websearch_provider": provider}}
    )

    assert all(condition["matched"] for condition in conditions) is expected
    assert registry.get_builtin_tool_class(name) is tool_class
    assert name in tools.WEB_SEARCH_TOOL_NAMES
    assert tool_class.__name__ in tools.__all__


@pytest.mark.parametrize("key,expected", [("old-key", ["old-key"]), ("", [])])
def test_serpapi_normalizes_string_keys(key, expected):
    config = MagicMock()
    settings = {"websearch_serpapi_key": key}
    config.get.return_value = settings

    tools.normalize_legacy_web_search_config(config)

    assert settings["websearch_serpapi_key"] == expected
    config.save_config.assert_called_once()
