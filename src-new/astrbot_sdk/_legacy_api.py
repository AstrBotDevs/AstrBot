"""旧版 API 兼容层聚合入口。

这个模块重导出来自 ``_legacy_context`` 和 ``_legacy_star`` 的所有公开符号，
供 ``compat.py``、``api/star/``、``api/components/`` 等外部导入路径使用。

不要在这里添加新的运行时逻辑；业务实现分别在 ``_legacy_context.py`` 和
``_legacy_star.py`` 中维护。

注意：``logger`` 在此显式导入，以保持向后兼容性——部分测试通过
``patch("astrbot_sdk._legacy_api.logger.warning")`` 路径拦截日志调用。
由于 loguru 的 ``logger`` 是全局单例，这里的引用与 ``_legacy_context``
内部使用的是同一个对象。
"""

from __future__ import annotations

from loguru import logger as logger  # noqa: PLC0414 — re-exported for patch compat

from ._legacy_context import (
    COMPAT_CONVERSATIONS_KEY,
    MIGRATION_DOC_URL,
    LegacyContext,
    LegacyConversationManager,
    _CompatHookEntry,
    _iter_registered_component_methods,
    _warn_once,
    _warned_methods,
)
from ._legacy_star import CommandComponent, LegacyStar, StarTools, register

# Historical alias: ``Context`` was the original public name for ``LegacyContext``.
Context = LegacyContext

__all__ = [
    "COMPAT_CONVERSATIONS_KEY",
    "CommandComponent",
    "Context",
    "LegacyContext",
    "LegacyConversationManager",
    "LegacyStar",
    "MIGRATION_DOC_URL",
    "StarTools",
    "_CompatHookEntry",
    "_iter_registered_component_methods",
    "_warn_once",
    "_warned_methods",
    "logger",
    "register",
]
