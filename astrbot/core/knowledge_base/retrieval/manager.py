"""检索管理器

协调稠密检索、稀疏检索和 Rerank,提供统一的检索接口
"""

import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from astrbot import logger
from astrbot.core.db.vec_db.base import Result
from astrbot.core.knowledge_base.capabilities import (
    DEFAULT_TOP_K_DENSE,
    DEFAULT_TOP_K_SPARSE,
    DEFAULT_TOP_M_FINAL,
)
from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
from astrbot.core.knowledge_base.retrieval.rank_fusion import FusedResult, RankFusion
from astrbot.core.knowledge_base.retrieval.sparse_retriever import SparseRetriever
from astrbot.core.provider.provider import RerankProvider

from ..kb_helper import KBHelper

if TYPE_CHECKING:
    from astrbot.core.db.vec_db.faiss_impl import FaissVecDB


RetrievalOverrideValue = int | str | None
RetrievalOverrides = dict[str, RetrievalOverrideValue]

DEDUP_SHINGLE_SIZE = 5
DEDUP_JACCARD_THRESHOLD = 0.92


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


@dataclass
class RetrievalTrace:
    """Detailed retrieval pipeline trace for diagnostics."""

    dense: list[dict]
    sparse: list[dict]
    fusion: list[dict]
    dedup: list[dict]
    dedup_removed: list[dict]
    rerank: list[dict]
    final: list[dict]

    def to_dict(self) -> dict:
        return {
            "dense": self.dense,
            "sparse": self.sparse,
            "fusion": self.fusion,
            "dedup": self.dedup,
            "dedup_removed": self.dedup_removed,
            "rerank": self.rerank,
            "final": self.final,
        }


@dataclass
class RetrievalWithTrace:
    """Retrieval results with optional pipeline diagnostics."""

    results: list[RetrievalResult]
    trace: RetrievalTrace


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
    ) -> None:
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
        kb_ids: list[str],
        kb_id_helper_map: dict[str, KBHelper],
        top_k_fusion: int = 20,
        top_m_final: int = DEFAULT_TOP_M_FINAL,
        retrieval_overrides: RetrievalOverrides | None = None,
    ) -> list[RetrievalResult]:
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

        kb_ids, kb_options = self._build_kb_options(
            kb_ids,
            kb_id_helper_map,
            retrieval_overrides=retrieval_overrides,
        )

        # 1. 稠密检索
        time_start = time.time()
        dense_results = await self._dense_retrieve(
            query=query,
            kb_ids=kb_ids,
            kb_options=kb_options,
        )
        time_end = time.time()
        logger.debug(
            f"Dense retrieval across {len(kb_ids)} bases took {time_end - time_start:.2f}s and returned {len(dense_results)} results.",
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
            f"Sparse retrieval across {len(kb_ids)} bases took {time_end - time_start:.2f}s and returned {len(sparse_results)} results.",
        )

        # 3. 结果融合
        time_start = time.time()
        fused_results = await self.rank_fusion.fuse(
            dense_results=dense_results,
            sparse_results=sparse_results,
            top_k=top_k_fusion,
        )
        deduped_results = self._deduplicate_fused_results(fused_results)
        time_end = time.time()
        logger.debug(
            f"Rank fusion took {time_end - time_start:.2f}s and returned "
            f"{len(fused_results)} results; dedup kept {len(deduped_results)}.",
        )

        # 4. 转换为 RetrievalResult (批量获取元数据)
        doc_ids = {fr.doc_id for fr in deduped_results}
        metadata_map = await self.kb_db.get_documents_with_metadata_batch(doc_ids)
        retrieval_results = self._build_retrieval_results(
            fused_results=deduped_results,
            metadata_map=metadata_map,
        )

        # 5. Rerank
        first_rerank = self._get_first_rerank_provider(kb_ids, kb_options)
        if first_rerank and retrieval_results:
            try:
                retrieval_results = await self._rerank(
                    query=query,
                    results=retrieval_results,
                    top_k=top_m_final,
                    rerank_provider=first_rerank,
                )
            except Exception as e:
                logger.warning(f"Rerank 执行失败，已跳过重排序并使用融合结果: {e}")

        return retrieval_results[:top_m_final]

    async def retrieve_with_trace(
        self,
        query: str,
        kb_ids: list[str],
        kb_id_helper_map: dict[str, KBHelper],
        top_k_fusion: int = 20,
        top_m_final: int = DEFAULT_TOP_M_FINAL,
        retrieval_overrides: RetrievalOverrides | None = None,
    ) -> RetrievalWithTrace:
        """Hybrid retrieval with detailed stage diagnostics."""
        if not kb_ids:
            return RetrievalWithTrace(
                results=[],
                trace=RetrievalTrace(
                    dense=[],
                    sparse=[],
                    fusion=[],
                    dedup=[],
                    dedup_removed=[],
                    rerank=[],
                    final=[],
                ),
            )

        kb_ids, kb_options = self._build_kb_options(
            kb_ids,
            kb_id_helper_map,
            retrieval_overrides=retrieval_overrides,
        )

        dense_results = await self._dense_retrieve(
            query=query,
            kb_ids=kb_ids,
            kb_options=kb_options,
        )
        sparse_results = await self.sparse_retriever.retrieve(
            query=query,
            kb_ids=kb_ids,
            kb_options=kb_options,
        )
        fused_results = await self.rank_fusion.fuse(
            dense_results=dense_results,
            sparse_results=sparse_results,
            top_k=top_k_fusion,
        )
        deduped_results, dedup_removed_results = (
            self._deduplicate_fused_results_with_trace(
                fused_results,
            )
        )

        doc_ids = self._collect_trace_doc_ids(
            dense_results=dense_results,
            sparse_results=sparse_results,
            fused_results=fused_results,
        )
        metadata_map = await self.kb_db.get_documents_with_metadata_batch(doc_ids)
        doc_lookup = {
            doc_id: {
                "doc_name": metadata["document"].doc_name,
                "kb_name": metadata["knowledge_base"].kb_name,
            }
            for doc_id, metadata in metadata_map.items()
        }

        retrieval_results = self._build_retrieval_results(
            fused_results=deduped_results,
            metadata_map=metadata_map,
        )

        rerank_results: list[RetrievalResult] = []
        first_rerank = self._get_first_rerank_provider(kb_ids, kb_options)
        if first_rerank and retrieval_results:
            try:
                retrieval_results = await self._rerank(
                    query=query,
                    results=retrieval_results,
                    top_k=top_m_final,
                    rerank_provider=first_rerank,
                )
                rerank_results = retrieval_results
            except Exception as e:
                logger.warning(f"Rerank 执行失败，已跳过重排序并使用融合结果: {e}")

        final_results = retrieval_results[:top_m_final]
        trace = RetrievalTrace(
            dense=self._serialize_dense_trace(dense_results, doc_lookup),
            sparse=self._serialize_sparse_trace(sparse_results, doc_lookup),
            fusion=self._serialize_fusion_trace(fused_results, doc_lookup),
            dedup=self._serialize_fusion_trace(deduped_results, doc_lookup),
            dedup_removed=self._serialize_dedup_removed_trace(
                dedup_removed_results,
                doc_lookup,
            ),
            rerank=self._serialize_retrieval_trace(rerank_results, "rerank"),
            final=self._serialize_retrieval_trace(final_results, "final"),
        )
        return RetrievalWithTrace(results=final_results, trace=trace)

    def _build_kb_options(
        self,
        kb_ids: list[str],
        kb_id_helper_map: dict[str, KBHelper],
        *,
        retrieval_overrides: RetrievalOverrides | None = None,
    ) -> tuple[list[str], dict]:
        kb_options: dict = {}
        valid_kb_ids = []
        for kb_id in kb_ids:
            kb_helper = kb_id_helper_map.get(kb_id)
            if not kb_helper:
                logger.warning(f"知识库 ID {kb_id} 实例未找到, 已跳过该知识库的检索")
                continue
            kb = kb_helper.kb
            kb_option = {
                "top_k_dense": kb.top_k_dense or DEFAULT_TOP_K_DENSE,
                "top_k_sparse": kb.top_k_sparse or DEFAULT_TOP_K_SPARSE,
                "top_m_final": kb.top_m_final or DEFAULT_TOP_M_FINAL,
                "vec_db": kb_helper.vec_db,
                "rerank_provider_id": kb.rerank_provider_id,
            }
            if retrieval_overrides:
                for field_name in (
                    "top_k_dense",
                    "top_k_sparse",
                    "top_m_final",
                    "rerank_provider_id",
                ):
                    if field_name in retrieval_overrides:
                        kb_option[field_name] = retrieval_overrides[field_name]
            kb_options[kb_id] = kb_option
            valid_kb_ids.append(kb_id)
        return valid_kb_ids, kb_options

    def _collect_trace_doc_ids(
        self,
        *,
        dense_results: list[Result],
        sparse_results,
        fused_results,
    ) -> set[str]:
        doc_ids = {result.doc_id for result in sparse_results}
        doc_ids.update(result.doc_id for result in fused_results)
        for result in dense_results:
            metadata = self._safe_metadata(result.data.get("metadata"))
            doc_id = metadata.get("kb_doc_id")
            if doc_id:
                doc_ids.add(doc_id)
        return doc_ids

    def _deduplicate_fused_results(
        self,
        fused_results: list[FusedResult],
    ) -> list[FusedResult]:
        deduped_results, _ = self._deduplicate_fused_results_with_trace(fused_results)
        return deduped_results

    def _deduplicate_fused_results_with_trace(
        self,
        fused_results: list[FusedResult],
    ) -> tuple[list[FusedResult], list[dict]]:
        selected: list[FusedResult] = []
        removed: list[dict] = []
        signatures: list[tuple[FusedResult, str, frozenset[str]]] = []

        for result in fused_results:
            normalized = self._normalize_content_for_dedup(result.content)
            if not normalized:
                selected.append(result)
                continue

            shingles = self._build_content_shingles(normalized)
            duplicate_of = self._find_duplicate_signature(
                normalized,
                shingles,
                signatures,
            )
            if duplicate_of:
                selected_result, selected_normalized, selected_shingles = duplicate_of
                removed.append(
                    {
                        "result": result,
                        "duplicate_of": selected_result,
                        "similarity": self._dedup_similarity(
                            normalized,
                            shingles,
                            selected_normalized,
                            selected_shingles,
                        ),
                    },
                )
                continue

            selected.append(result)
            signatures.append((result, normalized, shingles))

        return selected, removed

    @staticmethod
    def _normalize_content_for_dedup(content: str) -> str:
        return "".join(str(content or "").lower().split())

    @staticmethod
    def _build_content_shingles(
        normalized_content: str,
        size: int = DEDUP_SHINGLE_SIZE,
    ) -> frozenset[str]:
        if not normalized_content:
            return frozenset()
        if len(normalized_content) <= size:
            return frozenset({normalized_content})
        return frozenset(
            normalized_content[index : index + size]
            for index in range(len(normalized_content) - size + 1)
        )

    @staticmethod
    def _is_duplicate_signature(
        normalized: str,
        shingles: frozenset[str],
        existing: tuple[FusedResult, str, frozenset[str]],
    ) -> bool:
        _, existing_normalized, existing_shingles = existing
        return (
            RetrievalManager._dedup_similarity(
                normalized,
                shingles,
                existing_normalized,
                existing_shingles,
            )
            >= DEDUP_JACCARD_THRESHOLD
        )

    @staticmethod
    def _dedup_similarity(
        normalized: str,
        shingles: frozenset[str],
        existing_normalized: str,
        existing_shingles: frozenset[str],
    ) -> float:
        if normalized == existing_normalized:
            return 1.0
        if not shingles or not existing_shingles:
            return 0.0
        union = len(shingles | existing_shingles)
        if union == 0:
            return 0.0
        return len(shingles & existing_shingles) / union

    def _find_duplicate_signature(
        self,
        normalized: str,
        shingles: frozenset[str],
        signatures: list[tuple[FusedResult, str, frozenset[str]]],
    ) -> tuple[FusedResult, str, frozenset[str]] | None:
        for signature in signatures:
            if self._is_duplicate_signature(normalized, shingles, signature):
                return signature
        return None

    def _build_retrieval_results(
        self,
        *,
        fused_results,
        metadata_map: dict,
    ) -> list[RetrievalResult]:
        retrieval_results = []
        for fr in fused_results:
            metadata_dict = metadata_map.get(fr.doc_id)
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
                            **(fr.metadata or {}),
                            "chunk_index": fr.chunk_index,
                            "char_count": len(fr.content),
                            "dense_rank": fr.dense_rank,
                            "sparse_rank": fr.sparse_rank,
                            "dense_score": fr.dense_score,
                            "sparse_score": fr.sparse_score,
                            "rrf_score": fr.rrf_score
                            if fr.rrf_score is not None
                            else fr.score,
                        },
                    ),
                )
        return retrieval_results

    def _get_first_rerank_provider(self, kb_ids: list[str], kb_options: dict):
        first_rerank = None
        for kb_id in kb_ids:
            vec_db = kb_options[kb_id]["vec_db"]
            rerank_provider = (
                getattr(vec_db, "rerank_provider", None) if vec_db else None
            )
            if rerank_provider is None:
                continue

            rerank_pi = kb_options[kb_id]["rerank_provider_id"]
            if (
                vec_db
                and rerank_provider
                and rerank_pi
                and rerank_pi == rerank_provider.meta().id
            ):
                first_rerank = rerank_provider
                break
        return first_rerank

    @staticmethod
    def _content_preview(content: str, limit: int = 240) -> str:
        if len(content) <= limit:
            return content
        return f"{content[:limit]}..."

    def _serialize_dense_trace(
        self,
        dense_results: list[Result],
        doc_lookup: dict[str, dict],
    ) -> list[dict]:
        trace = []
        for rank, result in enumerate(dense_results, 1):
            chunk_id = result.data.get("doc_id")
            metadata = self._safe_metadata(result.data.get("metadata"))
            doc_id = metadata.get("kb_doc_id")
            source = doc_lookup.get(doc_id, {})
            trace.append(
                {
                    "rank": rank,
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "doc_name": source.get("doc_name"),
                    "kb_id": metadata.get("kb_id"),
                    "kb_name": source.get("kb_name"),
                    "chunk_index": metadata.get("chunk_index", 0),
                    "score": result.similarity,
                    "dense_score": result.similarity,
                    "title_path": metadata.get("title_path"),
                    "page_number": metadata.get("page_number"),
                    "section_index": metadata.get("section_index"),
                    "content_preview": self._content_preview(
                        result.data.get("text", ""),
                    ),
                },
            )
        return trace

    def _serialize_sparse_trace(
        self,
        sparse_results,
        doc_lookup: dict[str, dict],
    ) -> list[dict]:
        trace = []
        for rank, result in enumerate(sparse_results, 1):
            source = doc_lookup.get(result.doc_id, {})
            trace.append(
                {
                    "rank": rank,
                    "chunk_id": result.chunk_id,
                    "doc_id": result.doc_id,
                    "doc_name": source.get("doc_name"),
                    "kb_id": result.kb_id,
                    "kb_name": source.get("kb_name"),
                    "chunk_index": result.chunk_index,
                    "score": result.score,
                    "sparse_score": result.score,
                    "title_path": (result.metadata or {}).get("title_path"),
                    "page_number": (result.metadata or {}).get("page_number"),
                    "section_index": (result.metadata or {}).get("section_index"),
                    "content_preview": self._content_preview(result.content),
                },
            )
        return trace

    def _serialize_fusion_trace(
        self,
        fused_results,
        doc_lookup: dict[str, dict],
    ) -> list[dict]:
        trace = []
        for rank, result in enumerate(fused_results, 1):
            source = doc_lookup.get(result.doc_id, {})
            trace.append(
                {
                    "rank": rank,
                    "chunk_id": result.chunk_id,
                    "doc_id": result.doc_id,
                    "doc_name": source.get("doc_name"),
                    "kb_id": result.kb_id,
                    "kb_name": source.get("kb_name"),
                    "chunk_index": result.chunk_index,
                    "score": result.score,
                    "dense_rank": result.dense_rank,
                    "sparse_rank": result.sparse_rank,
                    "dense_score": result.dense_score,
                    "sparse_score": result.sparse_score,
                    "rrf_score": result.rrf_score
                    if result.rrf_score is not None
                    else result.score,
                    "title_path": (result.metadata or {}).get("title_path"),
                    "page_number": (result.metadata or {}).get("page_number"),
                    "section_index": (result.metadata or {}).get("section_index"),
                    "content_preview": self._content_preview(result.content),
                },
            )
        return trace

    def _serialize_dedup_removed_trace(
        self,
        removed_results: list[dict],
        doc_lookup: dict[str, dict],
    ) -> list[dict]:
        trace = []
        for rank, removed in enumerate(removed_results, 1):
            result = removed["result"]
            duplicate_of = removed["duplicate_of"]
            source = doc_lookup.get(result.doc_id, {})
            trace.append(
                {
                    "rank": rank,
                    "chunk_id": result.chunk_id,
                    "doc_id": result.doc_id,
                    "doc_name": source.get("doc_name"),
                    "kb_id": result.kb_id,
                    "kb_name": source.get("kb_name"),
                    "chunk_index": result.chunk_index,
                    "score": result.score,
                    "dense_rank": result.dense_rank,
                    "sparse_rank": result.sparse_rank,
                    "dense_score": result.dense_score,
                    "sparse_score": result.sparse_score,
                    "rrf_score": result.rrf_score
                    if result.rrf_score is not None
                    else result.score,
                    "duplicate_of_chunk_id": duplicate_of.chunk_id,
                    "duplicate_of_doc_id": duplicate_of.doc_id,
                    "dedup_similarity": removed["similarity"],
                    "title_path": (result.metadata or {}).get("title_path"),
                    "page_number": (result.metadata or {}).get("page_number"),
                    "section_index": (result.metadata or {}).get("section_index"),
                    "content_preview": self._content_preview(result.content),
                },
            )
        return trace

    def _serialize_retrieval_trace(
        self,
        results: list[RetrievalResult],
        stage: str,
    ) -> list[dict]:
        trace = []
        for rank, result in enumerate(results, 1):
            trace.append(
                {
                    "rank": rank,
                    "chunk_id": result.chunk_id,
                    "doc_id": result.doc_id,
                    "doc_name": result.doc_name,
                    "kb_id": result.kb_id,
                    "kb_name": result.kb_name,
                    "chunk_index": result.metadata.get("chunk_index", 0),
                    "score": result.score,
                    "dense_rank": result.metadata.get("dense_rank"),
                    "sparse_rank": result.metadata.get("sparse_rank"),
                    "dense_score": result.metadata.get("dense_score"),
                    "sparse_score": result.metadata.get("sparse_score"),
                    "rrf_score": result.metadata.get("rrf_score"),
                    "rerank_score": result.metadata.get("rerank_score"),
                    "title_path": result.metadata.get("title_path"),
                    "page_number": result.metadata.get("page_number"),
                    "section_index": result.metadata.get("section_index"),
                    "stage": stage,
                    "content_preview": self._content_preview(result.content),
                },
            )
        return trace

    @staticmethod
    def _safe_metadata(raw_metadata) -> dict:
        if not raw_metadata:
            return {}
        if isinstance(raw_metadata, dict):
            return raw_metadata
        try:
            return json.loads(raw_metadata)
        except Exception:
            return {}

    async def _dense_retrieve(
        self,
        query: str,
        kb_ids: list[str],
        kb_options: dict,
    ):
        """稠密检索 (向量相似度)

        为每个知识库使用独立的向量数据库进行并行检索，然后合并结果。

        Args:
            query: 查询文本
            kb_ids: 知识库 ID 列表
            top_k: 返回结果数量

        Returns:
            List[Result]: 检索结果列表

        """
        import asyncio

        async def _retrieve_one(kb_id: str) -> list[Result]:
            if kb_id not in kb_options:
                return []
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
                return vec_results
            except Exception as e:
                logger.error(
                    f"知识库 {kb_id} 稠密检索失败: {e}",
                    exc_info=True,
                )
                if len(kb_ids) == 1:
                    raise RuntimeError(
                        f"知识库 {kb_id} 稠密检索失败: {e}",
                    ) from e
                # multi-KB: skip the faulty KB and continue
                return []

        tasks = [_retrieve_one(kb_id) for kb_id in kb_ids]
        results_per_kb = await asyncio.gather(*tasks, return_exceptions=True)

        all_results: list[Result] = []
        for result in results_per_kb:
            if isinstance(result, Exception):
                logger.error(f"稠密检索异常: {result}", exc_info=True)
                continue
            all_results.extend(result)

        # 按相似度排序并返回
        all_results.sort(key=lambda x: x.similarity, reverse=True)
        return all_results

    async def _rerank(
        self,
        query: str,
        results: list[RetrievalResult],
        top_k: int,
        rerank_provider: RerankProvider,
    ) -> list[RetrievalResult]:
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
                result.metadata["rerank_score"] = rerank_result.relevance_score
                result.score = rerank_result.relevance_score
                reranked_list.append(result)

        reranked_list.sort(key=lambda x: x.score, reverse=True)

        return reranked_list[:top_k]
