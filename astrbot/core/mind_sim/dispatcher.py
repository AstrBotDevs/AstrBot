"""MindSim 调度器 - 负责将消息分发到对应的处理模块

根据会话类型（私聊/群聊）分发到不同的处理模块：
- 私聊：mind_sim.private
- 群聊：mind_sim.group（暂未实现）

调度器还负责：
- 维护会话状态
- 管理 MindSim 实例的生命周期
- 处理消息的输入输出
- 返回事件流供外部监听
"""

import asyncio
from collections.abc import AsyncGenerator
from typing import Optional

from astrbot.core import logger
from astrbot.core.mind_sim.context import MindContext
from astrbot.core.mind_sim.llm import MindSimLLM
from astrbot.core.mind_sim.messages import MindEvent


class MindSimDispatcher:
    """MindSim 调度器

    负责将消息分发到对应的处理模块，并管理 MindSim 实例。
    """

    def __init__(self):
        self._instances: dict[str, "MindSimInstance"] = {}
        self._lock = asyncio.Lock()

    async def dispatch(
        self,
        ctx: MindContext,
        message: str,
        sender_id: str,
        sender_name: str,
        llm: Optional[MindSimLLM] = None,
        persona: Optional[dict] = None,
    ) -> AsyncGenerator[MindEvent, None]:
        """分发消息到对应的处理模块

        Args:
            ctx: MindContext 会话上下文
            message: 用户消息
            sender_id: 发送者 ID
            sender_name: 发送者名称
            llm: MindSimLLM 实例（首次创建 Brain 时使用）
            persona: Personality 高级人格配置

        Yields:
            MindEvent: 事件流
        """
        session_id = ctx.session_id

        # 获取或创建实例
        async with self._lock:
            if session_id not in self._instances:
                # 根据会话类型选择处理模块
                if ctx.is_private:
                    from .private.brain import PrivateBrain

                    handler = PrivateBrain(ctx, persona=persona, llm=llm)
                    logger.info(f"[Dispatcher] 创建私聊 Brain 实例: {session_id}")
                else:
                    # 群聊暂未实现，使用私聊处理
                    logger.warning(
                        f"[Dispatcher] 群聊处理暂未实现，降级为私聊处理: {session_id}"
                    )
                    from .private.brain import PrivateBrain

                    handler = PrivateBrain(ctx, persona=persona, llm=llm)
                    handler._is_fallback = True

                self._instances[session_id] = MindSimInstance(
                    session_id=session_id,
                    handler=handler,
                )
            else:
                instance = self._instances[session_id]
                # 如果传入了新的 llm，更新已有实例
                if llm and not instance.handler.llm:
                    instance.handler.set_llm(llm)

            instance = self._instances[session_id]

        # 发送消息到 Brain
        await instance.handler.handle_message(message, sender_id, sender_name)

        # 返回 Brain 的输出事件流
        async for event in instance.handler.get_event_stream():
            yield event

    async def get_instance(self, session_id: str) -> Optional["MindSimInstance"]:
        """获取已存在的实例

        Args:
            session_id: 会话 ID

        Returns:
            MindSimInstance 或 None
        """
        return self._instances.get(session_id)

    async def remove_instance(self, session_id: str):
        """移除实例

        Args:
            session_id: 会话 ID
        """
        async with self._lock:
            if session_id in self._instances:
                instance = self._instances.pop(session_id)
                await instance.handler.stop()
                logger.info(f"[Dispatcher] 移除实例: {session_id}")

    async def stop_all(self):
        """停止所有实例"""
        async with self._lock:
            for session_id, instance in self._instances.items():
                await instance.handler.stop()
                logger.info(f"[Dispatcher] 停止实例: {session_id}")
            self._instances.clear()
            logger.info("[Dispatcher] 已停止所有实例")


class MindSimInstance:
    """MindSim 实例"""

    def __init__(self, session_id: str, handler):
        self.session_id = session_id
        self.handler = handler


# 全局调度器实例
_dispatcher: Optional[MindSimDispatcher] = None


def get_dispatcher() -> MindSimDispatcher:
    """获取全局调度器实例"""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = MindSimDispatcher()
    return _dispatcher
