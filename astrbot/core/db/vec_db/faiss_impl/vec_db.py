import uuid
import json
import numpy as np
from .document_storage import DocumentStorage
from .embedding_storage import EmbeddingStorage
from ..base import Result, BaseVecDB
from astrbot.core.provider.provider import EmbeddingProvider


class FaissVecDB(BaseVecDB):
    """
    A class to represent a vector database.
    """

    def __init__(
        self,
        doc_store_path: str,
        index_store_path: str,
        embedding_provider: EmbeddingProvider,
    ):
        self.doc_store_path = doc_store_path
        self.index_store_path = index_store_path
        self.embedding_provider = embedding_provider
        self.document_storage = DocumentStorage(doc_store_path)
        self.embedding_storage = EmbeddingStorage(
            embedding_provider.get_dim(), index_store_path
        )
        self.embedding_provider = embedding_provider

    async def initialize(self):
        await self.document_storage.initialize()

    async def insert(self, content: str, metadata: dict = None, id: str = None) -> int:
        """
        插入一条文本和其对应向量，自动生成 ID 并保持一致性。
        """
        metadata = metadata or {}
        str_id = id or str(uuid.uuid4())  # 使用 UUID 作为原始 ID

        vector = await self.embedding_provider.get_embedding(content)
        vector = np.array(vector, dtype=np.float32)
        async with self.document_storage.connection.cursor() as cursor:
            await cursor.execute(
                "INSERT INTO documents (doc_id, text, metadata) VALUES (?, ?, ?)",
                (str_id, content, json.dumps(metadata)),
            )
            await self.document_storage.connection.commit()
            result = await self.document_storage.get_document_by_doc_id(str_id)
            int_id = result["id"]

            # 插入向量到 FAISS
            await self.embedding_storage.insert(vector, int_id)
            return int_id

    async def retrieve(
        self, query: str, k: int = 5, fetch_k: int = 20, metadata_filters: dict = None
    ) -> list[Result]:
        """
        搜索最相似的文档。

        Args:
            query (str): 查询文本
            k (int): 返回的最相似文档的数量
            fetch_k (int): 在根据 metadata 过滤前从 FAISS 中获取的数量
            metadata_filters (dict): 元数据过滤器

        Returns:
            List[Result]: 查询结果
        """
        embedding = await self.embedding_provider.get_embedding(query)
        scores, indices = await self.embedding_storage.search(
            vector=np.array([embedding]).astype("float32"),
            k=fetch_k if metadata_filters else k,
        )
        # TODO: rerank
        if len(indices[0]) == 0 or indices[0][0] == -1:
            return []
        # normalize scores
        scores[0] = 1.0 - (scores[0] / 2.0)
        # NOTE: maybe the size is less than k.
        fetched_docs = await self.document_storage.get_documents(
            metadata_filters=metadata_filters or {}, ids=indices[0]
        )
        if not fetched_docs:
            return []
        result_docs = []

        idx_pos = {fetch_doc["id"]: idx for idx, fetch_doc in enumerate(fetched_docs)}
        for i, indice_idx in enumerate(indices[0]):
            pos = idx_pos.get(indice_idx)
            if pos is None:
                continue
            fetch_doc = fetched_docs[pos]
            score = scores[0][i]
            result_docs.append(Result(similarity=float(score), data=fetch_doc))
        return result_docs[:k]

    async def delete(self, doc_id: int):
        """
        删除一条文档
        """
        await self.document_storage.connection.execute(
            "DELETE FROM documents WHERE doc_id = ?", (doc_id,)
        )
        await self.document_storage.connection.commit()

    async def close(self):
        await self.document_storage.close()

    async def count_documents(self) -> int:
        """
        计算文档数量
        """
        async with self.document_storage.connection.cursor() as cursor:
            await cursor.execute("SELECT COUNT(*) FROM documents")
            count = await cursor.fetchone()
            return count[0] if count else 0
