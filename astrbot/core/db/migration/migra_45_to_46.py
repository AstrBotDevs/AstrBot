from copy import deepcopy

from astrbot.api import logger
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.umop_config_router import UmopConfigRouter


async def migrate_45_to_46(acm: AstrBotConfigManager, ucr: UmopConfigRouter) -> None:
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

    migrated_abconf_data = deepcopy(abconf_data)
    umo_to_conf_id: dict[str, str] = {}
    for conf_id, conf_info in migrated_abconf_data.items():
        if isinstance(conf_info, dict) and "umop" in conf_info:
            umop_ls = conf_info["umop"]
            if not isinstance(umop_ls, list):
                raise ValueError(
                    f"Invalid legacy umop for profile {conf_id!r}: expected a list, got {umop_ls!r}",
                )
            for umo in umop_ls:
                if not isinstance(umo, str) or ucr._split_umo(umo) is None:
                    raise ValueError(
                        f"Invalid legacy umop for profile {conf_id!r}: {umo!r}",
                    )
                umo_to_conf_id.setdefault(umo, conf_id)
            del conf_info["umop"]

    # Persist routing first so invalid data or a routing write failure leaves the
    # legacy profile metadata intact and available for another startup attempt.
    await ucr.update_routing_data(umo_to_conf_id)
    await acm._persist_abconf_mapping(migrated_abconf_data)

    logger.info("Migration from version 45 to 46 completed successfully")
