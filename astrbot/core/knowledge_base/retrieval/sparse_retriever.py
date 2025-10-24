"""稀疏检索器

使用 BM25 算法进行基于关键词的文档检索
"""

import jieba
import os
import json
from dataclasses import dataclass
from typing import List
from rank_bm25 import BM25Okapi
from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
from astrbot.core.db.vec_db.faiss_impl import FaissVecDB


@dataclass
class SparseResult:
    """稀疏检索结果"""

    chunk_index: int
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

        with open(
            os.path.join(os.path.dirname(__file__), "hit_stopwords.txt"),
            "r",
            encoding="utf-8",
        ) as f:
            self.hit_stopwords = {
                word.strip() for word in set(f.read().splitlines()) if word.strip()
            }

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
        chunks = []
        for kb_id in kb_ids:
            vec_db: FaissVecDB = kb_options.get(kb_id, {}).get("vec_db")
            if not vec_db:
                continue
            result = await vec_db.document_storage.get_documents(metadata_filters={})
            chunk_mds = [json.loads(doc["metadata"]) for doc in result]
            result = [
                {
                    "chunk_id": doc["doc_id"],
                    "chunk_index": chunk_md["chunk_index"],
                    "doc_id": chunk_md["doc_id"],
                    "kb_id": kb_id,
                    "text": doc["text"],
                }
                for doc, chunk_md in zip(result, chunk_mds)
            ]
            chunks.extend(result)

        if not chunks:
            return []

        # 2. 准备文档和索引
        corpus = [chunk["text"] for chunk in chunks]
        tokenized_corpus = [list(jieba.cut(doc)) for doc in corpus]
        tokenized_corpus = [
            [word for word in doc if word not in self.hit_stopwords]
            for doc in tokenized_corpus
        ]

        # 3. 构建 BM25 索引
        bm25 = BM25Okapi(tokenized_corpus)

        # 4. 执行检索
        tokenized_query = list(jieba.cut(query))
        tokenized_query = [
            word for word in tokenized_query if word not in self.hit_stopwords
        ]
        scores = bm25.get_scores(tokenized_query)

        # 5. 排序并返回 Top-K
        results = []
        for idx, score in enumerate(scores):
            chunk = chunks[idx]
            results.append(
                SparseResult(
                    chunk_id=chunk["chunk_id"],
                    chunk_index=chunk["chunk_index"],
                    doc_id=chunk["doc_id"],
                    kb_id=chunk["kb_id"],
                    content=chunk["text"],
                    score=float(score),
                )
            )

        results.sort(key=lambda x: x.score, reverse=True)
        # return results[: len(results) // len(kb_ids)]
        return results
