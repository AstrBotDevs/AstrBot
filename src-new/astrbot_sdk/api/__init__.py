"""过渡期 ``astrbot_sdk.api`` 兼容 facade。

这个包仅用于承接旧插件的历史导入路径，方便外部插件逐步迁移到 v4 顶层 API。
它不是新的推荐入口，也不应继续承载新的运行时实现逻辑。

迁移目标：

- ``astrbot_sdk.context.Context``
- ``astrbot_sdk.events.MessageEvent``
- ``astrbot_sdk.decorators``
- ``astrbot_sdk.star.Star``

维护约束：

- ``astrbot_sdk.api.*`` 保持为受控兼容面，后续会随迁移推进逐步移除
- 包内模块优先作为 facade / 重导出层存在，但允许少量必须保留行为的 compat 模块
- compat 真实行为应尽量收口到顶层 private compat 模块
- 新增运行时逻辑应优先放在 v4 主路径，由 compat 层按需转发或包装
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
