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

# 需要备份的目录列表
# 键：备份文件中的目录名称
# 值：相对于项目根目录的实际路径
BACKUP_DIRECTORIES: dict[str, str] = {
    "plugins": "data/plugins",  # 插件本体
    "plugin_data": "data/plugin_data",  # 插件数据
    "config": "data/config",  # 配置目录
    "t2i_templates": "data/t2i_templates",  # T2I 模板
    "webchat": "data/webchat",  # WebChat 数据
    "temp": "data/temp",  # 临时文件
}

# 备份清单版本号
BACKUP_MANIFEST_VERSION = "1.1"
