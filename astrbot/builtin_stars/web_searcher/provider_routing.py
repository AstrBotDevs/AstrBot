from __future__ import annotations

from .engines.bing import Bing
from .engines.comet import Comet
from .engines.duckduckgo import DuckDuckGo
from .engines.google import Google
from .engines.sogo import Sogo

DEFAULT_WEB_SEARCH_PROVIDER = "default"
DEFAULT_ENGINE_ORDER: tuple[str, ...] = (
    Bing.NAME,
    Sogo.NAME,
    # Keep DDG as a secondary fallback for compatibility with the original default chain.
    DuckDuckGo.NAME,
    Google.NAME,
    Comet.NAME,
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
    "duckduckgo": DuckDuckGo.NAME,
    "duckduck_go": DuckDuckGo.NAME,
    "duckduck-go": DuckDuckGo.NAME,
    "ddg": DuckDuckGo.NAME,
    "google": Google.NAME,
    "bing": Bing.NAME,
    "comet": Comet.NAME,
    "sogo": Sogo.NAME,
    "tavily": "tavily",
    "baidu_ai_search": "baidu_ai_search",
    "baidu_ai": "baidu_ai_search",
    "baidu": "baidu_ai_search",
    "bocha": "bocha",
    "bochaai": "bocha",
    # ZeroClaw compatibility: AstrBot has no Brave provider yet, so downgrade to default.
    "brave": DEFAULT_WEB_SEARCH_PROVIDER,
}


def _normalize_raw_provider(provider: object) -> str:
    return str(provider or "").strip().lower().replace(" ", "")


def normalize_websearch_provider(provider: object) -> str:
    raw = _normalize_raw_provider(provider)
    if not raw:
        return DEFAULT_WEB_SEARCH_PROVIDER
    return _WEB_SEARCH_PROVIDER_ALIASES.get(raw, raw)


def normalize_websearch_provider_for_tools(provider: object) -> tuple[str, bool]:
    normalized = normalize_websearch_provider(provider)
    is_known = normalized in _TOOL_BRANCH_PROVIDER_SET or normalized in _ENGINE_PROVIDER_SET
    if normalized in _TOOL_BRANCH_PROVIDER_SET:
        return normalized, is_known
    return DEFAULT_WEB_SEARCH_PROVIDER, is_known


def resolve_tool_branch_provider(provider: object) -> str:
    branch_provider, _ = normalize_websearch_provider_for_tools(provider)
    return branch_provider


def build_default_engine_order(provider: object) -> tuple[str, ...]:
    normalized = normalize_websearch_provider(provider)
    if normalized == DuckDuckGo.NAME:
        # Compatibility first: selecting DDG should not override the original default primary engine.
        return DEFAULT_ENGINE_ORDER
    if normalized not in _ENGINE_PROVIDER_SET:
        return DEFAULT_ENGINE_ORDER
    return (normalized, *tuple(name for name in DEFAULT_ENGINE_ORDER if name != normalized))


def is_known_websearch_provider(provider: object) -> bool:
    _, is_known = normalize_websearch_provider_for_tools(provider)
    return is_known
