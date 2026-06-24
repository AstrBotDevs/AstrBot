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
    将旧的 provider 结构迁移到新的 provider-source 分离结构。
    
    迁移规则：
        - Provider 只保留核心字段：id, provider_source_id, model, modalities, 
          custom_extra_body, enable
        - 所有其他字段移动到 provider_sources 中
        - 从 model_config 中提取 model 字段
        - 将 model_config 中的其他字段合并到 custom_extra_body
    
    迁移过程：
        1. 遍历所有 provider 配置
        2. 跳过已有 provider_source_id 的 provider（已迁移）
        3. 跳过非 chat_completion 类型的 provider
        4. 提取需要迁移的字段创建新的 provider_source
        5. 更新 provider 保留必要字段
        6. 处理 model_config 字段
        7. 将新的 source 添加到 provider_sources 列表
    
    Args:
        conf: AstrBot 配置对象，包含 provider 和 provider_sources 配置
    """
    # 获取当前的 provider 配置列表
    providers = conf.get("provider", [])
    # 获取当前的 provider_sources 配置列表
    provider_sources = conf.get("provider_sources", [])

    # 跟踪是否发生了任何迁移
    migrated = False

    # 定义应保留在 provider 中的核心字段集合
    # 这些字段不会迁移到 provider_source
    provider_only_fields = {
        "id",                  # Provider 唯一标识
        "provider_source_id",  # 关联的 provider_source ID
        "model",               # 使用的模型名称
        "modalities",          # 支持的模式（如文本、图像等）
        "custom_extra_body",   # 自定义额外请求体参数
        "enable",              # 是否启用
    }

    # 定义不应迁移到 source 的字段集合
    # 包含 provider_only_fields 和 model_config（需要特殊处理）
    source_exclude_fields = provider_only_fields | {"model_config"}

    # 遍历所有 provider 配置
    for provider in providers:
        # 如果 provider 已经有 provider_source_id，说明已经迁移过，跳过
        if provider.get("provider_source_id"):
            continue

        # 检查 provider 类型
        provider_type = provider.get("provider_type", "")
        # 如果不是 chat_completion 类型，不需要 source 分离，跳过
        if provider_type != "chat_completion":
            # 对于没有 provider_type 字段的旧配置，检查 type 字段
            old_type = provider.get("type", "")
            # 如果 type 字段中不包含 chat_completion，也跳过
            if "chat_completion" not in old_type:
                continue

        # 标记发生了迁移
        migrated = True
        # 记录迁移日志
        logger.info(f"Migrating provider {provider.get('id')} to new structure")

        # 第一步：从 provider 中提取需要迁移到 source 的字段
        source_fields = {}
        # 遍历 provider 的所有键值对（使用 list 避免迭代时修改字典）
        for key, value in list(provider.items()):
            # 如果字段不在排除列表中，说明需要迁移
            if key not in source_exclude_fields:
                source_fields[key] = value

        # 第二步：创建新的 provider_source 对象
        # source_id 格式：{provider_id}_source
        source_id = provider.get("id", "") + "_source"
        # 构建新的 source 对象，包含 id 和所有提取的字段
        new_source = {"id": source_id, **source_fields}

        # 第三步：更新 provider，设置 provider_source_id 关联
        provider["provider_source_id"] = source_id

        # 第四步：处理 model_config 字段（特殊迁移逻辑）
        if "model_config" in provider and isinstance(provider["model_config"], dict):
            model_config = provider["model_config"]
            # 从 model_config 中提取 model 字段
            provider["model"] = model_config.get("model", "")

            # 将 model_config 中除 model 外的其他字段合并到 custom_extra_body
            # 构建额外字段字典（排除 model 字段）
            extra_body_fields = {k: v for k, v in model_config.items() if k != "model"}
            # 如果存在额外字段
            if extra_body_fields:
                # 确保 custom_extra_body 字段存在
                if "custom_extra_body" not in provider:
                    provider["custom_extra_body"] = {}
                # 将额外字段合并到 custom_extra_body
                provider["custom_extra_body"].update(extra_body_fields)

        # 第五步：初始化缺失的核心字段（设置默认值）
        if "modalities" not in provider:
            provider["modalities"] = []  # 默认为空列表
        if "custom_extra_body" not in provider:
            provider["custom_extra_body"] = {}  # 默认为空字典

        # 第六步：从 provider 中移除所有不应保留的字段
        # 生成需要删除的字段列表
        keys_to_remove = [k for k in provider.keys() if k not in provider_only_fields]
        # 逐个删除不应保留的字段
        for key in keys_to_remove:
            del provider[key]

        # 第七步：将新创建的 source 添加到 provider_sources 列表
        provider_sources.append(new_source)

    # 如果发生了迁移，保存配置
    if migrated:
        # 更新配置中的 provider_sources
        conf["provider_sources"] = provider_sources
        # 保存配置到持久化存储
        conf.save_config()
        # 记录迁移完成日志
        logger.info("Provider-source structure migration completed")

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
