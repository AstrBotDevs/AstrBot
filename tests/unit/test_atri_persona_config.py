from __future__ import annotations

from scripts.ensure_runtime_config import (
    ATRI_IDENTITY,
    OWNER_QQ,
    PERSONA_ID,
    PERSONA_SKILL_PATH,
    ROOT,
    ensure_angel_heart,
    ensure_bilibili,
    ensure_core_config,
    ensure_parser,
    ensure_private_companion,
    ensure_self_learning,
    ensure_semantic_router,
    ensure_wakepro,
)


def test_atri_skill_is_plot_free_and_emotional() -> None:
    prompt = PERSONA_SKILL_PATH.read_text(encoding="utf-8")

    assert PERSONA_ID == "atri"
    assert "表情丰富、感情充沛的高性能机器人少女" in prompt
    assert "修理工" in prompt
    assert OWNER_QQ in prompt
    assert "不要继承原作剧情" in prompt
    assert "不只是拿来点功能的" in prompt
    assert "内在驱动力" in prompt
    assert "äºš" not in prompt
    assert "ÑÇÍÐ" not in prompt
    for legacy in ("香草", "铲屎官", "白毛猫娘", "小铃"):
        assert legacy not in prompt
    for story_character in ("夏生", "乃音子", "水菜萌", "凯瑟琳", "龙司"):
        assert story_character not in prompt


def test_persona_configs_share_atri_identity_and_repairer_mapping() -> None:
    angel: dict = {}
    companion: dict = {}
    wakepro: dict = {}

    ensure_angel_heart(angel)
    ensure_private_companion(companion)
    ensure_wakepro(wakepro)

    assert angel["personality"]["ai_self_identity"] == ATRI_IDENTITY
    assert angel["wake_interaction"]["alias"].startswith("亚托莉|")
    assert companion["basic_config"]["bot_name"] == "亚托莉"
    assert companion["basic_config"]["plugin_specific_persona_id"] == "atri"
    assert companion["basic_config"]["target_user_ids"] == [OWNER_QQ]
    assert companion["basic_config"]["private_user_aliases"] == (f"{OWNER_QQ}=你")
    assert "亚托莉" in wakepro["mention"]["names"]
    assert "萝卜子" in wakepro["mention"]["names"]
    assert wakepro["pipeline"]["steps"] == [
        "mention(提及唤醒)",
        "wake(智能唤醒)",
    ]
    assert wakepro["wake"]["prolong"] == 60.0
    assert wakepro["wake"]["similar"] == 0.35
    assert wakepro["wake"]["ask"] == 1.0
    assert wakepro["wake"]["bored"] == 1.0
    assert wakepro["wake"]["interest"] == 1.0
    assert wakepro["wake"]["prob"] == 0.0
    assert "自然使用“你”和“我”" in PERSONA_SKILL_PATH.read_text(encoding="utf-8")
    assert "香草" not in wakepro["mention"]["names"]


def test_user_visible_plugins_do_not_reintroduce_legacy_persona() -> None:
    paths = [
        ROOT / "data/plugins/astrbot_plugin_semantic_router/main.py",
        ROOT / "data/plugins/astrbot_plugin_image_processor/main.py",
        ROOT / "data/plugins/astrbot_plugin_reply_card/main.py",
        ROOT / "data/plugins/astrbot_plugin_reply_card/renderer.py",
    ]
    active_text = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    assert "亚托莉" in active_text
    assert "亚托莉 · 高性能手帐卡片" in active_text
    for legacy in ("香草", "铲屎官", "白毛猫娘", "小铃"):
        assert legacy not in active_text


def test_search_evidence_and_social_habits_use_controlled_background_learning() -> None:
    semantic: dict = {}
    self_learning: dict = {}

    ensure_semantic_router(semantic)
    ensure_self_learning(self_learning)

    assert semantic["knowledge_ingestion_enabled"] is True
    assert semantic["knowledge_auto_stage_search_enabled"] is True
    assert semantic["knowledge_auto_stage_notify_owner"] is False
    basic = self_learning["Self_Learning_Basic"]
    assert basic["enable_message_capture"] is True
    assert basic["enable_jargon_learning"] is True
    assert basic["enable_style_learning"] is True
    assert basic["enable_realtime_learning"] is False
    assert basic["enable_realtime_llm_filter"] is False
    learning = self_learning["Learning_Parameters"]
    assert learning["learning_interval_hours"] == 3
    assert learning["min_messages_for_learning"] == 30
    maibot = self_learning["MaiBot_Enhancement"]
    assert maibot["enable_expression_user_scope"] is True
    assert maibot["enable_realtime_expression_learning"] is False


def test_owner_and_bilibili_capabilities_are_kept_enabled() -> None:
    core: dict = {}
    bilibili: dict = {}
    parser = {
        "parsers_template": [
            {"__template_key": "bilibili", "enable": False, "use_proxy": False}
        ]
    }

    ensure_core_config(core)
    ensure_bilibili(bilibili)
    ensure_parser(parser)

    assert OWNER_QQ in core["admins_id"]
    assert core["callback_api_base"] == "http://host.docker.internal:6185"
    assert bilibili["enable_parse_miniapp"] is True
    assert bilibili["enable_parse_BV"] is True
    assert bilibili["enable_ai_summary"] is True
    assert bilibili["proxy"] == "http://127.0.0.1:7897"
    assert parser["proxy"] == "http://127.0.0.1:7897"
    assert parser["parsers_template"][0]["enable"] is True
    assert parser["parsers_template"][0]["use_proxy"] is True
