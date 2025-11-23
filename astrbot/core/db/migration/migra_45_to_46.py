from astrbot.api import logger, sp
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.umop_config_router import UmopConfigRouter


async def migrate_45_to_46(acm: AstrBotConfigManager, ucr: UmopConfigRouter):
    abconf_data = acm.abconf_data

    if not isinstance(abconf_data, dict):
        # should be unreachable
        logger.warning(
            f"migrate_45_to_46: abconf_data is not a dict (type={type(abconf_data)}). Value: {abconf_data!r}",
        )
        return

    # 如果任何一项带有 umop，则说明需要迁移
    need_migration = False
    for conf_id, conf_info in abconf_data.items():
        if isinstance(conf_info, dict) and "umop" in conf_info:
            need_migration = True
            break

    if not need_migration:
        return

    logger.info("Starting migration from version 4.5 to 4.6")

    # extract umo->conf_id mapping
    umo_to_conf_id = {}
    for conf_id, conf_info in abconf_data.items():
        if isinstance(conf_info, dict) and "umop" in conf_info:
            umop_ls = conf_info.pop("umop")
            if not isinstance(umop_ls, list):
                continue
            for umo in umop_ls:
                if isinstance(umo, str) and umo not in umo_to_conf_id:
                    umo_to_conf_id[umo] = conf_id

    # update the abconf data
    await sp.global_put("abconf_mapping", abconf_data)
    # update the umop config router
    await ucr.update_routing_data(umo_to_conf_id)

    logger.info("Migration from version 45 to 46 completed successfully")
