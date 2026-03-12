"""**兼容层** - 旧版 ``astrbot_sdk.api`` 导入路径的向后兼容入口。

.. warning::
   本目录是 ** 旧版本兼容层**，仅供旧版插件使用。

   **请插件制作者尽快迁移至新版导入路径**，兼容层将在未来版本移除。

   保留此目录路径是为了确保旧版插件无需修改代码即可运行。
   路径名 ``api`` 是历史原因，新版 SDK 的核心 API 已迁移至顶层模块。

新版推荐导入路径：

- ``astrbot_sdk.context.Context`` - 上下文管理
- ``astrbot_sdk.events.MessageEvent`` - 消息事件
- ``astrbot_sdk.decorators`` - 装饰器 (command, regex 等)
- ``astrbot_sdk.star.Star`` - 插件基类

迁移示例::

    # 旧版 (将在未来版本废弃)
    from astrbot_sdk.api.event import AstrMessageEvent
    from astrbot_sdk.api.star.context import Context

    # 新版 (推荐)
    from astrbot_sdk.events import MessageEvent
    from astrbot_sdk.context import Context

设计说明：
- 兼容层通过 thin re-export 方式暴露旧版 API
- 不复制独立运行时逻辑，保持架构清晰
"""

from . import (
    basic,
    components,
    event,
    message,
    message_components,
    platform,
    provider,
    star,
)

__all__ = [
    "basic",
    "components",
    "event",
    "message",
    "message_components",
    "platform",
    "provider",
    "star",
]
