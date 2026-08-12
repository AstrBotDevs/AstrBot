"""检索结果融合器

使用 Reciprocal Rank Fusion (RRF) 算法融合稠密检索和稀疏检索的结果
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
    - 全局归一化稠密分数，并在每个知识库内归一化稀疏分数
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
            k: RRF 参数,用于平滑排名
            dense_weight: 相对分数融合中的稠密检索权重

        """
        if not 0 <= dense_weight <= 1:
            raise ValueError("dense_weight must be between 0 and 1")
        self.kb_db = kb_db
        self.k = k
        self.dense_weight = dense_weight

    @staticmethod
    def _build_dense_lookup(dense_results: list[Result]) -> dict[str, Result]:
        return {result.data["doc_id"]: result for result in dense_results}

    @staticmethod
    def _build_sparse_lookup(
        sparse_results: list[SparseResult],
    ) -> dict[str, SparseResult]:
        return {result.chunk_id: result for result in sparse_results}

    @staticmethod
    def _build_rank_map(
        identifiers: list[str],
    ) -> dict[str, int]:
        return {identifier: index + 1 for index, identifier in enumerate(identifiers)}

    def _score_identifier(
        self,
        identifier: str,
        dense_ranks: dict[str, int],
        sparse_ranks: dict[str, int],
    ) -> float:
        score = 0.0
        if identifier in dense_ranks:
            score += 1.0 / (self.k + dense_ranks[identifier])
        if identifier in sparse_ranks:
            score += 1.0 / (self.k + sparse_ranks[identifier])
        return score

    @staticmethod
    def _build_sparse_fused_result(
        sparse_result: SparseResult,
        score: float,
    ) -> FusedResult:
        return FusedResult(
            chunk_id=sparse_result.chunk_id,
            chunk_index=sparse_result.chunk_index,
            doc_id=sparse_result.doc_id,
            kb_id=sparse_result.kb_id,
            content=sparse_result.content,
            score=score,
        )

    @staticmethod
    def _build_dense_fused_result(
        identifier: str,
        dense_result: Result,
        score: float,
    ) -> FusedResult:
        chunk_metadata = json.loads(dense_result.data["metadata"])
        return FusedResult(
            chunk_id=identifier,
            chunk_index=chunk_metadata["chunk_index"],
            doc_id=chunk_metadata["kb_doc_id"],
            kb_id=chunk_metadata["kb_id"],
            content=dense_result.data["text"],
            score=score,
        )

    async def fuse(
        self,
        dense_results: list[Result],
        sparse_results: list[SparseResult],
        top_k: int = 20,
    ) -> list[FusedResult]:
        """融合稠密和稀疏检索结果。

        在所有候选中对稠密相似度做 min-max 归一化，BM25 分数则在
        每个独立知识库内归一化，再按权重合并。最终结果只去除完全
        相同的文本块，不按来源文档去重。

        Args:
            dense_results: 稠密检索结果
            sparse_results: 稀疏检索结果
            top_k: 返回结果数量

        Returns:
            List[FusedResult]: 融合后的结果列表

        """
        if top_k <= 0:
            return []

        dense_ranks = {
            result.data["doc_id"]: index + 1
            for index, result in enumerate(dense_results)
        }
        sparse_ranks = {
            result.chunk_id: result.rank if result.rank is not None else index + 1
            for index, result in enumerate(sparse_results)
        }

        dense_lookup = self._build_dense_lookup(dense_results)
        sparse_lookup = self._build_sparse_lookup(sparse_results)
        all_chunk_ids = set(dense_lookup) | set(sparse_lookup)
        normalized_dense: dict[str, float] = {}
        if dense_lookup:
            scores = [result.similarity for result in dense_lookup.values()]
            minimum = min(scores)
            score_range = max(scores) - minimum
            for identifier, result in dense_lookup.items():
                normalized_dense[identifier] = (
                    (result.similarity - minimum) / score_range if score_range else 1.0
                )

        sparse_groups: dict[str, list[tuple[str, float]]] = {}
        for identifier, result in sparse_lookup.items():
            sparse_groups.setdefault(result.kb_id, []).append(
                (identifier, result.score)
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

        fusion_scores = {
            identifier: self.dense_weight * normalized_dense.get(identifier, 0.0)
            + (1 - self.dense_weight) * normalized_sparse.get(identifier, 0.0)
            for identifier in all_chunk_ids
        }
        rrf_scores = {
            identifier: self._score_identifier(
                identifier,
                dense_ranks=dense_ranks,
                sparse_ranks=sparse_ranks,
            )
            for identifier in all_chunk_ids
        }
        sorted_ids = sorted(
            fusion_scores,
            key=lambda identifier: (
                -fusion_scores[identifier],
                -rrf_scores[identifier],
                dense_ranks.get(identifier, float("inf")),
                sparse_ranks.get(identifier, float("inf")),
                identifier,
            ),
        )

        fused_results: list[FusedResult] = []
        seen_contents: set[str] = set()
        for identifier in sorted_ids:
            if identifier in sparse_lookup:
                result = self._build_sparse_fused_result(
                    sparse_lookup[identifier], fusion_scores[identifier]
                )
            elif identifier in dense_lookup:
                result = self._build_dense_fused_result(
                    identifier, dense_lookup[identifier], fusion_scores[identifier]
                )
            else:
                continue
            if result.content in seen_contents:
                continue
            seen_contents.add(result.content)
            fused_results.append(result)
            if len(fused_results) >= top_k:
                break

        return fused_results
