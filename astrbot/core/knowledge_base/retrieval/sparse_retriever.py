"""稀疏检索器

使用 BM25 算法进行基于关键词的文档检索
"""

from dataclasses import dataclass
from typing import List

from rank_bm25 import BM25Okapi

from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase


@dataclass
class SparseResult:
    """稀疏检索结果"""

    chunk_id: str
    doc_id: str
    kb_id: str
    content: str
    score: float


class SparseRetriever:
    """BM25 稀疏检索器

    职责:
    - 基于关键词的文档检索
    - 使用 BM25 算法计算相关度
    """

    def __init__(self, kb_db: KBSQLiteDatabase):
        """初始化稀疏检索器

        Args:
            kb_db: 知识库数据库实例
        """
        self.kb_db = kb_db
        self._index_cache = {}  # 缓存 BM25 索引

    async def retrieve(
        self,
        query: str,
        kb_ids: List[str],
        kb_options: dict,
    ) -> List[SparseResult]:
        """执行稀疏检索

        Args:
            query: 查询文本
            kb_ids: 知识库 ID 列表
            kb_options: 每个知识库的检索选项

        Returns:
            List[SparseResult]: 检索结果列表
        """
        # 1. 获取所有相关块
        chunks = await self.kb_db.get_chunks_by_kb_ids(kb_ids)

        if not chunks:
            return []

        # 2. 准备文档和索引
        corpus = [chunk.content for chunk in chunks]
        tokenized_corpus = [doc.split() for doc in corpus]

        # 3. 构建 BM25 索引
        bm25 = BM25Okapi(tokenized_corpus)

        # 4. 执行检索
        tokenized_query = query.split()
        scores = bm25.get_scores(tokenized_query)

        # 5. 排序并返回 Top-K
        results = []
        for idx, score in enumerate(scores):
            chunk = chunks[idx]
            results.append(
                SparseResult(
                    chunk_id=chunk.chunk_id,
                    doc_id=chunk.doc_id,
                    kb_id=chunk.kb_id,
                    content=chunk.content,
                    score=float(score),
                )
            )

        results.sort(key=lambda x: x.score, reverse=True)
        return results[: len(results) // len(kb_ids)]
