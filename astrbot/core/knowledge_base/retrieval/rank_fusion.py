"""检索结果融合器。

使用相对分数融合稠密检索和稀疏检索结果，并以 RRF 处理同分结果。
"""

import json
from dataclasses import dataclass

from astrbot.core.db.vec_db.base import Result
from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
from astrbot.core.knowledge_base.retrieval.sparse_retriever import SparseResult


@dataclass
class FusedResult:
    """融合后的检索结果"""

    chunk_id: str
    chunk_index: int
    doc_id: str
    kb_id: str
    content: str
    score: float


class RankFusion:
    """检索结果融合器

    职责:
    - 融合稠密检索和稀疏检索的结果
    - 在每个知识库内归一化不可直接比较的检索分数
    - 使用 RRF 作为确定性的同分排序依据
    """

    def __init__(
        self,
        kb_db: KBSQLiteDatabase,
        k: int = 60,
        dense_weight: float = 0.9,
    ) -> None:
        """初始化结果融合器

        Args:
            kb_db: 知识库数据库实例
            k: RRF 同分排序的平滑参数
            dense_weight: 相对分数融合中的稠密检索权重

        Raises:
            ValueError: If dense_weight is outside the inclusive range [0, 1].

        """
        if not 0 <= dense_weight <= 1:
            raise ValueError("dense_weight must be between 0 and 1")
        self.kb_db = kb_db
        self.k = k
        self.dense_weight = dense_weight

    async def fuse(
        self,
        dense_results: list[Result],
        sparse_results: list[SparseResult],
        top_k: int = 20,
    ) -> list[FusedResult]:
        """融合稠密和稀疏检索结果。

        每个知识库内分别对稠密相似度和 BM25 分数做 min-max 归一化，
        再按权重合并。RRF 分数仅用于融合分数相同时的稳定排序。

        Args:
            dense_results: 稠密检索结果
            sparse_results: 稀疏检索结果
            top_k: 返回结果数量

        Returns:
            List[FusedResult]: 融合后的结果列表

        """
        if top_k <= 0:
            return []

        # 1. 构建排名映射
        dense_ranks = {
            r.data["doc_id"]: (idx + 1) for idx, r in enumerate(dense_results)
        }  # 这里的 doc_id 实际上是 chunk_id
        sparse_ranks = {
            r.chunk_id: r.rank if r.rank is not None else idx + 1
            for idx, r in enumerate(sparse_results)
        }

        # 2. 收集所有唯一的 ID
        # 需要统一为 chunk_id
        all_chunk_ids = set()
        vec_doc_id_to_dense: dict[str, Result] = {}  # vec_doc_id -> Result
        chunk_id_to_sparse: dict[str, SparseResult] = {}  # chunk_id -> SparseResult
        dense_metadata: dict[str, dict] = {}

        # 处理稀疏检索结果
        for r in sparse_results:
            all_chunk_ids.add(r.chunk_id)
            chunk_id_to_sparse[r.chunk_id] = r

        # 处理稠密检索结果 (需要转换 vec_doc_id 到 chunk_id)
        for r in dense_results:
            vec_doc_id = r.data["doc_id"]
            all_chunk_ids.add(vec_doc_id)
            vec_doc_id_to_dense[vec_doc_id] = r
            dense_metadata[vec_doc_id] = json.loads(r.data["metadata"])

        # 3. 在每个知识库内归一化两路分数，避免跨索引直接比较 BM25。
        dense_groups: dict[str, list[tuple[str, float]]] = {}
        for identifier, result in vec_doc_id_to_dense.items():
            kb_id = dense_metadata[identifier].get("kb_id")
            if not kb_id and identifier in chunk_id_to_sparse:
                kb_id = chunk_id_to_sparse[identifier].kb_id
            dense_groups.setdefault(kb_id or "", []).append(
                (identifier, result.similarity)
            )

        sparse_groups: dict[str, list[tuple[str, float]]] = {}
        for identifier, result in chunk_id_to_sparse.items():
            sparse_groups.setdefault(result.kb_id, []).append(
                (identifier, result.score)
            )

        normalized_dense: dict[str, float] = {}
        for group in dense_groups.values():
            scores = [score for _, score in group]
            minimum = min(scores)
            score_range = max(scores) - minimum
            for identifier, score in group:
                normalized_dense[identifier] = (
                    (score - minimum) / score_range if score_range else 1.0
                )

        normalized_sparse: dict[str, float] = {}
        for group in sparse_groups.values():
            scores = [score for _, score in group]
            minimum = min(scores)
            score_range = max(scores) - minimum
            for identifier, score in group:
                normalized_sparse[identifier] = (
                    (score - minimum) / score_range if score_range else 1.0
                )

        # 4. 计算融合分数和 RRF 同分分数
        fusion_scores: dict[str, float] = {}
        rrf_scores: dict[str, float] = {}

        for identifier in all_chunk_ids:
            fusion_scores[identifier] = self.dense_weight * normalized_dense.get(
                identifier, 0.0
            ) + (1 - self.dense_weight) * normalized_sparse.get(identifier, 0.0)

            rrf_score = 0.0
            if identifier in dense_ranks:
                rrf_score += 1.0 / (self.k + dense_ranks[identifier])

            if identifier in sparse_ranks:
                rrf_score += 1.0 / (self.k + sparse_ranks[identifier])

            rrf_scores[identifier] = rrf_score

        # 5. 排序
        sorted_ids = sorted(
            fusion_scores,
            key=lambda cid: (
                -fusion_scores[cid],
                -rrf_scores[cid],
                dense_ranks.get(cid, float("inf")),
                sparse_ranks.get(cid, float("inf")),
                cid,
            ),
        )

        # 6. 构建融合结果，每篇来源文档只保留得分最高的块。
        fused_results = []
        seen_documents: set[tuple[str, str]] = set()
        for identifier in sorted_ids:
            # 优先从稀疏检索获取完整信息
            if identifier in chunk_id_to_sparse:
                sr = chunk_id_to_sparse[identifier]
                fused_result = FusedResult(
                    chunk_id=sr.chunk_id,
                    chunk_index=sr.chunk_index,
                    doc_id=sr.doc_id,
                    kb_id=sr.kb_id,
                    content=sr.content,
                    score=fusion_scores[identifier],
                )
            elif identifier in vec_doc_id_to_dense:
                # 从向量检索获取信息,需要从数据库获取块的详细信息
                vec_result = vec_doc_id_to_dense[identifier]
                chunk_md = dense_metadata[identifier]
                fused_result = FusedResult(
                    chunk_id=identifier,
                    chunk_index=chunk_md["chunk_index"],
                    doc_id=chunk_md["kb_doc_id"],
                    kb_id=chunk_md["kb_id"],
                    content=vec_result.data["text"],
                    score=fusion_scores[identifier],
                )
            else:
                continue

            document_key = (fused_result.kb_id, fused_result.doc_id)
            if document_key in seen_documents:
                continue
            seen_documents.add(document_key)
            fused_results.append(fused_result)
            if len(fused_results) >= top_k:
                break

        return fused_results
