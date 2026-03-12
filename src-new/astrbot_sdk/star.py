"""v4 原生插件基类。

旧版 ``StarMetadata`` 等兼容数据类型保留在 ``astrbot_sdk.api.star``，
这里仅承载新版插件生命周期与 handler 收集逻辑。
"""

from __future__ import annotations

import traceback
from typing import Any

from loguru import logger

from .errors import AstrBotError


class Star:
    __handlers__: tuple[str, ...] = ()

    def __init_subclass__(cls, **kwargs: Any) -> None:
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
        return None

    async def on_stop(self, ctx: Any | None = None) -> None:
        return None

    async def on_error(self, error: Exception, event, ctx) -> None:
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
        return True
