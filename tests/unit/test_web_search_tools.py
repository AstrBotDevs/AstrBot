from types import SimpleNamespace

import pytest

import astrbot.core.tools.registry as tool_registry
import astrbot.core.tools.web_search_tools as web_search_tools
from astrbot.core.knowledge_base.parsers.url_parser import URLExtractor
from astrbot.core.tools.web_search_tools import ExaWebSearchTool


def _make_tool_context(provider_settings: dict) -> SimpleNamespace:
    cfg = {"provider_settings": provider_settings}
    return SimpleNamespace(
        context=SimpleNamespace(
            context=SimpleNamespace(get_config=lambda umo=None: cfg),
            event=SimpleNamespace(unified_msg_origin="test:private:session"),
        )
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("search_type", "expected"),
    [
        ("deep-lite", "deep-lite"),
        ("deep-reasoning", "deep-reasoning"),
        ("instant", "instant"),
        ("unsupported", "auto"),
    ],
)
async def test_exa_web_search_tool_normalizes_search_type(
    monkeypatch: pytest.MonkeyPatch,
    search_type: str,
    expected: str,
):
    captured: dict[str, object] = {}

    async def fake_exa_search(provider_settings: dict, payload: dict, timeout: int):
        captured["provider_settings"] = provider_settings
        captured["payload"] = payload
        captured["timeout"] = timeout
        return []

    monkeypatch.setattr(web_search_tools, "_exa_search", fake_exa_search)

    tool = ExaWebSearchTool()
    result = await tool.call(
        _make_tool_context({"websearch_exa_key": ["test-key"]}),
        query="AstrBot",
        search_type=search_type,
    )

    assert result == "Error: Exa web searcher does not return any results."
    assert captured["payload"]["type"] == expected


def test_get_exa_base_url_rejects_endpoint_path():
    with pytest.raises(ValueError) as exc_info:
        web_search_tools._get_exa_base_url(
            {"websearch_exa_base_url": "https://api.exa.ai/search"}
        )

    assert str(exc_info.value) == (
        "Error: Exa API Base URL must be a base URL or proxy prefix, "
        "not a specific endpoint path. Received: 'https://api.exa.ai/search'."
    )


def test_url_extractor_rejects_endpoint_base_url():
    with pytest.raises(ValueError) as exc_info:
        URLExtractor(
            ["test-key"],
            tavily_base_url="https://api.tavily.com/extract",
        )

    assert str(exc_info.value) == (
        "Error: Tavily API Base URL must be a base URL or proxy prefix, "
        "not a specific endpoint path. Received: 'https://api.tavily.com/extract'."
    )


def test_bocha_builtin_config_statuses_are_registered():
    rule = tool_registry._BUILTIN_TOOL_CONFIG_RULES.get("web_search_bocha")

    assert rule is not None
    statuses = rule.evaluate(
        {
            "provider_settings": {
                "web_search": True,
                "websearch_provider": "bocha",
            }
        }
    )

    assert statuses == [
        {
            "key": "provider_settings.web_search",
            "operator": "equals",
            "expected": True,
            "actual": True,
            "matched": True,
            "message": None,
        },
        {
            "key": "provider_settings.websearch_provider",
            "operator": "equals",
            "expected": "bocha",
            "actual": "bocha",
            "matched": True,
            "message": None,
        }
    ]
