"""插件上下文 API 模块。

提供插件运行时上下文 Context 类，用于：
- 调用 LLM 生成文本
- 发送消息
- 管理会话
- 存储键值数据

此模块是旧版 astrbot_sdk.api.star 的兼容层。
Context 实际上是 LegacyContext 的别名，用于向后兼容旧版插件。

新版插件建议使用 astrbot_sdk.context.Context。

# TODO: 相比旧版 star 模块，新版缺少以下内容：

## 缺失的文件：
- star.py: StarMetadata 插件元数据类

## 旧版 star 模块结构：
1. context.py - Context 抽象类（已有兼容层）
2. star.py - StarMetadata 数据类（缺失）

StarMetadata 用于描述插件的元信息，包括：
- 基础信息: name, author, desc, version, repo
- 模块路径: module_path, root_dir_name
- 状态标志: reserved, activated
- 配置: config (AstrBotConfig)
- Handler 信息: star_handler_full_names
- 展示信息: display_name, logo_path

建议在新版中提供等效的插件元数据访问接口。
"""

from .context import Context

__all__ = ["Context"]
