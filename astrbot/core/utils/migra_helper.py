import traceback

from astrbot.core import astrbot_config, logger
from astrbot.core.astrbot_config_mgr import AstrBotConfig, AstrBotConfigManager
from astrbot.core.db.migration.migra_45_to_46 import migrate_45_to_46
from astrbot.core.db.migration.migra_webchat_session import migrate_webchat_session


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
            conf.save_config()
    except Exception as e:
        logger.error(f"Migration for third party agent runner configs failed: {e!s}")
        logger.error(traceback.format_exc())


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

    # migra third party agent runner configs
    _c = False
    providers = astrbot_config["provider"]
    ids_map = {}
    for prov in providers:
        type_ = prov.get("type")
        if type_ in ["dify", "coze", "dashscope"]:
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
