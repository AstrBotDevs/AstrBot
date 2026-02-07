from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from astrbot.api import logger, sp
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.config.node_config import AstrBotNodeConfig
from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import Preference
from astrbot.core.pipeline.agent.runner_config import (
    AGENT_RUNNER_PROVIDER_KEY,
    normalize_agent_runner_type,
)
from astrbot.core.pipeline.engine.chain_config import (
    ChainConfigModel,
    normalize_chain_nodes,
    serialize_chain_nodes,
)
from astrbot.core.pipeline.engine.chain_runtime_flags import (
    FEATURE_LLM,
    FEATURE_STT,
    FEATURE_T2I,
    FEATURE_TTS,
)
from astrbot.core.umop_config_router import UmopConfigRouter

_MIGRATION_FLAG = "migration_done_v5"
_MIGRATION_PROVIDER_CLEANUP_FLAG = "migration_done_v5_provider_cleanup"

_SESSION_RULE_KEYS = {
    "session_service_config",
    "session_plugin_config",
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


def _read_legacy_enabled(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    return bool(value)


def _has_kb_binding(conf: dict) -> bool:
    kb_names = conf.get("kb_names")
    if isinstance(kb_names, list):
        for kb_name in kb_names:
            if str(kb_name or "").strip():
                return True

    default_kb_collection = str(conf.get("default_kb_collection", "") or "").strip()
    return bool(default_kb_collection)


def _build_nodes_for_config(conf: dict) -> list[str]:
    provider_settings = conf.get("provider_settings", {}) or {}
    file_extract_cfg = provider_settings.get("file_extract", {}) or {}
    stt_settings = conf.get("provider_stt_settings", {}) or {}
    tts_settings = conf.get("provider_tts_settings", {}) or {}

    nodes: list[str] = []

    if _read_legacy_enabled(stt_settings.get("enable"), False):
        nodes.append("stt")

    if _read_legacy_enabled(file_extract_cfg.get("enable"), False):
        nodes.append("file_extract")

    if not _read_legacy_enabled(conf.get("kb_agentic_mode"), False) and _has_kb_binding(
        conf
    ):
        nodes.append("knowledge_base")

    nodes.append("agent")

    if _read_legacy_enabled(tts_settings.get("enable"), False):
        nodes.append("tts")

    if _read_legacy_enabled(conf.get("t2i"), False):
        nodes.append("t2i")

    return nodes


def _build_chain_runtime_flags_for_config(conf: dict) -> dict[str, bool]:
    provider_settings = conf.get("provider_settings", {}) or {}
    stt_settings = conf.get("provider_stt_settings", {}) or {}
    tts_settings = conf.get("provider_tts_settings", {}) or {}

    return {
        FEATURE_LLM: _read_legacy_enabled(provider_settings.get("enable"), True),
        FEATURE_STT: _read_legacy_enabled(stt_settings.get("enable"), False),
        FEATURE_TTS: _read_legacy_enabled(tts_settings.get("enable"), False),
        FEATURE_T2I: _read_legacy_enabled(conf.get("t2i"), False),
    }


async def _apply_chain_runtime_flags(
    chain_runtime_flags: list[tuple[str, dict[str, bool]]],
) -> None:
    if not chain_runtime_flags:
        return

    raw = await sp.global_get("chain_runtime_flags", {})
    all_flags = raw if isinstance(raw, dict) else {}

    for chain_id, flags in chain_runtime_flags:
        existing_flags = all_flags.get(chain_id)
        merged_flags = existing_flags if isinstance(existing_flags, dict) else {}
        merged_flags.update(
            {
                FEATURE_LLM: bool(flags.get(FEATURE_LLM, True)),
                FEATURE_STT: bool(flags.get(FEATURE_STT, False)),
                FEATURE_TTS: bool(flags.get(FEATURE_TTS, False)),
                FEATURE_T2I: bool(flags.get(FEATURE_T2I, False)),
            }
        )
        all_flags[chain_id] = merged_flags

    await sp.global_put("chain_runtime_flags", all_flags)


def _infer_legacy_agent_runner_from_default_provider(
    conf: dict,
) -> tuple[str, str] | None:
    provider_settings = conf.get("provider_settings", {}) or {}
    default_provider_id = str(
        provider_settings.get("default_provider_id", "") or ""
    ).strip()
    if not default_provider_id:
        return None

    for provider in conf.get("provider", []) or []:
        if provider.get("id") != default_provider_id:
            continue
        provider_type = str(provider.get("type") or "").strip().lower()
        if provider_type in AGENT_RUNNER_PROVIDER_KEY:
            return provider_type, default_provider_id
        return None

    return None


def _resolve_legacy_agent_node_config(conf: dict) -> dict:
    provider_settings = conf.get("provider_settings", {}) or {}

    runner_type = normalize_agent_runner_type(
        provider_settings.get("agent_runner_type")
    )
    provider_key = AGENT_RUNNER_PROVIDER_KEY.get(runner_type, "")
    provider_id = str(provider_settings.get(provider_key, "") or "").strip()

    if runner_type in AGENT_RUNNER_PROVIDER_KEY and not provider_id:
        inferred = _infer_legacy_agent_runner_from_default_provider(conf)
        if inferred is not None:
            runner_type, provider_id = inferred

    node_conf: dict[str, object] = {
        "agent_runner_type": runner_type,
        "provider_id": str(
            provider_settings.get("default_provider_id", "") or ""
        ).strip(),
    }
    for key in AGENT_RUNNER_PROVIDER_KEY.values():
        node_conf[key] = ""
    if runner_type in AGENT_RUNNER_PROVIDER_KEY:
        node_conf[AGENT_RUNNER_PROVIDER_KEY[runner_type]] = provider_id

    return node_conf


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
            schema={},
        ).save_config(t2i_conf)

    if "stt" in node_map:
        stt_settings = conf.get("provider_stt_settings", {}) or {}
        stt_conf = {
            "provider_id": str(stt_settings.get("provider_id", "") or "").strip(),
        }
        AstrBotNodeConfig.get_cached(
            node_name="stt",
            chain_id=chain_id,
            node_uuid=node_map["stt"],
            schema={},
        ).save_config(stt_conf)

    if "tts" in node_map:
        tts_settings = conf.get("provider_tts_settings", {}) or {}
        tts_conf = {
            "trigger_probability": tts_settings.get("trigger_probability", 1.0),
            "use_file_service": tts_settings.get("use_file_service", False),
            "dual_output": tts_settings.get("dual_output", False),
            "provider_id": str(tts_settings.get("provider_id", "") or "").strip(),
        }
        AstrBotNodeConfig.get_cached(
            node_name="tts",
            chain_id=chain_id,
            node_uuid=node_map["tts"],
            schema={},
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
            schema={},
        ).save_config(file_extract_conf)

    if "agent" in node_map:
        agent_conf = _resolve_legacy_agent_node_config(conf)
        AstrBotNodeConfig.get_cached(
            node_name="agent",
            chain_id=chain_id,
            node_uuid=node_map["agent"],
            schema={},
        ).save_config(agent_conf)


async def migrate_4_to_5(
    db_helper: BaseDatabase,
    acm: AstrBotConfigManager,
    ucr: UmopConfigRouter,
) -> None:
    """Migrate UMOP/session-manager rules to chain configs."""
    if await sp.global_get(_MIGRATION_FLAG, False):
        await _run_provider_cleanup_for_v5(db_helper, acm)
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
            await _run_provider_cleanup_for_v5(db_helper, acm)
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
    runtime_flag_defaults: list[tuple[str, dict[str, bool]]] = []

    def get_config(config_id: str | None) -> dict:
        if config_id and config_id in acm.confs:
            return acm.confs[config_id]
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

        plugin_filter = _build_plugin_filter(rules.get("session_plugin_config"))
        needs_chain = bool(plugin_filter)

        if not needs_chain:
            continue

        config_id = None
        try:
            config_id = ucr.get_config_id_for_umop(umo)
        except Exception:
            config_id = None
        if config_id not in acm.confs:
            config_id = "default"

        conf = get_config(config_id)
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
            plugin_filter=plugin_filter,
            config_id=config_id,
        )
        session_chains.append(chain)
        node_defaults.append((chain_id, normalized_nodes, conf))
        runtime_flag_defaults.append(
            (chain_id, _build_chain_runtime_flags_for_config(conf))
        )

    # Build chains for UMOP routing.
    for pattern, config_id in (ucr.umop_to_config_id or {}).items():
        norm = _normalize_umop_pattern(pattern)
        if not norm:
            continue

        if config_id not in acm.confs:
            config_id = "default"

        conf = get_config(config_id)
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
            plugin_filter=None,
            config_id=config_id,
        )
        umop_chains.append(chain)
        node_defaults.append((chain_id, normalized_nodes, conf))
        runtime_flag_defaults.append(
            (chain_id, _build_chain_runtime_flags_for_config(conf))
        )

    # Always create a default chain for legacy behavior.
    default_conf = get_config("default")
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
        plugin_filter=None,
        config_id="default",
    )
    node_defaults.append(("default", default_nodes, default_conf))
    runtime_flag_defaults.append(
        ("default", _build_chain_runtime_flags_for_config(default_conf))
    )

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

    try:
        await _apply_chain_runtime_flags(runtime_flag_defaults)
    except Exception as e:
        logger.warning(
            f"Failed to apply chain runtime flags during 4->5 migration: {e!s}"
        )

    await sp.global_put(_MIGRATION_FLAG, True)
    logger.info("Migration from v4 to v5 completed successfully.")
    await _run_provider_cleanup_for_v5(db_helper, acm)


def _read_provider_id(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


async def _migrate_chain_provider_columns_to_node_config(
    db_helper: BaseDatabase,
) -> None:
    table = ChainConfigModel.__tablename__

    async with db_helper.get_db() as session:
        cols = await session.execute(text(f"PRAGMA table_info({table})"))
        names = {row[1] for row in cols.fetchall()}
        has_tts = "tts_provider_id" in names
        has_stt = "stt_provider_id" in names
        if not has_tts and not has_stt:
            return

        select_cols = ["chain_id", "nodes"]
        if has_tts:
            select_cols.append("tts_provider_id")
        if has_stt:
            select_cols.append("stt_provider_id")
        rows = (
            await session.execute(text(f"SELECT {', '.join(select_cols)} FROM {table}"))
        ).fetchall()

    for row in rows:
        chain_id = row[0]
        raw_nodes = row[1]
        offset = 2
        tts_provider_id = _read_provider_id(row[offset]) if has_tts else ""
        if has_tts:
            offset += 1
        stt_provider_id = _read_provider_id(row[offset]) if has_stt else ""

        if isinstance(raw_nodes, str):
            try:
                raw_nodes = json.loads(raw_nodes)
            except Exception:
                raw_nodes = []

        nodes = normalize_chain_nodes(raw_nodes, chain_id)
        for node in nodes:
            if node.name == "tts" and tts_provider_id:
                cfg = AstrBotNodeConfig.get_cached(
                    node_name="tts",
                    chain_id=chain_id,
                    node_uuid=node.uuid,
                    schema={},
                )
                if not cfg.get("provider_id"):
                    cfg.save_config({"provider_id": tts_provider_id})
            if node.name == "stt" and stt_provider_id:
                cfg = AstrBotNodeConfig.get_cached(
                    node_name="stt",
                    chain_id=chain_id,
                    node_uuid=node.uuid,
                    schema={},
                )
                if not cfg.get("provider_id"):
                    cfg.save_config({"provider_id": stt_provider_id})


async def _drop_chain_provider_columns(db_helper: BaseDatabase) -> None:
    table = ChainConfigModel.__tablename__

    async with db_helper.get_db() as session:
        cols = await session.execute(text(f"PRAGMA table_info({table})"))
        names = {row[1] for row in cols.fetchall()}
        has_tts = "tts_provider_id" in names
        has_stt = "stt_provider_id" in names
        if not has_tts and not has_stt:
            return

        try:
            if has_tts:
                await session.execute(
                    text(f"ALTER TABLE {table} DROP COLUMN tts_provider_id")
                )
            if has_stt:
                await session.execute(
                    text(f"ALTER TABLE {table} DROP COLUMN stt_provider_id")
                )
            await session.commit()
            return
        except Exception:
            await session.rollback()

        old_table = f"{table}_old_v5_cleanup"
        await session.execute(text(f"ALTER TABLE {table} RENAME TO {old_table}"))
        await session.execute(
            text(
                f"""
                CREATE TABLE {table} (
                    id INTEGER NOT NULL PRIMARY KEY,
                    chain_id VARCHAR(36) NOT NULL UNIQUE,
                    match_rule JSON,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    nodes JSON,
                    plugin_filter JSON,
                    config_id VARCHAR(36),
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
        )
        await session.execute(
            text(
                f"""
                INSERT INTO {table} (
                    id,
                    chain_id,
                    match_rule,
                    sort_order,
                    enabled,
                    nodes,
                    plugin_filter,
                    config_id,
                    created_at,
                    updated_at
                )
                SELECT
                    id,
                    chain_id,
                    match_rule,
                    sort_order,
                    enabled,
                    nodes,
                    plugin_filter,
                    config_id,
                    created_at,
                    updated_at
                FROM {old_table}
                """
            )
        )
        await session.execute(text(f"DROP TABLE {old_table}"))
        await session.commit()


def _cleanup_legacy_provider_config_keys(acm: AstrBotConfigManager) -> None:
    for conf in acm.confs.values():
        changed = False
        if "provider_tts_settings" in conf:
            conf.pop("provider_tts_settings", None)
            changed = True
        if "provider_stt_settings" in conf:
            conf.pop("provider_stt_settings", None)
            changed = True

        provider_settings = conf.get("provider_settings")
        if isinstance(provider_settings, dict):
            for legacy_key in (
                "enable",
                "agent_runner_type",
                "dify_agent_runner_provider_id",
                "coze_agent_runner_provider_id",
                "dashscope_agent_runner_provider_id",
            ):
                if legacy_key in provider_settings:
                    provider_settings.pop(legacy_key, None)
                    changed = True

        if changed:
            conf.save_config()


async def _run_provider_cleanup_for_v5(
    db_helper: BaseDatabase,
    acm: AstrBotConfigManager,
) -> None:
    if await sp.global_get(_MIGRATION_PROVIDER_CLEANUP_FLAG, False):
        return

    logger.info("Starting v5 provider cleanup migration")
    await _migrate_chain_provider_columns_to_node_config(db_helper)
    _cleanup_legacy_provider_config_keys(acm)
    await _drop_chain_provider_columns(db_helper)
    await sp.global_put(_MIGRATION_PROVIDER_CLEANUP_FLAG, True)
    logger.info("v5 provider cleanup migration completed")
