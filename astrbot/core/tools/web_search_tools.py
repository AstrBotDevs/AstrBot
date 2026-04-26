import asyncio
import json
import uuid
from dataclasses import dataclass as std_dataclass
from dataclasses import field

import aiohttp
from pydantic import Field
from pydantic.dataclasses import dataclass as pydantic_dataclass

from astrbot.core import logger, sp
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.tools.registry import builtin_tool

WEB_SEARCH_TOOL_NAMES = [
    "web_search_baidu",
    "web_search_tavily",
    "tavily_extract_web_page",
    "web_search_bocha",
    "web_search_brave",
    "web_search_firecrawl",
    "firecrawl_extract_web_page",
]
_TAVILY_WEB_SEARCH_TOOL_CONFIG = {
    "provider_settings.web_search": True,
    "provider_settings.websearch_provider": "tavily",
}
_BOCHA_WEB_SEARCH_TOOL_CONFIG = {
    "provider_settings.web_search": True,
    "provider_settings.websearch_provider": "bocha",
}
_BRAVE_WEB_SEARCH_TOOL_CONFIG = {
    "provider_settings.web_search": True,
    "provider_settings.websearch_provider": "brave",
}
_FIRECRAWL_WEB_SEARCH_TOOL_CONFIG = {
    "provider_settings.web_search": True,
    "provider_settings.websearch_provider": "firecrawl",
}
_BAIDU_WEB_SEARCH_TOOL_CONFIG = {
    "provider_settings.web_search": True,
    "provider_settings.websearch_provider": "baidu_ai_search",
}


@std_dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    favicon: str | None = None


@std_dataclass
class _KeyRotator:
    setting_name: str
    provider_name: str
    index: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def get(self, provider_settings: dict) -> str:
        keys = provider_settings.get(self.setting_name, [])
        if not keys:
            raise ValueError(
                f"Error: {self.provider_name} API key is not configured in AstrBot."
            )

        async with self.lock:
            key = keys[self.index]
            self.index = (self.index + 1) % len(keys)
            return key


_TAVILY_KEY_ROTATOR = _KeyRotator("websearch_tavily_key", "Tavily")
_BOCHA_KEY_ROTATOR = _KeyRotator("websearch_bocha_key", "BoCha")
_BRAVE_KEY_ROTATOR = _KeyRotator("websearch_brave_key", "Brave")
_FIRECRAWL_KEY_ROTATOR = _KeyRotator("websearch_firecrawl_key", "Firecrawl")


def normalize_legacy_web_search_config(cfg) -> None:
    provider_settings = cfg.get("provider_settings")
    if not provider_settings:
        return

    changed = False
    if provider_settings.get(
        "websearch_provider"
    ) == "default" and provider_settings.get("web_search", False):
        provider_settings["web_search"] = False
        changed = True
        logger.warning(
            "The default websearch provider is no longer supported. "
            "Web search has been disabled and the config was saved.",
        )

    for setting_name in (
        "websearch_tavily_key",
        "websearch_bocha_key",
        "websearch_brave_key",
        "websearch_firecrawl_key",
    ):
        value = provider_settings.get(setting_name)
        if isinstance(value, str):
            provider_settings[setting_name] = [value] if value else []
            changed = True

    if changed:
        cfg.save_config()


def _get_runtime(context) -> tuple[dict, dict, str]:
    agent_ctx = context.context
    event = agent_ctx.event
    cfg = agent_ctx.context.get_config(umo=event.unified_msg_origin)
    provider_settings = cfg.get("provider_settings", {})
    return cfg, provider_settings, event.unified_msg_origin


def _cache_favicon(url: str, favicon: str | None) -> None:
    if favicon:
        sp.temporary_cache["_ws_favicon"][url] = favicon


def _search_result_payload(results: list[SearchResult]) -> str:
    ref_uuid = str(uuid.uuid4())[:4]
    ret_ls = []
    for idx, result in enumerate(results, 1):
        index = f"{ref_uuid}.{idx}"
        ret_ls.append(
            {
                "title": f"{result.title}",
                "url": f"{result.url}",
                "snippet": f"{result.snippet}",
                "index": index,
            }
        )
        _cache_favicon(result.url, result.favicon)
    return json.dumps({"results": ret_ls}, ensure_ascii=False)


async def _tavily_search(
    provider_settings: dict,
    payload: dict,
) -> list[SearchResult]:
    tavily_key = await _TAVILY_KEY_ROTATOR.get(provider_settings)
    header = {
        "Authorization": f"Bearer {tavily_key}",
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession(trust_env=True) as session:
        async with session.post(
            "https://api.tavily.com/search",
            json=payload,
            headers=header,
        ) as response:
            if response.status != 200:
                reason = await response.text()
                raise Exception(
                    f"Tavily web search failed: {reason}, status: {response.status}",
                )
            data = await response.json()
            return [
                SearchResult(
                    title=item.get("title"),
                    url=item.get("url"),
                    snippet=item.get("content"),
                    favicon=item.get("favicon"),
                )
                for item in data.get("results", [])
            ]


async def _tavily_extract(provider_settings: dict, payload: dict) -> list[dict]:
    tavily_key = await _TAVILY_KEY_ROTATOR.get(provider_settings)
    header = {
        "Authorization": f"Bearer {tavily_key}",
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession(trust_env=True) as session:
        async with session.post(
            "https://api.tavily.com/extract",
            json=payload,
            headers=header,
        ) as response:
            if response.status != 200:
                reason = await response.text()
                raise Exception(
                    f"Tavily web search failed: {reason}, status: {response.status}",
                )
            data = await response.json()
            results: list[dict] = data.get("results", [])
            if not results:
                raise ValueError(
                    "Error: Tavily web searcher does not return any results."
                )
            return results


async def _bocha_search(
    provider_settings: dict,
    payload: dict,
) -> list[SearchResult]:
    bocha_key = await _BOCHA_KEY_ROTATOR.get(provider_settings)
    header = {
        "Authorization": f"Bearer {bocha_key}",
        "Content-Type": "application/json",
        # Explicitly disable brotli encoding to avoid aiohttp >= 3.13.3 brotli
        # decompression incompatibility (TypeError: process() takes exactly 1 argument).
        # See: https://github.com/aio-libs/aiohttp/issues/11898
        "Accept-Encoding": "gzip, deflate",
    }
    async with aiohttp.ClientSession(trust_env=True) as session:
        async with session.post(
            "https://api.bochaai.com/v1/web-search",
            json=payload,
            headers=header,
        ) as response:
            if response.status != 200:
                reason = await response.text()
                raise Exception(
                    f"BoCha web search failed: {reason}, status: {response.status}",
                )
            data = await response.json()
            rows = data["data"]["webPages"]["value"]
            return [
                SearchResult(
                    title=item.get("name"),
                    url=item.get("url"),
                    snippet=item.get("snippet"),
                    favicon=item.get("siteIcon"),
                )
                for item in rows
            ]


async def _brave_search(
    provider_settings: dict,
    payload: dict,
) -> list[SearchResult]:
    brave_key = await _BRAVE_KEY_ROTATOR.get(provider_settings)
    header = {
        "Accept": "application/json",
        "X-Subscription-Token": brave_key,
    }
    async with aiohttp.ClientSession(trust_env=True) as session:
        async with session.get(
            "https://api.search.brave.com/res/v1/web/search",
            params=payload,
            headers=header,
        ) as response:
            if response.status != 200:
                reason = await response.text()
                raise Exception(
                    f"Brave web search failed: {reason}, status: {response.status}",
                )
            data = await response.json()
            rows = data.get("web", {}).get("results", [])
            return [
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("description", ""),
                )
                for item in rows
            ]


async def _firecrawl_search(
    provider_settings: dict,
    payload: dict,
) -> list[SearchResult]:
    firecrawl_key = await _FIRECRAWL_KEY_ROTATOR.get(provider_settings)
    header = {
        "Authorization": f"Bearer {firecrawl_key}",
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession(trust_env=True) as session:
        async with session.post(
            "https://api.firecrawl.dev/v2/search",
            json=payload,
            headers=header,
        ) as response:
            if response.status != 200:
                reason = await response.text()
                raise Exception(
                    f"Firecrawl web search failed: {reason}, status: {response.status}",
                )
            data = await response.json()
            rows = data.get("data", [])
            if isinstance(rows, dict):
                rows = rows.get("web", [])
            return [
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=(
                        item.get("description")
                        or item.get("snippet")
                        or item.get("markdown")
                        or ""
                    ),
                )
                for item in rows
                if item.get("url")
            ]


async def _firecrawl_scrape(provider_settings: dict, payload: dict) -> dict:
    firecrawl_key = await _FIRECRAWL_KEY_ROTATOR.get(provider_settings)
    header = {
        "Authorization": f"Bearer {firecrawl_key}",
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession(trust_env=True) as session:
        async with session.post(
            "https://api.firecrawl.dev/v2/scrape",
            json=payload,
            headers=header,
        ) as response:
            if response.status != 200:
                reason = await response.text()
                raise Exception(
                    f"Firecrawl web scraper failed: {reason}, status: {response.status}",
                )
            data = await response.json()
            result = data.get("data", {})
            if not result:
                raise ValueError(
                    "Error: Firecrawl web scraper does not return any results."
                )
            return result


async def _baidu_search(
    provider_settings: dict,
    payload: dict,
) -> list[SearchResult]:
    api_key = provider_settings.get("websearch_baidu_app_builder_key", "")
    if not api_key:
        raise ValueError("Error: Baidu AI Search API key is not configured in AstrBot.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "X-Appbuilder-Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession(trust_env=True) as session:
        async with session.post(
            "https://qianfan.baidubce.com/v2/ai_search/web_search",
            json=payload,
            headers=headers,
        ) as response:
            if response.status != 200:
                reason = await response.text()
                raise Exception(
                    f"Baidu AI Search failed: {reason}, status: {response.status}",
                )
            data = await response.json()
            references = data.get("references", [])
            return [
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("content", ""),
                    favicon=item.get("icon"),
                )
                for item in references
                if item.get("url")
            ]


@builtin_tool(config=_TAVILY_WEB_SEARCH_TOOL_CONFIG)
@pydantic_dataclass
class TavilyWebSearchTool(FunctionTool[AstrAgentContext]):
    name: str = "web_search_tavily"
    description: str = (
        "A web search tool that uses Tavily to search the web for relevant content. "
        "Ideal for gathering current information, news, and detailed web content analysis."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Required. Search query."},
                "max_results": {
                    "type": "integer",
                    "description": "Optional. The maximum number of results to return. Default is 7. Range is 5-20.",
                },
                "search_depth": {
                    "type": "string",
                    "description": 'Optional. The depth of the search, must be one of "basic", "advanced". Default is "basic".',
                },
                "topic": {
                    "type": "string",
                    "description": 'Optional. The topic of the search, must be one of "general", "news". Default is "general".',
                },
                "days": {
                    "type": "integer",
                    "description": 'Optional. The number of days back from the current date to include in the search results. This only applies when topic is "news".',
                },
                "time_range": {
                    "type": "string",
                    "description": 'Optional. The time range back from the current date to include in the search results. Must be one of "day", "week", "month", "year".',
                },
                "start_date": {
                    "type": "string",
                    "description": "Optional. The start date for the search results in the format YYYY-MM-DD.",
                },
                "end_date": {
                    "type": "string",
                    "description": "Optional. The end date for the search results in the format YYYY-MM-DD.",
                },
            },
            "required": ["query"],
        }
    )

    async def call(self, context, **kwargs) -> ToolExecResult:
        _, provider_settings, _ = _get_runtime(context)
        if not provider_settings.get("websearch_tavily_key", []):
            return "Error: Tavily API key is not configured in AstrBot."

        search_depth = kwargs.get("search_depth", "basic")
        if search_depth not in ["basic", "advanced"]:
            search_depth = "basic"

        topic = kwargs.get("topic", "general")
        if topic not in ["general", "news"]:
            topic = "general"

        payload = {
            "query": kwargs["query"],
            "max_results": kwargs.get("max_results", 7),
            "include_favicon": True,
            "search_depth": search_depth,
            "topic": topic,
        }
        if topic == "news":
            payload["days"] = kwargs.get("days", 3)

        time_range = kwargs.get("time_range", "")
        if time_range in ["day", "week", "month", "year"]:
            payload["time_range"] = time_range
        if kwargs.get("start_date"):
            payload["start_date"] = kwargs["start_date"]
        if kwargs.get("end_date"):
            payload["end_date"] = kwargs["end_date"]

        results = await _tavily_search(provider_settings, payload)
        if not results:
            return "Error: Tavily web searcher does not return any results."
        return _search_result_payload(results)


@builtin_tool(config=_TAVILY_WEB_SEARCH_TOOL_CONFIG)
@pydantic_dataclass
class TavilyExtractWebPageTool(FunctionTool[AstrAgentContext]):
    name: str = "tavily_extract_web_page"
    description: str = "Extract the content of a web page using Tavily."
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Required. A URL to extract content from.",
                },
                "extract_depth": {
                    "type": "string",
                    "description": 'Optional. The depth of the extraction, must be one of "basic", "advanced". Default is "basic".',
                },
            },
            "required": ["url"],
        }
    )

    async def call(self, context, **kwargs) -> ToolExecResult:
        _, provider_settings, _ = _get_runtime(context)
        if not provider_settings.get("websearch_tavily_key", []):
            return "Error: Tavily API key is not configured in AstrBot."

        url = str(kwargs.get("url", "")).strip()
        if not url:
            return "Error: url must be a non-empty string."

        extract_depth = kwargs.get("extract_depth", "basic")
        if extract_depth not in ["basic", "advanced"]:
            extract_depth = "basic"

        results = await _tavily_extract(
            provider_settings,
            {"urls": [url], "extract_depth": extract_depth},
        )
        ret_ls = []
        for result in results:
            ret_ls.append(f"URL: {result.get('url', 'No URL')}")
            ret_ls.append(f"Content: {result.get('raw_content', 'No content')}")
        ret = "\n".join(ret_ls)
        return ret or "Error: Tavily web searcher does not return any results."


@builtin_tool(config=_BOCHA_WEB_SEARCH_TOOL_CONFIG)
@pydantic_dataclass
class BochaWebSearchTool(FunctionTool[AstrAgentContext]):
    name: str = "web_search_bocha"
    description: str = (
        "A web search tool based on Bocha Search API, used to retrieve web pages "
        "related to the user's query."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Required. User's search query.",
                },
                "freshness": {
                    "type": "string",
                    "description": 'Optional. Time range of the search. Recommended value is "noLimit".',
                },
                "summary": {
                    "type": "boolean",
                    "description": "Optional. Whether to include a text summary for each search result.",
                },
                "include": {
                    "type": "string",
                    "description": "Optional. Domains to include in the search, separated by | or ,.",
                },
                "exclude": {
                    "type": "string",
                    "description": "Optional. Domains to exclude from the search, separated by | or ,.",
                },
                "count": {
                    "type": "integer",
                    "description": "Optional. Number of search results to return. Range: 1-50.",
                },
            },
            "required": ["query"],
        }
    )

    async def call(self, context, **kwargs) -> ToolExecResult:
        _, provider_settings, _ = _get_runtime(context)
        if not provider_settings.get("websearch_bocha_key", []):
            return "Error: BoCha API key is not configured in AstrBot."

        payload = {
            "query": kwargs["query"],
            "count": kwargs.get("count", 10),
            "summary": bool(kwargs.get("summary", False)),
        }
        if kwargs.get("freshness"):
            payload["freshness"] = kwargs["freshness"]
        if kwargs.get("include"):
            payload["include"] = kwargs["include"]
        if kwargs.get("exclude"):
            payload["exclude"] = kwargs["exclude"]

        results = await _bocha_search(provider_settings, payload)
        if not results:
            return "Error: BoCha web searcher does not return any results."
        return _search_result_payload(results)


@builtin_tool(config=_BRAVE_WEB_SEARCH_TOOL_CONFIG)
@pydantic_dataclass
class BraveWebSearchTool(FunctionTool[AstrAgentContext]):
    name: str = "web_search_brave"
    description: str = "A web search tool based on Brave Search API."
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Required. Search query."},
                "count": {
                    "type": "integer",
                    "description": "Optional. Number of results to return. Range: 1-20.",
                },
                "country": {
                    "type": "string",
                    "description": 'Optional. Country code for region-specific results, for example "US" or "CN".',
                },
                "search_lang": {
                    "type": "string",
                    "description": 'Optional. Brave language code, for example "zh-hans" or "en".',
                },
                "freshness": {
                    "type": "string",
                    "description": 'Optional. One of "day", "week", "month", "year".',
                },
            },
            "required": ["query"],
        }
    )

    async def call(self, context, **kwargs) -> ToolExecResult:
        _, provider_settings, _ = _get_runtime(context)
        if not provider_settings.get("websearch_brave_key", []):
            return "Error: Brave API key is not configured in AstrBot."

        count = int(kwargs.get("count", 10))
        if count < 1:
            count = 1
        if count > 20:
            count = 20

        payload = {
            "q": kwargs["query"],
            "count": count,
            "country": kwargs.get("country", "US"),
            "search_lang": kwargs.get("search_lang", "zh-hans"),
        }
        freshness = kwargs.get("freshness", "")
        if freshness in ["day", "week", "month", "year"]:
            payload["freshness"] = freshness

        results = await _brave_search(provider_settings, payload)
        if not results:
            return "Error: Brave web searcher does not return any results."
        return _search_result_payload(results)


@builtin_tool(config=_FIRECRAWL_WEB_SEARCH_TOOL_CONFIG)
@pydantic_dataclass
class FirecrawlWebSearchTool(FunctionTool[AstrAgentContext]):
    name: str = "web_search_firecrawl"
    description: str = (
        "A web search tool based on Firecrawl Search API, used to retrieve web "
        "pages related to the user's query."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Required. Search query."},
                "limit": {
                    "type": "integer",
                    "description": "Optional. Number of results to return. Range: 1-100. Default is 5.",
                },
                "location": {
                    "type": "string",
                    "description": "Optional. Geographic location for search results.",
                },
                "country": {
                    "type": "string",
                    "description": 'Optional. Country code for search results, for example "US" or "CN".',
                },
                "timeout": {
                    "type": "integer",
                    "description": "Optional. Request timeout in milliseconds.",
                },
            },
            "required": ["query"],
        }
    )

    async def call(self, context, **kwargs) -> ToolExecResult:
        _, provider_settings, _ = _get_runtime(context)
        if not provider_settings.get("websearch_firecrawl_key", []):
            return "Error: Firecrawl API key is not configured in AstrBot."

        payload = {
            "query": kwargs["query"],
            "limit": kwargs.get("limit", 5),
            "sources": ["web"],
        }
        for key in ("location", "country", "timeout"):
            if kwargs.get(key):
                payload[key] = kwargs[key]

        results = await _firecrawl_search(provider_settings, payload)
        if not results:
            return "Error: Firecrawl web searcher does not return any results."
        return _search_result_payload(results)


@builtin_tool(config=_FIRECRAWL_WEB_SEARCH_TOOL_CONFIG)
@pydantic_dataclass
class FirecrawlExtractWebPageTool(FunctionTool[AstrAgentContext]):
    name: str = "firecrawl_extract_web_page"
    description: str = "Extract the content of a web page using Firecrawl."
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Required. A URL to extract content from.",
                },
                "format": {
                    "type": "string",
                    "description": 'Optional. Output format, one of "markdown", "html", "rawHtml", "summary". Default is "markdown".',
                },
                "only_main_content": {
                    "type": "boolean",
                    "description": "Optional. Whether to extract only the main page content. Default is true.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Optional. Request timeout in milliseconds.",
                },
                "max_age": {
                    "type": "integer",
                    "description": "Optional. Maximum cache age in milliseconds.",
                },
            },
            "required": ["url"],
        }
    )

    async def call(self, context, **kwargs) -> ToolExecResult:
        _, provider_settings, _ = _get_runtime(context)
        if not provider_settings.get("websearch_firecrawl_key", []):
            return "Error: Firecrawl API key is not configured in AstrBot."

        url = str(kwargs.get("url", "")).strip()
        if not url:
            return "Error: url must be a non-empty string."

        output_format = kwargs.get("format", "markdown")
        if output_format not in ["markdown", "html", "rawHtml", "summary"]:
            output_format = "markdown"

        payload = {
            "url": url,
            "formats": [output_format],
            "onlyMainContent": kwargs.get("only_main_content", True),
        }
        if kwargs.get("timeout"):
            payload["timeout"] = kwargs["timeout"]
        if kwargs.get("max_age"):
            payload["maxAge"] = kwargs["max_age"]

        result = await _firecrawl_scrape(provider_settings, payload)
        content = result.get(output_format, "")
        result_url = result.get("url") or url
        ret = f"URL: {result_url}\nContent: {content}" if content else ""
        return ret or "Error: Firecrawl web scraper does not return any results."


@builtin_tool(config=_BAIDU_WEB_SEARCH_TOOL_CONFIG)
@pydantic_dataclass
class BaiduWebSearchTool(FunctionTool[AstrAgentContext]):
    name: str = "web_search_baidu"
    description: str = (
        "A web search tool based on Baidu AI Search. "
        "Use this for real-time web retrieval when Baidu AI Search is configured."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Required. Search query."},
                "top_k": {
                    "type": "integer",
                    "description": "Optional. Number of web results to return. Maximum 50. Default is 10.",
                },
                "search_recency_filter": {
                    "type": "string",
                    "description": 'Optional. One of "week", "month", "semiyear", "year".',
                },
                "site": {
                    "type": "string",
                    "description": "Optional. Restrict search to specific sites, separated by commas.",
                },
            },
            "required": ["query"],
        }
    )

    async def call(self, context, **kwargs) -> ToolExecResult:
        _, provider_settings, _ = _get_runtime(context)
        if not provider_settings.get("websearch_baidu_app_builder_key", ""):
            return "Error: Baidu AI Search API key is not configured in AstrBot."

        top_k = int(kwargs.get("top_k", 10))
        if top_k < 1:
            top_k = 1
        if top_k > 50:
            top_k = 50

        payload = {
            "messages": [{"role": "user", "content": str(kwargs["query"])[:72]}],
            "search_source": "baidu_search_v2",
            "resource_type_filter": [{"type": "web", "top_k": top_k}],
        }

        search_recency_filter = kwargs.get("search_recency_filter", "")
        if search_recency_filter in ["week", "month", "semiyear", "year"]:
            payload["search_recency_filter"] = search_recency_filter

        site = str(kwargs.get("site", "")).strip()
        if site:
            sites = [s.strip() for s in site.replace("|", ",").split(",") if s.strip()]
            if sites:
                payload["search_filter"] = {"match": {"site": sites[:100]}}

        results = await _baidu_search(provider_settings, payload)
        if not results:
            return "Error: Baidu AI Search does not return any results."
        return _search_result_payload(results)


__all__ = [
    "BaiduWebSearchTool",
    "BochaWebSearchTool",
    "BraveWebSearchTool",
    "TavilyExtractWebPageTool",
    "TavilyWebSearchTool",
    "WEB_SEARCH_TOOL_NAMES",
    "normalize_legacy_web_search_config",
]
