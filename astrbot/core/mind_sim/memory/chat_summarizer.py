"""MindSim 对话记忆总结器

复刻 MaiBot ChatHistorySummarizer 核心逻辑：
- 累积消息 → 话题识别 → 话题总结 → 持久化存储
- 话题缓存持久化到数据库 JSON 字段，避免重启丢失
"""

import difflib
import json
import time
from dataclasses import dataclass, field

from astrbot.core import logger
from astrbot.core.db import BaseDatabase
from astrbot.core.mind_sim.AgentMindSubStage import AgentMindSubStage

from .models import MindSimChatMemory
from .prompts import TOPIC_ANALYSIS_PROMPT, TOPIC_SUMMARY_PROMPT
from .utils import extract_json_from_response


@dataclass
class MessageItem:
    """单条消息"""

    user_id: str
    nickname: str
    content: str
    role: str  # "user" | "assistant"
    timestamp: float = field(default_factory=time.time)

    def to_readable(self, idx: int) -> str:
        """转为带编号的可读文本"""
        return f"{idx}. [{self.nickname}]: {self.content}"

    def to_text(self) -> str:
        """转为不带编号的文本"""
        return f"[{self.nickname}]: {self.content}"


@dataclass
class TopicCacheItem:
    """话题缓存项

    Attributes:
        topic: 话题标题（一句话描述时间、人物、事件和主题）
        messages: 与该话题相关的消息字符串列表
        participants: 涉及到的发言人昵称集合
        no_update_checks: 连续多少次"检查"没有新增内容
    """

    topic: str
    messages: list[str] = field(default_factory=list)
    participants: set[str] = field(default_factory=set)
    no_update_checks: int = 0


class ChatSummarizer:
    """对话记忆总结器

    核心流程（与 MaiBot 一致）：
    1. add_message() - 外部推入消息
    2. process() - 定期调用，检查是否需要话题识别
    3. 触发条件：消息数≥30 或 距上次检查>2小时且消息≥10
    4. _run_topic_check() - LLM识别话题，返回 topic→indices
    5. 话题相似度检查（difflib, 阈值90%）
    6. 更新 topic_cache，无更新的话题 no_update_checks+1
    7. 打包条件：连续3次无更新 或 消息>5条
    8. _finalize_and_store_topic() - LLM总结 → 写入数据库
    """

    def __init__(
        self,
        chat_id: str,
        agent_mind: AgentMindSubStage,
        db: BaseDatabase,
        check_interval: int = 60,
    ):
        self.chat_id = chat_id
        self.agent_mind = agent_mind
        self.db = db
        self.check_interval = check_interval

        # 消息缓冲区
        self.message_buffer: list[MessageItem] = []
        self.buffer_start_time: float = 0.0
        self.buffer_end_time: float = 0.0

        # 话题缓存
        self.topic_cache: dict[str, TopicCacheItem] = {}

        # 时间记录
        self.last_topic_check_time: float = time.time()

        # 日志前缀
        self._log_prefix = f"[记忆-{chat_id[:8] if len(chat_id) > 8 else chat_id}]"

    def add_message(
        self, user_id: str, nickname: str, content: str, role: str = "user"
    ):
        """外部推入消息"""
        if not content or not content.strip():
            return

        msg = MessageItem(
            user_id=user_id,
            nickname=nickname,
            content=content.strip(),
            role=role,
        )
        self.message_buffer.append(msg)

        now = time.time()
        if not self.buffer_start_time:
            self.buffer_start_time = now
        self.buffer_end_time = now

    async def process(self):
        """处理消息缓冲区，检查是否需要话题识别"""
        if not self.message_buffer:
            return

        current_time = time.time()
        message_count = len(self.message_buffer)
        time_since_last_check = current_time - self.last_topic_check_time

        # 检查触发条件（阈值比 MaiBot 小，适配私聊场景）
        should_check = False

        # 条件1: 消息数量 >= 30
        if message_count >= 30:
            should_check = True
            logger.info(
                f"{self._log_prefix} 触发检查: 消息数量达到 {message_count} 条（阈值: 30）"
            )

        # 条件2: 距上次检查 > 2小时 且消息 >= 10 条
        elif time_since_last_check > 7200 and message_count >= 10:
            should_check = True
            logger.info(
                f"{self._log_prefix} 触发检查: 距上次 {time_since_last_check / 3600:.1f}h 且消息 {message_count} 条"
            )

        if should_check:
            await self._run_topic_check_and_update_cache()
            # 清空缓冲区
            self.message_buffer.clear()
            self.buffer_start_time = 0.0
            self.buffer_end_time = 0.0
            self.last_topic_check_time = current_time

    async def _run_topic_check_and_update_cache(self):
        """执行话题检查并更新缓存

        与 MaiBot _run_topic_check_and_update_cache 逻辑一致：
        1. 检查是否有 assistant 发言
        2. 构造编号消息
        3. LLM 识别话题
        4. 相似度合并
        5. 更新缓存
        6. 检查打包条件
        """
        messages = self.message_buffer
        if not messages:
            return

        start_time = self.buffer_start_time or time.time()
        end_time = self.buffer_end_time or time.time()

        logger.info(f"{self._log_prefix} 开始话题检查 | 消息数: {len(messages)}")

        # 1. 检查是否有 assistant 发言
        has_bot_message = any(m.role == "assistant" for m in messages)
        if not has_bot_message:
            logger.info(f"{self._log_prefix} 当前批次无 Bot 发言，跳过")
            return

        # 2. 构造编号消息
        numbered_lines: list[str] = []
        index_to_text: dict[int, str] = {}
        index_to_participants: dict[int, set[str]] = {}

        for idx, msg in enumerate(messages, start=1):
            line = msg.to_readable(idx)
            numbered_lines.append(line)
            index_to_text[idx] = msg.to_text()
            index_to_participants[idx] = {msg.nickname}

        # 3. LLM 识别话题（最多重试3次）
        existing_topics = list(self.topic_cache.keys())
        topic_to_indices: dict[str, list[int]] = {}
        success = False

        for attempt in range(1, 4):
            success, topic_to_indices = await self._analyze_topics_with_llm(
                numbered_lines, existing_topics
            )
            if success and topic_to_indices:
                if attempt > 1:
                    logger.info(f"{self._log_prefix} 话题识别第 {attempt} 次重试成功")
                break
            logger.warning(f"{self._log_prefix} 话题识别第 {attempt} 次失败")

        if not success or not topic_to_indices:
            logger.error(f"{self._log_prefix} 话题识别连续3次失败，放弃本次检查")
            return

        # 4. 相似度合并（与 MaiBot 一致，阈值90%）
        topic_mapping = self._build_topic_mapping(topic_to_indices, 0.9)
        if topic_mapping:
            new_topic_to_indices: dict[str, list[int]] = {}
            for new_topic, indices in topic_to_indices.items():
                if new_topic in topic_mapping:
                    historical_topic = topic_mapping[new_topic]
                    if historical_topic in new_topic_to_indices:
                        combined = list(
                            set(new_topic_to_indices[historical_topic] + indices)
                        )
                        new_topic_to_indices[historical_topic] = combined
                    else:
                        new_topic_to_indices[historical_topic] = indices
                else:
                    new_topic_to_indices[new_topic] = indices
            topic_to_indices = new_topic_to_indices

        # 5. 更新缓存
        updated_topics: set[str] = set()

        for topic, indices in topic_to_indices.items():
            if not indices:
                continue

            item = self.topic_cache.get(topic)
            if not item:
                item = TopicCacheItem(topic=topic)
                self.topic_cache[topic] = item

            topic_msg_texts: list[str] = []
            new_participants: set[str] = set()
            for idx in indices:
                msg_text = index_to_text.get(idx)
                if not msg_text:
                    continue
                topic_msg_texts.append(msg_text)
                new_participants.update(index_to_participants.get(idx, set()))

            if not topic_msg_texts:
                continue

            merged_text = "\n".join(topic_msg_texts)
            item.messages.append(merged_text)
            item.participants.update(new_participants)
            item.no_update_checks = 0
            updated_topics.add(topic)

        # 对未更新的话题 no_update_checks + 1
        for topic, item in list(self.topic_cache.items()):
            if topic not in updated_topics:
                item.no_update_checks += 1

        # 6. 检查打包条件（与 MaiBot 一致）
        topics_to_finalize: list[str] = []
        for topic, item in self.topic_cache.items():
            if item.no_update_checks >= 3:
                logger.info(f"{self._log_prefix} 话题[{topic}] 连续3次无新增，触发打包")
                topics_to_finalize.append(topic)
                continue
            if len(item.messages) > 5:
                logger.info(f"{self._log_prefix} 话题[{topic}] 消息超过5条，触发打包")
                topics_to_finalize.append(topic)

        for topic in topics_to_finalize:
            item = self.topic_cache.get(topic)
            if not item:
                continue
            try:
                await self._finalize_and_store_topic(
                    topic=topic,
                    item=item,
                    start_time=start_time,
                    end_time=end_time,
                )
            finally:
                self.topic_cache.pop(topic, None)

    async def _analyze_topics_with_llm(
        self,
        numbered_lines: list[str],
        existing_topics: list[str],
    ) -> tuple[bool, dict[str, list[int]]]:
        """使用 LLM 识别话题（与 MaiBot _analyze_topics_with_llm 一致）"""
        if not numbered_lines:
            return False, {}

        history_topics_block = (
            "\n".join(f"- {t}" for t in existing_topics)
            if existing_topics
            else "（当前无历史话题）"
        )
        messages_block = "\n".join(numbered_lines)

        prompt = TOPIC_ANALYSIS_PROMPT.format(
            history_topics_block=history_topics_block,
            messages_block=messages_block,
        )

        try:
            response = await self.agent_mind.call_simple(prompt=prompt, role="fast", temperature=0.3)

            logger.debug(f"{self._log_prefix} 话题识别响应: {response[:200]}...")

            result = extract_json_from_response(response)
            if not isinstance(result, list):
                logger.error(f"{self._log_prefix} 话题识别返回非列表: {result}")
                return False, {}

            topic_to_indices: dict[str, list[int]] = {}
            for item in result:
                if not isinstance(item, dict):
                    continue
                topic = item.get("topic")
                indices = item.get("message_indices") or item.get("messages") or []
                if not topic or not isinstance(topic, str):
                    continue
                if isinstance(indices, list):
                    valid_indices: list[int] = []
                    for v in indices:
                        try:
                            iv = int(v)
                            if iv > 0:
                                valid_indices.append(iv)
                        except (TypeError, ValueError):
                            continue
                    if valid_indices:
                        topic_to_indices[topic] = valid_indices

            return True, topic_to_indices

        except Exception as e:
            logger.error(f"{self._log_prefix} 话题识别 LLM 调用失败: {e}")
            return False, {}

    def _find_most_similar_topic(
        self,
        new_topic: str,
        existing_topics: list[str],
        similarity_threshold: float = 0.9,
    ) -> tuple[str, float] | None:
        """查找最相似的历史话题（与 MaiBot 一致）"""
        if not existing_topics:
            return None

        best_match = None
        best_similarity = 0.0

        for existing_topic in existing_topics:
            similarity = difflib.SequenceMatcher(
                None, new_topic, existing_topic
            ).ratio()
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = existing_topic

        if best_match and best_similarity >= similarity_threshold:
            return (best_match, best_similarity)
        return None

    def _build_topic_mapping(
        self,
        topic_to_indices: dict[str, list[int]],
        similarity_threshold: float = 0.9,
    ) -> dict[str, str]:
        """构建新话题到历史话题的映射（与 MaiBot 一致）"""
        existing_topics_list = list(self.topic_cache.keys())
        topic_mapping: dict[str, str] = {}

        for new_topic in topic_to_indices.keys():
            if new_topic in existing_topics_list:
                continue
            result = self._find_most_similar_topic(
                new_topic, existing_topics_list, similarity_threshold
            )
            if result:
                historical_topic, similarity = result
                topic_mapping[new_topic] = historical_topic
                logger.info(
                    f"{self._log_prefix} 话题相似度: '{new_topic}' ≈ '{historical_topic}' ({similarity:.0%})"
                )

        return topic_mapping

    async def _finalize_and_store_topic(
        self,
        topic: str,
        item: TopicCacheItem,
        start_time: float,
        end_time: float,
    ):
        """对话题进行最终打包存储（与 MaiBot 一致）"""
        if not item.messages:
            logger.info(f"{self._log_prefix} 话题[{topic}] 无消息，跳过")
            return

        original_text = "\n".join(item.messages)

        logger.info(
            f"{self._log_prefix} 打包话题[{topic}] | 消息段数: {len(item.messages)}"
        )

        # LLM 总结
        success, keywords, summary, key_point = await self._compress_with_llm(
            original_text, topic
        )
        if not success:
            logger.warning(f"{self._log_prefix} 话题[{topic}] LLM 概括失败")
            return

        participants = list(item.participants)

        await self._store_to_database(
            start_time=start_time,
            end_time=end_time,
            original_text=original_text,
            participants=participants,
            theme=topic,
            keywords=keywords,
            summary=summary,
            key_point=key_point,
        )

        logger.info(
            f"{self._log_prefix} 话题[{topic}] 存储成功 | 参与者: {len(participants)}"
        )

    async def _compress_with_llm(
        self, original_text: str, topic: str
    ) -> tuple[bool, list[str], str, list[str]]:
        """使用 LLM 总结话题（与 MaiBot _compress_with_llm 一致）"""
        prompt = TOPIC_SUMMARY_PROMPT.format(topic=topic, original_text=original_text)

        try:
            response = await self.agent_mind.call_simple(prompt=prompt, role="fast")

            result = extract_json_from_response(response)
            if not isinstance(result, dict):
                logger.error(f"{self._log_prefix} 话题总结返回非字典: {result}")
                return False, [], "", []

            keywords = result.get("keywords", [])
            summary = result.get("summary", "")
            key_point = result.get("key_point", [])

            if not isinstance(keywords, list):
                keywords = []
            if not isinstance(summary, str) or not summary:
                return False, [], "", []
            if not isinstance(key_point, list):
                key_point = []

            return True, keywords, summary, key_point

        except Exception as e:
            logger.error(f"{self._log_prefix} 话题总结 LLM 调用失败: {e}")
            return False, [], "", []

    async def _store_to_database(
        self,
        start_time: float,
        end_time: float,
        original_text: str,
        participants: list[str],
        theme: str,
        keywords: list[str],
        summary: str,
        key_point: list[str] | None = None,
    ):
        """存储到数据库"""
        try:
            record = MindSimChatMemory(
                chat_id=self.chat_id,
                start_time=start_time,
                end_time=end_time,
                original_text=original_text,
                participants=json.dumps(participants, ensure_ascii=False),
                theme=theme,
                keywords=json.dumps(keywords, ensure_ascii=False),
                summary=summary,
                key_point=(
                    json.dumps(key_point, ensure_ascii=False) if key_point else None
                ),
                count=0,
            )

            async with self.db.get_db() as session:
                async with session.begin():
                    session.add(record)

            logger.debug(f"{self._log_prefix} 成功存储聊天记忆到数据库")

        except Exception as e:
            logger.error(f"{self._log_prefix} 存储到数据库失败: {e}")
            import traceback

            traceback.print_exc()

    def get_topic_cache_snapshot(self) -> dict:
        """获取话题缓存快照（用于持久化）"""
        return {
            "last_topic_check_time": self.last_topic_check_time,
            "topics": {
                topic: {
                    "messages": item.messages,
                    "participants": list(item.participants),
                    "no_update_checks": item.no_update_checks,
                }
                for topic, item in self.topic_cache.items()
            },
            "buffer": {
                "messages": [
                    {
                        "user_id": m.user_id,
                        "nickname": m.nickname,
                        "content": m.content,
                        "role": m.role,
                        "timestamp": m.timestamp,
                    }
                    for m in self.message_buffer
                ],
                "start_time": self.buffer_start_time,
                "end_time": self.buffer_end_time,
            },
        }

    def load_from_snapshot(self, data: dict):
        """从快照恢复状态"""
        if not data:
            return

        self.last_topic_check_time = data.get(
            "last_topic_check_time", self.last_topic_check_time
        )

        # 恢复话题缓存
        topics_data = data.get("topics", {})
        for topic, payload in topics_data.items():
            self.topic_cache[topic] = TopicCacheItem(
                topic=topic,
                messages=payload.get("messages", []),
                participants=set(payload.get("participants", [])),
                no_update_checks=payload.get("no_update_checks", 0),
            )

        # 恢复消息缓冲区
        buffer_data = data.get("buffer", {})
        buffer_messages = buffer_data.get("messages", [])
        for m in buffer_messages:
            self.message_buffer.append(
                MessageItem(
                    user_id=m.get("user_id", ""),
                    nickname=m.get("nickname", ""),
                    content=m.get("content", ""),
                    role=m.get("role", "user"),
                    timestamp=m.get("timestamp", time.time()),
                )
            )
        self.buffer_start_time = buffer_data.get("start_time", 0.0)
        self.buffer_end_time = buffer_data.get("end_time", 0.0)

        if self.topic_cache or self.message_buffer:
            logger.info(
                f"{self._log_prefix} 恢复缓存: {len(self.topic_cache)} 个话题, "
                f"{len(self.message_buffer)} 条消息"
            )
