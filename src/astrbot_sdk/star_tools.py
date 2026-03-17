from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from ._star_runtime import current_star_context
from .context import Context
from .message_components import BaseMessageComponent
from .message_result import MessageChain
from .message_session import MessageSession


class _StarToolsContextDescriptor:
    def __get__(self, _instance: object, _owner: type[object]) -> Context | None:
        return current_star_context()


class StarTools:
    """Star 工具类，提供类方法访问运行时上下文能力。

    所有方法都通过当前上下文动态路由到对应的能力接口。
    只在 lifecycle、handler 和已注册的 LLM tool 执行期间可用。
    """

    _context = _StarToolsContextDescriptor()

    @classmethod
    def _get_context(cls) -> Context | None:
        """获取当前 Star 运行时上下文。"""
        return cls._context

    @classmethod
    def _require_context(cls) -> Context:
        """获取当前运行时上下文，如果不存在则抛出 RuntimeError。"""
        ctx = current_star_context()
        if ctx is None:
            raise RuntimeError(
                "StarTools context is only available during lifecycle, "
                "handler, and registered LLM tool execution"
            )
        return ctx

    @classmethod
    def get_llm_tool_manager(cls):
        return cls._require_context().get_llm_tool_manager()

    @classmethod
    async def activate_llm_tool(cls, name: str) -> bool:
        return await cls._require_context().activate_llm_tool(name)

    @classmethod
    async def deactivate_llm_tool(cls, name: str) -> bool:
        return await cls._require_context().deactivate_llm_tool(name)

    @classmethod
    async def send_message(
        cls,
        session: str | MessageSession,
        content: (
            str
            | MessageChain
            | Sequence[BaseMessageComponent]
            | Sequence[dict[str, Any]]
        ),
    ) -> dict[str, Any]:
        return await cls._require_context().send_message(session, content)

    @classmethod
    async def send_message_by_id(
        cls,
        type: str,
        id: str,
        content: (
            str
            | MessageChain
            | Sequence[BaseMessageComponent]
            | Sequence[dict[str, Any]]
        ),
        *,
        platform: str,
    ) -> dict[str, Any]:
        return await cls._require_context().send_message_by_id(
            type,
            id,
            content,
            platform=platform,
        )

    @classmethod
    async def register_llm_tool(
        cls,
        name: str,
        parameters_schema: dict[str, Any],
        desc: str,
        func_obj: Callable[..., Awaitable[Any]] | Callable[..., Any],
        *,
        active: bool = True,
    ) -> list[str]:
        return await cls._require_context().register_llm_tool(
            name,
            parameters_schema,
            desc,
            func_obj,
            active=active,
        )

    @classmethod
    async def unregister_llm_tool(cls, name: str) -> bool:
        return await cls._require_context().unregister_llm_tool(name)
