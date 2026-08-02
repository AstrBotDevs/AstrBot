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
    - 使用 Reciprocal Rank Fusion (RRF) 算法
    """

    def __init__(self, kb_db: KBSQLiteDatabase, k: int = 60) -> None:
        """初始化结果融合器

        Args:
            kb_db: 知识库数据库实例
            k: RRF 参数,用于平滑排名

        """
        self.kb_db = kb_db
        self.k = k

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
        """融合稠密和稀疏检索结果

        RRF 公式:
        score(doc) = sum(1 / (k + rank_i))

        Args:
            dense_results: 稠密检索结果
            sparse_results: 稀疏检索结果
            top_k: 返回结果数量

        Returns:
            List[FusedResult]: 融合后的结果列表

        """
        dense_lookup = self._build_dense_lookup(dense_results)
        sparse_lookup = self._build_sparse_lookup(sparse_results)
        dense_ranks = self._build_rank_map(list(dense_lookup))
        sparse_ranks = {
            result.chunk_id: result.rank if result.rank is not None else index + 1
            for index, result in enumerate(sparse_results)
        }
        all_chunk_ids = set(dense_lookup) | set(sparse_lookup)
        rrf_scores = {
            identifier: self._score_identifier(
                identifier,
                dense_ranks=dense_ranks,
                sparse_ranks=sparse_ranks,
            )
            for identifier in all_chunk_ids
        }
        sorted_ids = sorted(
            rrf_scores,
            key=lambda identifier: (
                -rrf_scores[identifier],
                dense_ranks.get(identifier, float("inf")),
                sparse_ranks.get(identifier, float("inf")),
                identifier,
            ),
        )[:top_k]

        fused_results: list[FusedResult] = []
        for identifier in sorted_ids:
            if identifier in sparse_lookup:
                fused_results.append(
                    self._build_sparse_fused_result(
                        sparse_lookup[identifier],
                        rrf_scores[identifier],
                    )
                )
                continue
            if identifier in dense_lookup:
                fused_results.append(
                    self._build_dense_fused_result(
                        identifier,
                        dense_lookup[identifier],
                        rrf_scores[identifier],
                    )
                )

        return fused_results
