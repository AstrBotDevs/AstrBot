"""命令组件兼容层。

此模块提供旧版 CommandComponent 的向后兼容导入。
CommandComponent 是插件命令处理器的基类。

迁移说明：
- 旧版: 继承 CommandComponent，实现 command() 方法
- 新版: 继承 astrbot_sdk.star.Star，使用 @on_command 装饰器

示例:
    # 旧版写法
    class MyCommand(CommandComponent):
        async def command(self, ctx: Context):
            ...

    # 新版写法
    from astrbot_sdk import Star, on_command

    class MyPlugin(Star):
        @on_command("hello")
        async def handle_hello(self, ctx: Context):
            ...
"""

from ..._legacy_api import CommandComponent

__all__ = ["CommandComponent"]
