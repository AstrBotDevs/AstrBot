"""AstrBot 备份模块共享常量

此文件定义了导出器和导入器共享的常量，确保两端配置一致。
"""

from sqlmodel import SQLModel

from astrbot.core.db.po import (
    Attachment,
    CommandConfig,
    CommandConflict,
    ConversationV2,
    Persona,
    PlatformMessageHistory,
    PlatformSession,
    PlatformStat,
    Preference,
)
from astrbot.core.knowledge_base.models import (
    KBDocument,
    KBMedia,
    KnowledgeBase,
)
from astrbot.core.utils.astrbot_path import (
    get_astrbot_config_path,
    get_astrbot_plugin_data_path,
    get_astrbot_plugin_path,
    get_astrbot_t2i_templates_path,
    get_astrbot_temp_path,
    get_astrbot_webchat_path,
)

# ============================================================
# 共享常量 - 确保导出和导入端配置一致
# ============================================================

# 主数据库模型类映射
MAIN_DB_MODELS: dict[str, type[SQLModel]] = {
    "platform_stats": PlatformStat,
    "conversations": ConversationV2,
    "personas": Persona,
    "preferences": Preference,
    "platform_message_history": PlatformMessageHistory,
    "platform_sessions": PlatformSession,
    "attachments": Attachment,
    "command_configs": CommandConfig,
    "command_conflicts": CommandConflict,
}

# 知识库元数据模型类映射
KB_METADATA_MODELS: dict[str, type[SQLModel]] = {
    "knowledge_bases": KnowledgeBase,
    "kb_documents": KBDocument,
    "kb_media": KBMedia,
}


def get_backup_directories() -> dict[str, str]:
    """获取需要备份的目录列表

    使用 astrbot_path 模块动态获取路径，支持通过环境变量 ASTRBOT_ROOT 自定义根目录。

    Returns:
        dict: 键为备份文件中的目录名称，值为目录的绝对路径
    """
    return {
        "plugins": get_astrbot_plugin_path(),  # 插件本体
        "plugin_data": get_astrbot_plugin_data_path(),  # 插件数据
        "config": get_astrbot_config_path(),  # 配置目录
        "t2i_templates": get_astrbot_t2i_templates_path(),  # T2I 模板
        "webchat": get_astrbot_webchat_path(),  # WebChat 数据
        "temp": get_astrbot_temp_path(),  # 临时文件
    }


# 备份清单版本号
BACKUP_MANIFEST_VERSION = "1.1"
