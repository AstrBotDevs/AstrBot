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

# TODO: 新旧版 components 模块对比：

## 旧版 components 模块结构：
- command.py: CommandComponent 基类（已有兼容层）

## 新版与旧版基本一致：
旧版 components 模块仅包含 command.py，新版已提供兼容层。

## 无缺失内容
此模块功能完整，与旧版保持兼容。
"""

from ..._legacy_api import CommandComponent

__all__ = ["CommandComponent"]
