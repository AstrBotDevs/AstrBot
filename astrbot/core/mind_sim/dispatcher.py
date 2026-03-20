"""MindSim 简化的 Brain 工厂模块

只负责根据会话类型创建/管理 Brain 实例，不再是全局单例。
由 internal_mind 持有和管理。

调度逻辑：
- 私聊：mind_sim.private.brain.PrivateBrain
- 群聊：降级为私聊处理（暂未实现群聊）
"""

import asyncio
from collections.abc import AsyncGenerator

from astrbot.core import logger
from astrbot.core.mind_sim.context import MindContext
from astrbot.core.mind_sim.messages import MindEvent


class PrivateBrainFactory:
    """简化的 Brain 工厂

    不再是全局单例，由 internal_mind 持有。
    职责：
    1. 根据 session_id 管理 Brain 实例映射
    2. 创建 Brain 时根据会话类型选择处理模块（私聊/群聊）
    3. 提供 dispatch 方法启动事件流
    """

    def __init__(self):
        self._instances: dict = {}
        self._lock = asyncio.Lock()

    async def dispatch(
        self,
        ctx: MindContext,
        message: str,
        sender_id: str,
        sender_name: str,
        persona: dict | None = None,
    ) -> AsyncGenerator[MindEvent, None]:
        """分发消息到对应的 Brain

        Args:
            ctx: MindContext 会话上下文
            message: 用户消息
            sender_id: 发送者 ID
            sender_name: 发送者名称
            persona: 高级人格配置

        Yields:
            MindEvent: 事件流
        """
        session_id = ctx.session_id
        is_new_instance = False

        async with self._lock:
            if session_id not in self._instances:
                # 根据会话类型选择处理模块
                if ctx.is_private:
                    from .private.brain import PrivateBrain

                    handler = PrivateBrain(ctx, persona=persona)
                    handler.init_llm(ctx.event, ctx.plugin_context, persona)
                    logger.info(f"[BrainFactory] 创建私聊 Brain 实例: {session_id}")
                else:
                    # 群聊暂未实现，降级为私聊处理
                    logger.warning(
                        f"[BrainFactory] 群聊处理暂未实现，降级为私聊处理: {session_id}"
                    )
                    from .private.brain import PrivateBrain

                    handler = PrivateBrain(ctx, persona=persona)
                    handler.init_llm(ctx.event, ctx.plugin_context, persona)
                    handler._is_fallback = True

                self._instances[session_id] = handler
                is_new_instance = True
            else:
                handler = self._instances[session_id]

        # 发送消息到 Brain
        await handler.handle_message(message, sender_id, sender_name)

        # 只有首次创建实例或没有活跃的事件流时才监听
        if is_new_instance or not handler._stream_active:
            async for event in handler.get_event_stream():
                yield event
        else:
            logger.debug(f"[BrainFactory] 实例 {session_id} 已有活跃事件流，仅投递消息")

    async def stop_all(self):
        """停止所有 Brain 实例"""
        async with self._lock:
            for session_id, instance in self._instances.items():
                await instance.stop()
                logger.info(f"[BrainFactory] 停止实例: {session_id}")
            self._instances.clear()
            logger.info("[BrainFactory] 已停止所有实例")
