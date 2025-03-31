import abc
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple
from ..po import Stats, Conversation


@dataclass
class BaseDatabase(abc.ABC):
    """数据库基类"""

    def __init__(self) -> None:
        pass

    async def initialize(self):
        """初始化数据库连接"""
        pass

    @abc.abstractmethod
    async def insert_platform_metrics(self, metrics: dict):
        """插入平台指标数据"""
        raise NotImplementedError

    @abc.abstractmethod
    async def insert_llm_metrics(self, metrics: dict):
        """插入 LLM 指标数据"""
        raise NotImplementedError

    @abc.abstractmethod
    async def get_base_stats(self, offset_sec: int = 86400) -> Stats:
        """获取基础统计数据"""
        raise NotImplementedError

    @abc.abstractmethod
    async def get_total_message_count(self) -> int:
        """获取总消息数"""
        raise NotImplementedError

    @abc.abstractmethod
    async def get_grouped_base_stats(self, offset_sec: int = 86400) -> Stats:
        """获取基础统计数据(合并)"""
        raise NotImplementedError

    @abc.abstractmethod
    async def get_conversation_by_user_id(self, user_id: str, cid: str) -> Conversation:
        """通过 user_id 和 cid 获取 Conversation"""
        raise NotImplementedError

    @abc.abstractmethod
    async def new_conversation(self, user_id: str, cid: str):
        """新建 Conversation"""
        raise NotImplementedError

    @abc.abstractmethod
    async def get_conversations(self, user_id: str) -> List[Conversation]:
        raise NotImplementedError

    @abc.abstractmethod
    async def update_conversation(self, user_id: str, cid: str, history: str):
        """更新 Conversation"""
        raise NotImplementedError

    @abc.abstractmethod
    async def delete_conversation(self, user_id: str, cid: str):
        """删除 Conversation"""
        raise NotImplementedError

    @abc.abstractmethod
    async def update_conversation_title(self, user_id: str, cid: str, title: str):
        """更新 Conversation 标题"""
        raise NotImplementedError

    @abc.abstractmethod
    async def update_conversation_persona_id(self, user_id: str, cid: str, persona_id: str):
        """更新 Conversation Persona ID"""
        raise NotImplementedError

    @abc.abstractmethod
    async def get_all_conversations(
        self, page: int = 1, page_size: int = 20
    ) -> Tuple[List[Dict[str, Any]], int]:
        """获取所有对话，支持分页

        Args:
            page: 页码，从1开始
            page_size: 每页数量

        Returns:
            Tuple[List[Dict[str, Any]], int]: 返回一个元组，包含对话列表和总对话数
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def get_filtered_conversations(
        self,
        page: int = 1,
        page_size: int = 20,
        platforms: List[str] = None,
        message_types: List[str] = None,
        search_query: str = None,
        exclude_ids: List[str] = None,
        exclude_platforms: List[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """获取筛选后的对话列表

        Args:
            page: 页码
            page_size: 每页数量
            platforms: 平台筛选列表
            message_types: 消息类型筛选列表
            search_query: 搜索关键词
            exclude_ids: 排除的用户ID列表
            exclude_platforms: 排除的平台列表

        Returns:
            Tuple[List[Dict[str, Any]], int]: 返回一个元组，包含对话列表和总对话数
        """
        raise NotImplementedError
