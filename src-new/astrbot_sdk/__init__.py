# =============================================================================
# 新旧对比 - 第一层模块
# =============================================================================
#
# 【旧版 src/astrbot_sdk/ 第一层结构】
# - 文件夹: api/, cli/, runtime/, tests/
# - 文件: __main__.py (仅入口)
#
# 【新版 src-new/astrbot_sdk/ 第一层结构】
# - 文件夹: api/, clients/, protocol/, runtime/
# - 文件: __init__.py, __main__.py, cli.py, compat.py, context.py,
#         decorators.py, errors.py, events.py, star.py, _legacy_api.py
#
# 【结构变化说明】
# 新版将多个核心概念从子模块提升到第一层，便于导入和使用：
# - decorators.py: 装饰器（旧版在 api/star/decorators.py 或 api/event/filter.py）
# - errors.py: 错误类（旧版在 api/star/ 下）
# - events.py: 事件类（旧版在 api/event/ 下）
# - star.py: Star 基类（旧版在 api/star/ 下）
# - context.py: Context 上下文（旧版在 api/star/context.py）
# - _legacy_api.py: 旧版兼容层（提供 LegacyContext、CommandComponent 等）
#
# =============================================================================
# TODO: 缺失模块
# =============================================================================
#
# 1. tests/ 文件夹
#    - 旧版有 src/astrbot_sdk/tests/ 测试目录
#    - 新版缺失，测试代码已移至 tests_v4/ 目录
#    - 考虑是否需要保留 SDK 内置测试工具
#
# =============================================================================

from .context import Context
from .decorators import on_command, on_event, on_message, on_schedule, require_admin
from .errors import AstrBotError
from .events import MessageEvent
from .star import Star

__all__ = [
    "AstrBotError",
    "Context",
    "MessageEvent",
    "Star",
    "on_command",
    "on_event",
    "on_message",
    "on_schedule",
    "require_admin",
]
