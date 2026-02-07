import inspect
import traceback

from astrbot import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import EventType, star_handlers_registry


async def call_event_hook(
    event: AstrMessageEvent,
    hook_type: EventType,
    *args,
    **kwargs,
) -> bool:
    """调用事件钩子函数

    Returns:
        bool: 如果事件被终止，返回 True
    #

    """
    handlers = star_handlers_registry.get_handlers_by_event_type(
        hook_type,
        plugins_name=event.plugins_name,
    )
    for handler in handlers:
        try:
            assert inspect.iscoroutinefunction(handler.handler)
            logger.debug(
                f"hook({hook_type.name}) -> {star_map[handler.handler_module_path].name} - {handler.handler_name}",
            )
            await handler.handler(event, *args, **kwargs)
        except BaseException:
            logger.error(traceback.format_exc())

        if event.is_stopped():
            logger.info(
                f"{star_map[handler.handler_module_path].name} - {handler.handler_name} 终止了事件传播。",
            )
            return True

    return event.is_stopped()
