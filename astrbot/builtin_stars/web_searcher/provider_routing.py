from __future__ import annotations

DEFAULT_WEB_SEARCH_PROVIDER = "default"
DEFAULT_ENGINE_ORDER: tuple[str, ...] = (
    "bing",
    "sogo",
    # Keep DDG as a secondary fallback for compatibility with the original default chain.
    "duckduckgo",
    "google",
    "comet",
)

_ENGINE_PROVIDER_SET = set(DEFAULT_ENGINE_ORDER)
_TOOL_BRANCH_PROVIDER_SET = {
    DEFAULT_WEB_SEARCH_PROVIDER,
    "tavily",
    "baidu_ai_search",
    "bocha",
}
_WEB_SEARCH_PROVIDER_ALIASES = {
    "": DEFAULT_WEB_SEARCH_PROVIDER,
    "default": DEFAULT_WEB_SEARCH_PROVIDER,
    "native": DEFAULT_WEB_SEARCH_PROVIDER,
    "duckduckgo": "duckduckgo",
    "duckduck_go": "duckduckgo",
    "duckduck-go": "duckduckgo",
    "ddg": "duckduckgo",
    "google": "google",
    "bing": "bing",
    "comet": "comet",
    "sogo": "sogo",
    "tavily": "tavily",
    "baidu_ai_search": "baidu_ai_search",
    "baidu_ai": "baidu_ai_search",
    "baidu": "baidu_ai_search",
    "bocha": "bocha",
    "bochaai": "bocha",
    # ZeroClaw compatibility: AstrBot has no Brave provider yet, so downgrade to default.
    "brave": DEFAULT_WEB_SEARCH_PROVIDER,
}


def normalize_websearch_provider(provider: object) -> str:
    raw = str(provider or "").strip().lower().replace(" ", "")
    if not raw:
        return DEFAULT_WEB_SEARCH_PROVIDER
    return _WEB_SEARCH_PROVIDER_ALIASES.get(raw, raw)


def resolve_tool_branch_provider(provider: object) -> str:
    normalized = normalize_websearch_provider(provider)
    if normalized in _TOOL_BRANCH_PROVIDER_SET:
        return normalized
    if normalized in _ENGINE_PROVIDER_SET:
        return DEFAULT_WEB_SEARCH_PROVIDER
    return DEFAULT_WEB_SEARCH_PROVIDER


def build_default_engine_order(provider: object) -> tuple[str, ...]:
    normalized = normalize_websearch_provider(provider)
    if normalized == "duckduckgo":
        # Compatibility first: selecting DDG should not override the original default primary engine.
        return DEFAULT_ENGINE_ORDER
    if normalized not in _ENGINE_PROVIDER_SET:
        return DEFAULT_ENGINE_ORDER
    return (normalized, *tuple(name for name in DEFAULT_ENGINE_ORDER if name != normalized))


def is_known_websearch_provider(provider: object) -> bool:
    normalized = normalize_websearch_provider(provider)
    return normalized in _TOOL_BRANCH_PROVIDER_SET or normalized in _ENGINE_PROVIDER_SET
