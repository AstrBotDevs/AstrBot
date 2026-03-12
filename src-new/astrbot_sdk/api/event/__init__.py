"""事件处理 API 模块。

提供事件相关的公共接口：
- AstrMessageEvent: 消息事件类，包含消息文本、用户信息、平台信息等
- filter: 事件过滤器命名空间，提供命令、正则、权限等装饰器
- ADMIN: 管理员权限常量

此模块是旧版 astrbot_sdk.api.event 的兼容层。
新版 API 建议直接使用 astrbot_sdk.events.MessageEvent 和 astrbot_sdk.decorators。
"""

from ...events import MessageEvent as AstrMessageEvent
from .filter import ADMIN, filter

__all__ = ["ADMIN", "AstrMessageEvent", "filter"]
