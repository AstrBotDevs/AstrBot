"""过渡期兼容实现层 ``astrbot_sdk.api``。

这个包承载旧插件所需的兼容模型与逻辑实现，供 legacy 执行路径直接使用。
它不是简单的重导出层，而是维护旧语义所必需的实现模块：

- ``astrbot_sdk.api.event``：``AstrMessageEvent``、``filter``、``MessageEventResult``
- ``astrbot_sdk.api.message``：``MessageChain``、消息组件模型
- ``astrbot_sdk.api.provider``：``LLMResponse`` 兼容实体
- ``astrbot_sdk.api.basic``、``platform``、``components``：配置、平台、组件兼容面

与 ``src-new/astrbot/`` 对比：
- 此包（``astrbot_sdk.api``）是真正的兼容实现，包含运行时逻辑
- ``src-new/astrbot/`` 是薄 facade，只做导入路径转发

迁移目标（仅在有明确迁移计划时移除）：

- ``astrbot_sdk.context.Context``
- ``astrbot_sdk.events.MessageEvent``
- ``astrbot_sdk.decorators``
- ``astrbot_sdk.star.Star``

维护约束：

- 新增运行时逻辑优先放在 v4 主路径，由此层按需包装
- compat 真实执行边界收口在顶层私有模块（``_legacy_runtime.py`` 等）
- 新插件应直接使用 ``astrbot_sdk`` 顶层 v4 API
"""

from loguru import logger

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
from .basic import AstrBotConfig

__all__ = [
    "AstrBotConfig",
    "basic",
    "components",
    "event",
    "logger",
    "message",
    "message_components",
    "platform",
    "provider",
    "star",
]
