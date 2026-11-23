"""Search provider normalization preserves aliases and deterministic fallback order."""

import pytest

from astrbot.builtin_stars.web_searcher import provider_routing as routing


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        (" DuckDuck-Go ", "duckduckgo"),
        ("ddg", "duckduckgo"),
        ("baidu", "baidu_ai_search"),
        ("bochaai", "bocha"),
    ],
)
def test_legacy_provider_aliases_normalize_without_losing_tool_branch(raw, canonical):
    normalized = routing.normalize_websearch(raw)
    assert normalized.canonical == canonical
    assert normalized.is_known is True
    assert routing.normalize_websearch_provider(raw) == canonical
    assert routing.normalize_websearch_provider_for_tools(raw) == (
        normalized.tool_branch,
        True,
    )


@pytest.mark.parametrize("raw", [None, "", " default ", "native", "brave"])
def test_default_and_unsupported_legacy_provider_use_default(raw):
    assert (
        routing.normalize_websearch_provider(raw) == routing.DEFAULT_WEB_SEARCH_PROVIDER
    )


def test_unknown_provider_remains_visible_but_uses_default_tool_branch():
    normalized = routing.normalize_websearch(" custom-provider ")
    assert normalized.canonical == "custom-provider"
    assert normalized.is_known is False
    assert normalized.tool_branch == routing.DEFAULT_WEB_SEARCH_PROVIDER


@pytest.mark.parametrize("provider", routing.DEFAULT_ENGINE_ORDER)
def test_primary_engine_selection_never_duplicates_fallbacks(provider):
    order = routing.build_default_engine_order(provider)
    assert set(order) == set(routing.DEFAULT_ENGINE_ORDER)
    assert len(order) == len(routing.DEFAULT_ENGINE_ORDER)
    if provider == "duckduckgo":
        assert order == routing.DEFAULT_ENGINE_ORDER
    else:
        assert order[0] == provider
        assert order[1:] == tuple(
            name for name in routing.DEFAULT_ENGINE_ORDER if name != provider
        )


def test_engine_registry_rejects_missing_and_extra_engines():
    engines = dict.fromkeys(routing.DEFAULT_ENGINE_ORDER, object())
    routing.validate_default_engine_registry(engines)
    del engines[routing.DEFAULT_ENGINE_ORDER[0]]
    engines["unknown"] = object()
    with pytest.raises(ValueError, match="missing=.*extra=.*unknown"):
        routing.validate_default_engine_registry(engines)
