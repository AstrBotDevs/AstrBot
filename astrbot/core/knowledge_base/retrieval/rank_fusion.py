"""检索结果融合器

使用 Reciprocal Rank Fusion (RRF) 算法融合稠密检索和稀疏检索的结果
"""

import json
from dataclasses import dataclass

from astrbot.core import logger
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
    metadata: dict | None = None
    dense_rank: int | None = None
    sparse_rank: int | None = None
    dense_score: float | None = None
    sparse_score: float | None = None
    rrf_score: float | None = None


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
        # 1. Build rank maps keyed by vector-storage chunk IDs.
        dense_ranks = {
            r.data["doc_id"]: (idx + 1) for idx, r in enumerate(dense_results)
        }
        sparse_ranks = {r.chunk_id: (idx + 1) for idx, r in enumerate(sparse_results)}

        # 2. Collect all unique chunk IDs.
        all_chunk_ids = set()
        chunk_id_to_dense: dict[str, Result] = {}
        chunk_id_to_sparse: dict[str, SparseResult] = {}

        # 处理稀疏检索结果
        for r in sparse_results:
            all_chunk_ids.add(r.chunk_id)
            chunk_id_to_sparse[r.chunk_id] = r

        # Dense results use Document.doc_id, which stores the chunk UUID.
        for r in dense_results:
            chunk_id = r.data["doc_id"]
            all_chunk_ids.add(chunk_id)
            chunk_id_to_dense[chunk_id] = r

        # 3. 计算 RRF 分数
        rrf_scores: dict[str, float] = {}

        for identifier in all_chunk_ids:
            score = 0.0

            # 来自稠密检索的贡献
            if identifier in dense_ranks:
                score += 1.0 / (self.k + dense_ranks[identifier])

            # 来自稀疏检索的贡献
            if identifier in sparse_ranks:
                score += 1.0 / (self.k + sparse_ranks[identifier])

            rrf_scores[identifier] = score

        # 4. 排序
        sorted_ids = sorted(
            rrf_scores.keys(),
            key=lambda cid: rrf_scores[cid],
            reverse=True,
        )[:top_k]

        if logger.isEnabledFor(10):  # DEBUG
            details = []
            for cid in sorted_ids[:5]:
                d_rank = dense_ranks.get(cid, "-")
                s_rank = sparse_ranks.get(cid, "-")
                rrf = rrf_scores[cid]
                details.append(f"{cid[:8]}(d={d_rank},s={s_rank},rrf={rrf:.4f})")
            logger.debug(f"RRF top-5: {' | '.join(details)}")

        # 5. 构建融合结果
        fused_results = []
        for identifier in sorted_ids:
            # 优先从稀疏检索获取完整信息
            if identifier in chunk_id_to_sparse:
                sr = chunk_id_to_sparse[identifier]
                fused_results.append(
                    FusedResult(
                        chunk_id=sr.chunk_id,
                        chunk_index=sr.chunk_index,
                        doc_id=sr.doc_id,
                        kb_id=sr.kb_id,
                        content=sr.content,
                        score=rrf_scores[identifier],
                        metadata=sr.metadata,
                        dense_rank=dense_ranks.get(identifier),
                        sparse_rank=sparse_ranks.get(identifier),
                        dense_score=(
                            chunk_id_to_dense[identifier].similarity
                            if identifier in chunk_id_to_dense
                            else None
                        ),
                        sparse_score=sr.score,
                        rrf_score=rrf_scores[identifier],
                    ),
                )
            elif identifier in chunk_id_to_dense:
                # 从向量检索获取信息,需要从数据库获取块的详细信息
                vec_result = chunk_id_to_dense[identifier]
                chunk_md = json.loads(vec_result.data["metadata"])
                fused_results.append(
                    FusedResult(
                        chunk_id=identifier,
                        chunk_index=chunk_md["chunk_index"],
                        doc_id=chunk_md["kb_doc_id"],
                        kb_id=chunk_md["kb_id"],
                        content=vec_result.data["text"],
                        score=rrf_scores[identifier],
                        metadata=chunk_md,
                        dense_rank=dense_ranks.get(identifier),
                        sparse_rank=sparse_ranks.get(identifier),
                        dense_score=vec_result.similarity,
                        sparse_score=None,
                        rrf_score=rrf_scores[identifier],
                    ),
                )

        return fused_results
