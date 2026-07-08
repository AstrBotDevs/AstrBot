import traceback

from astrbot.core import astrbot_config, logger, sp
from astrbot.core.agent.runners.deerflow.constants import (
    DEERFLOW_AGENT_RUNNER_PROVIDER_ID_KEY,
    DEERFLOW_PROVIDER_TYPE,
)
from astrbot.core.astrbot_config_mgr import AstrBotConfig, AstrBotConfigManager
from astrbot.core.db.migration.migra_45_to_46 import migrate_45_to_46
from astrbot.core.db.migration.migra_token_usage import migrate_token_usage
from astrbot.core.db.migration.migra_webchat_session import migrate_webchat_session
from astrbot.core.provider.entities import ProviderType

CONFIG_OVERRIDE_MIGRATION_DONE_KEY = "migration_config_overrides_v1_done"


def _migra_agent_runner_configs(conf: AstrBotConfig, ids_map: dict) -> None:
    """
    Migra agent runner configs from provider configs.
    """
    try:
        default_prov_id = conf["provider_settings"]["default_provider_id"]
        if default_prov_id in ids_map:
            conf["provider_settings"]["default_provider_id"] = ""
            p = ids_map[default_prov_id]
            if p["type"] == "dify":
                conf["provider_settings"]["dify_agent_runner_provider_id"] = p["id"]
                conf["provider_settings"]["agent_runner_type"] = "dify"
            elif p["type"] == "coze":
                conf["provider_settings"]["coze_agent_runner_provider_id"] = p["id"]
                conf["provider_settings"]["agent_runner_type"] = "coze"
            elif p["type"] == "dashscope":
                conf["provider_settings"]["dashscope_agent_runner_provider_id"] = p[
                    "id"
                ]
                conf["provider_settings"]["agent_runner_type"] = "dashscope"
            elif p["type"] == DEERFLOW_PROVIDER_TYPE:
                conf["provider_settings"][DEERFLOW_AGENT_RUNNER_PROVIDER_ID_KEY] = p[
                    "id"
                ]
                conf["provider_settings"]["agent_runner_type"] = DEERFLOW_PROVIDER_TYPE
            conf.save_config()
    except Exception as e:
        logger.error(f"Migration for third party agent runner configs failed: {e!s}")
        logger.error(traceback.format_exc())


def _migra_provider_to_source_structure(conf: AstrBotConfig) -> None:
    """
    Migrate old provider structure to new provider-source separation.
    Provider only keeps: id, provider_source_id, model, modalities, custom_extra_body
    All other fields move to provider_sources.
    """
    providers = conf.get("provider", [])
    provider_sources = conf.get("provider_sources", [])

    # Track if any migration happened
    migrated = False

    # Provider-only fields that should stay in provider
    provider_only_fields = {
        "id",
        "provider_source_id",
        "model",
        "modalities",
        "custom_extra_body",
        "enable",
    }

    # Fields that should not go to source
    source_exclude_fields = provider_only_fields | {"model_config"}

    for provider in providers:
        # Skip if already has provider_source_id
        if provider.get("provider_source_id"):
            continue

        # Skip non-chat-completion types (they don't need source separation)
        provider_type = provider.get("provider_type", "")
        if provider_type != "chat_completion":
            # For old types without provider_type, check type field
            old_type = provider.get("type", "")
            if "chat_completion" not in old_type:
                continue

        migrated = True
        logger.info(f"Migrating provider {provider.get('id')} to new structure")

        # Extract source fields from provider
        source_fields = {}
        for key, value in list(provider.items()):
            if key not in source_exclude_fields:
                source_fields[key] = value

        # Create new provider_source
        source_id = provider.get("id", "") + "_source"
        new_source = {"id": source_id, **source_fields}

        # Update provider to only keep necessary fields
        provider["provider_source_id"] = source_id

        # Extract model from model_config if exists
        if "model_config" in provider and isinstance(provider["model_config"], dict):
            model_config = provider["model_config"]
            provider["model"] = model_config.get("model", "")

            # Put other model_config fields into custom_extra_body
            extra_body_fields = {k: v for k, v in model_config.items() if k != "model"}
            if extra_body_fields:
                if "custom_extra_body" not in provider:
                    provider["custom_extra_body"] = {}
                provider["custom_extra_body"].update(extra_body_fields)

        # Initialize new fields if not present
        if "modalities" not in provider:
            provider["modalities"] = []
        if "custom_extra_body" not in provider:
            provider["custom_extra_body"] = {}

        # Remove fields that should be in source
        keys_to_remove = [k for k in provider.keys() if k not in provider_only_fields]
        for key in keys_to_remove:
            del provider[key]

        # Add source to provider_sources
        provider_sources.append(new_source)

    if migrated:
        conf["provider_sources"] = provider_sources
        conf.save_config()
        logger.info("Provider-source structure migration completed")


async def _migrate_session_rules_to_config_overrides(
    db,
    acm: AstrBotConfigManager,
) -> None:
    """Migrate legacy UMO session rules into config override preferences.

    Args:
        db: Database helper used to migrate custom UMO names into aliases.
        acm: Config manager used to write override paths.
    """
    migration_done = await sp.global_get(CONFIG_OVERRIDE_MIGRATION_DONE_KEY, False)
    if migration_done:
        return

    provider_path_map = {
        f"provider_perf_{ProviderType.CHAT_COMPLETION.value}": (
            "provider_settings.default_provider_id"
        ),
        f"provider_perf_{ProviderType.SPEECH_TO_TEXT.value}": (
            "provider_stt_settings.provider_id"
        ),
        f"provider_perf_{ProviderType.TEXT_TO_SPEECH.value}": (
            "provider_tts_settings.provider_id"
        ),
    }
    legacy_keys = {
        "session_service_config",
        "session_plugin_config",
        "kb_config",
        *provider_path_map.keys(),
    }
    prefs = await sp.session_get(None, None)
    migrated_count = 0
    for pref in prefs:
        if pref.key not in legacy_keys:
            continue
        umo = pref.scope_id
        value = pref.value.get("val") if isinstance(pref.value, dict) else None
        override_paths = {}

        if pref.key == "session_service_config" and isinstance(value, dict):
            if "llm_enabled" in value:
                override_paths["provider_settings.enable"] = bool(value["llm_enabled"])
            if "tts_enabled" in value:
                override_paths["provider_tts_settings.enable"] = bool(
                    value["tts_enabled"]
                )
            if "persona_id" in value:
                override_paths["provider_settings.default_personality"] = (
                    value.get("persona_id") or ""
                )
            if value.get("session_enabled") is False:
                override_paths["platform_settings.id_blacklist"] = [umo]
            custom_name = str(value.get("custom_name") or "").strip()
            if custom_name:
                alias = await db.get_umo_alias(umo)
                if not alias or not alias.user_alias:
                    await db.upsert_umo_alias(
                        umo,
                        alias.creator_sender_id if alias else "",
                        alias.auto_name if alias else None,
                        custom_name,
                    )
        elif pref.key == "session_plugin_config" and isinstance(value, dict):
            session_config = value.get(umo, value)
            if isinstance(session_config, dict):
                disabled_plugins = session_config.get("disabled_plugins")
                if isinstance(disabled_plugins, list):
                    override_paths["plugin_disabled_set"] = disabled_plugins
        elif pref.key == "kb_config" and isinstance(value, dict):
            if "top_k" in value:
                override_paths["kb_final_top_k"] = value["top_k"]
            kb_ids = value.get("kb_ids")
            if isinstance(kb_ids, list):
                override_paths["kb_names"] = [
                    str(kb_id) for kb_id in kb_ids if str(kb_id).strip()
                ]
        elif pref.key in provider_path_map and value:
            override_paths[provider_path_map[pref.key]] = value

        if override_paths:
            await acm.update_conf_overrides(umo, override_paths)
            migrated_count += 1

    await sp.global_put(CONFIG_OVERRIDE_MIGRATION_DONE_KEY, True)
    if migrated_count:
        logger.info(
            "Migrated %s legacy session rule preferences to config overrides.",
            migrated_count,
        )


async def migra(
    db, astrbot_config_mgr, umop_config_router, acm: AstrBotConfigManager
) -> None:
    """
    Stores the migration logic here.
    btw, i really don't like migration :(
    """
    # 4.5 to 4.6 migration for umop_config_router
    try:
        await migrate_45_to_46(astrbot_config_mgr, umop_config_router)
    except Exception as e:
        logger.error(f"Migration from version 4.5 to 4.6 failed: {e!s}")
        logger.error(traceback.format_exc())

    # migration for webchat session
    try:
        await migrate_webchat_session(db)
    except Exception as e:
        logger.error(f"Migration for webchat session failed: {e!s}")
        logger.error(traceback.format_exc())

    # migration for token_usage column
    try:
        await migrate_token_usage(db)
    except Exception as e:
        logger.error(f"Migration for token_usage column failed: {e!s}")
        logger.error(traceback.format_exc())

    try:
        await _migrate_session_rules_to_config_overrides(db, acm)
    except Exception as e:
        logger.error(f"Migration for session rule config overrides failed: {e!s}")
        logger.error(traceback.format_exc())

    # migra third party agent runner configs
    _c = False
    providers = astrbot_config["provider"]
    ids_map = {}
    for prov in providers:
        type_ = prov.get("type")
        if type_ in ["dify", "coze", "dashscope", DEERFLOW_PROVIDER_TYPE]:
            prov["provider_type"] = "agent_runner"
            ids_map[prov["id"]] = {
                "type": type_,
                "id": prov["id"],
            }
            _c = True
    if _c:
        astrbot_config.save_config()

    for conf in acm.confs.values():
        _migra_agent_runner_configs(conf, ids_map)

    # Migrate providers to new structure: extract source fields to provider_sources
    try:
        _migra_provider_to_source_structure(astrbot_config)
    except Exception as e:
        logger.error(f"Migration for provider-source structure failed: {e!s}")
        logger.error(traceback.format_exc())
