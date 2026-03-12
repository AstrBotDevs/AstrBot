from __future__ import annotations

import traceback
from typing import Any

from loguru import logger

from .errors import AstrBotError


class Star:
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
