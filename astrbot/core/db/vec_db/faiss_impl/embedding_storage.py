try:
    import faiss
except ModuleNotFoundError:
    raise ImportError(
        "faiss 未安装。请使用 'pip install faiss-cpu' 或 'pip install faiss-gpu' 安装。",
    )
import os

import numpy as np


class EmbeddingStorage:
    def __init__(self, dimension: int, path: str | None = None):
        self.dimension = dimension
        self.path = path
        self.index = None
        if path and os.path.exists(path):
            self.index = faiss.read_index(path)
        else:
            base_index = faiss.IndexFlatL2(dimension)
            self.index = faiss.IndexIDMap(base_index)

    async def insert(self, vector: np.ndarray, id: int):
        """插入向量

        Args:
            vector (np.ndarray): 要插入的向量
            id (int): 向量的ID
        Raises:
            ValueError: 如果向量的维度与存储的维度不匹配

        """
        assert self.index is not None, "FAISS index is not initialized."
        if vector.shape[0] != self.dimension:
            raise ValueError(
                f"向量维度不匹配, 期望: {self.dimension}, 实际: {vector.shape[0]}",
            )
        self.index.add_with_ids(vector.reshape(1, -1), np.array([id]))
        await self.save_index()

    async def insert_batch(self, vectors: np.ndarray, ids: list[int]):
        """批量插入向量

        Args:
            vectors (np.ndarray): 要插入的向量数组
            ids (list[int]): 向量的ID列表
        Raises:
            ValueError: 如果向量的维度与存储的维度不匹配

        """
        assert self.index is not None, "FAISS index is not initialized."
        if vectors.shape[1] != self.dimension:
            raise ValueError(
                f"向量维度不匹配, 期望: {self.dimension}, 实际: {vectors.shape[1]}",
            )
        self.index.add_with_ids(vectors, np.array(ids))
        await self.save_index()

    async def search(self, vector: np.ndarray, k: int) -> tuple:
        """搜索最相似的向量

        Args:
            vector (np.ndarray): 查询向量
            k (int): 返回的最相似向量的数量
        Returns:
            tuple: (距离, 索引)

        """
        assert self.index is not None, "FAISS index is not initialized."
        faiss.normalize_L2(vector)
        distances, indices = self.index.search(vector, k)
        return distances, indices

    async def delete(self, ids: list[int]):
        """删除向量

        Args:
            ids (list[int]): 要删除的向量ID列表

        """
        assert self.index is not None, "FAISS index is not initialized."
        id_array = np.array(ids, dtype=np.int64)
        self.index.remove_ids(id_array)
        await self.save_index()

    async def save_index(self):
        """保存索引

        Args:
            path (str): 保存索引的路径

        """
        faiss.write_index(self.index, self.path)
