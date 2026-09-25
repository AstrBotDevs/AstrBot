"""AstrBot 备份与恢复模块

提供数据导出和导入功能，支持用户在服务器迁移时一键备份和恢复所有数据。
"""

# 从 constants 模块导入共享常量
from .constants import (
    BACKUP_MANIFEST_VERSION,
    HARD_FAIL_COMPONENTS,
    KB_METADATA_MODELS,
    MAIN_DB_MODELS,
    SPECIAL_COMPONENTS,
    component_of_entry,
    derive_component_states,
    get_backup_components,
    get_backup_directories,
)

# 导入导出器和导入器
from .exporter import AstrBotExporter
from .importer import AstrBotImporter, ImportPreCheckResult

__all__ = [
    "AstrBotExporter",
    "AstrBotImporter",
    "ImportPreCheckResult",
    "MAIN_DB_MODELS",
    "KB_METADATA_MODELS",
    "SPECIAL_COMPONENTS",
    "HARD_FAIL_COMPONENTS",
    "get_backup_components",
    "get_backup_directories",
    "component_of_entry",
    "derive_component_states",
    "BACKUP_MANIFEST_VERSION",
]
