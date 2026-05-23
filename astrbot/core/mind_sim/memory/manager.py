"""MindSim 记忆管理器 - 统一协调入口

每个 chat_id 一个实例（单例），协调对话记忆总结和人物记忆更新。
"""

import asyncio

from astrbot.core import logger
from astrbot.core.db import BaseDatabase
from astrbot.core.mind_sim.AgentMindSubStage import AgentMindSubStage
from astrbot.core.mind_sim.context import MindContext

from .chat_summarizer import ChatSummarizer
from .person_memory import PersonMemoryManager


class MemoryManager:
    """统一记忆管理入口"""

    _instances: dict[str, "MemoryManager"] = {}

    def __init__(self, chat_id: str, mind_ctx: MindContext, db: BaseDatabase):
        self.chat_id = chat_id
        self.mind_ctx = mind_ctx
        self.db = db
        self._agent_mind = self._create_agent_mind()
        self.chat_summarizer = ChatSummarizer(chat_id, self._agent_mind, db)
        self.person_memory = PersonMemoryManager(self._agent_mind, db)
        self._periodic_task: asyncio.Task | None = None
        self._running = False

    def _create_agent_mind(self) -> AgentMindSubStage:
        """Create AgentMindSubStage instance using MindContext"""
        persona_config = self.mind_ctx.personality_config.get("robot_config", {})
        return AgentMindSubStage.create_for_brain(
            event=self.mind_ctx.event,
            plugin_context=self.mind_ctx.plugin_context,
            persona_config=persona_config,
        )

    async def start(self):
        """启动周期性检查任务"""
        if self._running:
            return
        self._running = True
        self._periodic_task = asyncio.create_task(self._periodic_loop())
        logger.info(f"[记忆管理-{self.chat_id[:8]}] 已启动周期性检查")

    async def stop(self):
        """停止"""
        self._running = False
        if self._periodic_task:
            self._periodic_task.cancel()
            try:
                await self._periodic_task
            except asyncio.CancelledError:
                pass
            self._periodic_task = None
        logger.info(f"[记忆管理-{self.chat_id[:8]}] 已停止")

    async def on_message(
        self, user_id: str, nickname: str, content: str, role: str = "user"
    ):
        """收到消息时调用（用户消息和AI回复都要推入）"""
        self.chat_summarizer.add_message(user_id, nickname, content, role)

    async def on_conversation_end(
        self, user_id: str, nickname: str, conversation_text: str
    ):
        """对话结束时调用

        1. 立即执行一次话题检查
        2. 更新人物记忆
        """
        try:
            # 立即执行话题检查（不等周期）
            await self.chat_summarizer.process()
        except Exception as e:
            logger.error(f"[记忆管理] 话题检查失败: {e}")

        try:
            # 更新人物记忆
            await self.person_memory.update_person_memory(
                self.chat_id, user_id, nickname, conversation_text
            )
        except Exception as e:
            logger.error(f"[记忆管理] 人物记忆更新失败: {e}")

    async def _periodic_loop(self):
        """周期性检查循环（60秒间隔）"""
        try:
            while self._running:
                try:
                    await self.chat_summarizer.process()
                except Exception as e:
                    logger.error(f"[记忆管理] 周期检查出错: {e}")
                await asyncio.sleep(self.chat_summarizer.check_interval)
        except asyncio.CancelledError:
            pass

    def get_snapshot(self) -> dict:
        """获取状态快照（用于持久化）"""
        return self.chat_summarizer.get_snapshot()

    def restore_from_snapshot(self, data: dict):
        """从快照恢复状态"""
        self.chat_summarizer.restore_from_snapshot(data)

    @classmethod
    def get_or_create(
        cls, chat_id: str, mind_ctx: MindContext, db: BaseDatabase
    ) -> "MemoryManager":
        """获取或创建实例（单例 per chat_id）"""
        if chat_id not in cls._instances:
            cls._instances[chat_id] = MemoryManager(chat_id, mind_ctx, db)
            logger.info(f"[记忆管理] 创建新实例: {chat_id[:8]}")
        return cls._instances[chat_id]

    @classmethod
    def remove_instance(cls, chat_id: str):
        """移除实例"""
        inst = cls._instances.pop(chat_id, None)
        if inst:
            inst._running = False

    @classmethod
    def get_all_instances(cls) -> dict[str, "MemoryManager"]:
        """获取所有实例"""
        return cls._instances
