# =============================================================================
# 新旧对比 - context.py
# =============================================================================
#
# 【旧版 src/astrbot_sdk/api/star/context.py】
# - Context 是抽象类 (ABC)
# - 包含 conversation_manager、persona_manager 属性
# - 提供方法: llm_generate(), tool_loop_agent(), send_message(),
#            add_llm_tools(), put_kv_data(), get_kv_data(), delete_kv_data()
# - 所有方法都是抽象方法 (...)
# - 依赖: BaseConversationManager, ToolSet, FunctionTool, Message, LLMResponse, MessageChain
#
# 【新版 src-new/astrbot_sdk/context.py】
# - Context 是具体类，直接实例化
# - 包含客户端属性: llm, memory, db, platform
# - 包含: plugin_id, logger, cancel_token
# - 新增 CancelToken 数据类用于取消控制
# - 通过 CapabilityProxy 代理实现跨进程调用
#
# 【架构差异】
# - 旧版: 抽象基类，由 AstrBot Core 实现具体逻辑
# - 新版: 具体类，通过 CapabilityProxy 代理调用远程能力
#
# =============================================================================
# TODO: 功能缺失
# =============================================================================
#
# 1. 缺少 conversation_manager 属性
#    - 旧版: conversation_manager: BaseConversationManager
#    - 新版: 已移至 _legacy_api.py 的 LegacyConversationManager
#    - 迁移: 使用 ctx.db 直接操作会话数据，或使用 compat.LegacyConversationManager
#
# 2. 缺少 persona_manager 属性
#    - 旧版: persona_manager: Any
#    - 新版: 无对应实现
#    - TODO: 需要确定是否需要在 clients/ 中添加 PersonaClient
#
# 3. 缺少 _register_component() 方法
#    - 旧版: 用于注册组件实例及其公共方法
#    - 新版: 架构变化，不再需要此方法
#
# 4. 方法签名变化
#    - 旧版 llm_generate(chat_provider_id, ...): 需要 chat_provider_id
#    - 新版 LLMClient.chat_raw(prompt, ...): 不需要 chat_provider_id
#    - 迁移: 使用 ctx.llm.chat_raw() 替代 ctx.llm_generate()
#
# =============================================================================

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from loguru import logger as base_logger

from .clients import DBClient, LLMClient, MemoryClient, PlatformClient
from .clients._proxy import CapabilityProxy


@dataclass(slots=True)
class CancelToken:
    _cancelled: asyncio.Event

    def __init__(self) -> None:
        self._cancelled = asyncio.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    async def wait(self) -> None:
        await self._cancelled.wait()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise asyncio.CancelledError


class Context:
    def __init__(
        self,
        *,
        peer,
        plugin_id: str,
        cancel_token: CancelToken | None = None,
        logger: Any | None = None,
    ) -> None:
        proxy = CapabilityProxy(peer)
        self.llm = LLMClient(proxy)
        self.memory = MemoryClient(proxy)
        self.db = DBClient(proxy)
        self.platform = PlatformClient(proxy)
        self.plugin_id = plugin_id
        self.logger = logger or base_logger.bind(plugin_id=plugin_id)
        self.cancel_token = cancel_token or CancelToken()
