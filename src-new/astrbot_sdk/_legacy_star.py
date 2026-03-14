"""旧版 API 兼容层 — 插件基类与注册装饰器。

这个模块承接旧 ``Star`` / ``CommandComponent`` / ``register`` 的实现，
供旧版插件在不修改代码的情况下继续运行。

依赖关系：
- ``_legacy_context`` 提供 ``LegacyContext``（单向依赖，本模块不被 ``_legacy_context`` 导入）
- ``_legacy_llm`` 提供 ``CompatLLMToolManager``

外部代码应通过 ``_legacy_api`` 聚合入口导入，而不是直接导入本模块。
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ._legacy_context import LegacyContext
from ._legacy_llm import CompatLLMToolManager
from .star import Star


class StarTools:
    """旧版 ``StarTools`` 的最小兼容实现。"""

    @staticmethod
    def get_data_dir() -> Path:
        frame = inspect.currentframe()
        caller = frame.f_back if frame is not None else None
        try:
            while caller is not None:
                caller_file = caller.f_globals.get("__file__")
                if isinstance(caller_file, str) and caller_file:
                    data_dir = Path(caller_file).resolve().parent / "data"
                    data_dir.mkdir(parents=True, exist_ok=True)
                    return data_dir
                caller = caller.f_back
        finally:
            del frame
        data_dir = Path.cwd() / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir


class LegacyStar(Star):
    """旧版 ``astrbot.api.star.Star`` 兼容基类。"""

    def __init__(self, context: LegacyContext | None = None, config: Any | None = None):
        self.context = context
        if config is not None:
            self.config = config

    def _require_legacy_context(self) -> LegacyContext:
        if self.context is None:
            raise RuntimeError("LegacyStar 尚未绑定 compat Context")
        return self.context

    async def put_kv_data(self, key: str, value: Any) -> None:
        await self._require_legacy_context().put_kv_data(key, value)

    async def get_kv_data(self, key: str, default: Any = None) -> Any:
        return await self._require_legacy_context().get_kv_data(key, default)

    async def delete_kv_data(self, key: str) -> None:
        await self._require_legacy_context().delete_kv_data(key)

    async def send_message(self, session: str, message_chain: Any) -> None:
        await self._require_legacy_context().send_message(session, message_chain)

    async def llm_generate(
        self,
        chat_provider_id: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        return await self._require_legacy_context().llm_generate(
            chat_provider_id,
            *args,
            **kwargs,
        )

    async def tool_loop_agent(
        self,
        chat_provider_id: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        return await self._require_legacy_context().tool_loop_agent(
            chat_provider_id,
            *args,
            **kwargs,
        )

    async def add_llm_tools(self, *tools: Any) -> None:
        await self._require_legacy_context().add_llm_tools(*tools)

    def get_llm_tool_manager(self) -> CompatLLMToolManager:
        return self._require_legacy_context().get_llm_tool_manager()

    def activate_llm_tool(self, name: str) -> bool:
        return self._require_legacy_context().activate_llm_tool(name)

    def deactivate_llm_tool(self, name: str) -> bool:
        return self._require_legacy_context().deactivate_llm_tool(name)

    def register_llm_tool(
        self,
        name: str,
        func_args: list[dict[str, Any]],
        desc: str,
        func_obj: Callable[..., Any],
    ) -> None:
        self._require_legacy_context().register_llm_tool(
            name,
            func_args,
            desc,
            func_obj,
        )

    def unregister_llm_tool(self, name: str) -> None:
        self._require_legacy_context().unregister_llm_tool(name)

    def get_config(self) -> dict[str, Any]:
        return self._require_legacy_context().get_config()

    @classmethod
    def __astrbot_is_new_star__(cls) -> bool:
        return False

    @classmethod
    def _astrbot_create_legacy_context(cls, plugin_id: str) -> LegacyContext:
        return LegacyContext(plugin_id)


class CommandComponent(LegacyStar):
    @classmethod
    def __astrbot_is_new_star__(cls) -> bool:
        return False

    @classmethod
    def _astrbot_create_legacy_context(cls, plugin_id: str) -> LegacyContext:
        # Loader 通过这个工厂拿到旧 Context，避免核心运行时直接依赖 compat 实现。
        return LegacyContext(plugin_id)


def register(
    name: str | None = None,
    author: str | None = None,
    desc: str | None = None,
    version: str | None = None,
    repo: str | None = None,
):
    """旧版插件元数据装饰器兼容入口。"""

    metadata = {
        "name": name,
        "author": author,
        "desc": desc,
        "version": version,
        "repo": repo,
    }

    def decorator(cls):
        existing = getattr(cls, "__astrbot_plugin_metadata__", {})
        setattr(
            cls,
            "__astrbot_plugin_metadata__",
            {
                **existing,
                **{key: value for key, value in metadata.items() if value is not None},
            },
        )
        return cls

    return decorator
