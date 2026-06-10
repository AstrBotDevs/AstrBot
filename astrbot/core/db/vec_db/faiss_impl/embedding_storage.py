try:
    import faiss
except ModuleNotFoundError:
    raise ImportError(
        "faiss 未安装。请使用 'pip install faiss-cpu' 或 'pip install faiss-gpu' 安装。",
    )
import os

import numpy as np


class EmbeddingStorage:
    def __init__(self, dimension: int, path: str | None = None) -> None:
        self.dimension = dimension
        self.path = path
        self.index = None
        if path and os.path.exists(path):
            self.index = faiss.read_index(path)
        else:
            base_index = faiss.IndexFlatL2(dimension)
            self.index = faiss.IndexIDMap(base_index)

    def _add_with_ids(self, vectors: np.ndarray, ids: np.ndarray) -> None:
        assert self.index is not None, "FAISS index is not initialized."
        vectors = np.ascontiguousarray(vectors, dtype=np.float32)
        ids = np.ascontiguousarray(ids, dtype=np.int64)
        try:
            self.index.add_with_ids(vectors, ids)
        except TypeError as exc:
            if "missing" not in str(exc):
                raise
            self.index.add_with_ids(
                vectors.shape[0],
                faiss.swig_ptr(vectors),
                faiss.swig_ptr(ids),
            )

    async def insert(self, vector: np.ndarray, id: int) -> None:
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
        self._add_with_ids(vector.reshape(1, -1), np.array([id], dtype=np.int64))
        await self.save_index()

    async def insert_batch(self, vectors: np.ndarray, ids: list[int]) -> None:
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
        self._add_with_ids(vectors, np.array(ids, dtype=np.int64))
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
        vector = np.ascontiguousarray(vector, dtype=np.float32)
        if vector.ndim == 1:
            vector = vector.reshape(1, -1)
        faiss.normalize_L2(vector)
        try:
            distances, indices = self.index.search(vector, k)
        except TypeError as exc:
            if "missing" not in str(exc):
                raise
            distances = np.empty((vector.shape[0], k), dtype=np.float32)
            indices = np.empty((vector.shape[0], k), dtype=np.int64)
            self.index.search(
                vector.shape[0],
                faiss.swig_ptr(vector),
                k,
                faiss.swig_ptr(distances),
                faiss.swig_ptr(indices),
            )
        return distances, indices

    async def delete(self, ids: list[int]) -> None:
        """删除向量

        Args:
            ids (list[int]): 要删除的向量ID列表

        """
        assert self.index is not None, "FAISS index is not initialized."
        id_array = np.array(ids, dtype=np.int64)
        try:
            self.index.remove_ids(id_array)
        except TypeError as exc:
            if "IDSelector" not in str(exc):
                raise
            selector = faiss.IDSelectorBatch(id_array.size, faiss.swig_ptr(id_array))
            self.index.remove_ids(selector)
        await self.save_index()

    async def save_index(self) -> None:
        """保存索引

        Args:
            path (str): 保存索引的路径

        """
        if self.index is None:
            return
        faiss.write_index(self.index, self.path)
