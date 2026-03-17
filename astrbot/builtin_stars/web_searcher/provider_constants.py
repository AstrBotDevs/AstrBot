from __future__ import annotations

DEFAULT_WEB_SEARCH_PROVIDER = "default"

# Keep this order aligned with the default engine fallback chain.
WEB_SEARCH_ENGINE_PROVIDERS: tuple[str, ...] = (
    "bing",
    "sogo",
    "duckduckgo",
    "google",
    "comet",
)

# Canonical provider ids shown in config UI options.
WEB_SEARCH_PROVIDER_OPTIONS: tuple[str, ...] = (
    DEFAULT_WEB_SEARCH_PROVIDER,
    "duckduckgo",
    "google",
    "bing",
    "comet",
    "sogo",
    "tavily",
    "baidu_ai_search",
    "bocha",
)

# Provider ids that select non-default tool branches directly.
WEB_SEARCH_TOOL_BRANCH_PROVIDERS: tuple[str, ...] = (
    DEFAULT_WEB_SEARCH_PROVIDER,
    "tavily",
    "baidu_ai_search",
    "bocha",
)
