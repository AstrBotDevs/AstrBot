import json

from astrbot.core.utils.web_search_utils import (
    build_web_search_refs,
    collect_web_search_ref_items,
    collect_web_search_results,
)


def _make_web_search_parts() -> list[dict]:
    return [
        {
            "type": "tool_call",
            "tool_calls": [
                {
                    "name": "web_search_exa",
                    "result": json.dumps(
                        {
                            "results": [
                                {
                                    "index": "a152.1",
                                    "url": "https://example.com/1",
                                    "title": "Example 1",
                                    "snippet": "Snippet 1",
                                },
                                {
                                    "index": "a152.2",
                                    "url": "https://example.com/2",
                                    "title": "Example 2",
                                    "snippet": "Snippet 2",
                                },
                            ]
                        }
                    ),
                }
            ],
        }
    ]


def test_collect_web_search_results_builds_index_mapping():
    results = collect_web_search_results(_make_web_search_parts())

    assert results == {
        "a152.1": {
            "url": "https://example.com/1",
            "title": "Example 1",
            "snippet": "Snippet 1",
        },
        "a152.2": {
            "url": "https://example.com/2",
            "title": "Example 2",
            "snippet": "Snippet 2",
        },
    }


def test_collect_web_search_ref_items_preserves_order_and_favicon():
    refs = collect_web_search_ref_items(
        _make_web_search_parts(),
        {"https://example.com/2": "https://example.com/favicon.ico"},
    )

    assert [ref["index"] for ref in refs] == ["a152.1", "a152.2"]
    assert "favicon" not in refs[0]
    assert refs[1]["favicon"] == "https://example.com/favicon.ico"


def test_build_web_search_refs_uses_explicit_ref_indices_in_text_order():
    refs = build_web_search_refs(
        "Second <ref>a152.2</ref> first <ref>a152.1</ref>",
        _make_web_search_parts(),
    )

    assert [ref["index"] for ref in refs["used"]] == ["a152.2", "a152.1"]


def test_build_web_search_refs_falls_back_to_all_results_without_refs():
    refs = build_web_search_refs("No explicit refs here.", _make_web_search_parts())

    assert [ref["index"] for ref in refs["used"]] == ["a152.1", "a152.2"]


def test_build_web_search_refs_ignores_tool_call_id_and_falls_back():
    refs = build_web_search_refs(
        "<ref>call_a73499ddbaf845dba8310e44</ref>",
        _make_web_search_parts(),
    )

    assert [ref["index"] for ref in refs["used"]] == ["a152.1", "a152.2"]
