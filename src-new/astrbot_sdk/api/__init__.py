"""旧版 ``astrbot_sdk.api`` 的兼容入口。

新版 SDK 的推荐导入路径在顶层模块：

- ``astrbot_sdk.context.Context``
- ``astrbot_sdk.events.MessageEvent``
- ``astrbot_sdk.decorators``
- ``astrbot_sdk.star.Star``

这里保留 ``api`` 目录，目的是兼容旧版插件的导入路径，而不是复制一套独立的新运行时。
"""

from . import basic, components, event, message, platform, provider, star

__all__ = [
    "basic",
    "components",
    "event",
    "message",
    "platform",
    "provider",
    "star",
]
