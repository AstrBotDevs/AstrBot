"""检索结果融合器

使用 Reciprocal Rank Fusion (RRF) 算法融合稠密检索和稀疏检索的结果
"""

from dataclasses import dataclass
from typing import Dict, List

from astrbot.core.db.vec_db.base import Result
from astrbot.core.knowledge_base.database import KBDatabase
from astrbot.core.knowledge_base.retrieval.sparse_retriever import SparseResult


@dataclass
class FusedResult:
    """融合后的检索结果"""

    chunk_id: str
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

    def __init__(self, kb_db: KBDatabase, k: int = 60):
        """初始化结果融合器

        Args:
            kb_db: 知识库数据库实例
            k: RRF 参数,用于平滑排名
        """
        self.kb_db = kb_db
        self.k = k

    async def fuse(
        self,
        dense_results: List[Result],
        sparse_results: List[SparseResult],
        top_k: int = 20,
    ) -> List[FusedResult]:
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
        # 1. 构建排名映射
        dense_ranks = {
            r.data["doc_id"]: (idx + 1) for idx, r in enumerate(dense_results)
        }
        sparse_ranks = {r.chunk_id: (idx + 1) for idx, r in enumerate(sparse_results)}

        # 2. 收集所有唯一的 ID (来自稠密检索的是 vec_doc_id, 稀疏检索的是 chunk_id)
        # 需要统一为 chunk_id
        all_chunk_ids = set()
        vec_doc_id_to_dense = {}  # vec_doc_id -> Result
        chunk_id_to_sparse = {}  # chunk_id -> SparseResult

        # 处理稀疏检索结果
        for r in sparse_results:
            all_chunk_ids.add(r.chunk_id)
            chunk_id_to_sparse[r.chunk_id] = r

        # 处理稠密检索结果 (需要转换 vec_doc_id 到 chunk_id)
        for r in dense_results:
            vec_doc_id = r.data["doc_id"]
            all_chunk_ids.add(vec_doc_id)
            vec_doc_id_to_dense[vec_doc_id] = r

        # 3. 计算 RRF 分数
        rrf_scores: Dict[str, float] = {}

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
            rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True
        )[:top_k]

        # 5. 构建融合结果
        fused_results = []
        for identifier in sorted_ids:
            # 优先从稀疏检索获取完整信息
            if identifier in chunk_id_to_sparse:
                sr = chunk_id_to_sparse[identifier]
                fused_results.append(
                    FusedResult(
                        chunk_id=sr.chunk_id,
                        doc_id=sr.doc_id,
                        kb_id=sr.kb_id,
                        content=sr.content,
                        score=rrf_scores[identifier],
                    )
                )
            elif identifier in vec_doc_id_to_dense:
                # 从向量检索获取信息,需要从数据库获取块的详细信息
                chunk = await self.kb_db.get_chunk_by_vec_doc_id(identifier)
                if chunk:
                    fused_results.append(
                        FusedResult(
                            chunk_id=chunk.chunk_id,
                            doc_id=chunk.doc_id,
                            kb_id=chunk.kb_id,
                            content=chunk.content,
                            score=rrf_scores[identifier],
                        )
                    )

        return fused_results
