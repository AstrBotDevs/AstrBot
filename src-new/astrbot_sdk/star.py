"""v4 原生插件基类。

所有 v4 插件都应继承 `Star` 类，并通过装饰器声明 handler。
框架会自动收集带有 @on_command、@on_message 等装饰器的方法。

生命周期：
    1. 插件加载时，__init_subclass__ 收集所有 handler 方法名
    2. 插件启动时，调用 on_start() 进行初始化
    3. 收到消息时，调用匹配的 handler 方法
    4. handler 出错时，调用 on_error() 处理异常
    5. 插件卸载时，调用 on_stop() 进行清理

Example:
    class MyPlugin(Star):
        @on_command("hello")
        async def hello(self, event: MessageEvent, ctx: Context):
            await event.reply("Hello!")

        async def on_start(self, ctx):
            # 初始化资源
            pass

        async def on_stop(self, ctx):
            # 清理资源
            pass
"""

from __future__ import annotations

import traceback
from typing import Any

from loguru import logger

from .errors import AstrBotError


class Star:
    """v4 原生插件基类。

    所有插件都应继承此类。子类可以使用装饰器声明 handler，
    框架会自动收集并注册。

    Class Attributes:
        __handlers__: 收集到的 handler 方法名元组

    Lifecycle Methods:
        on_start: 插件启动时调用
        on_stop: 插件停止时调用
        on_error: handler 执行出错时调用
    """

    __handlers__: tuple[str, ...] = ()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """收集子类中所有带有 handler 装饰器的方法。

        遍历类的 MRO，收集所有标记了 __astrbot_handler_meta__ 的方法。
        使用 dict 去重保证每个方法名只出现一次。
        """
        super().__init_subclass__(**kwargs)
        from .decorators import get_handler_meta

        handlers: dict[str, None] = {}
        for base in reversed(cls.__mro__):
            for name, attr in getattr(base, "__dict__", {}).items():
                func = getattr(attr, "__func__", attr)
                meta = get_handler_meta(func)
                if meta is not None and meta.trigger is not None:
                    handlers[name] = None
        cls.__handlers__ = tuple(handlers.keys())

    async def on_start(self, ctx: Any | None = None) -> None:
        """插件启动时的初始化钩子。

        在插件首次加载或重新加载时调用。
        可用于初始化数据库连接、加载配置等。

        Args:
            ctx: 运行时上下文（可选）

        Note:
            子类可以重写此方法以执行初始化逻辑
        """
        return None

    async def on_stop(self, ctx: Any | None = None) -> None:
        """插件停止时的清理钩子。

        在插件卸载或重新加载前调用。
        可用于关闭连接、保存状态等。

        Args:
            ctx: 运行时上下文（可选）

        Note:
            子类可以重写此方法以执行清理逻辑
        """
        return None

    async def on_error(self, error: Exception, event, ctx) -> None:
        """handler 执行出错时的错误处理钩子。

        默认行为：
        - AstrBotError: 根据 retryable/hint/message 生成回复
        - 其他异常: 返回通用错误消息

        Args:
            error: 捕获的异常
            event: 触发 handler 的事件对象
            ctx: 运行时上下文

        Note:
            子类可以重写此方法以自定义错误处理逻辑
        """
        if isinstance(error, AstrBotError):
            if error.retryable:
                await event.reply("请求失败，请稍后重试")
            elif error.hint:
                await event.reply(error.hint)
            else:
                await event.reply(error.message)
        else:
            await event.reply("出了点问题，请联系插件作者")
        logger.error("handler 执行失败\n{}", traceback.format_exc())

    @classmethod
    def __astrbot_is_new_star__(cls) -> bool:
        """标识这是 v4 原生 Star 类。

        用于区分 v4 插件和 legacy 插件。

        Returns:
            总是返回 True
        """
        return True
