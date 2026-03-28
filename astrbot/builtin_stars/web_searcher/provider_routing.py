from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .engines.bing import Bing
from .engines.comet import Comet
from .engines.duckduckgo import DuckDuckGo
from .engines.google import Google
from .engines.sogo import Sogo
from .provider_constants import (
    DEFAULT_WEB_SEARCH_PROVIDER,
    WEB_SEARCH_PROVIDER_OPTIONS,
    WEB_SEARCH_TOOL_BRANCH_PROVIDERS,
)

ENGINE_REGISTRY: tuple[tuple[str, type[object], bool], ...] = (
    (Bing.NAME, Bing, True),
    (Sogo.NAME, Sogo, True),
    # Compatibility first: DDG should stay as fallback and cannot become primary.
    (DuckDuckGo.NAME, DuckDuckGo, False),
    (Google.NAME, Google, True),
    (Comet.NAME, Comet, True),
)

DEFAULT_ENGINE_ORDER: tuple[str, ...] = tuple(name for name, _, _ in ENGINE_REGISTRY)

_ENGINE_PROVIDER_SET = {name for name, _, _ in ENGINE_REGISTRY}
_ENGINE_CAN_BE_PRIMARY = {
    name: can_be_primary for name, _, can_be_primary in ENGINE_REGISTRY
}
_TOOL_BRANCH_PROVIDER_SET = set(WEB_SEARCH_TOOL_BRANCH_PROVIDERS)
_CANONICAL_PROVIDER_SET = _ENGINE_PROVIDER_SET | _TOOL_BRANCH_PROVIDER_SET

if not _CANONICAL_PROVIDER_SET.issubset(set(WEB_SEARCH_PROVIDER_OPTIONS)):
    raise RuntimeError(
        "web search provider options and routing providers are out of sync: "
        f"canonical={sorted(_CANONICAL_PROVIDER_SET)} options={list(WEB_SEARCH_PROVIDER_OPTIONS)}",
    )

_WEB_SEARCH_PROVIDER_ALIASES: dict[str, str] = {
    "": DEFAULT_WEB_SEARCH_PROVIDER,
    "default": DEFAULT_WEB_SEARCH_PROVIDER,
    "native": DEFAULT_WEB_SEARCH_PROVIDER,
}
_WEB_SEARCH_PROVIDER_ALIASES.update({name: name for name in _CANONICAL_PROVIDER_SET})
_WEB_SEARCH_PROVIDER_ALIASES.update(
    {
        "duckduck_go": DuckDuckGo.NAME,
        "duckduck-go": DuckDuckGo.NAME,
        "ddg": DuckDuckGo.NAME,
        "baidu_ai": "baidu_ai_search",
        "baidu": "baidu_ai_search",
        "bochaai": "bocha",
        # ZeroClaw compatibility: AstrBot has no Brave provider yet, so downgrade to default.
        "brave": DEFAULT_WEB_SEARCH_PROVIDER,
    }
)


@dataclass(frozen=True)
class NormalizedProvider:
    canonical: str
    tool_branch: str
    is_known: bool


def _normalize_raw_provider(provider: object) -> str:
    return str(provider or "").strip().lower().replace(" ", "")


def normalize_websearch(provider: object) -> NormalizedProvider:
    raw = _normalize_raw_provider(provider)
    alias = _WEB_SEARCH_PROVIDER_ALIASES.get(raw, raw)
    canonical = alias or DEFAULT_WEB_SEARCH_PROVIDER

    is_engine = canonical in _ENGINE_PROVIDER_SET
    is_tool_branch = canonical in _TOOL_BRANCH_PROVIDER_SET
    is_known = is_engine or is_tool_branch
    tool_branch = canonical if is_tool_branch else DEFAULT_WEB_SEARCH_PROVIDER

    return NormalizedProvider(
        canonical=canonical,
        tool_branch=tool_branch,
        is_known=is_known,
    )


def normalize_websearch_provider(provider: object) -> str:
    return normalize_websearch(provider).canonical


def normalize_websearch_provider_for_tools(provider: object) -> tuple[str, bool]:
    normalized = normalize_websearch(provider)
    return normalized.tool_branch, normalized.is_known


def resolve_tool_branch_provider(provider: object) -> str:
    return normalize_websearch(provider).tool_branch


def build_default_engine_order(provider: object) -> tuple[str, ...]:
    normalized = normalize_websearch(provider)
    engine_name = normalized.canonical

    if engine_name not in _ENGINE_PROVIDER_SET:
        return DEFAULT_ENGINE_ORDER

    if not _ENGINE_CAN_BE_PRIMARY.get(engine_name, False):
        return DEFAULT_ENGINE_ORDER

    return (
        engine_name,
        *tuple(name for name in DEFAULT_ENGINE_ORDER if name != engine_name),
    )


def is_known_websearch_provider(provider: object) -> bool:
    return normalize_websearch(provider).is_known


def validate_default_engine_registry(engines_by_name: Mapping[str, object]) -> None:
    expected_names = {name for name, _, _ in ENGINE_REGISTRY}
    missing = [name for name in DEFAULT_ENGINE_ORDER if name not in engines_by_name]
    extra = [name for name in engines_by_name if name not in expected_names]
    if not missing and not extra:
        return

    raise ValueError(
        "default search engine registry mismatch. "
        f"missing={missing}, extra={extra}, expected_order={list(DEFAULT_ENGINE_ORDER)}",
    )
