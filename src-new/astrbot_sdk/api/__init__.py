"""AstrBot SDK 公共 API 模块。

此模块提供插件开发所需的公共接口，包括：
- components: 命令组件基类
- event: 事件处理相关工具（过滤器、事件类）
- star: 插件上下文

注意：大部分 API 是为了兼容旧版插件而保留的兼容层。
新版 API 请参考 astrbot_sdk.context.Context 和 astrbot_sdk.decorators 模块。
"""

__all__: list[str] = []
