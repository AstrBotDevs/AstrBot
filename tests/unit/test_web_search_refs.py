import json

import pytest

from astrbot.core import sp
from astrbot.core.config.default import CONFIG_METADATA_3, DEFAULT_CONFIG
from astrbot.dashboard.services.chat_service import extract_web_search_refs
from astrbot.dashboard.services.live_chat_service import LiveChatService


@pytest.mark.parametrize(
    "extract_refs",
    [extract_web_search_refs, LiveChatService.extract_web_search_refs],
    ids=["chat", "live_chat"],
)
@pytest.mark.parametrize("cited", [True, False])
@pytest.mark.parametrize(
    "tool_name",
    [
        "web_search_deepseek",
        "web_search_serpapi",
        "image_search_serpapi",
        "finance_search_serpapi",
        "scholar_search_serpapi",
    ],
)
def test_search_refs_include_only_cited_sources(
    monkeypatch, extract_refs, cited, tool_name
):
    result = {
        "title": "Search result",
        "url": "https://example.com/article",
        "snippet": "Page summary",
        "index": "abcd.1",
    }
    monkeypatch.setitem(
        sp.temporary_cache,
        "_ws_favicon",
        {result["url"]: "https://example.com/favicon.ico"},
    )
    parts = [
        {
            "type": "tool_call",
            "tool_calls": [
                {
                    "name": tool_name,
                    "result": json.dumps({"results": [result]}),
                }
            ],
        }
    ]
    text = "Answer <ref>abcd.1</ref>" if cited else "Answer without a citation"

    refs = extract_refs(text, parts)

    assert refs == (
        {"used": [{**result, "favicon": "https://example.com/favicon.ico"}]}
        if cited
        else {}
    )


@pytest.mark.parametrize("provider", ["deepseek", "serpapi"])
def test_search_configuration_is_available_in_webui(provider):
    settings = DEFAULT_CONFIG["provider_settings"]
    items = CONFIG_METADATA_3["ai_group"]["metadata"]["websearch"]["items"]

    assert settings[f"websearch_{provider}_key"] == []
    assert settings["websearch_provider"] == "tavily"
    assert provider in items["provider_settings.websearch_provider"]["options"]
    key_metadata = items[f"provider_settings.websearch_{provider}_key"]
    assert key_metadata["secret"] is True
    assert key_metadata["type"] == "list"
    assert key_metadata["items"] == {"type": "string"}
    assert key_metadata["condition"] == {
        "provider_settings.websearch_provider": provider,
        "provider_settings.web_search": True,
    }
