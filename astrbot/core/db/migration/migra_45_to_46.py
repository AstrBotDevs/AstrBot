# 导入全局日志记录器和共享偏好设置实例
from astrbot.api import logger, sp
# 导入 AstrBot 配置管理器
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
# 导入 UMOP 配置路由器
from astrbot.core.umop_config_router import UmopConfigRouter


async def migrate_45_to_46(acm: AstrBotConfigManager, ucr: UmopConfigRouter) -> None:
    """
    执行从版本 4.5 到 4.6 的数据迁移。
    
    主要变更：在 4.5 版本中，UMOP（统一消息对象标识符）路由信息存储在
    abconf_data 的每个配置项内部（作为 'umop' 字段）；在 4.6 版本中，
    UMOP 路由被提取到独立的 UmopConfigRouter 中进行管理。
    
    迁移过程：
        1. 检测是否需要迁移（检查配置中是否存在 'umop' 字段）
        2. 提取所有 umop 到 conf_id 的映射关系
        3. 从原配置中移除 'umop' 字段
        4. 更新配置存储和 UMOP 路由器

    Args:
        acm: AstrBot 配置管理器实例，包含旧版本的配置数据
        ucr: UMOP 配置路由器实例，用于存储迁移后的路由数据
    """
    # 获取当前的配置数据（包含可能的旧版本 umop 字段）
    abconf_data = acm.abconf_data

    # 验证配置数据类型是否为字典
    if not isinstance(abconf_data, dict):
        # 理论上不应该到达这里，但如果数据格式异常则记录警告并退出
        logger.warning(
            f"migrate_45_to_46: abconf_data is not a dict (type={type(abconf_data)}). Value: {abconf_data!r}",
        )
        return  # 数据类型异常，无法进行迁移

    # 检查是否需要执行迁移：
    # 遍历所有配置项，查找是否包含旧版本的 'umop' 字段
    need_migration = False  # 迁移标志，默认为不需要
    for conf_id, conf_info in abconf_data.items():
        # 检查配置项是否为字典且包含 'umop' 键
        if isinstance(conf_info, dict) and "umop" in conf_info:
            need_migration = True  # 发现需要迁移的数据
            break  # 找到一个就足够了，跳出循环

    # 如果没有需要迁移的数据，直接返回
    if not need_migration:
        return

    # 记录迁移开始日志
    logger.info("Starting migration from version 4.5 to 4.6")

    # 第一步：提取 umo 到 conf_id 的映射关系
    umo_to_conf_id = {}  # 初始化 UMOP 到配置 ID 的映射字典
    for conf_id, conf_info in abconf_data.items():
        # 只处理包含 'umop' 字段的字典类型配置项
        if isinstance(conf_info, dict) and "umop" in conf_info:
            # 从配置项中取出并删除 'umop' 字段（pop 方法会同时删除该字段）
            umop_ls = conf_info.pop("umop")
            # 验证 umop 字段是否为列表类型
            if not isinstance(umop_ls, list):
                continue  # 如果不是列表，跳过该配置项
            # 遍历 umop 列表中的每个 UMO 字符串
            for umo in umop_ls:
                # 确保 umo 是字符串类型且尚未存在于映射中
                if isinstance(umo, str) and umo not in umo_to_conf_id:
                    # 建立 UMO 到配置 ID 的映射关系
                    umo_to_conf_id[umo] = conf_id

    # 第二步：更新配置数据到持久化存储
    # 将移除了 umop 字段的配置数据保存到 SharedPreferences
    await sp.global_put("abconf_mapping", abconf_data)
    
    # 第三步：更新 UMOP 配置路由器
    # 将提取的映射关系批量更新到路由器中
    await ucr.update_routing_data(umo_to_conf_id)

    # 记录迁移完成日志
    logger.info("Migration from version 45 to 46 completed successfully")