try:
    import faiss
except ModuleNotFoundError:
    raise ImportError(
        "faiss ??????? 'pip install faiss-cpu' ? 'pip install faiss-gpu' ???",
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
        """????

        Args:
            vector (np.ndarray): ??????
            id (int): ???ID
        Raises:
            ValueError: ????????????????

        """
        assert self.index is not None, "FAISS index is not initialized."
        if vector.shape[0] != self.dimension:
            raise ValueError(
                f"???????, ??: {self.dimension}, ??: {vector.shape[0]}",
            )
        self._add_with_ids(vector.reshape(1, -1), np.array([id], dtype=np.int64))
        await self.save_index()

    async def insert_batch(self, vectors: np.ndarray, ids: list[int]) -> None:
        """??????

        Args:
            vectors (np.ndarray): ????????
            ids (list[int]): ???ID??
        Raises:
            ValueError: ????????????????

        """
        assert self.index is not None, "FAISS index is not initialized."
        if vectors.shape[1] != self.dimension:
            raise ValueError(
                f"???????, ??: {self.dimension}, ??: {vectors.shape[1]}",
            )
        self._add_with_ids(vectors, np.array(ids, dtype=np.int64))
        await self.save_index()

    async def search(self, vector: np.ndarray, k: int) -> tuple:
        """????????

        Args:
            vector (np.ndarray): ????
            k (int): ???????????
        Returns:
            tuple: (??, ??)

        """
        assert self.index is not None, "FAISS index is not initialized."
        faiss.normalize_L2(vector)
        try:
            distances, indices = self.index.search(vector, k)
        except TypeError as exc:
            if "missing 3 required positional arguments" not in str(exc):
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
        """????

        Args:
            ids (list[int]): ??????ID??

        """
        assert self.index is not None, "FAISS index is not initialized."
        id_array = np.array(ids, dtype=np.int64)
        self.index.remove_ids(id_array)
        await self.save_index()

    async def save_index(self) -> None:
        """????

        Args:
            path (str): ???????

        """
        if self.index is None:
            return
        faiss.write_index(self.index, self.path)
