"""检索管理器

协调稠密检索、稀疏检索和 Rerank,提供统一的检索接口
"""

import re
import time
import weakref
from dataclasses import dataclass
from typing import TYPE_CHECKING

from astrbot import logger
from astrbot.core.db.vec_db.base import Result
from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
from astrbot.core.knowledge_base.retrieval.rank_fusion import RankFusion
from astrbot.core.knowledge_base.retrieval.sparse_retriever import SparseRetriever
from astrbot.core.provider.provider import RerankProvider

from ..kb_helper import KBHelper

if TYPE_CHECKING:
    from astrbot.core.db.vec_db.faiss_impl import FaissVecDB

RERANK_AUTH_BILLING_STATUS_CODES = frozenset({401, 402, 403})
DEFAULT_RERANK_AUTH_COOLDOWN_SECONDS = 300.0
DEFAULT_RERANK_AUTH_MAX_COOLDOWN_SECONDS = 1800.0

_HTTP_STATUS_TEXT_RE = re.compile(
    r"\b(?:HTTP\s*|status[_\s]*code[:=\s]*)(401|402|403)\b",
    re.IGNORECASE,
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-~+/=]+")
_SECRET_KV_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|authorization)\s*([=:])\s*[^\s,;'\"]+"
)
_URL_QUERY_RE = re.compile(r"(https?://[^\s?'\"<>]+)\?[^\s'\"<>]+")


def _make_provider_ref(provider: object) -> weakref.ReferenceType[object] | None:
    try:
        return weakref.ref(provider)
    except TypeError:
        return None


@dataclass
class _RerankCooldownState:
    open_until: float
    cooldown_seconds: float
    status_code: int
    provider_ref: weakref.ReferenceType[object] | None
    provider_ref_id: int

    def matches_provider(self, provider: object) -> bool:
        if self.provider_ref is not None:
            return self.provider_ref() is provider
        return self.provider_ref_id == id(provider)


def _extract_http_status(exc: BaseException) -> int | None:
    """Extract an HTTP status code from an exception or its cause/context chain."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        for attr in ("status", "status_code"):
            raw = getattr(current, attr, None)
            if isinstance(raw, int) and not isinstance(raw, bool) and 100 <= raw <= 599:
                return raw
        response = getattr(current, "response", None)
        if response is not None:
            for attr in ("status_code", "status"):
                raw = getattr(response, attr, None)
                if (
                    isinstance(raw, int)
                    and not isinstance(raw, bool)
                    and 100 <= raw <= 599
                ):
                    return raw
        match = _HTTP_STATUS_TEXT_RE.search(str(current))
        if match:
            return int(match.group(1))
        current = current.__cause__ or current.__context__
    return None


def _sanitize_error_summary(exc: BaseException, *, max_len: int = 200) -> str:
    """Produce a concise, single-line, credential-free summary for logs."""
    text = " ".join(str(exc).split())
    text = _BEARER_RE.sub("Bearer ***", text)
    text = _SECRET_KV_RE.sub(r"\1\2***", text)
    text = _URL_QUERY_RE.sub(r"\1?***", text)
    if len(text) > max_len:
        text = text[:max_len].rstrip() + "..."
    return text or type(exc).__name__


def _resolve_rerank_provider_id(
    rerank_provider: RerankProvider, explicit_id: str | None = None
) -> str:
    if explicit_id:
        return str(explicit_id)
    meta_fn = getattr(rerank_provider, "meta", None)
    if callable(meta_fn):
        try:
            meta = meta_fn()
            meta_id = getattr(meta, "id", None)
            if meta_id:
                return str(meta_id)
        except Exception:
            pass
    provider_config = getattr(rerank_provider, "provider_config", None)
    if isinstance(provider_config, dict) and provider_config.get("id"):
        return str(provider_config["id"])
    return f"{type(rerank_provider).__name__}@{id(rerank_provider)}"


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
        *,
        rerank_auth_cooldown_seconds: float = DEFAULT_RERANK_AUTH_COOLDOWN_SECONDS,
        rerank_auth_max_cooldown_seconds: float = DEFAULT_RERANK_AUTH_MAX_COOLDOWN_SECONDS,
    ) -> None:
        """初始化检索管理器

        Args:
            vec_db_factory: 向量数据库工厂
            sparse_retriever: 稀疏检索器
            rank_fusion: 结果融合器
            kb_db: 知识库数据库实例
            rerank_auth_cooldown_seconds: Rerank 遇到 401/402/403 时的初始冷却秒数
            rerank_auth_max_cooldown_seconds: Rerank 连续认证/欠费失败时的最大冷却秒数

        """
        self.sparse_retriever = sparse_retriever
        self.rank_fusion = rank_fusion
        self.kb_db = kb_db
        self._rerank_auth_cooldown_seconds = max(1.0, float(rerank_auth_cooldown_seconds))
        self._rerank_auth_max_cooldown_seconds = max(
            self._rerank_auth_cooldown_seconds,
            float(rerank_auth_max_cooldown_seconds),
        )
        self._rerank_cooldowns: dict[str, _RerankCooldownState] = {}

    def _is_rerank_in_cooldown(
        self, provider_id: str, rerank_provider: RerankProvider, now: float
    ) -> float:
        """Return remaining cooldown seconds (>0) if the provider circuit is open."""
        state = self._rerank_cooldowns.get(provider_id)
        if state is None:
            return 0.0
        # If the provider instance was reloaded (e.g., API key updated in WebUI),
        # reset the circuit immediately so fixed credentials take effect right away.
        if not state.matches_provider(rerank_provider):
            self._rerank_cooldowns.pop(provider_id, None)
            return 0.0
        remaining = state.open_until - now
        if remaining > 0:
            return remaining
        return 0.0

    def _record_rerank_auth_failure(
        self,
        provider_id: str,
        rerank_provider: RerankProvider,
        status_code: int,
        now: float,
    ) -> float:
        """Open or extend the recoverable cooldown circuit for auth/billing HTTP errors."""
        prev = self._rerank_cooldowns.get(provider_id)
        if prev is not None and prev.matches_provider(rerank_provider):
            cooldown = min(
                self._rerank_auth_max_cooldown_seconds,
                prev.cooldown_seconds * 2.0,
            )
        else:
            cooldown = self._rerank_auth_cooldown_seconds
        self._rerank_cooldowns[provider_id] = _RerankCooldownState(
            open_until=now + cooldown,
            cooldown_seconds=cooldown,
            status_code=status_code,
            provider_ref=_make_provider_ref(rerank_provider),
            provider_ref_id=id(rerank_provider),
        )
        return cooldown

    def _record_rerank_success(self, provider_id: str) -> None:
        if self._rerank_cooldowns.pop(provider_id, None) is not None:
            logger.info(
                f"Rerank 提供商 '{provider_id}' 在冷却探测后已恢复正常，重新启用重排序。"
            )

    async def retrieve(
        self,
        query: str,
        kb_ids: list[str],
        kb_id_helper_map: dict[str, KBHelper],
        top_k_fusion: int = 20,
        top_m_final: int = 5,
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
        time_end = time.time()
        logger.debug(
            f"Rank fusion took {time_end - time_start:.2f}s and returned {len(fused_results)} results.",
        )

        # 4. 转换为 RetrievalResult (批量获取元数据)
        doc_ids = {fr.doc_id for fr in fused_results}
        metadata_map = await self.kb_db.get_documents_with_metadata_batch(doc_ids)

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
                            "chunk_index": fr.chunk_index,
                            "char_count": len(fr.content),
                        },
                    ),
                )

        # 5. Rerank
        first_rerank = None
        first_rerank_provider_id = None
        for kb_opt in kb_options.values():
            vec_db = kb_opt.get("vec_db")
            rerank_provider = (
                getattr(vec_db, "rerank_provider", None) if vec_db else None
            )
            if rerank_provider is not None:
                first_rerank = rerank_provider
                first_rerank_provider_id = kb_opt.get("rerank_provider_id")
                break
        if first_rerank and retrieval_results:
            provider_id = _resolve_rerank_provider_id(
                first_rerank, first_rerank_provider_id
            )
            now = time.monotonic()
            remaining = self._is_rerank_in_cooldown(provider_id, first_rerank, now)
            if remaining > 0:
                logger.debug(
                    f"Rerank 提供商 '{provider_id}' 处于认证/欠费冷却中（剩余约 {int(remaining)}s），跳过重排序并使用融合结果"
                )
            else:
                try:
                    retrieval_results = await self._rerank(
                        query=query,
                        results=retrieval_results,
                        top_k=top_m_final,
                        rerank_provider=first_rerank,
                    )
                    self._record_rerank_success(provider_id)
                except Exception as e:
                    status_code = _extract_http_status(e)
                    summary = _sanitize_error_summary(e)
                    if status_code in RERANK_AUTH_BILLING_STATUS_CODES:
                        cooldown = self._record_rerank_auth_failure(
                            provider_id, first_rerank, status_code, time.monotonic()
                        )
                        logger.warning(
                            f"Rerank 提供商 '{provider_id}' 返回 HTTP {status_code}（认证/额度异常），"
                            f"已进入冷却熔断 {int(cooldown)}s 并使用融合结果: {summary}"
                        )
                    else:
                        logger.warning(
                            f"Rerank 执行失败，已跳过重排序并使用融合结果: {type(e).__name__}: {summary}"
                        )

        return retrieval_results[:top_m_final]

    async def _dense_retrieve(
        self,
        query: str,
        kb_ids: list[str],
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
                logger.error(
                    f"知识库 {kb_id} 稠密检索失败: {type(e).__name__}: {e}",
                    exc_info=True,
                )
                # skip the faulty KB and continue

        # 按相似度排序并返回 top_k
        all_results.sort(key=lambda x: x.similarity, reverse=True)
        # return all_results[: len(all_results) // len(kb_ids)]
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
                result.score = rerank_result.relevance_score
                reranked_list.append(result)

        reranked_list.sort(key=lambda x: x.score, reverse=True)

        return reranked_list[:top_k]
