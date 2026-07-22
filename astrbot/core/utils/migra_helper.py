import traceback

from astrbot.core import astrbot_config, logger
from astrbot.core.agent.runners.deerflow.constants import (
    DEERFLOW_AGENT_RUNNER_PROVIDER_ID_KEY,
    DEERFLOW_PROVIDER_TYPE,
)
from astrbot.core.astrbot_config_mgr import AstrBotConfig, AstrBotConfigManager
from astrbot.core.db.migration.migra_45_to_46 import migrate_45_to_46
from astrbot.core.db.migration.migra_token_usage import migrate_token_usage
from astrbot.core.db.migration.migra_webchat_session import migrate_webchat_session


def _migra_agent_runner_configs(conf: AstrBotConfig, ids_map: dict) -> None:
    """Migra agent runner configs from provider configs."""
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
    """Migrate old provider structure to new provider-source separation.
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


async def migra(
    db,
    astrbot_config_mgr,
    umop_config_router,
    acm: AstrBotConfigManager,
) -> None:
    """Stores the migration logic here.
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

    # Migrate context config: old implicit-value fields → orthogonal trigger/disposal
    try:
        _migra_context_config(astrbot_config["provider_settings"])
        _validate_context_config(astrbot_config["provider_settings"])
        for conf in acm.confs.values():
            _migra_context_config(conf["provider_settings"])
            _validate_context_config(conf["provider_settings"])
    except Exception as e:
        logger.error(f"Migration for context config failed: {e!s}")
        logger.error(traceback.format_exc())


def _migra_context_config(ps: dict) -> bool:
    """Migrate old context config fields to new orthogonal fields.

    Returns True if any migration happened.
    """
    migrated = False

    # 1. max_context_length → enable_turn_limit + max_turns
    if "max_context_length" in ps:
        old_val = ps.pop("max_context_length")
        migrated = True
        if isinstance(old_val, (int, float)) and old_val > 0:
            ps["enable_turn_limit"] = True
            ps["max_turns"] = int(old_val)
        else:
            ps["enable_turn_limit"] = False

    # 2. dequeue_context_length → discard_turns
    if "dequeue_context_length" in ps:
        ps["discard_turns"] = ps.pop("dequeue_context_length")
        migrated = True

    # 3. context_limit_reached_strategy → enable_summary + enable_discard
    if "context_limit_reached_strategy" in ps:
        strategy = ps.pop("context_limit_reached_strategy")
        migrated = True
        if strategy == "llm_compress":
            ps["enable_summary"] = True
            ps["enable_discard"] = True
            ps["retention_method"] = "percentage"
        else:  # truncate_by_turns or other
            ps["enable_summary"] = False
            ps["enable_discard"] = True
            ps["retention_method"] = "turns"

    # 4. llm_compress_instruction → summary_prompt
    if "llm_compress_instruction" in ps:
        ps["summary_prompt"] = ps.pop("llm_compress_instruction")
        migrated = True

    # 5. llm_compress_keep_recent_ratio → retain_percentage + retention_method
    if "llm_compress_keep_recent_ratio" in ps:
        ps["retain_percentage"] = ps.pop("llm_compress_keep_recent_ratio")
        if "retention_method" not in ps:
            ps["retention_method"] = "percentage"
        migrated = True

    # 6. llm_compress_provider_id → summary_provider_id
    if "llm_compress_provider_id" in ps:
        ps["summary_provider_id"] = ps.pop("llm_compress_provider_id")
        migrated = True

    if migrated:
        logger.info("Migrated old context config to orthogonal trigger/disposal model.")

    return migrated


def _validate_context_config(ps: dict) -> None:
    """Validate new context config fields and log warnings for violations."""

    def _has(k: str) -> bool:
        return k in ps

    if _has("enable_turn_limit") and _has("max_turns"):
        if ps.get("enable_turn_limit") and ps.get("max_turns", 50) < 2:
            logger.warning("max_turns should be >= 2 when enable_turn_limit is True.")

    if _has("token_guard_threshold"):
        val = ps["token_guard_threshold"]
        if not (0.5 <= val <= 0.99):
            logger.warning(
                "token_guard_threshold %.2f is outside recommended range [0.5, 0.99].",
                val,
            )

    if _has("discard_turns") and ps.get("discard_turns", 1) < 1:
        logger.warning("discard_turns should be >= 1.")

    if _has("retention_method"):
        method = ps["retention_method"]
        if method not in ("turns", "percentage", "null"):
            logger.warning(
                "Unknown retention_method '%s'. Use 'turns', 'percentage', or 'null'.",
                method,
            )

    if (
        _has("retention_method")
        and ps["retention_method"] == "turns"
        and _has("retain_turns")
        and ps.get("retain_turns", 20) < 1
    ):
        logger.warning("retain_turns should be >= 1.")

    if (
        _has("retention_method")
        and ps["retention_method"] == "percentage"
        and _has("retain_percentage")
    ):
        val = ps["retain_percentage"]
        if not (0.1 <= val <= 0.9):
            logger.warning(
                "retain_percentage %.2f is outside recommended range [0.1, 0.9].",
                val,
            )

    # Both disposal methods disabled → trigger fires but nothing happens
    if _has("enable_summary") and _has("enable_discard"):
        if not ps.get("enable_summary") and not ps.get("enable_discard"):
            logger.warning(
                "Both enable_summary and enable_discard are False. "
                "Context will not be compressed when triggers fire.",
            )

    # Implicit constraint: retain_turns > max_turns is pointless
    if (
        _has("enable_turn_limit")
        and ps.get("enable_turn_limit")
        and _has("retention_method")
        and ps["retention_method"] == "turns"
        and _has("retain_turns")
        and _has("max_turns")
    ):
        if ps["retain_turns"] > ps["max_turns"]:
            logger.warning(
                "retain_turns (%d) > max_turns (%d). Retention lower bound will take priority.",
                ps["retain_turns"],
                ps["max_turns"],
            )
