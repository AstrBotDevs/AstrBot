import inspect
import traceback
import typing as T
from dataclasses import dataclass
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star import PluginManager
from astrbot.api import logger
from astrbot.core.star.star_handler import star_handlers_registry, EventType
from astrbot.core.star.star import star_map
from astrbot.core.message.message_event_result import MessageEventResult, CommandResult


@dataclass
class PipelineContext:
    """上下文对象，包含管道执行所需的上下文信息"""

    astrbot_config: AstrBotConfig  # AstrBot 配置对象
    plugin_manager: PluginManager  # 插件管理器对象

    async def call_event_hook(
        self,
        event: AstrMessageEvent,
        hook_type: EventType,
        *args,
    ):
        platform_id = event.get_platform_id()
        handlers = star_handlers_registry.get_handlers_by_event_type(
            hook_type, platform_id=platform_id
        )
        for handler in handlers:
            try:
                logger.debug(
                    f"hook(on_llm_request) -> {star_map[handler.handler_module_path].name} - {handler.handler_name}"
                )
                await handler.handler(event, *args)
            except BaseException:
                logger.error(traceback.format_exc())

            if event.is_stopped():
                logger.info(
                    f"{star_map[handler.handler_module_path].name} - {handler.handler_name} 终止了事件传播。"
                )
                return

    async def call_handler(
        self,
        event: AstrMessageEvent,
        handler: T.Awaitable,
        *args,
        **kwargs,
    ) -> T.AsyncGenerator[None, None]:
        """执行事件处理函数并处理其返回结果

        该方法负责调用处理函数并处理不同类型的返回值。它支持两种类型的处理函数:
        1. 异步生成器: 实现洋葱模型，每次 yield 都会将控制权交回上层
        2. 协程: 执行一次并处理返回值

        Args:
            ctx (PipelineContext): 消息管道上下文对象
            event (AstrMessageEvent): 事件对象
            handler (Awaitable): 事件处理函数

        Returns:
            AsyncGenerator[None, None]: 异步生成器，用于在管道中传递控制流
        """
        ready_to_call = None  # 一个协程或者异步生成器

        trace_ = None

        try:
            ready_to_call = handler(event, *args, **kwargs)
        except TypeError as _:
            # 向下兼容
            trace_ = traceback.format_exc()
            # 以前的 handler 会额外传入一个参数, 但是 context 对象实际上在插件实例中有一份
            ready_to_call = handler(event, self.plugin_manager.context, *args, **kwargs)

        if isinstance(ready_to_call, T.AsyncGenerator):
            _has_yielded = False
            try:
                async for ret in ready_to_call:
                    # 这里逐步执行异步生成器, 对于每个 yield 返回的 ret, 执行下面的代码
                    # 返回值只能是 MessageEventResult 或者 None（无返回值）
                    _has_yielded = True
                    if isinstance(ret, (MessageEventResult, CommandResult)):
                        # 如果返回值是 MessageEventResult, 设置结果并继续
                        event.set_result(ret)
                        yield
                    else:
                        # 如果返回值是 None, 则不设置结果并继续
                        # 继续执行后续阶段
                        yield ret
                if not _has_yielded:
                    # 如果这个异步生成器没有执行到 yield 分支
                    yield
            except Exception as e:
                logger.error(f"Previous Error: {trace_}")
                raise e
        elif inspect.iscoroutine(ready_to_call):
            # 如果只是一个协程, 直接执行
            ret = await ready_to_call
            if isinstance(ret, (MessageEventResult, CommandResult)):
                event.set_result(ret)
                yield
            else:
                yield ret
