# =============================================================================
# 新旧对比 - compat.py
# =============================================================================
#
# 【说明】
# compat.py 是新版新增的兼容层模块，用于导出旧版 API。
#
# 【旧版】
# 旧版没有独立的 compat.py 文件。
# 旧版的 Context、CommandComponent 等类型定义在 api/star/ 目录下。
#
# 【新版】
# 新版通过此兼容层重新导出 _legacy_api.py 中的旧版类型，
# 使得旧代码可以通过 `from astrbot_sdk.compat import Context` 方式导入。
#
# 【设计目的】
# 提供平滑的迁移路径，让旧版插件可以在新版 SDK 下继续工作，
# 同时逐步引导开发者使用新版 API。
#
# =============================================================================

from ._legacy_api import (
    CommandComponent,
    Context,
    LegacyContext,
    LegacyConversationManager,
)

__all__ = [
    "CommandComponent",
    "Context",
    "LegacyContext",
    "LegacyConversationManager",
]
