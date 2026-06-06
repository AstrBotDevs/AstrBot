"""稀疏检索器

使用 BM25 算法进行基于关键词的文档检索
"""

import json
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rank_bm25 import BM25Okapi

from astrbot.core import logger
from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
from astrbot.core.knowledge_base.retrieval.tokenizer import (
    load_stopwords,
    tokenize_text,
)

if TYPE_CHECKING:
    from astrbot.core.db.vec_db.faiss_impl import FaissVecDB


@dataclass
class SparseResult:
    """稀疏检索结果

    score 语义: 越低越相关 (0 = 最佳匹配), 统一按升序排列后送入 RRF 融合。
    """

    chunk_index: int
    chunk_id: str
    doc_id: str
    kb_id: str
    content: str
    score: float
    metadata: dict | None = None


class SparseRetriever:
    """BM25 稀疏检索器"""

    def __init__(self, kb_db: KBSQLiteDatabase) -> None:
        self.kb_db = kb_db
        self._index_cache = {}

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

        优先使用 FTS5 全文索引; 不可用时回退到内存 BM25。
        结果按 score 升序排列 (lower-is-better), 直接喂给 RRF。
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
                # FTS5 bm25(): 0=最佳, 极短文档可能为负值 → clamp 到 0
                fts_results.append(
                    SparseResult(
                        chunk_id=doc["doc_id"],
                        chunk_index=chunk_md["chunk_index"],
                        doc_id=chunk_md["kb_doc_id"],
                        kb_id=kb_id,
                        content=doc["text"],
                        score=max(0.0, float(doc["score"])),
                        metadata=chunk_md,
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
        results.sort(key=lambda x: x.score)

        if logger.isEnabledFor(10):  # DEBUG
            fts_top = [f"{r.chunk_id[:8]}={r.score:.4f}" for r in fts_results[:5]]
            bm_top = [f"{r.chunk_id[:8]}={r.score:.4f}" for r in fallback_results[:5]]
            merged_top = [f"{r.chunk_id[:8]}={r.score:.4f}" for r in results[:5]]
            logger.debug(
                f"Sparse top-5 | FTS5({len(fts_results)}): [{', '.join(fts_top)}] | "
                f"BM25({len(fallback_results)}): [{', '.join(bm_top)}] | "
                f"Merged({len(results)}): [{', '.join(merged_top)}]",
            )

        return results

    # BM25 回退路径单次最多加载的文档数，防止 OOM
    MAX_BM25_DOCS = 10_000

    async def _retrieve_with_bm25(
        self,
        query: str,
        kb_ids: list[str],
        kb_options: dict,
    ) -> list[SparseResult]:
        """FTS5 不可用时的 BM25Okapi 回退路径。

        BM25Okapi 原始分值 higher-is-better → 取反统一为 lower-is-better。
        单 KB 最多加载 MAX_BM25_DOCS 条 chunk，超限时截断并打 warning。
        """
        top_k_sparse = 0
        all_kb_chunks: list[dict] = []

        for kb_id in kb_ids:
            vec_db: FaissVecDB | None = kb_options.get(kb_id, {}).get("vec_db")
            if not vec_db:
                continue
            kb_top_k = kb_options.get(kb_id, {}).get("top_k_sparse", 50)
            top_k_sparse = max(top_k_sparse, kb_top_k)

            result = await vec_db.document_storage.get_documents(
                metadata_filters={"kb_id": kb_id},
                limit=self.MAX_BM25_DOCS,
                offset=0,
            )
            if len(result) >= self.MAX_BM25_DOCS:
                logger.warning(
                    f"知识库 {kb_id} 的 BM25 回退检索已触及 {self.MAX_BM25_DOCS} "
                    f"条 chunk 上限，结果可能不完整。建议检查 FTS5 索引状态。",
                )
            chunk_mds = [json.loads(doc["metadata"]) for doc in result]
            kb_chunks = [
                {
                    "chunk_id": doc["doc_id"],
                    "chunk_index": chunk_md["chunk_index"],
                    "doc_id": chunk_md["kb_doc_id"],
                    "kb_id": kb_id,
                    "text": doc["text"],
                    "kb_top_k": kb_top_k,
                    "metadata": chunk_md,
                }
                for doc, chunk_md in zip(result, chunk_mds)
            ]
            all_kb_chunks.append(kb_chunks)

        if not any(all_kb_chunks):
            return []

        # 每个知识库独立计算 BM25 分数并截断，再合并。
        merged_results: list[SparseResult] = []
        for kb_chunks in all_kb_chunks:
            if not kb_chunks:
                continue
            kb_top_k = kb_chunks[0]["kb_top_k"]

            corpus = [chunk["text"] for chunk in kb_chunks]
            tokenized_corpus = [
                tokenize_text(doc, self.hit_stopwords) for doc in corpus
            ]
            bm25 = BM25Okapi(tokenized_corpus)

            tokenized_query = tokenize_text(query, self.hit_stopwords)
            scores = bm25.get_scores(tokenized_query)

            kb_results: list[SparseResult] = []
            for idx, score in enumerate(scores):
                chunk = kb_chunks[idx]
                kb_results.append(
                    SparseResult(
                        chunk_id=chunk["chunk_id"],
                        chunk_index=chunk["chunk_index"],
                        doc_id=chunk["doc_id"],
                        kb_id=chunk["kb_id"],
                        content=chunk["text"],
                        score=-float(score),
                        metadata=chunk["metadata"],
                    ),
                )

            merged_results.extend(sorted(kb_results, key=lambda x: x.score)[:kb_top_k])

        merged_results.sort(key=lambda x: x.score)
        return merged_results[:top_k_sparse]
