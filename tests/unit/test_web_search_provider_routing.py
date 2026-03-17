import pytest

from astrbot.builtin_stars.web_searcher.provider_routing import (
    DEFAULT_ENGINE_ORDER,
    build_default_engine_order,
    normalize_websearch_provider,
    normalize_websearch_provider_for_tools,
    resolve_tool_branch_provider,
    validate_default_engine_registry,
)


def test_normalize_websearch_provider_aliases() -> None:
    assert normalize_websearch_provider("duckduckgo") == "duckduckgo"
    assert normalize_websearch_provider("ddg") == "duckduckgo"
    assert normalize_websearch_provider("duckduck-go") == "duckduckgo"
    assert normalize_websearch_provider("baidu") == "baidu_ai_search"
    assert normalize_websearch_provider("bochaai") == "bocha"
    assert normalize_websearch_provider("brave") == "default"


def test_resolve_tool_branch_provider_uses_default_branch_for_engine_aliases() -> None:
    assert resolve_tool_branch_provider("duckduckgo") == "default"
    assert resolve_tool_branch_provider("google") == "default"
    assert resolve_tool_branch_provider("ddg") == "default"
    assert resolve_tool_branch_provider("tavily") == "tavily"
    assert resolve_tool_branch_provider("baidu_ai_search") == "baidu_ai_search"
    assert resolve_tool_branch_provider("bocha") == "bocha"
    # Unknown provider should fall back to default branch instead of leaving mixed tool set.
    assert resolve_tool_branch_provider("unknown_provider") == "default"


def test_build_default_engine_order_keeps_dev_compatible_default_chain() -> None:
    assert DEFAULT_ENGINE_ORDER[:2] == ("bing", "sogo")

    order = build_default_engine_order("duckduckgo")
    assert order == DEFAULT_ENGINE_ORDER
    assert order[0] == "bing"

    order = build_default_engine_order("bing")
    assert order[0] == "bing"
    assert set(order) == set(DEFAULT_ENGINE_ORDER)

    order = build_default_engine_order("google")
    assert order[0] == "google"
    assert set(order) == set(DEFAULT_ENGINE_ORDER)

    order = build_default_engine_order("tavily")
    assert order == DEFAULT_ENGINE_ORDER


def test_build_default_engine_order_covers_all_engines_unknown_and_no_duplicates() -> None:
    order = build_default_engine_order("sogo")
    assert order[0] == "sogo"
    assert set(order) == set(DEFAULT_ENGINE_ORDER)

    order = build_default_engine_order("comet")
    assert order[0] == "comet"
    assert set(order) == set(DEFAULT_ENGINE_ORDER)

    order = build_default_engine_order("xxx")
    assert order == DEFAULT_ENGINE_ORDER

    order = build_default_engine_order("bing")
    assert len(order) == len(set(order))


def test_normalize_websearch_provider_for_tools_returns_branch_and_known() -> None:
    assert normalize_websearch_provider_for_tools("tavily") == ("tavily", True)
    assert normalize_websearch_provider_for_tools("ddg") == ("default", True)
    assert normalize_websearch_provider_for_tools("unknown_provider") == (
        "default",
        False,
    )


def test_validate_default_engine_registry_allows_expected_names() -> None:
    engines_by_name = {name: object() for name in DEFAULT_ENGINE_ORDER}
    validate_default_engine_registry(engines_by_name)


def test_validate_default_engine_registry_rejects_missing_or_extra() -> None:
    missing_last = DEFAULT_ENGINE_ORDER[:-1]
    with_missing = {name: object() for name in missing_last}

    with_extra = {name: object() for name in DEFAULT_ENGINE_ORDER}
    with_extra["unknown_engine"] = object()

    with pytest.raises(ValueError):
        validate_default_engine_registry(with_missing)
    with pytest.raises(ValueError):
        validate_default_engine_registry(with_extra)
