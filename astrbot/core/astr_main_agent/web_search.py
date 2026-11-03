"""Web search services, retrieval tools, and result citation instructions."""

from astrbot.core.agent.tool import ToolSet
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.context import Context
from astrbot.core.tools.web_search_tools import (
    AnySearchWebSearchTool,
    BaiduWebSearchTool,
    BochaWebSearchTool,
    BraveWebSearchTool,
    DeepSeekFetchWebPageTool,
    DeepSeekWebSearchTool,
    ExaGetContentsTool,
    ExaWebSearchTool,
    FirecrawlExtractWebPageTool,
    FirecrawlWebSearchTool,
    SerpApiFinanceSearchTool,
    SerpApiImageSearchTool,
    SerpApiNewsSearchTool,
    SerpApiScholarSearchTool,
    SerpApiWebSearchTool,
    TavilyExtractWebPageTool,
    TavilyWebSearchTool,
)

WEB_SEARCH_CITATION_TOOL_NAMES = frozenset(
    {
        "web_search_baidu",
        "web_search_tavily",
        "web_search_bocha",
        "web_search_brave",
        "web_search_exa",
        "web_search_anysearch",
        "web_search_deepseek",
        "web_search_serpapi",
        "news_search_serpapi",
        "image_search_serpapi",
        "finance_search_serpapi",
        "scholar_search_serpapi",
    }
)


WEB_SEARCH_CITATION_PROMPT = (
    "Always cite web search results you rely on. "
    "Index is a unique identifier for each search result. "
    "Use the exact citation format <ref>index</ref> (e.g. <ref>abcd.3</ref>) "
    "after the sentence that uses the information. Do not invent citations."
)


def apply_web_search(
    req: ProviderRequest,
    plugin_context: Context,
    prov_settings: dict,
    event: AstrMessageEvent,
) -> str:
    """Register the selected search service and prepare its citation instructions.

    Args:
        req: Request with already-selected registered tools.
        plugin_context: Registry providing builtin search tools.
        prov_settings: Search enablement and provider settings.
        event: Output platform used to select the citation format.

    Returns:
        Citation instructions to append after the other system instructions.
        Registered search tools also receive citations when builtin search is off.
    """
    if prov_settings.get("web_search", False):
        if req.func_tool is None:
            req.func_tool = ToolSet()

        tool_mgr = plugin_context.get_llm_tool_manager()
        provider = prov_settings.get("websearch_provider", "tavily")
        if provider == "tavily":
            req.func_tool.add_tool(tool_mgr.get_builtin_tool(TavilyWebSearchTool))
            req.func_tool.add_tool(tool_mgr.get_builtin_tool(TavilyExtractWebPageTool))
        elif provider == "bocha":
            req.func_tool.add_tool(tool_mgr.get_builtin_tool(BochaWebSearchTool))
        elif provider == "brave":
            req.func_tool.add_tool(tool_mgr.get_builtin_tool(BraveWebSearchTool))
        elif provider == "firecrawl":
            req.func_tool.add_tool(tool_mgr.get_builtin_tool(FirecrawlWebSearchTool))
            req.func_tool.add_tool(
                tool_mgr.get_builtin_tool(FirecrawlExtractWebPageTool)
            )
        elif provider == "baidu_ai_search":
            req.func_tool.add_tool(tool_mgr.get_builtin_tool(BaiduWebSearchTool))
        elif provider == "exa":
            req.func_tool.add_tool(tool_mgr.get_builtin_tool(ExaWebSearchTool))
            req.func_tool.add_tool(tool_mgr.get_builtin_tool(ExaGetContentsTool))
        elif provider == "anysearch":
            req.func_tool.add_tool(tool_mgr.get_builtin_tool(AnySearchWebSearchTool))
        elif provider == "deepseek":
            req.func_tool.add_tool(tool_mgr.get_builtin_tool(DeepSeekWebSearchTool))
            req.func_tool.add_tool(tool_mgr.get_builtin_tool(DeepSeekFetchWebPageTool))
        elif provider == "serpapi":
            req.func_tool.add_tool(tool_mgr.get_builtin_tool(SerpApiWebSearchTool))
            req.func_tool.add_tool(tool_mgr.get_builtin_tool(SerpApiNewsSearchTool))
            req.func_tool.add_tool(tool_mgr.get_builtin_tool(SerpApiImageSearchTool))
            req.func_tool.add_tool(tool_mgr.get_builtin_tool(SerpApiFinanceSearchTool))
            req.func_tool.add_tool(tool_mgr.get_builtin_tool(SerpApiScholarSearchTool))

    return _get_citation_instructions(event, req)


def _get_citation_instructions(
    event: AstrMessageEvent,
    req: ProviderRequest,
) -> str:
    """Describe citations for available search tools on supported clients.

    Args:
        event: Event identifying the output platform.
        req: Request containing selected tools and existing instructions.

    Returns:
        Citation instructions, or an empty string when unnecessary or present.
    """
    if event.get_platform_name() != "webchat" or not req.func_tool:
        return ""

    if not any(req.func_tool.get_tool(name) for name in WEB_SEARCH_CITATION_TOOL_NAMES):
        return ""

    system_prompt = req.system_prompt or ""
    if WEB_SEARCH_CITATION_PROMPT in system_prompt:
        return ""

    return f"\n{WEB_SEARCH_CITATION_PROMPT}\n"
