"""命令组件模块。

提供 CommandComponent 基类，用于定义命令处理器。
CommandComponent 是旧版 Star 基类的别名，用于向后兼容。

新版插件建议直接使用 astrbot_sdk.star.Star 和装饰器模式。
"""

from .command import CommandComponent

__all__ = ["CommandComponent"]
