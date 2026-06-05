import time
import uuid
from collections import OrderedDict
from hashlib import sha256

import numpy as np

from astrbot import logger
from astrbot.core.exceptions import KnowledgeBaseUploadError
from astrbot.core.provider.provider import EmbeddingProvider, RerankProvider

from ..base import BaseVecDB, Result
from .document_storage import DocumentStorage
from .embedding_storage import EmbeddingStorage


class EmbeddingCache:
    """基于 LRU 的文本 → 嵌入向量缓存（线程安全）

    使用 SHA256 哈希文本作为缓存 key，避免对相同内容重复调用 embedding API。
    """

    def __init__(self, max_size: int = 10000) -> None:
        import asyncio

        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._max_size = max_size
        self._lock = asyncio.Lock()

    @staticmethod
    def _hash(text: str) -> str:
        return sha256(text.encode()).hexdigest()

    async def get(self, text: str) -> np.ndarray | None:
        async with self._lock:
            key = self._hash(text)
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key].copy()
            return None

    async def put(self, text: str, embedding: np.ndarray) -> None:
        async with self._lock:
            key = self._hash(text)
            if key not in self._cache:
                if len(self._cache) >= self._max_size:
                    self._cache.popitem(last=False)
            else:
                self._cache.move_to_end(key)
            self._cache[key] = embedding.copy()

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()

    async def __len__(self) -> int:
        async with self._lock:
            return len(self._cache)


class FaissVecDB(BaseVecDB):
    """A class to represent a vector database."""

    def __init__(
        self,
        doc_store_path: str,
        index_store_path: str,
        embedding_provider: EmbeddingProvider,
        rerank_provider: RerankProvider | None = None,
        index_type: str = "flat",
    ) -> None:
        self.doc_store_path = doc_store_path
        self.index_store_path = index_store_path
        self.embedding_provider = embedding_provider
        self.document_storage = DocumentStorage(doc_store_path)
        self.embedding_storage = EmbeddingStorage(
            embedding_provider.get_dim(),
            index_store_path,
            index_type=index_type,
        )
        self.embedding_provider = embedding_provider
        self.rerank_provider = rerank_provider
        self.embedding_cache = EmbeddingCache()

    async def initialize(self) -> None:
        await self.document_storage.initialize()

    async def insert(
        self,
        content: str,
        metadata: dict | None = None,
        id: str | None = None,
    ) -> int:
        """插入一条文本和其对应向量，自动生成 ID 并保持一致性。"""
        metadata = metadata or {}
        str_id = id or str(uuid.uuid4())  # 使用 UUID 作为原始 ID

        vector = await self.embedding_provider.get_embedding(content)
        vector = np.array(vector, dtype=np.float32)

        # 使用 DocumentStorage 的方法插入文档
        int_id = await self.document_storage.insert_document(str_id, content, metadata)

        # 插入向量到 FAISS
        await self.embedding_storage.insert(vector, int_id)
        return int_id

    async def insert_batch(
        self,
        contents: list[str],
        metadatas: list[dict] | None = None,
        ids: list[str] | None = None,
        batch_size: int = 32,
        tasks_limit: int = 3,
        max_retries: int = 3,
        progress_callback=None,
    ) -> list[int]:
        """批量插入文本和其对应向量，自动生成 ID 并保持一致性。

        Args:
            progress_callback: 进度回调函数，接收参数 (current, total)

        """
        metadatas = metadatas or [{} for _ in contents]
        ids = ids or [str(uuid.uuid4()) for _ in contents]

        if not contents:
            logger.debug(
                "No contents provided for batch insert; skipping embedding generation."
            )
            return []

        # 空列表快速返回后，确保不再处理零向量
        assert len(contents) > 0, "contents must not be empty"

        content_count = len(contents)
        if len(metadatas) != content_count:
            raise KnowledgeBaseUploadError(
                stage="storage",
                user_message=(
                    f"存储失败：文本分块数量与元数据数量不一致（期望 {content_count}，"
                    f"实际 {len(metadatas)}）。"
                ),
                details={
                    "expected_contents": content_count,
                    "actual_metadatas": len(metadatas),
                },
            )
        if len(ids) != content_count:
            raise KnowledgeBaseUploadError(
                stage="storage",
                user_message=(
                    f"存储失败：文本分块数量与文档 ID 数量不一致（期望 {content_count}，"
                    f"实际 {len(ids)}）。"
                ),
                details={
                    "expected_contents": content_count,
                    "actual_ids": len(ids),
                },
            )

        # 检查嵌入缓存，分离已缓存的文本和需要计算的文本
        start = time.time()
        cached_vectors: dict[int, np.ndarray] = {}
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        for idx, text in enumerate(contents):
            cached = await self.embedding_cache.get(text)
            if cached is not None:
                cached_vectors[idx] = cached
            else:
                uncached_indices.append(idx)
                uncached_texts.append(text)

        cache_hits = len(cached_vectors)
        cache_misses = len(uncached_texts)
        logger.debug(
            f"Embedding cache: {cache_hits} hits, {cache_misses} misses "
            f"out of {len(contents)} contents.",
        )

        # 只对未缓存的文本生成嵌入
        vectors = [np.empty(0, dtype=np.float32) for _ in contents]
        if uncached_texts:
            new_embeddings = await self.embedding_provider.get_embeddings_batch(
                uncached_texts,
                batch_size=batch_size,
                tasks_limit=tasks_limit,
                max_retries=max_retries,
                progress_callback=progress_callback,
            )
            # 验证返回数量
            if len(new_embeddings) != len(uncached_texts):
                raise KnowledgeBaseUploadError(
                    stage="embedding",
                    user_message=(
                        "向量化失败：嵌入模型返回的向量数量与文本分块数量不一致"
                        f"（期望 {len(uncached_texts)}，实际 {len(new_embeddings)}）。"
                        "这通常说明当前 Embedding 接口未完整返回批量结果，"
                        "或该服务不兼容当前批量请求格式。"
                    ),
                    details={
                        "expected_contents": len(uncached_texts),
                        "actual_vectors": len(new_embeddings),
                    },
                )
            for i, idx in enumerate(uncached_indices):
                vectors[idx] = np.asarray(new_embeddings[i], dtype=np.float32)
                await self.embedding_cache.put(uncached_texts[i], vectors[idx])

        for idx, cached_vec in cached_vectors.items():
            vectors[idx] = cached_vec

        end = time.time()
        logger.debug(
            f"Embeddings ready for {len(contents)} contents "
            f"in {end - start:.2f}s (cached: {cache_hits}, fresh: {cache_misses}).",
        )

        # 使用 DocumentStorage 的批量插入方法
        int_ids = await self.document_storage.insert_documents_batch(
            ids,
            contents,
            metadatas,
        )
        if len(int_ids) != content_count:
            raise KnowledgeBaseUploadError(
                stage="storage",
                user_message=(
                    f"存储失败：写入文档索引后返回的内部 ID 数量与文本分块数量不一致"
                    f"（期望 {content_count}，实际 {len(int_ids)}）。"
                ),
                details={
                    "expected_contents": content_count,
                    "actual_int_ids": len(int_ids),
                },
            )

        # 批量插入向量到 FAISS
        try:
            vectors_array = np.asarray(vectors, dtype=np.float32)
        except (TypeError, ValueError) as exc:
            raise KnowledgeBaseUploadError(
                stage="embedding",
                user_message=(
                    "向量化失败：嵌入模型返回的向量格式不正确，"
                    "无法转换为统一的浮点向量矩阵。"
                ),
                details={"vector_count": len(vectors)},
            ) from exc
        if vectors_array.ndim != 2:
            raise KnowledgeBaseUploadError(
                stage="embedding",
                user_message=(
                    "向量化失败：嵌入模型返回的向量格式不正确，无法构造成二维向量矩阵。"
                ),
                details={"actual_ndim": int(vectors_array.ndim)},
            )
        if vectors_array.shape[1] != self.embedding_storage.dimension:
            raise KnowledgeBaseUploadError(
                stage="embedding",
                user_message=(
                    "向量化失败：返回向量维度与当前知识库索引维度不一致"
                    f"（期望 {self.embedding_storage.dimension}，"
                    f"实际 {vectors_array.shape[1]}）。"
                ),
                details={
                    "expected_dimension": self.embedding_storage.dimension,
                    "actual_dimension": int(vectors_array.shape[1]),
                },
            )
        await self.embedding_storage.insert_batch(vectors_array, int_ids)
        return int_ids

    async def retrieve(
        self,
        query: str,
        k: int = 5,
        fetch_k: int = 20,
        rerank: bool = False,
        metadata_filters: dict | None = None,
    ) -> list[Result]:
        """搜索最相似的文档。

        Args:
            query (str): 查询文本
            k (int): 返回的最相似文档的数量
            fetch_k (int): 在根据 metadata 过滤前从 FAISS 中获取的数量
            rerank (bool): 是否使用重排序。这需要在实例化时提供 rerank_provider, 如果未提供并且 rerank 为 True, 不会抛出异常。
            metadata_filters (dict): 元数据过滤器

        Returns:
            List[Result]: 查询结果

        """
        # 先查缓存，再调 embedding provider
        cached = await self.embedding_cache.get(query)
        if cached is not None:
            embedding = cached
        else:
            embedding = await self.embedding_provider.get_embedding(query)
            await self.embedding_cache.put(
                query,
                np.asarray(embedding, dtype=np.float32),
            )
        scores, indices = await self.embedding_storage.search(
            vector=np.array([embedding]).astype("float32"),
            k=fetch_k if metadata_filters else k,
        )
        if len(indices[0]) == 0 or indices[0][0] == -1:
            return []
        # 将内积分数 (余弦相似度, 范围 [-1, 1]) 映射到 [0, 1]
        scores[0] = (scores[0] + 1.0) / 2.0
        # NOTE: maybe the size is less than k.
        fetched_docs = await self.document_storage.get_documents(
            metadata_filters=metadata_filters or {},
            ids=indices[0],
        )
        if not fetched_docs:
            return []
        result_docs: list[Result] = []

        idx_pos = {fetch_doc["id"]: idx for idx, fetch_doc in enumerate(fetched_docs)}
        for i, indice_idx in enumerate(indices[0]):
            pos = idx_pos.get(indice_idx)
            if pos is None:
                continue
            fetch_doc = fetched_docs[pos]
            score = scores[0][i]
            result_docs.append(Result(similarity=float(score), data=fetch_doc))

        top_k_results = result_docs[:k]

        if rerank and self.rerank_provider:
            documents = [doc.data["text"] for doc in top_k_results]
            reranked_results = await self.rerank_provider.rerank(query, documents)
            reranked_results = sorted(
                reranked_results,
                key=lambda x: x.relevance_score,
                reverse=True,
            )
            top_k_results = [
                top_k_results[reranked_result.index]
                for reranked_result in reranked_results
            ]

        return top_k_results

    async def delete(self, doc_id: str) -> bool:
        """删除一条文档块（chunk）"""
        # 获得对应的 int id
        result = await self.document_storage.get_document_by_doc_id(doc_id)
        int_id = result["id"] if result else None
        if int_id is None:
            return False

        # 使用 DocumentStorage 的删除方法
        await self.document_storage.delete_document_by_doc_id(doc_id)
        await self.embedding_storage.delete([int_id])
        return True

    async def close(self) -> None:
        await self.document_storage.close()

    async def count_documents(self, metadata_filter: dict | None = None) -> int:
        """计算文档数量

        Args:
            metadata_filter (dict | None): 元数据过滤器

        """
        count = await self.document_storage.count_documents(
            metadata_filters=metadata_filter or {},
        )
        return count

    async def delete_documents(self, metadata_filters: dict) -> None:
        """根据元数据过滤器删除文档"""
        docs = await self.document_storage.get_documents(
            metadata_filters=metadata_filters,
            offset=None,
            limit=None,
        )
        doc_ids: list[int] = [doc["id"] for doc in docs]
        await self.embedding_storage.delete(doc_ids)
        await self.document_storage.delete_documents(metadata_filters=metadata_filters)
