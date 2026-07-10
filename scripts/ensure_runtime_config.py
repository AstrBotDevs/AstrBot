from __future__ import annotations

import argparse
import copy
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OWNER_QQ = "2831304142"
DEFAULT_PROVIDER = "google_gemini/gemini-2.5-flash"
FALLBACK_PROVIDER = "deepseek/deepseek-v4-pro"
PERSONA_ID = "catgirl"
DB_PATH = ROOT / "data/data_v4.db"
DISABLED_PLUGIN_MODULES = [
    "data.plugins.astrbot_plugin_livingmemory.main",
    "data.plugins.astrbot_plugin_bilibili.main",
]
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
    provider_settings = data.setdefault("provider_settings", {})
    set_many(
        provider_settings,
        {
            "default_provider_id": DEFAULT_PROVIDER,
            "fallback_chat_models": [FALLBACK_PROVIDER],
            "default_personality": PERSONA_ID,
            "web_search": False,
            "websearch_provider": "tavily",
            "web_search_link": False,
            "request_max_retries": 2,
        },
    )
    data["log_file_enable"] = True
    data["trace_log_enable"] = False

    ltm = data.setdefault("provider_ltm_settings", {})
    ltm["active_reply"] = {
        "enable": False,
        "method": "possibility_reply",
        "possibility_reply": 0.1,
        "whitelist": [],
    }
    ltm["image_caption"] = False
    provider_settings["default_image_caption_provider_id"] = FALLBACK_PROVIDER

    for source in data.get("provider_sources", []) or []:
        source_id = str(source.get("id", ""))
        provider_name = str(source.get("provider", ""))
        if source_id.startswith("google_gemini") or provider_name == "google":
            source["enable"] = True
            source["proxy"] = "http://127.0.0.1:7897"
            source["gm_resp_image_modal"] = False
        elif source_id == "deepseek" or provider_name == "deepseek":
            source["enable"] = True

    for provider in data.get("provider", []) or []:
        provider_id = str(provider.get("id", ""))
        if provider_id.startswith("google_gemini/"):
            provider["enable"] = provider_id == DEFAULT_PROVIDER
        elif provider_id in {DEFAULT_PROVIDER, FALLBACK_PROVIDER}:
            provider["enable"] = True


def ensure_spectrecore(data: dict[str, Any]) -> None:
    data["use_func_tool"] = True
    data["read_air"] = False
    data["enable_all_groups"] = True
    data["enabled_private"] = True

    freq = data.setdefault("model_frequency", {})
    freq["method"] = "\u6982\u7387\u56de\u590d"
    freq.setdefault("probability", {})["probability"] = 0.3
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
    admin_only_tools = list(permission.get("admin_only_tools", []))
    ensure_list_item(admin_only_tools, "browser_*")
    permission["admin_only_tools"] = admin_only_tools

    allow_users = {str(user) for user in permission.get("tool_allow_users", [])}
    allow_users.add(OWNER_QQ)
    permission["tool_allow_users"] = sorted(allow_users)
    permission["llm_ignore_permission_check"] = False
    permission["allow_group_admin"] = False


def ensure_angel_heart(data: dict[str, Any]) -> None:
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
            "force_reply_when_summoned": False,
            "reply_even_not_questioned": False,
        },
    )


def ensure_self_evolution(data: dict[str, Any]) -> None:
    data.setdefault("base", {})["persona_name"] = PERSONA_ID
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
            "enable_jargon_learning": False,
            "enable_style_learning": False,
            "enable_realtime_learning": False,
            "enable_realtime_llm_filter": False,
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
    data["enable_parse_miniapp"] = False
    data["enable_parse_BV"] = False
    data["enable_ai_summary"] = False
    data["interval_secs"] = max(int(data.get("interval_secs", 300) or 300), 3600)


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
    basic["plugin_specific_persona_id"] = PERSONA_ID
    basic["target_user_ids"] = [OWNER_QQ]

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
    pipeline["steps"] = ["mention(\u63d0\u53ca\u5524\u9192)"]
    pipeline["whitelist_steps"] = []
    pipeline["blacklist_steps"] = []

    mention = data.setdefault("mention", {})
    mention["disable_reply_wake"] = False
    mention["names"] = ["\u5c0f\u52a9\u624b", "\u673a\u5668\u4eba", "bot"]

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
    ("data/config/astrbot_plugin_angel_heart_config.json", ensure_angel_heart),
    ("data/config/astrbot_plugin_self_evolution_config.json", ensure_self_evolution),
    ("data/config/astrbot_plugin_self_learning_config.json", ensure_self_learning),
    ("data/config/astrbot_plugin_livingmemory_config.json", ensure_livingmemory),
    ("data/config/astrbot_plugin_bilibili_config.json", ensure_bilibili),
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

    if missing or (args.check and (changed or preference_changes)):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
