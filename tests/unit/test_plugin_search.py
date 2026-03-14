from __future__ import annotations

from astrbot.core.star.plugin_search import (
    search_plugin_market_records,
    search_plugin_records,
)


def test_search_plugin_market_records_normalizes_mixed_shapes_and_ranks_name_first() -> (
    None
):
    raw_market = {
        "astrbot_plugin_exact": {
            "desc": "general helper",
            "author": "alice",
            "repo": "https://github.com/example/exact",
        },
        "other_plugin": {
            "name": "other_plugin",
            "display_name": "Other Plugin",
            "desc": "contains astrbot_plugin_exact in description only",
            "author": "bob",
            "repo": "https://github.com/example/other",
        },
    }

    results = search_plugin_market_records(raw_market, "astrbot_plugin_exact", limit=10)

    assert [item["name"] for item in results] == [
        "astrbot_plugin_exact",
        "other_plugin",
    ]
    assert results[0]["repo"] == "https://github.com/example/exact"


def test_search_plugin_records_prioritizes_prefix_then_description_author_repo() -> (
    None
):
    records = [
        {
            "name": "helper-suite",
            "display_name": "Helper Suite",
            "desc": "utility plugin",
            "author": "team",
            "repo": "https://github.com/example/helper-suite",
        },
        {
            "name": "suite-helper-addon",
            "display_name": "Suite Helper Addon",
            "desc": "utility plugin",
            "author": "team",
            "repo": "https://github.com/example/suite-helper-addon",
        },
        {
            "name": "misc-plugin",
            "display_name": "Misc Plugin",
            "desc": "mentions helper suite in description",
            "author": "team",
            "repo": "https://github.com/example/misc-plugin",
        },
        {
            "name": "repo-match",
            "display_name": "Repo Match",
            "desc": "utility plugin",
            "author": "team",
            "repo": "https://github.com/example/helper",
        },
    ]

    results = search_plugin_records(records, "helper", limit=10)

    assert [item["name"] for item in results] == [
        "helper-suite",
        "suite-helper-addon",
        "misc-plugin",
        "repo-match",
    ]


def test_search_plugin_records_respects_limit() -> None:
    records = [
        {"name": f"plugin-{idx}", "desc": "demo", "author": "tester", "repo": ""}
        for idx in range(10)
    ]

    results = search_plugin_records(records, "plugin", limit=3)

    assert len(results) == 3
