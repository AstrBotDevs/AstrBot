"""配置文件迁移工具 - 将旧的单一配置拆分为多个独立配置文件"""

import json
import logging
import os

from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .platforms_default import PLATFORMS_CONFIG_KEYS, PLATFORMS_DEFAULT_CONFIG
from .providers_default import PROVIDERS_CONFIG_KEYS, PROVIDERS_DEFAULT_CONFIG

logger = logging.getLogger("astrbot")

# 配置文件路径
DATA_PATH = get_astrbot_data_path()
CORE_CONFIG_PATH = os.path.join(DATA_PATH, "cmd_config.json")
PROVIDERS_CONFIG_PATH = os.path.join(DATA_PATH, "providers.json")
PLATFORMS_CONFIG_PATH = os.path.join(DATA_PATH, "platforms.json")


def load_json_file(path: str) -> dict | None:
    """安全加载 JSON 文件"""
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"加载配置文件失败 {path}: {e}")
        return None


def save_json_file(path: str, data: dict) -> bool:
    """保存 JSON 文件"""
    try:
        with open(path, "w", encoding="utf-8-sig") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except OSError as e:
        logger.error(f"保存配置文件失败 {path}: {e}")
        return False


def extract_config_keys(source: dict, keys: list[str]) -> dict:
    """从源配置中提取指定的键"""
    extracted = {}
    for key in keys:
        if key in source:
            extracted[key] = source[key]
    return extracted


def remove_config_keys(source: dict, keys: list[str]) -> dict:
    """从源配置中移除指定的键（返回副本）"""
    result = source.copy()
    for key in keys:
        result.pop(key, None)
    return result


def needs_migration() -> bool:
    """检查是否需要配置迁移

    如果核心配置存在且包含供应商/平台配置键，且独立配置文件不存在，则需要迁移。
    """
    if not os.path.exists(CORE_CONFIG_PATH):
        return False

    # 如果独立配置文件都存在，无需迁移
    if os.path.exists(PROVIDERS_CONFIG_PATH) and os.path.exists(PLATFORMS_CONFIG_PATH):
        return False

    # 检查核心配置是否包含需要迁移的键
    core_config = load_json_file(CORE_CONFIG_PATH)
    if core_config is None:
        return False

    has_provider_keys = any(key in core_config for key in PROVIDERS_CONFIG_KEYS)
    has_platform_keys = any(key in core_config for key in PLATFORMS_CONFIG_KEYS)

    return has_provider_keys or has_platform_keys


def migrate_config() -> tuple[bool, str]:
    """执行配置迁移

    Returns:
        (success: bool, message: str)
    """
    logger.info("开始配置迁移...")

    core_config = load_json_file(CORE_CONFIG_PATH)
    if core_config is None:
        return False, "无法加载核心配置文件"

    # 如果供应商配置文件不存在，提取并创建
    if not os.path.exists(PROVIDERS_CONFIG_PATH):
        providers_config = extract_config_keys(core_config, PROVIDERS_CONFIG_KEYS)
        if providers_config:
            if save_json_file(PROVIDERS_CONFIG_PATH, providers_config):
                logger.info(f"已创建供应商配置文件: {PROVIDERS_CONFIG_PATH}")
            else:
                return False, "无法创建供应商配置文件"
        else:
            # 如果没有供应商配置，使用默认值创建
            if not save_json_file(PROVIDERS_CONFIG_PATH, PROVIDERS_DEFAULT_CONFIG):
                return False, "无法创建默认供应商配置文件"
            logger.info(f"已使用默认值创建供应商配置文件: {PROVIDERS_CONFIG_PATH}")

    # 如果平台配置文件不存在，提取并创建
    if not os.path.exists(PLATFORMS_CONFIG_PATH):
        platforms_config = extract_config_keys(core_config, PLATFORMS_CONFIG_KEYS)
        if platforms_config:
            if save_json_file(PLATFORMS_CONFIG_PATH, platforms_config):
                logger.info(f"已创建平台配置文件: {PLATFORMS_CONFIG_PATH}")
            else:
                return False, "无法创建平台配置文件"
        else:
            # 如果没有平台配置，使用默认值创建
            if not save_json_file(PLATFORMS_CONFIG_PATH, PLATFORMS_DEFAULT_CONFIG):
                return False, "无法创建默认平台配置文件"
            logger.info(f"已使用默认值创建平台配置文件: {PLATFORMS_CONFIG_PATH}")

    # 从核心配置中移除已迁移的键
    keys_to_remove = PROVIDERS_CONFIG_KEYS + PLATFORMS_CONFIG_KEYS
    updated_core = remove_config_keys(core_config, keys_to_remove)

    if len(updated_core) != len(core_config):
        if save_json_file(CORE_CONFIG_PATH, updated_core):
            removed_count = len(core_config) - len(updated_core)
            logger.info(f"已从核心配置中移除 {removed_count} 个已迁移的配置项")
        else:
            return False, "无法更新核心配置文件"

    logger.info("配置迁移完成")
    return True, "配置迁移成功"


def get_merged_config(core_conf: dict | None = None) -> dict:
    """获取合并后的完整配置

    Args:
        core_conf: 可选的核心配置字典。如果未提供，将从文件加载。

    Returns:
        合并后的完整配置字典
    """
    merged = {}

    # 加载核心配置
    if core_conf is not None:
        merged.update(core_conf)
    else:
        loaded_core = load_json_file(CORE_CONFIG_PATH)
        if loaded_core:
            merged.update(loaded_core)

    # 加载供应商配置
    providers_config = load_json_file(PROVIDERS_CONFIG_PATH)
    if providers_config:
        merged.update(providers_config)

    # 加载平台配置
    platforms_config = load_json_file(PLATFORMS_CONFIG_PATH)
    if platforms_config:
        merged.update(platforms_config)

    return merged


def save_config_by_category(full_config: dict) -> bool:
    """将完整配置按类别保存到对应文件

    Args:
        full_config: 包含所有配置的完整字典

    Returns:
        是否保存成功
    """
    # 提取供应商配置
    providers_config = extract_config_keys(full_config, PROVIDERS_CONFIG_KEYS)
    if providers_config:
        if not save_json_file(PROVIDERS_CONFIG_PATH, providers_config):
            return False

    # 提取平台配置
    platforms_config = extract_config_keys(full_config, PLATFORMS_CONFIG_KEYS)
    if platforms_config:
        if not save_json_file(PLATFORMS_CONFIG_PATH, platforms_config):
            return False

    # 剩余的保存到核心配置
    core_config = remove_config_keys(
        full_config, PROVIDERS_CONFIG_KEYS + PLATFORMS_CONFIG_KEYS
    )
    if not save_json_file(CORE_CONFIG_PATH, core_config):
        return False

    return True
