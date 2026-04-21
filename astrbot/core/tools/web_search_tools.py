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
from astrbot.core.utils.web_search_utils import normalize_web_search_base_url

MIN_WEB_SEARCH_TIMEOUT = 30

WEB_SEARCH_TOOL_NAMES = [
    "web_search_baidu",
    "web_search_tavily",
    "tavily_extract_web_page",
    "web_search_bocha",
    "web_search_brave",
    "web_search_exa",
    "exa_extract_web_page",
    "exa_find_similar",
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
_BAIDU_WEB_SEARCH_TOOL_CONFIG = {
    "provider_settings.web_search": True,
    "provider_settings.websearch_provider": "baidu_ai_search",
}
_EXA_WEB_SEARCH_TOOL_CONFIG = {
    "provider_settings.web_search": True,
    "provider_settings.websearch_provider": "exa",
}
_EXA_SEARCH_TYPES = (
    "auto",
    "fast",
    "deep",
    "deep-lite",
    "deep-reasoning",
    "instant",
    "neural",
)


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
_EXA_KEY_ROTATOR = _KeyRotator("websearch_exa_key", "Exa")


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
        "websearch_exa_key",
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


def _normalize_timeout(timeout: int | float | str | None) -> aiohttp.ClientTimeout:
    try:
        timeout_value = int(timeout) if timeout is not None else MIN_WEB_SEARCH_TIMEOUT
    except (TypeError, ValueError):
        timeout_value = MIN_WEB_SEARCH_TIMEOUT
    return aiohttp.ClientTimeout(total=max(timeout_value, MIN_WEB_SEARCH_TIMEOUT))


def _cache_favicon(url: str, favicon: str | None) -> None:
    if favicon:
        sp.temporary_cache["_ws_favicon"][url] = favicon


def _format_provider_request_error(
    provider_name: str, action: str, url: str, reason: str, status: int
) -> str:
    return (
        f"{provider_name} {action} failed for URL {url}: {reason}, status: {status}. "
        "If you configured an API Base URL, make sure it is a base URL or proxy "
        "prefix rather than a specific endpoint path."
    )


def _get_tavily_base_url(provider_settings: dict) -> str:
    return normalize_web_search_base_url(
        provider_settings.get("websearch_tavily_base_url"),
        default="https://api.tavily.com",
        provider_name="Tavily",
        disallowed_path_suffixes=("search", "extract"),
    )


def _get_exa_base_url(provider_settings: dict) -> str:
    return normalize_web_search_base_url(
        provider_settings.get("websearch_exa_base_url"),
        default="https://api.exa.ai",
        provider_name="Exa",
        disallowed_path_suffixes=("search", "contents", "findSimilar"),
    )


def _search_result_payload(results: list[SearchResult]) -> str:
    ref_uuid = uuid.uuid4().hex
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
    timeout: int = MIN_WEB_SEARCH_TIMEOUT,
) -> list[SearchResult]:
    tavily_key = await _TAVILY_KEY_ROTATOR.get(provider_settings)
    url = f"{_get_tavily_base_url(provider_settings)}/search"
    header = {
        "Authorization": f"Bearer {tavily_key}",
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession(trust_env=True) as session:
        async with session.post(
            url,
            json=payload,
            headers=header,
            timeout=_normalize_timeout(timeout),
        ) as response:
            if response.status != 200:
                reason = await response.text()
                raise Exception(
                    _format_provider_request_error(
                        "Tavily",
                        "web search",
                        url,
                        reason,
                        response.status,
                    )
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


async def _tavily_extract(
    provider_settings: dict,
    payload: dict,
    timeout: int = MIN_WEB_SEARCH_TIMEOUT,
) -> list[dict]:
    tavily_key = await _TAVILY_KEY_ROTATOR.get(provider_settings)
    url = f"{_get_tavily_base_url(provider_settings)}/extract"
    header = {
        "Authorization": f"Bearer {tavily_key}",
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession(trust_env=True) as session:
        async with session.post(
            url,
            json=payload,
            headers=header,
            timeout=_normalize_timeout(timeout),
        ) as response:
            if response.status != 200:
                reason = await response.text()
                raise Exception(
                    _format_provider_request_error(
                        "Tavily",
                        "content extraction",
                        url,
                        reason,
                        response.status,
                    )
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
    timeout: int = MIN_WEB_SEARCH_TIMEOUT,
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
            timeout=_normalize_timeout(timeout),
        ) as response:
            if response.status != 200:
                reason = await response.text()
                raise Exception(
                    f"BoCha web search failed: {reason}, status: {response.status}"
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
    timeout: int = MIN_WEB_SEARCH_TIMEOUT,
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
            timeout=_normalize_timeout(timeout),
        ) as response:
            if response.status != 200:
                reason = await response.text()
                raise Exception(
                    f"Brave web search failed: {reason}, status: {response.status}"
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


async def _baidu_search(
    provider_settings: dict,
    payload: dict,
    timeout: int = MIN_WEB_SEARCH_TIMEOUT,
) -> list[SearchResult]:
    api_key = provider_settings.get("websearch_baidu_app_builder_key", "")
    if not api_key:
        raise ValueError("Error: Baidu AI Search API key is not configured in AstrBot.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "X-Appbuilder-Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    url = "https://qianfan.baidubce.com/v2/ai_search/web_search"
    async with aiohttp.ClientSession(trust_env=True) as session:
        async with session.post(
            url,
            json=payload,
            headers=headers,
            timeout=_normalize_timeout(timeout),
        ) as response:
            if response.status != 200:
                reason = await response.text()
                raise Exception(
                    f"Baidu AI Search failed: {reason}, status: {response.status}"
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


async def _exa_search(
    provider_settings: dict,
    payload: dict,
    timeout: int = MIN_WEB_SEARCH_TIMEOUT,
) -> list[SearchResult]:
    exa_key = await _EXA_KEY_ROTATOR.get(provider_settings)
    url = f"{_get_exa_base_url(provider_settings)}/search"
    header = {
        "x-api-key": exa_key,
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession(trust_env=True) as session:
        async with session.post(
            url,
            json=payload,
            headers=header,
            timeout=_normalize_timeout(timeout),
        ) as response:
            if response.status != 200:
                reason = await response.text()
                raise Exception(
                    _format_provider_request_error(
                        "Exa",
                        "web search",
                        url,
                        reason,
                        response.status,
                    )
                )
            data = await response.json()
            return [
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=(item.get("text") or "")[:500],
                    favicon=item.get("favicon"),
                )
                for item in data.get("results", [])
            ]


async def _exa_extract(
    provider_settings: dict,
    payload: dict,
    timeout: int = MIN_WEB_SEARCH_TIMEOUT,
) -> list[dict]:
    exa_key = await _EXA_KEY_ROTATOR.get(provider_settings)
    url = f"{_get_exa_base_url(provider_settings)}/contents"
    header = {
        "x-api-key": exa_key,
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession(trust_env=True) as session:
        async with session.post(
            url,
            json=payload,
            headers=header,
            timeout=_normalize_timeout(timeout),
        ) as response:
            if response.status != 200:
                reason = await response.text()
                raise Exception(
                    _format_provider_request_error(
                        "Exa",
                        "content extraction",
                        url,
                        reason,
                        response.status,
                    )
                )
            data = await response.json()
            return data.get("results", [])


async def _exa_find_similar(
    provider_settings: dict,
    payload: dict,
    timeout: int = MIN_WEB_SEARCH_TIMEOUT,
) -> list[SearchResult]:
    exa_key = await _EXA_KEY_ROTATOR.get(provider_settings)
    url = f"{_get_exa_base_url(provider_settings)}/findSimilar"
    header = {
        "x-api-key": exa_key,
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession(trust_env=True) as session:
        async with session.post(
            url,
            json=payload,
            headers=header,
            timeout=_normalize_timeout(timeout),
        ) as response:
            if response.status != 200:
                reason = await response.text()
                raise Exception(
                    _format_provider_request_error(
                        "Exa",
                        "find similar",
                        url,
                        reason,
                        response.status,
                    )
                )
            data = await response.json()
            return [
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=(item.get("text") or "")[:500],
                    favicon=item.get("favicon"),
                )
                for item in data.get("results", [])
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
                "timeout": {
                    "type": "integer",
                    "description": "Optional. Request timeout in seconds. Minimum is 30. Default is 30.",
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

        results = await _tavily_search(
            provider_settings,
            payload,
            timeout=kwargs.get("timeout", MIN_WEB_SEARCH_TIMEOUT),
        )
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
                "timeout": {
                    "type": "integer",
                    "description": "Optional. Request timeout in seconds. Minimum is 30. Default is 30.",
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
            timeout=kwargs.get("timeout", MIN_WEB_SEARCH_TIMEOUT),
        )
        ret_ls = []
        for result in results:
            ret_ls.append(f"URL: {result.get('url', 'No URL')}")
            ret_ls.append(f"Content: {result.get('raw_content', 'No content')}")
        ret = "\n".join(ret_ls)
        return ret or "Error: Tavily web searcher does not return any results."


@builtin_tool(config=_EXA_WEB_SEARCH_TOOL_CONFIG)
@pydantic_dataclass
class ExaWebSearchTool(FunctionTool[AstrAgentContext]):
    name: str = "web_search_exa"
    description: str = (
        "A semantic web search tool based on Exa. Use it for general search, "
        "vertical search, and concept-oriented retrieval."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Required. Search query."},
                "max_results": {
                    "type": "integer",
                    "description": "Optional. Maximum number of results to return. Default is 10. Range is 1-100.",
                },
                "search_type": {
                    "type": "string",
                    "description": 'Optional. Search type. Must be one of "auto", "fast", "deep", "deep-lite", "deep-reasoning", "instant", "neural". Default is "auto".',
                },
                "category": {
                    "type": "string",
                    "description": 'Optional. Vertical search category. Supported values: "company", "people", "research paper", "news", "personal site", "financial report".',
                },
                "timeout": {
                    "type": "integer",
                    "description": "Optional. Request timeout in seconds. Minimum is 30. Default is 30.",
                },
            },
            "required": ["query"],
        }
    )

    async def call(self, context, **kwargs) -> ToolExecResult:
        _, provider_settings, _ = _get_runtime(context)
        if not provider_settings.get("websearch_exa_key", []):
            return "Error: Exa API key is not configured in AstrBot."

        search_type = str(kwargs.get("search_type", "auto")).strip().lower()
        if search_type not in _EXA_SEARCH_TYPES:
            search_type = "auto"

        max_results = max(1, min(int(kwargs.get("max_results", 10)), 100))
        payload = {
            "query": kwargs["query"],
            "numResults": max_results,
            "type": search_type,
            "contents": {"text": {"maxCharacters": 500}},
        }

        category = str(kwargs.get("category", "")).strip()
        if category in (
            "company",
            "people",
            "research paper",
            "news",
            "personal site",
            "financial report",
        ):
            payload["category"] = category

        results = await _exa_search(
            provider_settings,
            payload,
            timeout=kwargs.get("timeout", MIN_WEB_SEARCH_TIMEOUT),
        )
        if not results:
            return "Error: Exa web searcher does not return any results."
        return _search_result_payload(results)


@builtin_tool(config=_EXA_WEB_SEARCH_TOOL_CONFIG)
@pydantic_dataclass
class ExaExtractWebPageTool(FunctionTool[AstrAgentContext]):
    name: str = "exa_extract_web_page"
    description: str = "Extract the content of a web page using Exa."
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Required. A URL to extract content from.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Optional. Request timeout in seconds. Minimum is 30. Default is 30.",
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

        results = await _exa_extract(
            provider_settings,
            {"urls": [url], "text": True},
            timeout=kwargs.get("timeout", MIN_WEB_SEARCH_TIMEOUT),
        )
        if not results:
            return "Error: Exa content extraction does not return any results."

        ret_ls = []
        for result in results:
            ret_ls.append(f"URL: {result.get('url', 'No URL')}")
            ret_ls.append(f"Content: {result.get('text', 'No content')}")
        ret = "\n".join(ret_ls)
        return ret or "Error: Exa content extraction does not return any results."


@builtin_tool(config=_EXA_WEB_SEARCH_TOOL_CONFIG)
@pydantic_dataclass
class ExaFindSimilarTool(FunctionTool[AstrAgentContext]):
    name: str = "exa_find_similar"
    description: str = "Find semantically similar pages to a given URL using Exa."
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Required. The URL to find similar content for.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Optional. Maximum number of results to return. Default is 10. Range is 1-100.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Optional. Request timeout in seconds. Minimum is 30. Default is 30.",
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

        results = await _exa_find_similar(
            provider_settings,
            {
                "url": url,
                "numResults": max(1, min(int(kwargs.get("max_results", 10)), 100)),
                "contents": {"text": {"maxCharacters": 500}},
            },
            timeout=kwargs.get("timeout", MIN_WEB_SEARCH_TIMEOUT),
        )
        if not results:
            return "Error: Exa find similar does not return any results."
        return _search_result_payload(results)


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
                "timeout": {
                    "type": "integer",
                    "description": "Optional. Request timeout in seconds. Minimum is 30. Default is 30.",
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

        results = await _bocha_search(
            provider_settings,
            payload,
            timeout=kwargs.get("timeout", MIN_WEB_SEARCH_TIMEOUT),
        )
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
                "timeout": {
                    "type": "integer",
                    "description": "Optional. Request timeout in seconds. Minimum is 30. Default is 30.",
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

        results = await _brave_search(
            provider_settings,
            payload,
            timeout=kwargs.get("timeout", MIN_WEB_SEARCH_TIMEOUT),
        )
        if not results:
            return "Error: Brave web searcher does not return any results."
        return _search_result_payload(results)


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
                "timeout": {
                    "type": "integer",
                    "description": "Optional. Request timeout in seconds. Minimum is 30. Default is 30.",
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

        results = await _baidu_search(
            provider_settings,
            payload,
            timeout=kwargs.get("timeout", MIN_WEB_SEARCH_TIMEOUT),
        )
        if not results:
            return "Error: Baidu AI Search does not return any results."
        return _search_result_payload(results)


__all__ = [
    "BaiduWebSearchTool",
    "BochaWebSearchTool",
    "BraveWebSearchTool",
    "ExaExtractWebPageTool",
    "ExaFindSimilarTool",
    "ExaWebSearchTool",
    "TavilyExtractWebPageTool",
    "TavilyWebSearchTool",
    "WEB_SEARCH_TOOL_NAMES",
    "normalize_legacy_web_search_config",
]
