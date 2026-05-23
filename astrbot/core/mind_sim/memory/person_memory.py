"""MindSim 人物记忆管理

从对话中提取人物印象并持久化更新。
"""

import json

from astrbot.core import logger
from astrbot.core.db import BaseDatabase
from astrbot.core.mind_sim.AgentMindSubStage import AgentMindSubStage

from .models import MindSimPersonMemory
from .prompts import PERSON_IMPRESSION_PROMPT
from .utils import extract_json_from_response


class PersonMemoryManager:
    """人物记忆管理器"""

    def __init__(self, agent_mind: AgentMindSubStage, db: BaseDatabase):
        self.agent_mind = agent_mind
        self.db = db

    async def update_person_memory(
        self,
        chat_id: str,
        user_id: str,
        nickname: str,
        conversation_text: str,
    ):
        """对话结束后，提取人物印象并更新

        Args:
            chat_id: 对话标识
            user_id: 用户ID
            nickname: 用户昵称
            conversation_text: 本次对话文本
        """
        if not conversation_text or not conversation_text.strip():
            return

        log_prefix = f"[人物记忆-{nickname}]"

        try:
            # 1. 查询已有记忆
            existing = await self._get_existing_memory(chat_id, user_id)
            existing_impression = "（暂无已有印象）"
            if existing:
                existing_impression = (
                    f"印象：{existing.impression}\n"
                    f"性格特点：{existing.traits or '未知'}\n"
                    f"关系：{existing.relationship or '未知'}\n"
                    f"记忆事件：{existing.memorable_events or '无'}"
                )

            # 2. LLM 分析本次对话
            prompt = PERSON_IMPRESSION_PROMPT.format(
                nickname=nickname,
                user_id=user_id,
                existing_impression=existing_impression,
                conversation_text=conversation_text[-3000:],  # 限制长度
            )

            response = await self.agent_mind.call_simple(prompt, role="fast")
            result = extract_json_from_response(response)

            if not result or not isinstance(result, dict):
                logger.warning(f"{log_prefix} LLM 返回无效 JSON，跳过更新")
                return

            impression = result.get("impression", "")
            traits = result.get("traits", [])
            relationship = result.get("relationship", "")
            memorable_events = result.get("memorable_events", [])

            if not impression:
                logger.warning(f"{log_prefix} 未提取到有效印象，跳过")
                return

            # 3. 保存/更新到数据库
            await self._save_person_memory(
                chat_id=chat_id,
                user_id=user_id,
                nickname=nickname,
                impression=impression,
                traits=json.dumps(traits, ensure_ascii=False) if traits else None,
                relationship=relationship or None,
                memorable_events=(
                    json.dumps(memorable_events, ensure_ascii=False)
                    if memorable_events
                    else None
                ),
                existing=existing,
            )

            logger.info(
                f"{log_prefix} 人物记忆已更新 | "
                f"特点: {len(traits)} 个 | 事件: {len(memorable_events)} 个"
            )

        except Exception as e:
            logger.error(f"{log_prefix} 更新人物记忆失败: {e}")

    async def _get_existing_memory(
        self, chat_id: str, user_id: str
    ) -> MindSimPersonMemory | None:
        """查询已有的人物记忆"""
        try:
            from sqlmodel import select

            async with self.db.get_db() as session:
                stmt = select(MindSimPersonMemory).where(
                    MindSimPersonMemory.chat_id == chat_id,
                    MindSimPersonMemory.user_id == user_id,
                )
                result = await session.execute(stmt)
                return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"[人物记忆] 查询失败: {e}")
            return None

    async def _save_person_memory(
        self,
        chat_id: str,
        user_id: str,
        nickname: str,
        impression: str,
        traits: str | None,
        relationship: str | None,
        memorable_events: str | None,
        existing: MindSimPersonMemory | None,
    ):
        """保存人物记忆到数据库"""
        try:
            from sqlmodel import select

            async with self.db.get_db() as session:
                async with session.begin():
                    if existing:
                        # 更新已有记录
                        stmt = select(MindSimPersonMemory).where(
                            MindSimPersonMemory.id == existing.id
                        )
                        result = await session.execute(stmt)
                        record = result.scalar_one_or_none()
                        if record:
                            record.nickname = nickname
                            record.impression = impression
                            record.traits = traits
                            record.relationship = relationship
                            record.memorable_events = memorable_events
                    else:
                        # 创建新记录
                        record = MindSimPersonMemory(
                            chat_id=chat_id,
                            user_id=user_id,
                            nickname=nickname,
                            impression=impression,
                            traits=traits,
                            relationship=relationship,
                            memorable_events=memorable_events,
                        )
                        session.add(record)
        except Exception as e:
            logger.error(f"[人物记忆] 保存失败: {e}")
            raise
