"""知识库上下文注入器

负责检索相关知识并格式化为 LLM 可用的上下文文本
"""

from typing import List, Optional

from astrbot.core.knowledge_base.database import KBDatabase
from astrbot.core.knowledge_base.retrieval.manager import (
    RetrievalManager,
    RetrievalResult,
)


class KnowledgeBaseInjector:
    """知识库上下文注入器

    职责:
    - 检索相关知识
    - 格式化为上下文文本
    - 注入到 LLM Prompt
    """

    def __init__(
        self,
        kb_db: KBDatabase,
        retrieval_manager: RetrievalManager,
    ):
        """初始化知识库上下文注入器

        Args:
            kb_db: 知识库数据库实例
            retrieval_manager: 检索管理器实例
        """
        self.kb_db = kb_db
        self.retrieval_manager = retrieval_manager

    async def retrieve_and_inject(
        self,
        unified_msg_origin: str,
        query: str,
        top_k: int = 5,
    ) -> Optional[dict]:
        """检索并注入知识库上下文

        Args:
            unified_msg_origin: 统一消息来源 ID (会话 ID)
            query: 用户查询
            top_k: 返回结果数量

        Returns:
            Optional[dict]: 包含检索结果和格式化上下文的字典,如果无结果则返回 None
            {
                "context_text": str,  # 格式化的上下文文本
                "results": List[dict],  # 原始检索结果列表
            }
        """
        # 1. 获取会话关联的知识库
        kb_ids = await self.kb_db.get_session_kb_ids(unified_msg_origin)

        if not kb_ids:
            return None

        # 2. 检索知识
        results = await self.retrieval_manager.retrieve(
            query=query,
            kb_ids=kb_ids,
            top_m_final=top_k,
        )

        if not results:
            return None

        # 3. 格式化上下文
        context_text = self._format_context(results)

        # 4. 转换结果为字典格式
        results_dict = [
            {
                "chunk_id": r.chunk_id,
                "doc_id": r.doc_id,
                "kb_id": r.kb_id,
                "kb_name": r.kb_name,
                "doc_name": r.doc_name,
                "chunk_index": r.metadata.get("chunk_index", 0),
                "content": r.content,
                "score": r.score,
            }
            for r in results
        ]

        return {
            "context_text": context_text,
            "results": results_dict,
        }

    async def inject(
        self,
        session_id: str,
        query: str,
        top_k: int = 5,
    ) -> Optional[str]:
        """注入知识库上下文 (简化版本,仅返回文本)

        Args:
            session_id: 会话 ID (来自主数据库)
            query: 用户查询
            top_k: 返回结果数量

        Returns:
            Optional[str]: 格式化的知识上下文,如果无结果则返回 None
        """
        result = await self.retrieve_and_inject(
            unified_msg_origin=session_id,
            query=query,
            top_k=top_k,
        )

        return result["context_text"] if result else None

    def _format_context(self, results: List[RetrievalResult]) -> str:
        """格式化知识上下文

        Args:
            results: 检索结果列表

        Returns:
            str: 格式化的上下文文本
        """
        lines = ["以下是相关的知识库内容,请参考这些信息回答用户的问题:\n"]

        for i, result in enumerate(results, 1):
            lines.append(f"【知识 {i}】")
            lines.append(f"来源: {result.kb_name} / {result.doc_name}")
            lines.append(f"内容: {result.content}")
            lines.append(f"相关度: {result.score:.2f}")
            lines.append("")

        return "\n".join(lines)
