"""v4 原生插件基类。"""

from __future__ import annotations

import json
import traceback
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Any, cast

from loguru import logger

from .errors import AstrBotError
from .plugin_kv import PluginKVStoreMixin

if TYPE_CHECKING:
    from .context import Context


class Star(PluginKVStoreMixin):
    """v4 原生插件基类。"""

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

    @property
    def context(self) -> Context | None:
        return self._context_var().get()

    def _require_runtime_context(self) -> Context:
        ctx = self.context
        if ctx is None:
            raise RuntimeError(
                "Star runtime context is only available during lifecycle, "
                "handler, and registered LLM tool execution"
            )
        return ctx

    def _context_var(self) -> ContextVar[Context | None]:
        existing_context_var = getattr(self, "__astrbot_context_var__", None)
        if isinstance(existing_context_var, ContextVar):
            return cast("ContextVar[Context | None]", existing_context_var)
        created_context_var: ContextVar[Context | None] = ContextVar(
            f"astrbot_sdk_star_context_{id(self)}",
            default=None,
        )
        setattr(self, "__astrbot_context_var__", created_context_var)
        return created_context_var

    def _bind_runtime_context(self, ctx: Context | None) -> Token[Context | None]:
        return self._context_var().set(ctx)

    def _reset_runtime_context(self, token: Token[Context | None]) -> None:
        self._context_var().reset(token)

    async def on_start(self, ctx: Any | None = None) -> None:
        await self.initialize()

    async def on_stop(self, ctx: Any | None = None) -> None:
        await self.terminate()

    async def initialize(self) -> None:
        return None

    async def terminate(self) -> None:
        return None

    async def text_to_image(
        self,
        text: str,
        *,
        return_url: bool = True,
    ) -> str:
        return await self._require_runtime_context().text_to_image(
            text,
            return_url=return_url,
        )

    async def html_render(
        self,
        tmpl: str,
        data: dict[str, Any],
        *,
        return_url: bool = True,
        options: dict[str, Any] | None = None,
    ) -> str:
        return await self._require_runtime_context().html_render(
            tmpl,
            data,
            return_url=return_url,
            options=options,
        )

    async def on_error(self, error: Exception, event, ctx) -> None:
        if isinstance(error, AstrBotError):
            lines: list[str] = []
            if error.retryable:
                lines.append("请求失败，请稍后重试")
            elif error.hint:
                lines.append(error.hint)
            else:
                lines.append(error.message)
            if error.docs_url:
                lines.append(f"文档：{error.docs_url}")
            if error.details:
                lines.append(
                    f"详情：{json.dumps(error.details, ensure_ascii=False, sort_keys=True)}"
                )
            await event.reply("\n".join(lines))
        else:
            await event.reply("出了点问题，请联系插件作者")
        logger.error("handler 执行失败\n{}", traceback.format_exc())

    @classmethod
    def __astrbot_is_new_star__(cls) -> bool:
        return True
