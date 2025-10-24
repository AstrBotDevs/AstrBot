"""检索管理器

协调稠密检索、稀疏检索和 Rerank,提供统一的检索接口
"""

import time

from dataclasses import dataclass
from typing import List

from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
from astrbot.core.knowledge_base.retrieval.rank_fusion import RankFusion
from astrbot.core.knowledge_base.retrieval.sparse_retriever import SparseRetriever
from astrbot.core.provider.provider import RerankProvider
from astrbot.core.db.vec_db.base import Result
from astrbot.core.db.vec_db.faiss_impl import FaissVecDB
from ..kb_helper import KBHelper
from astrbot import logger


@dataclass
class RetrievalResult:
    """检索结果"""

    chunk_id: str
    doc_id: str
    doc_name: str
    kb_id: str
    kb_name: str
    content: str
    score: float
    metadata: dict


class RetrievalManager:
    """检索管理器

    职责:
    - 协调稠密检索、稀疏检索和 Rerank
    - 结果融合和排序
    """

    def __init__(
        self,
        sparse_retriever: SparseRetriever,
        rank_fusion: RankFusion,
        kb_db: KBSQLiteDatabase,
    ):
        """初始化检索管理器

        Args:
            vec_db_factory: 向量数据库工厂
            sparse_retriever: 稀疏检索器
            rank_fusion: 结果融合器
            kb_db: 知识库数据库实例
        """
        self.sparse_retriever = sparse_retriever
        self.rank_fusion = rank_fusion
        self.kb_db = kb_db

    async def retrieve(
        self,
        query: str,
        kb_ids: List[str],
        kb_id_helper_map: dict[str, KBHelper],
        top_k_fusion: int = 20,
        top_m_final: int = 5,
    ) -> List[RetrievalResult]:
        """混合检索

        流程:
        1. 稠密检索 (向量相似度)
        2. 稀疏检索 (BM25)
        3. 结果融合 (RRF)
        4. Rerank 重排序

        Args:
            query: 查询文本
            kb_ids: 知识库 ID 列表
            top_m_final: 最终返回数量
            enable_rerank: 是否启用 Rerank

        Returns:
            List[RetrievalResult]: 检索结果列表
        """
        if not kb_ids:
            return []

        kb_options: dict = {}
        new_kb_ids = []
        for kb_id in kb_ids:
            kb_helper = kb_id_helper_map.get(kb_id)
            if kb_helper:
                kb = kb_helper.kb
                kb_options[kb_id] = {
                    "top_k_dense": kb.top_k_dense or 50,
                    "top_k_sparse": kb.top_k_sparse or 50,
                    "top_m_final": kb.top_m_final or 5,
                    "vec_db": kb_helper.vec_db,
                    "rerank_provider_id": kb.rerank_provider_id,
                }
                new_kb_ids.append(kb_id)
            else:
                logger.warning(f"知识库 ID {kb_id} 实例未找到, 已跳过该知识库的检索")

        kb_ids = new_kb_ids

        # 1. 稠密检索
        time_start = time.time()
        dense_results = await self._dense_retrieve(
            query=query,
            kb_ids=kb_ids,
            kb_options=kb_options,
        )
        time_end = time.time()
        logger.debug(
            f"Dense retrieval across {len(kb_ids)} bases took {time_end - time_start:.2f}s and returned {len(dense_results)} results."
        )

        # 2. 稀疏检索
        time_start = time.time()
        sparse_results = await self.sparse_retriever.retrieve(
            query=query,
            kb_ids=kb_ids,
            kb_options=kb_options,
        )
        time_end = time.time()
        logger.debug(
            f"Sparse retrieval across {len(kb_ids)} bases took {time_end - time_start:.2f}s and returned {len(sparse_results)} results."
        )

        # 3. 结果融合
        time_start = time.time()
        fused_results = await self.rank_fusion.fuse(
            dense_results=dense_results,
            sparse_results=sparse_results,
            top_k=top_k_fusion,
        )
        time_end = time.time()
        logger.debug(
            f"Rank fusion took {time_end - time_start:.2f}s and returned {len(fused_results)} results."
        )

        # 4. 转换为 RetrievalResult (获取元数据)
        retrieval_results = []
        for fr in fused_results:
            metadata_dict = await self.kb_db.get_document_with_metadata(fr.doc_id)
            if metadata_dict:
                retrieval_results.append(
                    RetrievalResult(
                        chunk_id=fr.chunk_id,
                        doc_id=fr.doc_id,
                        doc_name=metadata_dict["document"].doc_name,
                        kb_id=fr.kb_id,
                        kb_name=metadata_dict["knowledge_base"].kb_name,
                        content=fr.content,
                        score=fr.score,
                        metadata={
                            "chunk_index": fr.chunk_index,
                            "char_count": len(fr.content),
                        },
                    )
                )

        # 5. Rerank
        first_rerank = None
        for kb_id in kb_ids:
            vec_db: FaissVecDB = kb_options[kb_id]["vec_db"]
            rerank_pi = kb_options[kb_id]["rerank_provider_id"]
            if (
                vec_db
                and vec_db.rerank_provider
                and rerank_pi
                and rerank_pi == vec_db.rerank_provider.meta().id
            ):
                first_rerank = vec_db.rerank_provider
                break
        if first_rerank and retrieval_results:
            retrieval_results = await self._rerank(
                query=query,
                results=retrieval_results,
                top_k=top_m_final,
                rerank_provider=first_rerank,
            )

        return retrieval_results[:top_m_final]

    async def _dense_retrieve(
        self,
        query: str,
        kb_ids: List[str],
        kb_options: dict,
    ):
        """稠密检索 (向量相似度)

        为每个知识库使用独立的向量数据库进行检索,然后合并结果。

        Args:
            query: 查询文本
            kb_ids: 知识库 ID 列表
            top_k: 返回结果数量

        Returns:
            List[Result]: 检索结果列表
        """
        all_results: list[Result] = []
        for kb_id in kb_ids:
            if kb_id not in kb_options:
                continue
            try:
                vec_db: FaissVecDB = kb_options[kb_id]["vec_db"]
                dense_k = int(kb_options[kb_id]["top_k_dense"])
                vec_results = await vec_db.retrieve(
                    query=query,
                    k=dense_k,
                    fetch_k=dense_k * 2,
                    rerank=False,  # 稠密检索阶段不进行 rerank
                    metadata_filters={"kb_id": kb_id},
                )

                all_results.extend(vec_results)
            except Exception as e:
                from astrbot.core import logger

                logger.warning(f"知识库 {kb_id} 稠密检索失败: {e}")
                continue

        # 按相似度排序并返回 top_k
        all_results.sort(key=lambda x: x.similarity, reverse=True)
        # return all_results[: len(all_results) // len(kb_ids)]
        return all_results

    async def _rerank(
        self,
        query: str,
        results: List[RetrievalResult],
        top_k: int,
        rerank_provider: RerankProvider,
    ) -> List[RetrievalResult]:
        """Rerank 重排序

        Args:
            query: 查询文本
            results: 检索结果列表
            top_k: 返回结果数量

        Returns:
            List[RetrievalResult]: 重排序后的结果列表
        """
        if not results:
            return []

        # 准备文档列表
        docs = [r.content for r in results]

        # 调用 Rerank Provider
        rerank_results = await rerank_provider.rerank(
            query=query,
            documents=docs,
        )

        # 更新分数并重新排序
        reranked_list = []
        for rerank_result in rerank_results:
            idx = rerank_result.index
            if idx < len(results):
                result = results[idx]
                result.score = rerank_result.relevance_score
                reranked_list.append(result)

        reranked_list.sort(key=lambda x: x.score, reverse=True)

        return reranked_list[:top_k]
