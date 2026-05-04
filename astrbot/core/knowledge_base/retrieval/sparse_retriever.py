"""稀疏检索器

使用 BM25 算法进行基于关键词的文档检索
"""

import json
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rank_bm25 import BM25Okapi

from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
from astrbot.core.knowledge_base.retrieval.tokenizer import (
    load_stopwords,
    tokenize_text,
)

if TYPE_CHECKING:
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

    def __init__(self, kb_db: KBSQLiteDatabase) -> None:
        """初始化稀疏检索器

        Args:
            kb_db: 知识库数据库实例

        """
        self.kb_db = kb_db
        self._index_cache = {}  # 缓存 BM25 索引

        self.hit_stopwords = load_stopwords(
            os.path.join(os.path.dirname(__file__), "hit_stopwords.txt"),
        )

    async def retrieve(
        self,
        query: str,
        kb_ids: list[str],
        kb_options: dict,
    ) -> list[SparseResult]:
        """执行稀疏检索

        Args:
            query: 查询文本
            kb_ids: 知识库 ID 列表
            kb_options: 每个知识库的检索选项

        Returns:
            List[SparseResult]: 检索结果列表

        """
        fts_results = []
        fallback_kb_ids = []
        query_tokens = tokenize_text(query, self.hit_stopwords)
        for kb_id in kb_ids:
            vec_db: FaissVecDB | None = kb_options.get(kb_id, {}).get("vec_db")
            if not vec_db:
                continue
            top_k_sparse = kb_options.get(kb_id, {}).get("top_k_sparse", 50)
            result = await vec_db.document_storage.search_sparse(
                query_tokens=query_tokens,
                limit=top_k_sparse,
            )
            if result is None:
                fallback_kb_ids.append(kb_id)
                continue

            for doc in result:
                chunk_md = json.loads(doc["metadata"])
                fts_results.append(
                    SparseResult(
                        chunk_id=doc["doc_id"],
                        chunk_index=chunk_md["chunk_index"],
                        doc_id=chunk_md["kb_doc_id"],
                        kb_id=kb_id,
                        content=doc["text"],
                        score=-float(doc["score"]),
                    ),
                )

        fallback_results = []
        if fallback_kb_ids:
            fallback_results = await self._retrieve_with_bm25(
                query=query,
                kb_ids=fallback_kb_ids,
                kb_options=kb_options,
            )
        results = fts_results + fallback_results
        results.sort(key=lambda x: x.score, reverse=True)
        return results

    async def _retrieve_with_bm25(
        self,
        query: str,
        kb_ids: list[str],
        kb_options: dict,
    ) -> list[SparseResult]:
        top_k_sparse = 0
        chunks = []
        for kb_id in kb_ids:
            vec_db: FaissVecDB | None = kb_options.get(kb_id, {}).get("vec_db")
            if not vec_db:
                continue
            result = await vec_db.document_storage.get_documents(
                metadata_filters={},
                limit=None,
                offset=None,
            )
            chunk_mds = [json.loads(doc["metadata"]) for doc in result]
            result = [
                {
                    "chunk_id": doc["doc_id"],
                    "chunk_index": chunk_md["chunk_index"],
                    "doc_id": chunk_md["kb_doc_id"],
                    "kb_id": kb_id,
                    "text": doc["text"],
                }
                for doc, chunk_md in zip(result, chunk_mds)
            ]
            chunks.extend(result)
            top_k_sparse += kb_options.get(kb_id, {}).get("top_k_sparse", 50)

        if not chunks:
            return []

        # 2. 准备文档和索引
        corpus = [chunk["text"] for chunk in chunks]
        tokenized_corpus = [tokenize_text(doc, self.hit_stopwords) for doc in corpus]

        # 3. 构建 BM25 索引
        bm25 = BM25Okapi(tokenized_corpus)

        # 4. 执行检索
        tokenized_query = tokenize_text(query, self.hit_stopwords)
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
                ),
            )

        results.sort(key=lambda x: x.score, reverse=True)
        # return results[: len(results) // len(kb_ids)]
        return results[:top_k_sparse]
