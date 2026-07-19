from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from data.plugins.astrbot_plugin_semantic_router.main import SemanticRouterPlugin


@pytest.mark.asyncio
async def test_initialize_preserves_existing_browser_search_tool() -> None:
    existing_tool = object()
    manager = SimpleNamespace(get_tool=lambda name: existing_tool)
    context = SimpleNamespace(
        get_llm_tool_manager=lambda: manager,
        add_llm_tools=MagicMock(),
        activate_llm_tool=MagicMock(),
    )
    control_plane = SimpleNamespace(
        register_diagnostic_tools=MagicMock(),
        rescan_capabilities=MagicMock(return_value={"status_active": 1}),
        enforce=True,
    )
    plugin = SemanticRouterPlugin.__new__(SemanticRouterPlugin)
    plugin.context = context
    plugin.control_plane = control_plane
    plugin.search_tool_name = "browser_search"
    plugin.debug = False

    await plugin.initialize()

    context.add_llm_tools.assert_not_called()
    context.activate_llm_tool.assert_called_once_with("browser_search")
    control_plane.rescan_capabilities.assert_called_once()


def test_registered_tool_supports_legacy_manager_interface() -> None:
    expected = object()
    manager = SimpleNamespace(
        get_func=lambda name: expected if name == "search" else None
    )
    plugin = SemanticRouterPlugin.__new__(SemanticRouterPlugin)
    plugin.context = SimpleNamespace(get_llm_tool_manager=lambda: manager)

    assert plugin._get_registered_tool("search") is expected


def test_gold_capability_matches_natural_language() -> None:
    plugin = SemanticRouterPlugin.__new__(SemanticRouterPlugin)
    plugin.capabilities = [
        {
            "id": "daily.gold",
            "plugin": "astrbot_plugin_dailyhub",
            "method": "cmd_gold",
            "command": "金价",
            "arg_mode": "none",
            "risk": "safe",
            "triggers": ["今日金价", "金价", "黄金价格"],
        }
    ]
    plugin._rule_music_decision = lambda text: None
    plugin._looks_like_search_meta = lambda text: False
    plugin._normalize_text = lambda text: text.strip()

    decision = plugin._capability_decision(SimpleNamespace(), "今日金价")

    assert decision is not None
    assert decision.intent == "plugin.daily.gold"
    assert decision.action == "cmd_gold"
    assert decision.confidence >= 0.86


def test_known_meme_phrase_triggers_evidence_search_without_question_words() -> None:
    plugin = SemanticRouterPlugin.__new__(SemanticRouterPlugin)
    plugin.meme_auto_search_terms = ["哈基米", "南北绿豆"]
    plugin._looks_like_search_meta = lambda text: False
    plugin._rule_music_decision = lambda text: None
    plugin._normalize_text = lambda text: text.strip()

    query = plugin._extract_search_query("亚托莉，哈基米南北绿豆")

    assert "哈基米南北绿豆" in query
    assert "网络梗" in query
    assert "亚托莉" not in query


def test_common_atri_spelling_variants_are_wake_aliases() -> None:
    plugin = SemanticRouterPlugin.__new__(SemanticRouterPlugin)

    assert plugin._search_wake_text("亚托里，帮我查一下天气")
    assert plugin._search_wake_text("阿托里在吗")
    assert plugin._search_wake_text("亚托，看看这个")
    assert plugin._image_wake_text("萝卜子看看图")
