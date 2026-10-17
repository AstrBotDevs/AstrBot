import asyncio
import json
import uuid
from dataclasses import dataclass as std_dataclass
from dataclasses import field
from urllib.parse import urlsplit

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
    "web_search_exa",
    "exa_get_contents",
    "web_search_anysearch",
    "web_search_deepseek",
    "deepseek_fetch_web_page",
    "web_search_keenable",
    "keenable_extract_web_page",
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
_EXA_WEB_SEARCH_TOOL_CONFIG = {
    "provider_settings.web_search": True,
    "provider_settings.websearch_provider": "exa",
}
_ANYSEARCH_WEB_SEARCH_TOOL_CONFIG = {
    "provider_settings.web_search": True,
    "provider_settings.websearch_provider": "anysearch",
}
_DEEPSEEK_WEB_SEARCH_TOOL_CONFIG = {
    "provider_settings.web_search": True,
    "provider_settings.websearch_provider": "deepseek",
}
_KEENABLE_WEB_SEARCH_TOOL_CONFIG = {
    "provider_settings.web_search": True,
    "provider_settings.websearch_provider": "keenable",
}


@std_dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    favicon: str | None = None


@std_dataclass
class _KeyRotator:
    """Concurrency-safe round-robin API key rotator.

    Each call returns the current key and advances the index. Search functions
    combine this with failover loops to retry with the next configured key.
    """

    setting_name: str
    provider_name: str
    index: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def get(self, provider_settings: dict) -> str:
        """Return the current key and advance the round-robin index.

        Args:
            provider_settings: Provider settings containing API key lists.

        Returns:
            The API key selected for this call.

        Raises:
            ValueError: If the configured key list is empty or missing.
        """
        keys = provider_settings.get(self.setting_name, [])
        if not keys:
            raise ValueError(
                f"Error: {self.provider_name} API key is not configured in AstrBot."
            )

        async with self.lock:
            # Keep the index valid if runtime config reloads shrink the key list.
            self.index = self.index % len(keys)
            key = keys[self.index]
            self.index = (self.index + 1) % len(keys)
            return key


# Retry with the next API key when these HTTP statuses indicate key-specific
# auth, quota, or rate-limit failures.
# 401 - Unauthorized, usually invalid or expired key.
# 403 - Forbidden, usually disabled key.
# 429 - Rate limited.
# 432 - Tavily quota exceeded.
_RETRYABLE_HTTP_STATUSES: frozenset[int] = frozenset({401, 403, 429, 432})
_ANYSEARCH_RETRYABLE_HTTP_STATUSES: frozenset[int] = frozenset({401, 402, 403, 429})

_TAVILY_KEY_ROTATOR = _KeyRotator("websearch_tavily_key", "Tavily")
_BOCHA_KEY_ROTATOR = _KeyRotator("websearch_bocha_key", "BoCha")
_BRAVE_KEY_ROTATOR = _KeyRotator("websearch_brave_key", "Brave")
_FIRECRAWL_KEY_ROTATOR = _KeyRotator("websearch_firecrawl_key", "Firecrawl")
_EXA_KEY_ROTATOR = _KeyRotator("websearch_exa_key", "Exa")
_ANYSEARCH_KEY_ROTATOR = _KeyRotator("websearch_anysearch_key", "AnySearch")
_DEEPSEEK_KEY_ROTATOR = _KeyRotator("websearch_deepseek_key", "DeepSeek")
_KEENABLE_KEY_ROTATOR = _KeyRotator("websearch_keenable_key", "Keenable")


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
        "websearch_exa_key",
        "websearch_anysearch_key",
        "websearch_keenable_key",
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
    """Call the Tavily Search API with API key failover.

    Args:
        provider_settings: Provider settings containing Tavily API keys.
        payload: Request payload for the Tavily search endpoint.

    Returns:
        Normalized search results.

    Raises:
        ValueError: If Tavily API keys are not configured.
        Exception: If the request fails after all retryable keys are exhausted,
            or if a non-retryable HTTP error is returned.
    """
    keys = provider_settings.get("websearch_tavily_key", [])
    if not keys:
        raise ValueError("Error: Tavily API key is not configured in AstrBot.")

    # Retry key-specific failures with the next key, but fail fast for
    # non-retryable errors such as server-side 5xx responses.
    last_error = None
    for _ in range(len(keys)):
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
                if response.status == 200:
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
                reason = await response.text()
                # Retryable errors are saved so the final failure is meaningful.
                if response.status in _RETRYABLE_HTTP_STATUSES:
                    last_error = Exception(
                        f"Tavily web search failed: {reason}, status: {response.status}",
                    )
                    continue
                raise Exception(
                    f"Tavily web search failed: {reason}, status: {response.status}",
                )

    if last_error is not None:
        raise last_error
    raise Exception("Tavily web search failed with all configured keys.")


async def _tavily_extract(provider_settings: dict, payload: dict) -> list[dict]:
    """Call the Tavily Extract API with API key failover.

    Args:
        provider_settings: Provider settings containing Tavily API keys.
        payload: Request payload for the Tavily extract endpoint.

    Returns:
        Raw Tavily extraction results.

    Raises:
        ValueError: If Tavily API keys are not configured or no results are
            returned.
        Exception: If the request fails after all retryable keys are exhausted,
            or if a non-retryable HTTP error is returned.
    """
    keys = provider_settings.get("websearch_tavily_key", [])
    if not keys:
        raise ValueError("Error: Tavily API key is not configured in AstrBot.")

    last_error = None
    for _ in range(len(keys)):
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
                if response.status == 200:
                    data = await response.json()
                    results: list[dict] = data.get("results", [])
                    if not results:
                        raise ValueError(
                            "Error: Tavily web searcher does not return any results."
                        )
                    return results
                reason = await response.text()
                if response.status in _RETRYABLE_HTTP_STATUSES:
                    last_error = Exception(
                        f"Tavily web search failed: {reason}, status: {response.status}",
                    )
                    continue
                raise Exception(
                    f"Tavily web search failed: {reason}, status: {response.status}",
                )

    if last_error is not None:
        raise last_error
    raise Exception("Tavily web extract failed with all configured keys.")


async def _bocha_search(
    provider_settings: dict,
    payload: dict,
) -> list[SearchResult]:
    """Call the BoCha Search API with API key failover.

    Args:
        provider_settings: Provider settings containing BoCha API keys.
        payload: Request payload for the BoCha search endpoint.

    Returns:
        Normalized search results.

    Raises:
        ValueError: If BoCha API keys are not configured.
        Exception: If the request fails after all retryable keys are exhausted,
            or if a non-retryable HTTP error is returned.
    """
    keys = provider_settings.get("websearch_bocha_key", [])
    if not keys:
        raise ValueError("Error: BoCha API key is not configured in AstrBot.")

    last_error = None
    for _ in range(len(keys)):
        bocha_key = await _BOCHA_KEY_ROTATOR.get(provider_settings)
        header = {
            "Authorization": f"Bearer {bocha_key}",
            "Content-Type": "application/json",
            # Explicitly disable brotli encoding to avoid aiohttp >= 3.13.3
            # decompression incompatibility.
            # See: https://github.com/aio-libs/aiohttp/issues/11898
            "Accept-Encoding": "gzip, deflate",
        }
        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.post(
                "https://api.bochaai.com/v1/web-search",
                json=payload,
                headers=header,
            ) as response:
                if response.status == 200:
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
                reason = await response.text()
                if response.status in _RETRYABLE_HTTP_STATUSES:
                    last_error = Exception(
                        f"BoCha web search failed: {reason}, status: {response.status}",
                    )
                    continue
                raise Exception(
                    f"BoCha web search failed: {reason}, status: {response.status}",
                )

    if last_error is not None:
        raise last_error
    raise Exception("BoCha web search failed with all configured keys.")


async def _brave_search(
    provider_settings: dict,
    payload: dict,
) -> list[SearchResult]:
    """Call the Brave Search API with API key failover.

    Args:
        provider_settings: Provider settings containing Brave API keys.
        payload: Request payload for the Brave search endpoint.

    Returns:
        Normalized search results.

    Raises:
        ValueError: If Brave API keys are not configured.
        Exception: If the request fails after all retryable keys are exhausted,
            or if a non-retryable HTTP error is returned.
    """
    keys = provider_settings.get("websearch_brave_key", [])
    if not keys:
        raise ValueError("Error: Brave API key is not configured in AstrBot.")

    last_error = None
    for _ in range(len(keys)):
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
                if response.status == 200:
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
                reason = await response.text()
                if response.status in _RETRYABLE_HTTP_STATUSES:
                    last_error = Exception(
                        f"Brave web search failed: {reason}, status: {response.status}",
                    )
                    continue
                raise Exception(
                    f"Brave web search failed: {reason}, status: {response.status}",
                )

    if last_error is not None:
        raise last_error
    raise Exception("Brave web search failed with all configured keys.")


async def _firecrawl_search(
    provider_settings: dict,
    payload: dict,
) -> list[SearchResult]:
    """Call the Firecrawl Search API with API key failover.

    Args:
        provider_settings: Provider settings containing Firecrawl API keys.
        payload: Request payload for the Firecrawl search endpoint.

    Returns:
        Normalized search results.

    Raises:
        ValueError: If Firecrawl API keys are not configured.
        Exception: If the request fails after all retryable keys are exhausted,
            or if a non-retryable HTTP error is returned.
    """
    keys = provider_settings.get("websearch_firecrawl_key", [])
    if not keys:
        raise ValueError("Error: Firecrawl API key is not configured in AstrBot.")

    last_error = None
    for _ in range(len(keys)):
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
                if response.status == 200:
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
                reason = await response.text()
                if response.status in _RETRYABLE_HTTP_STATUSES:
                    last_error = Exception(
                        f"Firecrawl web search failed: {reason}, status: {response.status}",
                    )
                    continue
                raise Exception(
                    f"Firecrawl web search failed: {reason}, status: {response.status}",
                )

    if last_error is not None:
        raise last_error
    raise Exception("Firecrawl web search failed with all configured keys.")


async def _firecrawl_scrape(provider_settings: dict, payload: dict) -> dict:
    """Call the Firecrawl Scrape API with API key failover.

    Args:
        provider_settings: Provider settings containing Firecrawl API keys.
        payload: Request payload for the Firecrawl scrape endpoint.

    Returns:
        Raw Firecrawl scrape result data.

    Raises:
        ValueError: If Firecrawl API keys are not configured or no result data
            is returned.
        Exception: If the request fails after all retryable keys are exhausted,
            or if a non-retryable HTTP error is returned.
    """
    keys = provider_settings.get("websearch_firecrawl_key", [])
    if not keys:
        raise ValueError("Error: Firecrawl API key is not configured in AstrBot.")

    last_error = None
    for _ in range(len(keys)):
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
                if response.status == 200:
                    data = await response.json()
                    result = data.get("data", {})
                    if not result:
                        raise ValueError(
                            "Error: Firecrawl web scraper does not return any results."
                        )
                    return result
                reason = await response.text()
                if response.status in _RETRYABLE_HTTP_STATUSES:
                    last_error = Exception(
                        f"Firecrawl web scraper failed: {reason}, status: {response.status}",
                    )
                    continue
                raise Exception(
                    f"Firecrawl web scraper failed: {reason}, status: {response.status}",
                )

    if last_error is not None:
        raise last_error
    raise Exception("Firecrawl web scraper failed with all configured keys.")


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

        start_date = str(kwargs.get("start_date") or "").strip()
        end_date = str(kwargs.get("end_date") or "").strip()
        if start_date or end_date:
            if start_date:
                payload["start_date"] = start_date
            if end_date:
                payload["end_date"] = end_date
        else:
            time_range = kwargs.get("time_range", "")
            if time_range in ["day", "week", "month", "year"]:
                payload["time_range"] = time_range

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


async def _exa_search(
    provider_settings: dict,
    payload: dict,
) -> list[SearchResult]:
    """Call the Exa /search endpoint and return normalized results."""
    exa_key = await _EXA_KEY_ROTATOR.get(provider_settings)
    headers = {
        "x-api-key": exa_key,
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession(trust_env=True) as session:
        async with session.post(
            "https://api.exa.ai/search",
            json=payload,
            headers=headers,
        ) as response:
            if response.status != 200:
                reason = await response.text()
                raise Exception(
                    f"Exa web search failed: {reason}, status: {response.status}",
                )
            data = await response.json()
            return [
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=(
                        item.get("text")
                        or (item.get("highlights") or [""])[0]
                        or item.get("summary", "")
                    ),
                )
                for item in data.get("results", [])
                if item.get("url")
            ]


async def _exa_get_contents(
    provider_settings: dict,
    payload: dict,
) -> list[dict]:
    """Call the Exa /contents endpoint and return raw result dicts."""
    exa_key = await _EXA_KEY_ROTATOR.get(provider_settings)
    headers = {
        "x-api-key": exa_key,
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession(trust_env=True) as session:
        async with session.post(
            "https://api.exa.ai/contents",
            json=payload,
            headers=headers,
        ) as response:
            if response.status != 200:
                reason = await response.text()
                raise Exception(
                    f"Exa get contents failed: {reason}, status: {response.status}",
                )
            data = await response.json()
            return data.get("results", [])


@builtin_tool(config=_EXA_WEB_SEARCH_TOOL_CONFIG)
@pydantic_dataclass
class ExaWebSearchTool(FunctionTool[AstrAgentContext]):
    """Web search tool powered by the Exa Search API."""

    name: str = "web_search_exa"
    description: str = (
        "A web search tool powered by Exa, an AI-native search engine. "
        "Supports keyword and semantic search with domain, date, and category filters."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Required. Search query."},
                "num_results": {
                    "type": "integer",
                    "description": "Optional. Number of results to return. Default is 10.",
                },
                "type": {
                    "type": "string",
                    "description": (
                        'Optional. Search type. One of "auto", "keyword", "neural". '
                        'Default is "auto".'
                    ),
                },
                "category": {
                    "type": "string",
                    "description": (
                        "Optional. Category filter. One of "
                        '"company", "research paper", "news", "github", '
                        '"tweet", "personal site", "pdf", "linkedin profile".'
                    ),
                },
                "include_domains": {
                    "type": "string",
                    "description": "Optional. Comma-separated domains to restrict results to.",
                },
                "exclude_domains": {
                    "type": "string",
                    "description": "Optional. Comma-separated domains to exclude from results.",
                },
                "start_published_date": {
                    "type": "string",
                    "description": "Optional. Start date filter in ISO 8601 format (e.g. 2024-01-01T00:00:00.000Z).",
                },
                "end_published_date": {
                    "type": "string",
                    "description": "Optional. End date filter in ISO 8601 format.",
                },
            },
            "required": ["query"],
        }
    )

    async def call(self, context, **kwargs) -> ToolExecResult:
        _, provider_settings, _ = _get_runtime(context)
        if not provider_settings.get("websearch_exa_key", []):
            return "Error: Exa API key is not configured in AstrBot."

        try:
            num_results = int(kwargs.get("num_results", 10))
        except (TypeError, ValueError):
            num_results = 10
        if num_results < 1:
            num_results = 1

        search_type = kwargs.get("type", "auto")
        if search_type not in ("auto", "keyword", "neural"):
            search_type = "auto"

        payload: dict = {
            "query": kwargs["query"],
            "numResults": num_results,
            "type": search_type,
            "contents": {"text": {"maxCharacters": 500}},
        }

        category = kwargs.get("category", "")
        if category:
            payload["category"] = category

        include_domains = str(kwargs.get("include_domains", "")).strip()
        if include_domains:
            payload["includeDomains"] = [
                d.strip() for d in include_domains.split(",") if d.strip()
            ]

        exclude_domains = str(kwargs.get("exclude_domains", "")).strip()
        if exclude_domains:
            payload["excludeDomains"] = [
                d.strip() for d in exclude_domains.split(",") if d.strip()
            ]

        if kwargs.get("start_published_date"):
            payload["startPublishedDate"] = kwargs["start_published_date"]
        if kwargs.get("end_published_date"):
            payload["endPublishedDate"] = kwargs["end_published_date"]

        results = await _exa_search(provider_settings, payload)
        if not results:
            return "Error: Exa web search does not return any results."
        return _search_result_payload(results)


@builtin_tool(config=_EXA_WEB_SEARCH_TOOL_CONFIG)
@pydantic_dataclass
class ExaGetContentsTool(FunctionTool[AstrAgentContext]):
    """Extract full page content from URLs using the Exa Contents API."""

    name: str = "exa_get_contents"
    description: str = "Extract the content of a web page using Exa."
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Required. A URL to extract content from.",
                },
                "max_characters": {
                    "type": "integer",
                    "description": "Optional. Maximum number of characters to return. Default is 3000.",
                },
            },
            "required": ["url"],
        }
    )

    async def call(self, context, **kwargs) -> ToolExecResult:
        _, provider_settings, _ = _get_runtime(context)
        if not provider_settings.get("websearch_exa_key", []):
            return "Error: Exa API key is not configured in AstrBot."

        url = str(kwargs.get("url", "")).strip()
        if not url:
            return "Error: url must be a non-empty string."

        try:
            max_characters = int(kwargs.get("max_characters", 3000))
        except (TypeError, ValueError):
            max_characters = 3000
        results = await _exa_get_contents(
            provider_settings,
            {
                "ids": [url],
                "text": {"maxCharacters": max_characters},
            },
        )
        ret_ls = []
        for result in results:
            ret_ls.append(f"URL: {result.get('url', 'No URL')}")
            ret_ls.append(f"Content: {result.get('text', 'No content')}")
        ret = "\n".join(ret_ls)
        return ret or "Error: Exa get contents does not return any results."


async def _anysearch_search(
    provider_settings: dict,
    payload: dict,
) -> list[SearchResult]:
    """Call the AnySearch /v1/search endpoint and return normalized results.

    AnySearch also serves anonymous traffic with a daily free quota, so an empty
    key list is valid and results in a single unauthenticated request.

    Args:
        provider_settings: Provider settings containing AnySearch API keys.
        payload: Request payload for the AnySearch search endpoint.

    Returns:
        Normalized search results.

    Raises:
        Exception: If the request fails after all configured keys are exhausted,
            or if a non-retryable HTTP error is returned.
    """
    keys = provider_settings.get("websearch_anysearch_key", [])
    # `None` marks the anonymous attempt used when no key is configured.
    attempts: list[str | None] = list(keys) if keys else [None]

    last_error = None
    for _ in range(len(attempts)):
        headers = {"Content-Type": "application/json"}
        if keys:
            anysearch_key = await _ANYSEARCH_KEY_ROTATOR.get(provider_settings)
            headers["Authorization"] = f"Bearer {anysearch_key}"

        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.post(
                "https://api.anysearch.com/v1/search",
                json=payload,
                headers=headers,
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    # AnySearch reports business errors (e.g. missing required vertical params)
                    # with HTTP 200 and a non-zero code; surface the message to the LLM.
                    code = data.get("code")
                    if code not in (None, 0):
                        raise Exception(
                            f"AnySearch web search failed: {data.get('message') or code}"
                        )
                    body = data.get("data") or data
                    results = []
                    for item in body.get("results", []):
                        if not item.get("url"):
                            continue
                        snippet = item.get("snippet") or item.get("content") or ""
                        # Vertical searches (finance.quote, security.vuln, ...) return structured
                        # fields instead of snippet/content; append them as text so they are not lost.
                        extras = []
                        for key, value in item.items():
                            if (
                                key in {"title", "url", "snippet", "content", "favicon"}
                                or value is None
                            ):
                                continue
                            if isinstance(value, dict | list):
                                # Nested structures (e.g. security.vuln affected_products,
                                # travel.flight segments) are serialized as JSON text
                                # so no structured data is dropped.
                                value = json.dumps(value, ensure_ascii=False)
                            elif not isinstance(value, str | int | float | bool):
                                continue
                            extras.append(f"{key}: {value}")
                        if extras:
                            snippet = "\n".join([snippet, *extras]).strip()
                        results.append(
                            SearchResult(
                                title=item.get("title", ""),
                                url=item["url"],
                                snippet=snippet,
                            )
                        )
                    return results
                reason = await response.text()
                if response.status in _ANYSEARCH_RETRYABLE_HTTP_STATUSES:
                    last_error = Exception(
                        f"AnySearch web search failed: {reason}, status: {response.status}",
                    )
                    continue
                raise Exception(
                    f"AnySearch web search failed: {reason}, status: {response.status}",
                )

    if last_error is not None:
        raise last_error
    raise Exception("AnySearch web search failed with all configured keys.")


@builtin_tool(config=_ANYSEARCH_WEB_SEARCH_TOOL_CONFIG)
@pydantic_dataclass
class AnySearchWebSearchTool(FunctionTool[AstrAgentContext]):
    """Web search tool powered by the AnySearch API."""

    name: str = "web_search_anysearch"
    description: str = (
        "A web search tool powered by AnySearch. Supports general web search and "
        "16 vertical domains: academic(search/biomedical/citation/preprint/dataset), "
        "business(company/jobs/people/trade), code(doc/snippet), "
        "energy(production/electricity), environment(aqi), "
        "finance(quote/fundamental/news/calendar/screen/macro), film(torrent), "
        "gaming(esports/store), health(drug/stats/trial), ip(global), "
        "legal(case/statute/legislation), resource(image), "
        "security(vuln/noise/intel/scan), social_media, "
        "travel(flight/flight_status), agriculture(fao), and general web search."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Required. Search query."},
                "max_results": {
                    "type": "integer",
                    "description": "Optional. The maximum number of results to return. Default is 10. Range is 1-10.",
                },
                "tag": {
                    "type": "string",
                    "description": (
                        'Optional. Domain capability tag in "{domain}.{subdomain}" form, '
                        'for example "finance.quote" or "academic.search". '
                        "Available domains: general, resource, social_media, finance(quote/fundamental/news/calendar/screen/macro), "
                        "academic(search/biomedical/citation/preprint/dataset), legal(case/statute/legislation), "
                        "health(drug/stats/trial), business(company/jobs/people/trade), "
                        "security(vuln/noise/intel/scan), ip(global), code(doc/snippet), "
                        "energy(production/electricity), environment(aqi), agriculture(fao), "
                        "travel(flight/flight_status), film(torrent), gaming(esports/store). "
                        "Omit for general web search."
                    ),
                },
                "zone": {
                    "type": "string",
                    "description": 'Optional. Result region, must be one of "cn", "intl", "global".',
                },
                "language": {
                    "type": "string",
                    "description": 'Optional. Preferred result language, for example "zh-CN" or "en".',
                },
                "params": {
                    "type": "object",
                    "description": (
                        "Optional. Extra parameters required by specific vertical tags. "
                        'Examples: {"symbol": "AAPL", "type": "stock"} for finance.quote, '
                        '{"type": "cve", "value": "CVE-2021-44228"} for security.vuln, '
                        '{"doi": "10.1038/s41586-021-03819-2"} for academic.search, '
                        '{"departure": "SHA", "arrival": "PEK", "date": "2026-09-10"} for travel.flight.'
                    ),
                },
            },
            "required": ["query"],
        }
    )

    async def call(self, context, **kwargs) -> ToolExecResult:
        _, provider_settings, _ = _get_runtime(context)

        try:
            max_results = int(kwargs.get("max_results", 10))
        except (TypeError, ValueError):
            max_results = 10
        max_results = min(max(max_results, 1), 10)

        payload: dict = {
            "query": kwargs["query"],
            "max_results": max_results,
            "format": "json",
        }

        tag = str(kwargs.get("tag", "")).strip()
        if tag:
            payload["tag"] = tag

        zone = kwargs.get("zone", "")
        if zone in ("cn", "intl", "global"):
            payload["zone"] = zone

        language = str(kwargs.get("language", "")).strip()
        if language:
            payload["language"] = language

        params = kwargs.get("params")
        if isinstance(params, dict):
            payload["params"] = params

        results = await _anysearch_search(provider_settings, payload)
        if not results:
            return "Error: AnySearch web search does not return any results."
        return _search_result_payload(results)


@builtin_tool(config=_DEEPSEEK_WEB_SEARCH_TOOL_CONFIG)
@pydantic_dataclass
class DeepSeekWebSearchTool(FunctionTool[AstrAgentContext]):
    name: str = "web_search_deepseek"
    description: str = (
        "Search the web using DeepSeek and return summaries with source references. "
        "Use deepseek_fetch_web_page for full page content when needed."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 128,
                    "description": (
                        "Search query, 1-128 Unicode characters including filters, "
                        "not all whitespace. Filters can be combined. Examples:\n"
                        "Find DeepSeek API references on GitHub or Hugging Face -> "
                        'DeepSeek "API reference" site:github.com OR site:huggingface.co\n'
                        "Find Chinese or English DeepSeek news published after 2026-01-01 "
                        "and before 2027-01-01 -> "
                        "DeepSeek news lang:zh,en after:2026-01-01 before:2027-01-01\n"
                        "Find DeepSeek information excluding ads, example.com and the phrase "
                        '"release notes" -> DeepSeek -Ads -site:example.com -"release notes"\n'
                        "Date filters accept YYYY or YYYY-MM-DD."
                    ),
                },
                "count": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 50,
                    "default": 10,
                    "description": "Optional. Number of results, 1-50. Default is 10.",
                },
                "ori_question": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 128,
                    "description": "Optional. Original user question, 1-128 Unicode characters.",
                },
                "need_content": {
                    "type": "boolean",
                    "default": False,
                    "description": "Optional. Include full page content in results. Default is false.",
                },
            },
            "required": ["query"],
        }
    )

    async def call(self, context, **kwargs) -> ToolExecResult:
        """Search DeepSeek and normalize summaries and optional page content.

        Args:
            context: Current agent execution context.
            **kwargs: Search query and optional count, ori_question, need_content.

        Returns:
            Search results with citation indices, or an input/configuration error.

        Raises:
            RuntimeError: If the DeepSeek API returns an HTTP error.
        """
        _, provider_settings, _ = _get_runtime(context)
        if not provider_settings.get("websearch_deepseek_key", []):
            return "Error: DeepSeek API key is not configured in AstrBot."

        query = kwargs.get("query")
        if (
            not isinstance(query, str)
            or not query.strip()
            or not 1 <= len(query) <= 128
        ):
            return (
                "Error: query must be a non-blank string of 1-128 Unicode characters."
            )
        count = kwargs.get("count", 10)
        if type(count) is not int or not 1 <= count <= 50:
            return "Error: count must be an integer between 1 and 50."
        ori_question = kwargs.get("ori_question")
        if ori_question is not None and (
            not isinstance(ori_question, str) or not 1 <= len(ori_question) <= 128
        ):
            return "Error: ori_question must be a string of 1-128 Unicode characters."
        need_content = kwargs.get("need_content", False)
        if not isinstance(need_content, bool):
            return "Error: need_content must be a boolean."

        payload = {"query": query, "count": count, "need_content": need_content}
        if ori_question is not None:
            payload["ori_question"] = ori_question
        key = await _DEEPSEEK_KEY_ROTATOR.get(provider_settings)
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        # Account-level limits and safety refusals cannot be resolved by rotating keys.
        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.post(
                "https://api.deepseek.com/v1/tools/search",
                json=payload,
                headers=headers,
            ) as response:
                if response.status != 200:
                    reason = await response.text()
                    raise RuntimeError(
                        f"DeepSeek web search failed: {reason}, status: {response.status}"
                    )
                data = await response.json()

        results = []
        for item in data.get("results", []):
            snippet = item.get("summary") or item.get("snippet") or ""
            if need_content and item.get("content"):
                snippet = "\n\n".join(filter(None, [snippet, item["content"]]))
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=snippet,
                    favicon=item.get("site_icon"),
                )
            )
        if not results:
            return "Error: DeepSeek web search does not return any results."
        return _search_result_payload(results)


@builtin_tool(config=_DEEPSEEK_WEB_SEARCH_TOOL_CONFIG)
@pydantic_dataclass
class DeepSeekFetchWebPageTool(FunctionTool[AstrAgentContext]):
    name: str = "deepseek_fetch_web_page"
    description: str = (
        "Fetch a single web page using DeepSeek and return its title and Markdown content. "
        "Use this to read a known URL, including a page found through web search."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 8192,
                    "description": "Required. HTTP or HTTPS URL with a host, no embedded credentials, and at most 8192 characters.",
                },
            },
            "required": ["url"],
        }
    )

    async def call(self, context, **kwargs) -> ToolExecResult:
        """Fetch Markdown content from the DeepSeek Fetch API.

        Args:
            context: Current agent execution context.
            **kwargs: The HTTP or HTTPS page URL to fetch.

        Returns:
            The page URL, title and Markdown content, or an input/configuration error.

        Raises:
            RuntimeError: If the DeepSeek API returns an HTTP error.
        """
        _, provider_settings, _ = _get_runtime(context)
        if not provider_settings.get("websearch_deepseek_key", []):
            return "Error: DeepSeek API key is not configured in AstrBot."

        url = kwargs.get("url")
        if not isinstance(url, str) or not 1 <= len(url) <= 8192:
            return "Error: url must be a string of 1-8192 characters."
        try:
            parsed = urlsplit(url)
            # Port syntax and range are validated only when this property is read.
            _ = parsed.port
            valid_url = (
                parsed.scheme in {"http", "https"}
                and bool(parsed.hostname)
                and parsed.username is None
                and parsed.password is None
                and not any(char.isspace() for char in url)
            )
        except ValueError:
            valid_url = False
        if not valid_url:
            return "Error: url must be an HTTP or HTTPS URL with a host and no embedded credentials."

        key = await _DEEPSEEK_KEY_ROTATOR.get(provider_settings)
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.post(
                "https://api.deepseek.com/v1/tools/fetch",
                json={"url": url},
                headers=headers,
            ) as response:
                if response.status != 200:
                    reason = await response.text()
                    raise RuntimeError(
                        f"DeepSeek fetch failed: {reason}, status: {response.status}"
                    )
                data = await response.json()

        if not data.get("content"):
            return "Error: DeepSeek fetch does not return any content."
        return f"URL: {url}\nTitle: {data.get('title', '')}\nContent: {data['content']}"


_KEENABLE_API_BASE = "https://api.keenable.ai"
# Identifies AstrBot to Keenable. Requests without an API key are rejected
# unless this header is present.
_KEENABLE_APP_TITLE = "astrbot"


async def _keenable_request(
    provider_settings: dict,
    path: str,
    action: str,
    *,
    payload: dict | None = None,
    params: dict | None = None,
) -> dict:
    """Call a Keenable API endpoint with API key failover.

    Keenable serves requests without an API key on `<path>/public` under a
    free rate limit, so an empty key list is valid and results in a single
    request there. Configured keys use `<path>` and raise that limit.

    Args:
        provider_settings: Provider settings containing Keenable API keys.
        path: Endpoint path, for example "/v1/search".
        action: Name used in error messages, for example "web search".
        payload: JSON body; when given the request is a POST.
        params: Query parameters; used for a GET when no payload is given.

    Returns:
        The decoded JSON response.

    Raises:
        Exception: If the request fails after all configured keys are exhausted,
            or if a non-retryable HTTP error is returned.
    """
    keys = provider_settings.get("websearch_keenable_key") or []

    last_error = None
    for _ in range(len(keys) or 1):
        headers = {"X-Keenable-Title": _KEENABLE_APP_TITLE}
        url = f"{_KEENABLE_API_BASE}{path}"
        if keys:
            headers["X-API-Key"] = await _KEENABLE_KEY_ROTATOR.get(provider_settings)
        else:
            url += "/public"

        async with aiohttp.ClientSession(trust_env=True) as session:
            if payload is not None:
                request = session.post(url, json=payload, headers=headers)
            else:
                request = session.get(url, params=params, headers=headers)
            async with request as response:
                if response.status == 200:
                    return await response.json()
                reason = await response.text()
                error = Exception(
                    f"Keenable {action} failed: {reason}, status: {response.status}",
                )
                if keys and response.status in _RETRYABLE_HTTP_STATUSES:
                    last_error = error
                    continue
                raise error

    if last_error is not None:
        raise last_error
    raise Exception(f"Keenable {action} failed with all configured keys.")


async def _keenable_search(
    provider_settings: dict,
    payload: dict,
) -> list[SearchResult]:
    """Call the Keenable search endpoint and return normalized results."""
    data = await _keenable_request(
        provider_settings, "/v1/search", "web search", payload=payload
    )
    return [
        SearchResult(
            title=item.get("title") or "",
            url=item["url"],
            # `snippet` carries the page text; `description` is usually empty.
            # The text keeps the page's line breaks, so collapse whitespace.
            snippet=" ".join(
                (item.get("snippet") or item.get("description") or "").split()
            ),
        )
        for item in data.get("results") or []
        if item.get("url")
    ]


async def _keenable_fetch(provider_settings: dict, params: dict) -> dict:
    """Call the Keenable fetch endpoint and return the page as a dict."""
    return await _keenable_request(
        provider_settings, "/v1/fetch", "page fetch", params=params
    )


@builtin_tool(config=_KEENABLE_WEB_SEARCH_TOOL_CONFIG)
@pydantic_dataclass
class KeenableWebSearchTool(FunctionTool[AstrAgentContext]):
    """Web search tool powered by the Keenable Search API."""

    name: str = "web_search_keenable"
    description: str = (
        "A web search tool powered by Keenable. Returns relevant web pages "
        "with a text excerpt of each, and can restrict results to one site."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Required. Search query."},
                "max_results": {
                    "type": "integer",
                    "description": "Optional. The maximum number of results to return. Default is 10. Range is 1-50.",
                },
                "site": {
                    "type": "string",
                    "description": 'Optional. Restrict results to one domain, for example "github.com".',
                },
            },
            "required": ["query"],
        }
    )

    async def call(self, context, **kwargs) -> ToolExecResult:
        _, provider_settings, _ = _get_runtime(context)

        try:
            max_results = int(kwargs.get("max_results", 10))
        except (TypeError, ValueError):
            max_results = 10
        max_results = min(max(max_results, 1), 50)

        payload: dict = {
            "query": kwargs["query"],
            "max_results": max_results,
            "snippet_max_length": 500,
        }

        site = str(kwargs.get("site") or "").strip()
        if site:
            payload["site"] = site

        results = await _keenable_search(provider_settings, payload)
        if not results:
            return "Error: Keenable web search does not return any results."
        return _search_result_payload(results)


@builtin_tool(config=_KEENABLE_WEB_SEARCH_TOOL_CONFIG)
@pydantic_dataclass
class KeenableExtractWebPageTool(FunctionTool[AstrAgentContext]):
    """Extract page content from a URL using the Keenable Fetch API."""

    name: str = "keenable_extract_web_page"
    description: str = "Extract the content of a web page as Markdown using Keenable."
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Required. A URL to extract content from.",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Optional. Maximum number of characters of content to return.",
                },
            },
            "required": ["url"],
        }
    )

    async def call(self, context, **kwargs) -> ToolExecResult:
        _, provider_settings, _ = _get_runtime(context)

        url = str(kwargs.get("url", "")).strip()
        if not url:
            return "Error: url must be a non-empty string."
        if urlsplit(url).scheme.lower() not in ("http", "https"):
            return "Error: url must be an http or https URL."

        params: dict = {"url": url}
        try:
            max_chars = int(kwargs.get("max_chars") or 0)
        except (TypeError, ValueError):
            max_chars = 0
        if max_chars > 0:
            params["max_chars"] = max_chars

        result = await _keenable_fetch(provider_settings, params)
        content = result.get("content")
        if not content:
            return "Error: Keenable page fetch does not return any content."
        return f"URL: {result.get('url') or url}\nContent: {content}"


__all__ = [
    "AnySearchWebSearchTool",
    "BaiduWebSearchTool",
    "BochaWebSearchTool",
    "BraveWebSearchTool",
    "DeepSeekFetchWebPageTool",
    "DeepSeekWebSearchTool",
    "ExaGetContentsTool",
    "ExaWebSearchTool",
    "KeenableExtractWebPageTool",
    "KeenableWebSearchTool",
    "TavilyExtractWebPageTool",
    "TavilyWebSearchTool",
    "WEB_SEARCH_TOOL_NAMES",
    "normalize_legacy_web_search_config",
]
