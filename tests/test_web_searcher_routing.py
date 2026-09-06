from __future__ import annotations

from astrbot.builtin_stars.web_searcher.provider_routing import (
    NormalizedProvider,
    normalize_websearch,
    normalize_websearch_provider,
    normalize_websearch_provider_for_tools,
    resolve_tool_branch_provider,
    build_default_engine_order,
    is_known_websearch_provider,
    validate_default_engine_registry,
    DEFAULT_WEB_SEARCH_PROVIDER,
    DEFAULT_ENGINE_ORDER,
    ENGINE_REGISTRY,
)


def test_provider_routing_imported():
    assert NormalizedProvider is not None


def test_provider_routing_normalize():
    result = normalize_websearch("")
    assert isinstance(result, NormalizedProvider)
    assert result.canonical == DEFAULT_WEB_SEARCH_PROVIDER


def test_provider_routing_provider():
    result = normalize_websearch_provider("")
    assert result == DEFAULT_WEB_SEARCH_PROVIDER


def test_provider_routing_tools():
    branch, known = normalize_websearch_provider_for_tools("")
    assert isinstance(branch, str)
    assert isinstance(known, bool)


def test_provider_routing_resolve_tool_branch():
    result = resolve_tool_branch_provider("")
    assert isinstance(result, str)


def test_provider_routing_build_order():
    order = build_default_engine_order("")
    assert isinstance(order, tuple)
    assert len(order) > 0


def test_provider_routing_is_known():
    assert is_known_websearch_provider("") is True


def test_provider_routing_constants():
    assert isinstance(DEFAULT_ENGINE_ORDER, tuple)
    assert isinstance(ENGINE_REGISTRY, tuple)


def test_provider_routing_validate():
    engines = {name: None for name in DEFAULT_ENGINE_ORDER}
    validate_default_engine_registry(engines)
