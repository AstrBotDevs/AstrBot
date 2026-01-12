import time
import uuid

import numpy as np

from astrbot import logger
from astrbot.core.provider.provider import EmbeddingProvider, RerankProvider

from ..base import BaseVecDB, Result
from .document_storage import DocumentStorage
from .embedding_storage import EmbeddingStorage


class FaissVecDB(BaseVecDB):
    """A class to represent a vector database."""

    def __init__(
        self,
        doc_store_path: str,
        index_store_path: str,
        embedding_provider: EmbeddingProvider,
        rerank_provider: RerankProvider | None = None,
    ):
        self.doc_store_path = doc_store_path
        self.index_store_path = index_store_path
        self.embedding_provider = embedding_provider
        self.document_storage = DocumentStorage(doc_store_path)
        self.embedding_storage = EmbeddingStorage(
            embedding_provider.get_dim(),
            index_store_path,
        )
        self.embedding_provider = embedding_provider
        self.rerank_provider = rerank_provider

    async def initialize(self):
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

        start = time.time()
        logger.debug(f"Generating embeddings for {len(contents)} contents...")
        vectors = await self.embedding_provider.get_embeddings_batch(
            contents,
            batch_size=batch_size,
            tasks_limit=tasks_limit,
            max_retries=max_retries,
            progress_callback=progress_callback,
        )
        end = time.time()
        logger.debug(
            f"Generated embeddings for {len(contents)} contents in {end - start:.2f} seconds.",
        )

        # 使用 DocumentStorage 的批量插入方法
        int_ids = await self.document_storage.insert_documents_batch(
            ids,
            contents,
            metadatas,
        )

        # 批量插入向量到 FAISS
        vectors_array = np.array(vectors).astype("float32")
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
        embedding = await self.embedding_provider.get_embedding(query)
        scores, indices = await self.embedding_storage.search(
            vector=np.array([embedding]).astype("float32"),
            k=fetch_k if metadata_filters else k,
        )
        if len(indices[0]) == 0 or indices[0][0] == -1:
            return []
        # normalize scores
        scores[0] = 1.0 - (scores[0] / 2.0)
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

    async def delete(self, doc_id: str):
        """删除一条文档块（chunk）"""
        # 获得对应的 int id
        result = await self.document_storage.get_document_by_doc_id(doc_id)
        int_id = result["id"] if result else None
        if int_id is None:
            return

        # 使用 DocumentStorage 的删除方法
        await self.document_storage.delete_document_by_doc_id(doc_id)
        await self.embedding_storage.delete([int_id])

    async def close(self):
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

    async def delete_documents(self, metadata_filters: dict):
        """根据元数据过滤器删除文档"""
        docs = await self.document_storage.get_documents(
            metadata_filters=metadata_filters,
            offset=None,
            limit=None,
        )
        doc_ids: list[int] = [doc["id"] for doc in docs]
        await self.embedding_storage.delete(doc_ids)
        await self.document_storage.delete_documents(metadata_filters=metadata_filters)
