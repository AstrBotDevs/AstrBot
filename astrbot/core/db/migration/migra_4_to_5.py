from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from astrbot.api import logger, sp
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.config.node_config import AstrBotNodeConfig
from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import Preference
from astrbot.core.pipeline.engine.chain_config import (
    ChainConfigModel,
    normalize_chain_nodes,
    serialize_chain_nodes,
)
from astrbot.core.umop_config_router import UmopConfigRouter

_MIGRATION_FLAG = "migration_done_v5"

_SESSION_RULE_KEYS = {
    "session_service_config",
    "session_plugin_config",
    "kb_config",
    "provider_perf_chat_completion",
    "provider_perf_text_to_speech",
    "provider_perf_speech_to_text",
}


def _normalize_umop_pattern(pattern: str) -> str | None:
    parts = [p.strip() for p in str(pattern).split(":")]
    if len(parts) != 3:
        return None
    normalized = [p if p != "" else "*" for p in parts]
    return ":".join(normalized)


def _build_umo_rule(pattern: str) -> dict:
    return {
        "type": "condition",
        "condition": {
            "type": "umo",
            "operator": "include",
            "value": pattern,
        },
    }


def _merge_excludes(rule: dict | None, disabled_umos: list[str]) -> dict | None:
    if not disabled_umos:
        return rule
    excludes = [
        {
            "type": "condition",
            "condition": {
                "type": "umo",
                "operator": "exclude",
                "value": umo,
            },
        }
        for umo in disabled_umos
    ]
    if rule is None:
        return {"type": "and", "children": excludes}
    return {"type": "and", "children": [rule, *excludes]}


def _build_plugin_filter(plugin_cfg: dict | None) -> dict | None:
    if not isinstance(plugin_cfg, dict):
        return None
    enabled = plugin_cfg.get("enabled_plugins") or []
    disabled = plugin_cfg.get("disabled_plugins") or []
    if disabled:
        return {"mode": "blacklist", "plugins": list(disabled)}
    if enabled:
        return {"mode": "whitelist", "plugins": list(enabled)}
    return None


def _build_nodes_for_config(conf: dict) -> list[str]:
    nodes: list[str] = ["stt"]

    file_extract_cfg = conf.get("provider_settings", {}).get("file_extract", {}) or {}
    if file_extract_cfg.get("enable", False):
        nodes.append("file_extract")

    if not conf.get("kb_agentic_mode", False):
        nodes.append("knowledge_base")

    nodes.extend(["agent", "tts", "t2i"])
    return nodes


def _apply_node_defaults(chain_id: str, nodes: list, conf: dict) -> None:
    node_map = {node.name: node.uuid for node in nodes if node.name}

    if "t2i" in node_map:
        t2i_conf = {
            "word_threshold": conf.get("t2i_word_threshold", 150),
            "strategy": conf.get("t2i_strategy", "remote"),
            "active_template": conf.get("t2i_active_template", ""),
            "use_file_service": conf.get("t2i_use_file_service", False),
        }
        AstrBotNodeConfig.get_cached(
            node_name="t2i",
            chain_id=chain_id,
            node_uuid=node_map["t2i"],
        ).save_config(t2i_conf)

    if "tts" in node_map:
        tts_settings = conf.get("provider_tts_settings", {}) or {}
        tts_conf = {
            "trigger_probability": tts_settings.get("trigger_probability", 1.0),
            "use_file_service": tts_settings.get("use_file_service", False),
            "dual_output": tts_settings.get("dual_output", False),
        }
        AstrBotNodeConfig.get_cached(
            node_name="tts",
            chain_id=chain_id,
            node_uuid=node_map["tts"],
        ).save_config(tts_conf)

    if "file_extract" in node_map:
        file_extract_cfg = (
            conf.get("provider_settings", {}).get("file_extract", {}) or {}
        )
        file_extract_conf = {
            "provider": file_extract_cfg.get("provider", "moonshotai"),
            "moonshotai_api_key": file_extract_cfg.get("moonshotai_api_key", ""),
        }
        AstrBotNodeConfig.get_cached(
            node_name="file_extract",
            chain_id=chain_id,
            node_uuid=node_map["file_extract"],
        ).save_config(file_extract_conf)


async def migrate_4_to_5(
    db_helper: BaseDatabase,
    acm: AstrBotConfigManager,
    ucr: UmopConfigRouter,
) -> None:
    """Migrate UMOP/session-manager rules to chain configs."""
    if await sp.global_get(_MIGRATION_FLAG, False):
        return

    try:
        await ucr.initialize()
    except Exception as e:
        logger.warning(f"Failed to initialize UmopConfigRouter: {e!s}")

    # Skip if chain configs already exist.
    async with db_helper.get_db() as session:
        session: AsyncSession
        result = await session.execute(select(ChainConfigModel))
        existing = list(result.scalars().all())
        if existing:
            logger.info(
                "Chain configs already exist, skip 4->5 migration to avoid conflicts."
            )
            await sp.global_put(_MIGRATION_FLAG, True)
            return

    # Load session-level rules from preferences.
    async with db_helper.get_db() as session:
        session: AsyncSession
        result = await session.execute(
            select(Preference).where(
                col(Preference.scope) == "umo",
                col(Preference.key).in_(_SESSION_RULE_KEYS),
            )
        )
        prefs = list(result.scalars().all())

    rules_map: dict[str, dict[str, Any]] = {}
    for pref in prefs:
        umo = pref.scope_id
        rules_map.setdefault(umo, {})
        if isinstance(pref.value, dict):
            value = pref.value.get("val")
        else:
            value = pref.value
        if pref.key == "session_plugin_config":
            if isinstance(value, dict):
                if isinstance(value.get(umo), dict):
                    rules_map[umo][pref.key] = value.get(umo)
                elif "enabled_plugins" in value or "disabled_plugins" in value:
                    rules_map[umo][pref.key] = value
        else:
            rules_map[umo][pref.key] = value

    disabled_umos: list[str] = []
    session_chains: list[ChainConfigModel] = []
    umop_chains: list[ChainConfigModel] = []
    node_defaults: list[tuple[str, list, dict]] = []

    def get_conf(conf_id: str | None) -> dict:
        if conf_id and conf_id in acm.confs:
            return acm.confs[conf_id]
        return acm.confs["default"]

    # Build chains for session-specific rules.
    for umo, rules in rules_map.items():
        service_cfg = rules.get("session_service_config") or {}
        if (
            isinstance(service_cfg, dict)
            and service_cfg.get("session_enabled") is False
        ):
            disabled_umos.append(umo)
            continue

        llm_enabled = None
        if isinstance(service_cfg, dict) and "llm_enabled" in service_cfg:
            llm_enabled = service_cfg.get("llm_enabled")

        plugin_filter = _build_plugin_filter(rules.get("session_plugin_config"))
        kb_config = rules.get("kb_config")
        if not isinstance(kb_config, dict):
            kb_config = None

        needs_chain = False
        if llm_enabled is not None:
            needs_chain = True
        if plugin_filter:
            needs_chain = True
        if kb_config is not None:
            needs_chain = True

        if not needs_chain:
            continue

        conf_id = None
        try:
            conf_id = ucr.get_conf_id_for_umop(umo)
        except Exception:
            conf_id = None
        if conf_id not in acm.confs:
            conf_id = "default"

        conf = get_conf(conf_id)
        chain_id = str(uuid.uuid4())
        nodes_list = _build_nodes_for_config(conf)
        normalized_nodes = normalize_chain_nodes(nodes_list, chain_id)
        nodes_payload = serialize_chain_nodes(normalized_nodes)

        chain = ChainConfigModel(
            chain_id=chain_id,
            match_rule=_build_umo_rule(umo),
            sort_order=0,
            enabled=True,
            nodes=nodes_payload,
            llm_enabled=bool(llm_enabled) if llm_enabled is not None else True,
            chat_provider_id=None,
            tts_provider_id=None,
            stt_provider_id=None,
            plugin_filter=plugin_filter,
            kb_config=kb_config,
            config_id=conf_id,
        )
        session_chains.append(chain)
        node_defaults.append((chain_id, normalized_nodes, conf))

    # Build chains for UMOP routing.
    for pattern, conf_id in (ucr.umop_to_conf_id or {}).items():
        norm = _normalize_umop_pattern(pattern)
        if not norm:
            continue

        if conf_id not in acm.confs:
            conf_id = "default"

        conf = get_conf(conf_id)
        chain_id = str(uuid.uuid4())
        nodes_list = _build_nodes_for_config(conf)
        normalized_nodes = normalize_chain_nodes(nodes_list, chain_id)
        nodes_payload = serialize_chain_nodes(normalized_nodes)

        chain = ChainConfigModel(
            chain_id=chain_id,
            match_rule=_build_umo_rule(norm),
            sort_order=0,
            enabled=True,
            nodes=nodes_payload,
            llm_enabled=True,
            chat_provider_id=None,
            tts_provider_id=None,
            stt_provider_id=None,
            plugin_filter=None,
            kb_config=None,
            config_id=conf_id,
        )
        umop_chains.append(chain)
        node_defaults.append((chain_id, normalized_nodes, conf))

    # Always create a default chain for legacy behavior.
    default_conf = get_conf("default")
    default_nodes_list = _build_nodes_for_config(default_conf)
    default_nodes = normalize_chain_nodes(default_nodes_list, "default")
    default_nodes_payload = serialize_chain_nodes(default_nodes)
    default_rule = _merge_excludes(None, disabled_umos)
    default_chain = ChainConfigModel(
        chain_id="default",
        match_rule=default_rule,
        sort_order=-1,
        enabled=True,
        nodes=default_nodes_payload,
        llm_enabled=True,
        chat_provider_id=None,
        tts_provider_id=None,
        stt_provider_id=None,
        plugin_filter=None,
        kb_config=None,
        config_id="default",
    )
    node_defaults.append(("default", default_nodes, default_conf))

    # Apply disabled session exclusions.
    if disabled_umos:
        for chain in session_chains + umop_chains:
            chain.match_rule = _merge_excludes(chain.match_rule, disabled_umos)

    # Assign sort_order (higher value -> higher priority)
    ordered_chains = [*session_chains, *umop_chains]
    total = len(ordered_chains)
    for idx, chain in enumerate(ordered_chains):
        chain.sort_order = total - 1 - idx

    async with db_helper.get_db() as session:
        session: AsyncSession
        session.add_all([*ordered_chains, default_chain])
        await session.commit()

    # Apply node config defaults from legacy config.
    for chain_id, nodes, conf in node_defaults:
        try:
            _apply_node_defaults(chain_id, nodes, conf)
        except Exception as e:
            logger.warning(f"Failed to apply node defaults for chain {chain_id}: {e!s}")

    await sp.global_put(_MIGRATION_FLAG, True)
    logger.info("Migration from v4 to v5 completed successfully.")
