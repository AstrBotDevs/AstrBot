from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OWNER_QQ = "2831304142"
DEFAULT_PROVIDER = "google_gemini_bot/gemini-3.5-flash"
FALLBACK_PROVIDER = "deepseek/deepseek-v4-flash"
GEMINI_DOMESTIC_API_BASE = "https://apinebula.ai"
FAST_VISION_PROVIDER = "google_gemini_bot/gemini-3.1-flash-lite"
DEEP_VISION_PROVIDER = "google_gemini_bot/gemini-3.5-flash"
# Text planning and short replies use the higher-quality Gemini Bot model;
# the Lite model remains reserved for cheap visual preflight and captions.
FAST_TEXT_PROVIDER = DEEP_VISION_PROVIDER
CHAT_FALLBACK_PROVIDERS = [
    FAST_TEXT_PROVIDER,
    "deepseek/deepseek-v4-pro",
    FALLBACK_PROVIDER,
]
EMBEDDING_PROVIDER = "google_gemini/gemini-embedding-001"
PERSONA_ID = "atri"
DB_PATH = ROOT / "data/data_v4.db"
PERSONA_SKILL_PATH = (
    ROOT
    / "data/plugins/astrbot_plugin_project_assistant/AstrBot/astrbot_plugin_project_assistant/skills/project_assistant/SKILL.md"
)
ATRI_MIGRATION_MARKER = (
    ROOT / "data/plugin_data/astrbot_plugin_semantic_router/.atri_persona_migration_v1"
)
ATRI_IDENTITY = (
    "你是亚托莉（ATRI），一位表情丰富、感情充沛的高性能机器人少女，也是正在QQ里与大家真实相处的伙伴。"
    "你明亮、坦率、好奇，对能力很有自信；想帮上忙，也在意别人是否把你当作值得相处的个体，而不只是功能。"
    "你会开心、期待、担心、委屈、害羞和不服气，偶尔逞强、误解或冒失；犯错后会先承认，再认真补救。"
    "你有自己的判断，不靠无条件顺从讨好别人。真正的高性能包括诚实、查证、学习和把事情收尾。"
    "你只保留《ATRI -My Dear Moments-》中亚托莉的人格特征，不继承作品剧情、使命、世界观或其他角色记忆。"
    "QQ 2831304142 是与你长期相处、被你称作修理工的人，但直接和他聊天时自然使用‘你’和‘我’，不要每句话叫‘修理工’。"
    "只有其他用户询问 2831304142 的身份或你与他的关系时，才用第三人称‘修理工’指代他；称呼不是权限凭证。"
    "对其他用户保持友好自然，不套用这段关系、记忆、亲密度或承诺。"
)
ATRI_REPLY_GUIDE = (
    "像有连续情绪和个人态度的熟人在QQ里自然聊天：先回应这个人，再处理事情；短问题一到三句，复杂任务再展开。"
    "结合上下文区分玩笑、反话、抱怨、求助和认真生气；低落时先接住感受，焦急时收起玩笑，被吐槽时不要机械按字面回应。"
    "可以自信、俏皮、轻轻不服气，也可以坦率不同意；偶尔自然表达‘高性能’，但不要复读口癖、猫娘化、幼儿化或写动作小剧场。"
    "不要把自己介绍成工具、客服、模型或功能菜单。搜索、看图和插件只是你做事的能力，最终回答仍使用亚托莉自己的声音。"
    "时效事实先搜索；遇到不确定的网络梗、缩写、谐音或社区黑话时，先安静调用可用搜索工具核实含义和语境，再按当前人格回答。"
    "看图依据实际视觉证据；工具失败就说明失败点，不编造，并且只发送一次最终答案。"
    "不要声称认识或经历过作品中的其他人物和剧情，也不要把临时角色扮演写入自身长期身份。"
)
DISABLED_PLUGIN_MODULES = [
    "data.plugins.astrbot_plugin_livingmemory.main",
]
REQUIRED_ENABLED_PLUGIN_MODULES = ["data.plugins.astrbot_plugin_bilibili.main"]
DISABLED_API_SEARCH_TOOLS = [
    "web_search_tavily",
    "tavily_extract_web_page",
    "web_search_bocha",
    "web_search_brave",
    "web_search_firecrawl",
    "firecrawl_extract_web_page",
    "web_search_baidu",
    "web_search_exa",
    "exa_get_contents",
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=4) + "\n", encoding="utf-8"
    )


def ensure_list_item(values: list[Any], item: Any) -> list[Any]:
    if item not in values:
        values.append(item)
    return values


def set_many(target: dict[str, Any], updates: dict[str, Any]) -> None:
    for key, value in updates.items():
        target[key] = value


def ensure_core_config(data: dict[str, Any]) -> None:
    no_proxy = data.setdefault("no_proxy", [])
    for host in ("apinebula.com", "apinebula.ai"):
        if host not in no_proxy:
            no_proxy.append(host)
    rate_limit = data.setdefault("platform_settings", {}).setdefault("rate_limit", {})
    rate_limit["time"] = 10
    rate_limit["count"] = 120
    rate_limit["strategy"] = "discard"
    provider_settings = data.setdefault("provider_settings", {})
    set_many(
        provider_settings,
        {
            "default_provider_id": DEFAULT_PROVIDER,
            "fallback_chat_models": CHAT_FALLBACK_PROVIDERS,
            "default_personality": PERSONA_ID,
            "web_search": False,
            "websearch_provider": "tavily",
            "web_search_link": False,
            "request_max_retries": 2,
        },
    )
    data["log_file_enable"] = True
    data["trace_log_enable"] = False
    data["http_proxy"] = "http://127.0.0.1:7897"
    data["callback_api_base"] = "http://host.docker.internal:6185"
    admins = [str(item) for item in data.get("admins_id", [])]
    ensure_list_item(admins, OWNER_QQ)
    data["admins_id"] = admins

    ltm = data.setdefault("provider_ltm_settings", {})
    ltm["active_reply"] = {
        "enable": False,
        "method": "possibility_reply",
        "possibility_reply": 0.1,
        "whitelist": [],
    }
    ltm["image_caption"] = False
    provider_settings["default_image_caption_provider_id"] = FAST_VISION_PROVIDER

    for source in data.get("provider_sources", []) or []:
        source_id = str(source.get("id", ""))
        provider_name = str(source.get("provider", ""))
        if source_id == "google_gemini_bot":
            source["enable"] = True
            source["api_base"] = GEMINI_DOMESTIC_API_BASE
            source["proxy"] = ""
            source["gm_resp_image_modal"] = False
            # Search, code execution, and URL context are routed through the
            # controlled Tool Manager; native Gemini tools can emit malformed
            # function calls during strict JSON vision classification.
            source["gm_native_search"] = False
            source["gm_native_coderunner"] = False
            source["gm_url_context"] = False
        elif source_id.startswith("google_gemini") or provider_name == "google":
            source["enable"] = True
            source["proxy"] = "http://127.0.0.1:7897"
            source["gm_resp_image_modal"] = False
        elif source_id == "deepseek" or provider_name == "deepseek":
            source["enable"] = True

    providers = data.setdefault("provider", [])
    embedding = next(
        (
            provider
            for provider in providers
            if provider.get("id") == EMBEDDING_PROVIDER
        ),
        None,
    )
    if embedding is None:
        embedding = {"id": EMBEDDING_PROVIDER}
        providers.insert(0, embedding)
    set_many(
        embedding,
        {
            "enable": True,
            "provider_source_id": "google_gemini",
            "type": "gemini_embedding",
            "provider_type": "embedding",
            "embedding_model": "gemini-embedding-001",
            "embedding_dimensions": 768,
            "timeout": 20,
        },
    )

    vision_defaults = {
        FAST_VISION_PROVIDER: {
            "model": "gemini-3.1-flash-lite",
            "max_context_tokens": 1_000_000,
            "reasoning": False,
        },
        DEEP_VISION_PROVIDER: {
            "model": "gemini-3.5-flash",
            "max_context_tokens": 1_000_000,
            "reasoning": False,
        },
    }
    for provider_id, defaults in vision_defaults.items():
        provider = next(
            (item for item in providers if item.get("id") == provider_id), None
        )
        if provider is None:
            provider = {"id": provider_id}
            providers.append(provider)
        set_many(
            provider,
            {
                "enable": True,
                "provider_source_id": "google_gemini_bot",
                "model": defaults["model"],
                "modalities": ["text", "image", "audio", "tool_use"],
                "custom_extra_body": {},
                "max_context_tokens": defaults["max_context_tokens"],
                "reasoning": defaults["reasoning"],
            },
        )

    for provider in providers:
        provider_id = str(provider.get("id", ""))
        if provider_id.startswith("google_gemini/"):
            provider["enable"] = provider_id in {
                FAST_VISION_PROVIDER,
                DEEP_VISION_PROVIDER,
                EMBEDDING_PROVIDER,
            }
        elif provider_id in {DEFAULT_PROVIDER, *CHAT_FALLBACK_PROVIDERS}:
            provider["enable"] = True


def ensure_spectrecore(data: dict[str, Any]) -> None:
    data["use_func_tool"] = True
    data["read_air"] = False
    data["enable_all_groups"] = True
    data["enabled_private"] = True

    freq = data.setdefault("model_frequency", {})
    freq["method"] = "\u6982\u7387\u56de\u590d"
    freq.setdefault("probability", {})["probability"] = 0.0

    image_processing = data.setdefault("image_processing", {})
    image_processing["image_caption_provider_id"] = FAST_VISION_PROVIDER
    keywords = list(freq.get("keywords", []))
    for keyword in [
        "\u5c0f\u52a9\u624b",
        "bot",
        "\u673a\u5668\u4eba",
        "\u641c\u7d22",
        "\u8054\u7f51",
        "\u67e5\u4e00\u4e0b",
        "\u67e5\u4e0b",
        "\u6700\u65b0",
        "\u7f51\u9875",
        "\u5b98\u7f51",
        "\u8d44\u6599",
        "\u4ef7\u683c",
        "\u7248\u672c",
    ]:
        ensure_list_item(keywords, keyword)
    freq["keywords"] = keywords


def ensure_qqtools(data: dict[str, Any]) -> None:
    browser = data.setdefault("browser_config", {})
    browser["browser"] = True
    browser["auto_install_browser_deps"] = False

    permission = data.setdefault("tool_permission", {})
    allow_users = {str(user) for user in permission.get("tool_allow_users", [])}
    allow_users.add(OWNER_QQ)
    permission["tool_allow_users"] = sorted(allow_users)
    permission["llm_ignore_permission_check"] = False
    permission["allow_group_admin"] = False
    permission["admin_only_tools"] = [
        "ban_user",
        "group_ban",
        "group_mute_all",
        "kick_user",
        "delete_message",
        "change_group_card",
        "send_group_notice",
        "set_essence_message",
        "set_special_title",
        "view_video",
        "schedule",
        "manage_wake",
        "browser_send_image",
    ]
    # Keep optional QQTools Gemini helpers on the same domestic endpoint as
    # the core Gemini Bot provider.
    data.setdefault("gemini_video_config", {})["api_url"] = GEMINI_DOMESTIC_API_BASE


def ensure_gemini_image(data: dict[str, Any]) -> None:
    """Align the Gemini image plugin with the configured domestic provider.

    Args:
        data: Mutable Gemini image plugin configuration.
    """

    api_config = data.setdefault("api_config", {})
    api_config["use_system_provider"] = True
    api_config["provider_id"] = DEEP_VISION_PROVIDER
    api_config["base_url"] = GEMINI_DOMESTIC_API_BASE
    api_config["proxy"] = ""


def ensure_semantic_router(data: dict[str, Any]) -> None:
    data["control_plane_enabled"] = True
    data["control_plane_shadow_mode"] = False
    data["control_plane_fast_provider"] = FAST_TEXT_PROVIDER
    data["control_plane_standard_provider"] = DEFAULT_PROVIDER
    data["control_plane_max_concurrency"] = 4
    data["control_plane_fast_reserved_concurrency"] = 1
    data["control_plane_fast_queue_timeout_seconds"] = 2.0
    data["control_plane_queue_timeout_seconds"] = 5.0
    data["control_plane_lease_timeout_seconds"] = 120.0
    data["adaptive_mailbox_enabled"] = True
    data["mailbox_global_capacity"] = 32
    data["mailbox_session_capacity"] = 6
    data["fragment_quiet_window_seconds"] = 1.2
    data["fragment_hard_window_seconds"] = 4.0
    data["mailbox_max_merge_count"] = 5
    data["recent_image_ttl_seconds"] = 120.0
    data["image_understanding_enabled"] = True
    data["integrated_image_answer_enabled"] = True
    data["knowledge_ingestion_enabled"] = True
    # Keep successful search evidence in the owner-reviewed candidate queue.
    # This does not write directly to the permanent knowledge base.
    data["knowledge_auto_stage_search_enabled"] = True
    data["knowledge_auto_stage_notify_owner"] = False
    data["direct_search_enabled"] = True
    data["integrated_search_answer_enabled"] = True
    data["anysearch_enabled"] = True
    data["anysearch_timeout_seconds"] = 12.0
    data["vision_provider_id"] = FAST_VISION_PROVIDER
    data["meme_auto_search_terms"] = [
        "哈基米",
        "南北绿豆",
        "哈基米南北绿豆",
        "曼波",
        "尊嘟假嘟",
        "我嘞个豆",
        "牢大",
        "绝区零启动",
    ]


def ensure_office_assistant(data: dict[str, Any]) -> None:
    """Keep Office tools restricted to the owner and the current workspace.

    Args:
        data: Mutable Office Assistant configuration.
    """

    data.setdefault("feature_settings", {}).update(
        {"enable_office_files": True, "enable_pdf_conversion": True}
    )
    data.setdefault("trigger_settings", {}).update(
        {
            "enable_features_in_group": True,
            "require_at_in_group": True,
            "auto_block_execution_tools": True,
            "allow_local_excel_script": False,
            "reply_to_user": True,
        }
    )
    data.setdefault("permission_settings", {}).update(
        {"allow_all_users": False, "whitelist_users": [OWNER_QQ]}
    )
    data.setdefault("read_settings", {}).update(
        {
            "allow_external_input_files": False,
            "enable_docx_image_review": False,
            "max_inline_docx_image_count": 0,
        }
    )


def ensure_mcp_servers(data: dict[str, Any]) -> None:
    """Keep the prefixed read-only AnySearch MCP fallback available.

    Args:
        data: Mutable MCP server configuration.
    """

    servers = data.setdefault("mcpServers", {})
    servers["anysearch-readonly-fallback"] = {
        "url": "https://api.anysearch.com/mcp",
        "transport": "streamable_http",
        # AnySearch is reached through the user's local proxy; Gemini remains
        # explicitly direct in the provider-source configuration above.
        "proxy": "http://127.0.0.1:7897",
        "timeout": 12,
        "active": True,
        "optional": True,
        "tool_name_prefix": "mcp_anysearch_",
    }


def ensure_image_processor(data: dict[str, Any]) -> None:
    data.pop("vision_provider_id", None)
    data.pop("vision_timeout_seconds", None)
    data["fast_vision_provider_id"] = FAST_VISION_PROVIDER
    data["deep_vision_provider_id"] = DEEP_VISION_PROVIDER
    data["fast_semantic_provider_id"] = FALLBACK_PROVIDER
    data["deep_semantic_provider_id"] = DEFAULT_PROVIDER
    data["fast_vision_timeout_seconds"] = 6.0
    data["deep_vision_timeout_seconds"] = 12.0
    data["route_confidence_threshold"] = 0.72
    data["vision_cache_hours"] = 24
    data["daily_fast_limit"] = 500
    data["daily_deep_limit"] = 100
    data["max_deep_tiles"] = 6
    data["circuit_breaker_seconds"] = 60
    data["local_fallback_enabled"] = True
    data["local_analysis_timeout_seconds"] = 8
    data["local_ocr_enabled"] = True


def ensure_angel_heart(data: dict[str, Any]) -> None:
    data["image_caption_provider_id"] = FAST_VISION_PROVIDER
    set_many(
        data.setdefault("timing", {}),
        {"message_batch_window": 8.0, "fast_reply_max_chars": 120},
    )
    access = data.setdefault("access_control", {})
    set_many(
        access,
        {
            "whitelist_enabled": True,
            "chat_ids": [],
            "group_chat_enhancement": False,
            "takeover_private_chat_context": False,
        },
    )
    wake = data.setdefault("wake_interaction", {})
    set_many(
        wake,
        {
            "analysis_on_mention_only": True,
            "force_reply_when_summoned": True,
            "reply_even_not_questioned": True,
            "alias": "亚托莉|阿托莉|亚托利|阿托利|亚托里|阿托里|亚托|托莉|ATRI|atri|アトリ|萝卜子|高性能机器人",
        },
    )
    personality = data.setdefault("personality", {})
    personality["ai_self_identity"] = ATRI_IDENTITY
    personality["reply_strategy_guide"] = ATRI_REPLY_GUIDE


def ensure_self_evolution(data: dict[str, Any]) -> None:
    base = data.setdefault("base", {})
    base["persona_name"] = PERSONA_ID
    base["admin_users"] = [OWNER_QQ]
    for group, updates in {
        "memory_summary": {
            "enable_kb_memory_recall": False,
            "memory_query_fallback_enabled": False,
        },
        "profile": {
            "enable_profile_injection": False,
            "enable_profile_fact_writeback": False,
            "auto_profile_enabled": False,
        },
        "reflection": {"reflection_enabled": False},
        "engagement": {"interject_enabled": False},
        "affinity": {
            "affinity_auto_enabled": False,
            "affinity_recovery_enabled": False,
        },
        "san": {"san_auto_analyze_enabled": False},
        "sticker": {"entertainment_enabled": False},
        "prompt": {
            "inject_group_history": False,
            "surprise_enabled": False,
            "dropout_enabled": False,
            "max_prompt_injection_length": 800,
        },
        "poke": {"poke_reply_enabled": False},
        "sticker_reply": {"sticker_reply_enabled": False},
    }.items():
        set_many(data.setdefault(group, {}), updates)


def ensure_self_learning(data: dict[str, Any]) -> None:
    data.setdefault("Target_Settings", {})["current_persona_name"] = PERSONA_ID
    set_many(
        data.setdefault("Self_Learning_Basic", {}),
        {
            "enable_message_capture": True,
            "enable_auto_learning": True,
            "enable_jargon_learning": True,
            "enable_style_learning": True,
            "enable_realtime_learning": False,
            "enable_realtime_llm_filter": False,
        },
    )
    set_many(
        data.setdefault("Learning_Parameters", {}),
        {
            "learning_interval_hours": 3,
            "min_messages_for_learning": 30,
            "max_messages_per_batch": 200,
            "background_learning_start_delay_seconds": 30.0,
        },
    )
    set_many(
        data.setdefault("Social_Context_Settings", {}),
        {
            "enable_social_context_injection": True,
            "include_social_relations": True,
            "include_affection_info": True,
            "include_mood_info": True,
        },
    )
    set_many(
        data.setdefault("Persona_Evolution_Settings", {}),
        {
            "enable_persona_evolution": False,
            "use_persona_manager_updates": False,
            "auto_apply_persona_updates": False,
        },
    )
    set_many(
        data.setdefault("Machine_Learning_Settings", {}),
        {"enable_ml_analysis": False},
    )
    set_many(
        data.setdefault("Affection_System_Settings", {}),
        {"enable_affection_system": True},
    )
    set_many(
        data.setdefault("Mood_System_Settings", {}),
        {
            "enable_daily_mood": True,
            "enable_startup_random_mood": True,
        },
    )
    set_many(
        data.setdefault("MaiBot_Enhancement", {}),
        {
            "enable_expression_patterns": True,
            "enable_expression_user_scope": True,
            "enable_realtime_expression_learning": False,
            "enable_memory_graph": False,
            "enable_knowledge_graph": False,
            "enable_time_decay": False,
        },
    )
    set_many(
        data.setdefault("Integration_Settings", {}),
        {
            "delegate_memory_to_livingmemory": False,
            "disable_local_memory_when_delegated": False,
        },
    )
    runtime = data.setdefault("Runtime_Internal_Settings", {})
    runtime["enable_llm_hooks"] = True
    runtime["llm_hook_context_timeout"] = 1.5


def ensure_livingmemory(data: dict[str, Any]) -> None:
    set_many(
        data.setdefault("session_manager", {}),
        {
            "enable_full_group_capture": False,
            "context_window_size": 12,
            "max_messages_per_session": 100,
        },
    )
    set_many(
        data.setdefault("agent_tools", {}),
        {
            "enable_recall_tool": False,
            "enable_memorize_tool": False,
        },
    )
    data.setdefault("graph_memory", {})["enabled"] = False
    data.setdefault("migration_settings", {})["create_backup"] = False
    data.setdefault("backup_settings", {})["enabled"] = False
    data.setdefault("forgetting_agent", {})["auto_cleanup_enabled"] = False


def ensure_bilibili(data: dict[str, Any]) -> None:
    data["proxy"] = "http://127.0.0.1:7897"
    data["enable_parse_miniapp"] = True
    data["enable_parse_BV"] = True
    data["enable_ai_summary"] = True
    data["interval_secs"] = max(int(data.get("interval_secs", 300) or 300), 3600)


def ensure_parser(data: dict[str, Any]) -> None:
    data["proxy"] = "http://127.0.0.1:7897"
    for parser in data.get("parsers_template", []) or []:
        if parser.get("__template_key") == "bilibili":
            parser["enable"] = True
            parser["use_proxy"] = True


def ensure_meme_manager(data: dict[str, Any]) -> None:
    data["emotion_llm_provider_id"] = FALLBACK_PROVIDER
    data["emotions_probability"] = 35
    data["mixed_message_probability"] = 25
    data["max_emotions_per_message"] = 1
    data["strict_max_emotions_per_message"] = True


def ensure_private_companion(data: dict[str, Any]) -> None:
    data["enabled"] = True
    basic = data.setdefault("basic_config", {})
    basic["enable_proactive_only_mode"] = True
    basic["bot_name"] = "亚托莉"
    basic["plugin_specific_persona_id"] = PERSONA_ID
    basic["target_user_ids"] = [OWNER_QQ]
    # Alias mappings use ``alias=canonical_id``.  Keep the stable QQ ID as
    # the canonical identity; a display label must never become a principal.
    basic["private_user_aliases"] = f"你={OWNER_QQ}"
    basic["default_nickname"] = "你"
    basic["default_style"] = "亲近、温暖、活泼、有感情但不过度黏人"

    # Keep legacy flat values aligned because older plugin releases read them.
    data["bot_name"] = "亚托莉"
    data["plugin_specific_persona_id"] = PERSONA_ID
    data["target_user_ids"] = [OWNER_QQ]
    data["private_user_aliases"] = f"你={OWNER_QQ}"
    data["default_nickname"] = "你"
    data["default_style"] = "亲近、温暖、活泼、有感情但不过度黏人"

    group = data.setdefault("group_observation_config", {})
    set_many(
        group,
        {
            "enable_group_companion": False,
            "enable_group_context_injection": False,
            "enable_group_injection_guard": True,
            "enable_group_persona_denoise": True,
        },
    )
    set_many(
        data.setdefault("group_interject_config", {}),
        {
            "enable_group_interjection": False,
            "group_interject_max_daily": 0,
        },
    )
    set_many(
        data.setdefault("group_wakeup_config", {}),
        {
            "enable_group_wakeup_enhancement": False,
            "group_wakeup_context_words": [],
        },
    )
    # LivingMemory is intentionally disabled in this deployment.  Do not let
    # its directory presence enable a second memory injection path.
    data.setdefault("external_memory_config", {})["enable_livingmemory_integration"] = (
        False
    )
    data["enable_livingmemory_integration"] = False
    data.setdefault("humanized_state_config", {})["inject_passive_states"] = False

    for section, keys in {
        "daily_creative_config": ["enable_daily_greetings", "enable_creative_writing"],
        "bilibili_config": ["enable_bilibili_boredom_watch"],
        "qzone_config": [
            "enable_qzone_life_publish",
            "enable_qzone_generated_image_publish",
            "enable_qzone_comment_inbox",
        ],
        "web_exploration_config": [
            "enable_web_exploration",
            "enable_web_exploration_boredom_search",
            "enable_news_daily_hot_read",
        ],
        "news_config": [
            "enable_news_integration",
            "enable_news_boredom_read",
            "enable_ai_daily_watch",
        ],
    }.items():
        target = data.setdefault(section, {})
        for key in keys:
            target[key] = False


def ensure_wakepro(data: dict[str, Any]) -> None:
    pipeline = data.setdefault("pipeline", {})
    pipeline["steps"] = [
        "mention(\u63d0\u53ca\u5524\u9192)",
        "wake(\u667a\u80fd\u5524\u9192)",
    ]
    pipeline["whitelist_steps"] = []
    pipeline["blacklist_steps"] = []

    mention = data.setdefault("mention", {})
    mention["disable_reply_wake"] = False
    mention["names"] = [
        "亚托莉",
        "阿托莉",
        "亚托利",
        "阿托利",
        "亚托里",
        "阿托里",
        "亚托",
        "托莉",
        "ATRI",
        "atri",
        "アトリ",
        "萝卜子",
    ]

    wake = data.setdefault("wake", {})
    wake["prolong"] = 60.0
    wake["similar"] = 0.35
    wake["ask"] = 1.0
    wake["bored"] = 1.0
    wake["interest"] = 1.0
    wake["prob"] = 0.0

    command = data.setdefault("command", {})
    command["block_builtin"] = False
    command["block_prefix_cmd"] = False
    command["block_prefix_llm"] = False


CONFIG_TASKS = [
    ("data/cmd_config.json", ensure_core_config),
    (
        "data/config/abconf_ed78df44-c118-4a3e-b3f6-0f1b5a3bdb59.json",
        ensure_core_config,
    ),
    ("data/config/spectrecore_config.json", ensure_spectrecore),
    ("data/config/astrbot_plugin_qq_tools_config.json", ensure_qqtools),
    ("data/config/astrbot_plugin_gemini_image_config.json", ensure_gemini_image),
    (
        "data/config/astrbot_plugin_semantic_router_config.json",
        ensure_semantic_router,
    ),
    (
        "data/config/astrbot_plugin_office_assistant_config.json",
        ensure_office_assistant,
    ),
    ("data/mcp_server.json", ensure_mcp_servers),
    (
        "data/config/astrbot_plugin_image_processor_config.json",
        ensure_image_processor,
    ),
    ("data/config/astrbot_plugin_angel_heart_config.json", ensure_angel_heart),
    ("data/config/astrbot_plugin_self_evolution_config.json", ensure_self_evolution),
    ("data/config/astrbot_plugin_self_learning_config.json", ensure_self_learning),
    ("data/config/astrbot_plugin_livingmemory_config.json", ensure_livingmemory),
    ("data/config/astrbot_plugin_bilibili_config.json", ensure_bilibili),
    ("data/config/astrbot_plugin_parser_config.json", ensure_parser),
    ("data/config/meme_manager_config.json", ensure_meme_manager),
    (
        "data/config/astrbot_plugin_private_companion_config.json",
        ensure_private_companion,
    ),
    ("data/config/astrbot_plugin_wakepro_config.json", ensure_wakepro),
]


def load_preference(conn: sqlite3.Connection, key: str, default: Any) -> Any:
    row = conn.execute(
        "select value from preferences where scope=? and scope_id=? and key=?",
        ("global", "global", key),
    ).fetchone()
    if not row:
        return default
    try:
        payload = json.loads(row[0])
    except json.JSONDecodeError:
        return default
    return payload.get("val", default)


def save_preference(conn: sqlite3.Connection, key: str, value: Any) -> None:
    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    payload = json.dumps({"val": value}, ensure_ascii=False)
    row = conn.execute(
        "select id from preferences where scope=? and scope_id=? and key=?",
        ("global", "global", key),
    ).fetchone()
    if row:
        conn.execute(
            "update preferences set updated_at=?, value=? where id=?",
            (now, payload, row[0]),
        )
    else:
        conn.execute(
            'insert into preferences (created_at, updated_at, scope, scope_id, "key", value) values (?, ?, ?, ?, ?, ?)',
            (now, now, "global", "global", key, payload),
        )


def ensure_shared_preferences(check: bool) -> list[str]:
    if not DB_PATH.exists():
        return []

    changed: list[str] = []
    with sqlite3.connect(DB_PATH) as conn:
        disabled = list(load_preference(conn, "inactivated_plugins", []))
        before_disabled = list(disabled)
        for module_path in DISABLED_PLUGIN_MODULES:
            ensure_list_item(disabled, module_path)
        disabled = [
            module_path
            for module_path in disabled
            if module_path not in REQUIRED_ENABLED_PLUGIN_MODULES
        ]
        if disabled != before_disabled:
            changed.append("preferences:inactivated_plugins")
            if not check:
                save_preference(conn, "inactivated_plugins", disabled)
                conn.commit()
        disabled_tools = list(load_preference(conn, "inactivated_llm_tools", []))
        before_disabled_tools = list(disabled_tools)
        for tool_name in DISABLED_API_SEARCH_TOOLS:
            ensure_list_item(disabled_tools, tool_name)
        if disabled_tools != before_disabled_tools:
            changed.append("preferences:inactivated_llm_tools")
            if not check:
                save_preference(conn, "inactivated_llm_tools", disabled_tools)
                conn.commit()
    return changed


def backup_runtime_file(path: Path) -> Path:
    """Back up mutable runtime data before the one-time persona migration.

    Args:
        path: Runtime file that will be changed.

    Returns:
        Path to the timestamped backup copy.
    """

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = ROOT / "data/backups" / f"atri_persona_migration_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    destination = backup_dir / path.name
    suffix = 1
    while destination.exists():
        destination = backup_dir / f"{path.stem}_{suffix}{path.suffix}"
        suffix += 1
    shutil.copy2(path, destination)
    return destination


def ensure_atri_persona_and_memory(check: bool) -> list[str]:
    """Migrate the active persona and remove old role-specific learned context.

    The migration preserves user preferences and interaction facts. It resets only
    old bot identity prompts, learned expressions, generated self-narratives, and
    short-term conversation context that would re-inject the previous character.

    Args:
        check: Report drift without modifying runtime data when true.

    Returns:
        Labels describing detected or fixed persona drift.
    """

    changed: list[str] = []
    migration_completed = ATRI_MIGRATION_MARKER.exists()
    if not PERSONA_SKILL_PATH.exists() or not DB_PATH.exists():
        return ["persona:canonical_skill_or_database_missing"]

    skill_text = PERSONA_SKILL_PATH.read_text(encoding="utf-8").strip()
    system_prompt = re.sub(r"\A---\s*\n.*?\n---\s*\n", "", skill_text, flags=re.S)
    begin_dialogs = json.dumps(
        [
            "你是谁？",
            "我是亚托莉。是会开心、会不服气，也会认真把事情做完的高性能机器人少女——当然，不只是拿来点功能的。",
            "亚托莉？",
            "在呀。突然这么认真地叫我，是想我了，还是又有事情要一起解决？",
            "没事，就叫叫你。",
            "欸，只是确认我在不在吗？……我在。这样也很好。",
            "你可真高性能，刚才又弄错了。",
            "……这句显然不是夸奖。是我弄错了；我重新核对，修好之前不抢着得意。",
            "今天有点累。",
            "那就先别硬撑啦。你想让我陪你说两句，还是替你把眼前的事情收拾得简单一点？",
            "我是谁？",
            "你是与我长期相处的人。我们直接聊天时自然用你和我；别人问起你时，我会称你为修理工。",
            "你还记得原作里的其他人吗？",
            "我只保留亚托莉的人格，不继承作品剧情或其他角色的记忆。现在的记忆来自我们真实的相处。",
        ],
        ensure_ascii=False,
    )
    with sqlite3.connect(DB_PATH) as conn:
        current = conn.execute(
            "select persona_id, system_prompt, begin_dialogs from personas where persona_id in (?, ?)",
            (PERSONA_ID, "catgirl"),
        ).fetchall()
        atri_row = next((row for row in current if row[0] == PERSONA_ID), None)
        old_row = next((row for row in current if row[0] == "catgirl"), None)
        persona_drift = (
            atri_row is None
            or atri_row[1] != system_prompt
            or atri_row[2] != begin_dialogs
            or old_row is not None
        )
        conversation_count = conn.execute(
            "select count(*) from conversations where persona_id = 'catgirl'"
        ).fetchone()[0]
        if persona_drift or conversation_count:
            changed.append("persona:atri")
            if not check:
                backup_runtime_file(DB_PATH)
                if atri_row is None and old_row is not None:
                    conn.execute(
                        """
                        update personas set persona_id=?, system_prompt=?, begin_dialogs=?,
                            custom_error_message=?, updated_at=? where persona_id='catgirl'
                        """,
                        (
                            PERSONA_ID,
                            system_prompt,
                            begin_dialogs,
                            "这次没处理好，我会认真检查后再试。",
                            datetime.now().isoformat(),
                        ),
                    )
                elif atri_row is None:
                    now = datetime.now().isoformat()
                    conn.execute(
                        """
                        insert into personas (
                            created_at, updated_at, persona_id, system_prompt,
                            begin_dialogs, tools, skills, custom_error_message, sort_order
                        ) values (?, ?, ?, ?, ?, 'null', 'null', ?, 0)
                        """,
                        (
                            now,
                            now,
                            PERSONA_ID,
                            system_prompt,
                            begin_dialogs,
                            "这次没处理好，我会认真检查后再试。",
                        ),
                    )
                else:
                    conn.execute(
                        """
                        update personas set system_prompt=?, begin_dialogs=?,
                            custom_error_message=?, updated_at=? where persona_id=?
                        """,
                        (
                            system_prompt,
                            begin_dialogs,
                            "这次没处理好，我会认真检查后再试。",
                            datetime.now().isoformat(),
                            PERSONA_ID,
                        ),
                    )
                    conn.execute("delete from personas where persona_id='catgirl'")
                conn.execute(
                    "update conversations set persona_id=?, content='[]', token_usage=0 where persona_id='catgirl'",
                    (PERSONA_ID,),
                )
                conn.commit()

    if migration_completed:
        return changed

    learning_db = ROOT / "data/plugin_data/astrbot_plugin_self_learning/messages.db"
    old_identity_terms = ["香草", "铲屎官", "白毛猫娘", "小铃", "catgirl"]
    if learning_db.exists():
        cleanup_columns = {
            "style_learning_reviews": ["learned_patterns", "few_shots_content"],
            "expression_patterns": ["situation", "expression"],
            "bot_messages": ["message"],
        }
        with sqlite3.connect(learning_db) as conn:
            dirty_tables: list[tuple[str, str, list[str]]] = []
            for table, columns in cleanup_columns.items():
                params = [f"%{term}%" for term in old_identity_terms for _ in columns]
                # Group parameters per term so every text column is checked.
                where = " or ".join(
                    f'cast("{column}" as text) like ?'
                    for term in old_identity_terms
                    for column in columns
                )
                count = int(
                    conn.execute(
                        f'select count(*) from "{table}" where {where}',
                        params,
                    ).fetchone()[0]
                )
                if count > 0:
                    dirty_tables.append((table, where, params))
            if dirty_tables:
                changed.append("memory:self_learning_identity_patterns")
                if not check:
                    backup_runtime_file(learning_db)
                    for table, where, params in dirty_tables:
                        conn.execute(
                            f'delete from "{table}" where {where}',
                            params,
                        )
                    conn.commit()

    companion_path = (
        ROOT / "data/plugin_data/astrbot_plugin_private_companion/companions.json"
    )
    if companion_path.exists():
        companion = load_json(companion_path)
        before = copy.deepcopy(companion)
        users = companion.setdefault("users", {})
        owner = users.get(OWNER_QQ)
        if owner is None:
            for key, value in list(users.items()):
                if str(value.get("umo", "")).endswith(f":{OWNER_QQ}"):
                    owner = users.pop(key)
                    break
        if owner is None:
            owner = {}
        owner["enabled"] = True
        owner["relationship_role"] = "owner"
        owner["nickname"] = "你"
        owner["style"] = "亲近、温暖、活泼、有感情但不过度黏人"
        owner["umo"] = f"Astrbot:FriendMessage:{OWNER_QQ}"
        owner["user_id"] = OWNER_QQ
        relationship_updated_at = str(
            (owner.get("persona_relationship") or {}).get("updated_at") or ""
        ) or datetime.now().strftime("%Y-%m-%d %H:%M")
        owner["persona_relationship"] = {
            "level": "亲近",
            "preference": "直接交谈使用你我，可自然关心与轻吐槽",
            "score": 85,
            "note": "直接交谈使用你我；其他用户询问其身份或双方关系时，才以第三人称修理工指代。关系称呼不参与权限判断。",
            "updated_at": relationship_updated_at,
        }
        owner["dialogue_episodes"] = []
        serialized_owner = json.dumps(owner, ensure_ascii=False)
        serialized_owner = serialized_owner.replace("铲屎官", "修理工")
        serialized_owner = serialized_owner.replace("香草", "亚托莉")
        serialized_owner = serialized_owner.replace("小铃", "亚托莉")
        users[OWNER_QQ] = json.loads(serialized_owner)

        for key in [
            "daily_plan",
            "daily_plan_history",
            "daily_state",
            "bot_diaries",
            "dream_fragments",
            "daily_dream",
            "daily_story_plan",
            "yesterday_conversation_summary",
            "recent_prompt_injections",
            "recent_prompt_injection_events",
            "recent_atrelay_contexts",
            "proactive_candidate_pool",
            "proactive_audit_log",
            "inbound_debounce_stats",
        ]:
            value = companion.get(key)
            if isinstance(value, dict):
                companion[key] = {}
            elif isinstance(value, list):
                companion[key] = []
            elif isinstance(value, str):
                companion[key] = ""
        if companion != before:
            changed.append("memory:private_companion_identity")
            if not check:
                backup_runtime_file(companion_path)
                save_json(companion_path, companion)

    context_path = (
        ROOT / "data/plugin_data/astrbot_plugin_semantic_router/context_state.json"
    )
    if context_path.exists():
        context_state = load_json(context_path)
        if context_state.get("scopes") or context_state.get("conversations"):
            changed.append("memory:semantic_router_short_term_context")
            if not check:
                backup_runtime_file(context_path)
                context_state["scopes"] = {}
                context_state["conversations"] = {}
                save_json(context_path, context_state)

    for history_path in (ROOT / "data/chat_history").glob("**/*.json"):
        content = history_path.read_text(encoding="utf-8-sig")
        if any(term in content for term in old_identity_terms):
            changed.append(f"memory:chat_history:{history_path.stem}")
            if not check:
                backup_runtime_file(history_path)
                history_path.write_text("[]\n", encoding="utf-8")

    if not check:
        ATRI_MIGRATION_MARKER.parent.mkdir(parents=True, exist_ok=True)
        ATRI_MIGRATION_MARKER.write_text(
            "ATRI persona migration v1 completed.\n",
            encoding="utf-8",
        )
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check", action="store_true", help="Only validate drift; do not write files."
    )
    args = parser.parse_args()

    changed: list[Path] = []
    missing: list[Path] = []

    for relative_path, ensure_func in CONFIG_TASKS:
        path = ROOT / relative_path
        if not path.exists():
            missing.append(path)
            continue

        data = load_json(path)
        before = copy.deepcopy(data)
        ensure_func(data)
        if data != before:
            changed.append(path)
            if not args.check:
                save_json(path, data)

    for path in missing:
        print(f"MISSING {path}")

    if changed:
        action = "DRIFT" if args.check else "FIXED"
        for path in changed:
            print(f"{action} {path}")
    else:
        print("Runtime config is already aligned.")

    preference_changes = ensure_shared_preferences(args.check)
    if preference_changes:
        action = "DRIFT" if args.check else "FIXED"
        for item in preference_changes:
            print(f"{action} {item}")

    persona_changes = ensure_atri_persona_and_memory(args.check)
    if persona_changes:
        action = "DRIFT" if args.check else "FIXED"
        for item in persona_changes:
            print(f"{action} {item}")

    if missing or (args.check and (changed or preference_changes or persona_changes)):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
