"""插件上下文 API 模块。

提供插件运行时上下文 Context 类，用于：
- 调用 LLM 生成文本
- 发送消息
- 管理会话
- 存储键值数据

此模块是旧版 astrbot_sdk.api.star 的兼容层。
Context 实际上是 LegacyContext 的别名，用于向后兼容旧版插件。

新版插件建议使用 astrbot_sdk.context.Context。
"""

from .context import Context

__all__ = ["Context"]
