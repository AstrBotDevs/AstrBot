import os

import numpy as np


class EmbeddingStorage:
    @staticmethod
    def read_index_type(storage_path: str | None) -> str:
        """从存储路径所在目录读取 index_type 文件的配置。

        Args:
            storage_path: 向量数据库文件路径

        Returns:
            str: "faiss" 或 "numpy"
        """
        if not storage_path:
            return "faiss"
        parent_dir = os.path.dirname(storage_path)
        index_type_path = os.path.join(parent_dir, "index_type")
        if os.path.exists(index_type_path):
            try:
                with open(index_type_path, encoding="utf-8") as f:
                    val = f.read().strip()
                    if val in ("faiss", "numpy"):
                        return val
            except Exception:
                pass
        return "faiss"

    @staticmethod
    def write_index_type(storage_path: str | None, db_type: str) -> None:
        """在存储路径所在目录写入 index_type 文件的配置。

        Args:
            storage_path: 向量数据库文件路径
            db_type: 数据库类型，"faiss" 或 "numpy"
        """
        if not storage_path:
            return
        parent_dir = os.path.dirname(storage_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        index_type_path = os.path.join(parent_dir, "index_type")
        try:
            with open(index_type_path, "w", encoding="utf-8") as f:
                f.write(db_type)
        except Exception:
            pass

    def __init__(self, dimension: int, path: str | None = None) -> None:
        self.dimension = dimension
        self.path = path
        self.index = None
        self.db_type = self.read_index_type(path)

        # If db_type is faiss, check if the CPU supports it
        if self.db_type == "faiss":
            from astrbot.core.utils.runtime_env import is_faiss_importable

            if not is_faiss_importable():
                self.db_type = "numpy"
                # Update index_type file to numpy
                self.write_index_type(path, "numpy")

        if self.db_type == "faiss":
            try:
                import faiss
            except ModuleNotFoundError as e:
                raise ImportError(
                    "faiss 未安装。请使用 'pip install faiss-cpu' 或 'pip install faiss-gpu' 安装。",
                ) from e
            self._faiss = faiss

            is_npz = False
            if path and os.path.exists(path):
                try:
                    with open(path, "rb") as f:
                        header = f.read(4)
                        if header == b"PK\x03\x04":
                            is_npz = True
                except Exception:
                    pass

            if is_npz:
                # Auto-convert NumPy fallback index to FAISS format
                try:
                    with np.load(path) as data:
                        vectors = data["vectors"]
                        ids = data["ids"]

                        base_index = faiss.IndexFlatL2(dimension)
                        self.index = faiss.IndexIDMap(base_index)
                        if len(ids) > 0:
                            self.index.add_with_ids(
                                vectors.astype(np.float32), ids.astype(np.int64)
                            )

                    # Save the converted FAISS index
                    faiss.write_index(self.index, path)

                    # Update index_type file to faiss
                    self.write_index_type(path, "faiss")

                    from astrbot import logger

                    logger.info(
                        f"成功将知识库向量索引从 NumPy 格式转换为 FAISS 格式: {path}"
                    )
                except Exception as e:
                    from astrbot import logger

                    logger.error(
                        f"转换 NumPy 向量索引到 FAISS 格式失败: {e}",
                        exc_info=True,
                    )
                    base_index = faiss.IndexFlatL2(dimension)
                    self.index = faiss.IndexIDMap(base_index)
            else:
                if path and os.path.exists(path):
                    self.index = faiss.read_index(path)
                else:
                    base_index = faiss.IndexFlatL2(dimension)
                    self.index = faiss.IndexIDMap(base_index)
        else:
            # NumPy flat index fallback
            self._numpy_vectors = np.empty((0, dimension), dtype=np.float32)
            self._numpy_ids = np.empty((0,), dtype=np.int64)

            is_npz = False
            if path and os.path.exists(path):
                try:
                    with open(path, "rb") as f:
                        header = f.read(4)
                        if header == b"PK\x03\x04":
                            is_npz = True
                except Exception:
                    pass

            if path and os.path.exists(path):
                if is_npz:
                    try:
                        with np.load(path) as data:
                            self._numpy_vectors = data["vectors"].astype(np.float32)
                            self._numpy_ids = data["ids"].astype(np.int64)
                    except Exception as e:
                        from astrbot import logger

                        logger.warning(f"无法加载 NumPy 格式的向量索引: {e}")
                else:
                    from astrbot import logger

                    logger.warning(
                        f"检测到 legacy FAISS 索引但当前运行在 NumPy 降级模式，无法直接读取，将启动空索引: {path}"
                    )

    @property
    def ntotal(self) -> int:
        """获取索引中的向量总数。"""
        if self.db_type == "faiss":
            return self.index.ntotal if self.index is not None else 0
        else:
            return len(self._numpy_vectors)

    def get_all_vectors(self) -> np.ndarray:
        """从存储中获取所有的向量。

        Returns:
            np.ndarray: 包含所有向量的 numpy 数组，形状为 (n_total, dimension)。
        """
        if self.db_type == "faiss":
            if self.index is None or self.index.ntotal == 0:
                return np.empty((0, self.dimension), dtype=np.float32)

            index = self.index
            if isinstance(index, self._faiss.IndexIDMap):
                base_index = self._faiss.downcast_index(index.index)
                if hasattr(base_index, "reconstruct_n"):
                    return base_index.reconstruct_n(0, index.ntotal)
                else:
                    vectors = np.zeros((index.ntotal, index.d), dtype=np.float32)
                    for i in range(index.ntotal):
                        base_index.reconstruct(i, vectors[i])
                    return vectors
            elif hasattr(index, "reconstruct_n"):
                return index.reconstruct_n(0, index.ntotal)
            else:
                vectors = np.zeros((index.ntotal, index.d), dtype=np.float32)
                for i in range(index.ntotal):
                    index.reconstruct(i, vectors[i])
                return vectors
        else:
            return self._numpy_vectors

    async def insert(self, vector: np.ndarray, id: int) -> None:
        """插入向量

        Args:
            vector (np.ndarray): 要插入的向量
            id (int): 向量的ID
        Raises:
            ValueError: 如果向量的维度与存储的维度不匹配

        """
        if self.db_type == "faiss":
            assert self.index is not None, "FAISS index is not initialized."
            if vector.shape[0] != self.dimension:
                raise ValueError(
                    f"向量维度不匹配, 期望: {self.dimension}, 实际: {vector.shape[0]}",
                )
            self.index.add_with_ids(vector.reshape(1, -1), np.array([id]))
        else:
            if vector.shape[0] != self.dimension:
                raise ValueError(
                    f"向量维度不匹配, 期望: {self.dimension}, 实际: {vector.shape[0]}",
                )
            vec = vector.reshape(1, -1).astype(np.float32)
            self._numpy_vectors = np.vstack([self._numpy_vectors, vec])
            self._numpy_ids = np.hstack(
                [self._numpy_ids, np.array([id], dtype=np.int64)]
            )
        await self.save_index()

    async def insert_batch(self, vectors: np.ndarray, ids: list[int]) -> None:
        """批量插入向量

        Args:
            vectors (np.ndarray): 要插入的向量数组
            ids (list[int]): 向量的ID列表
        Raises:
            ValueError: 如果向量的维度与存储的维度不匹配

        """
        if self.db_type == "faiss":
            assert self.index is not None, "FAISS index is not initialized."
            if vectors.shape[1] != self.dimension:
                raise ValueError(
                    f"向量维度不匹配, 期望: {self.dimension}, 实际: {vectors.shape[1]}",
                )
            self.index.add_with_ids(vectors, np.array(ids))
        else:
            if vectors.shape[1] != self.dimension:
                raise ValueError(
                    f"向量维度不匹配, 期望: {self.dimension}, 实际: {vectors.shape[1]}",
                )
            self._numpy_vectors = np.vstack(
                [self._numpy_vectors, vectors.astype(np.float32)]
            )
            self._numpy_ids = np.hstack(
                [self._numpy_ids, np.array(ids, dtype=np.int64)]
            )
        await self.save_index()

    async def search(self, vector: np.ndarray, k: int) -> tuple:
        """搜索最相似的向量

        Args:
            vector (np.ndarray): 查询向量
            k (int): 返回的最相似向量的数量
        Returns:
            tuple: (距离, 索引)

        Note:
            通常 Embedding 接口（如 OpenAI）返回的向量本身即为 L2 归一化单位向量。
            为了与其保持距离度量语义一致，FAISS 与 NumPy 均在检索时对查询向量进行 L2 归一化。
            这使得两边对于实际输入的距离度量语义（L2 距离平方在归一化后等价于 2 * (1 - cosine_similarity)）保持完全一致。
        """
        if self.db_type == "faiss":
            assert self.index is not None, "FAISS index is not initialized."
            self._faiss.normalize_L2(vector)
            distances, indices = self.index.search(vector, k)
            return distances, indices
        else:
            if len(self._numpy_ids) == 0:
                return np.empty((1, 0), dtype=np.float32), np.empty(
                    (1, 0), dtype=np.int64
                )

            if vector.ndim == 1:
                vec = vector.reshape(1, -1)
            else:
                vec = vector

            # Normalizing the query vector like FAISS normalize_L2
            norm = np.linalg.norm(vec, axis=1, keepdims=True)
            if norm[0, 0] > 0:
                vec = vec / norm

            # Compute L2 distances
            diff = self._numpy_vectors - vec
            distances = np.sum(diff**2, axis=1)

            # Sort distances ascending
            sorted_indices = np.argsort(distances)
            k = min(k, len(sorted_indices))
            top_k_idx = sorted_indices[:k]

            return (
                distances[top_k_idx].reshape(1, -1),
                self._numpy_ids[top_k_idx].reshape(1, -1),
            )

    async def delete(self, ids: list[int]) -> None:
        """删除向量

        Args:
            ids (list[int]): 要删除的向量ID列表

        """
        if self.db_type == "faiss":
            assert self.index is not None, "FAISS index is not initialized."
            id_array = np.array(ids, dtype=np.int64)
            self.index.remove_ids(id_array)
        else:
            mask = ~np.isin(self._numpy_ids, ids)
            self._numpy_vectors = self._numpy_vectors[mask]
            self._numpy_ids = self._numpy_ids[mask]
        await self.save_index()

    async def save_index(self) -> None:
        """保存索引"""
        if self.db_type == "faiss":
            if self.index is None:
                return
            self._faiss.write_index(self.index, self.path)
        else:
            if self.path:
                np.savez(
                    self.path,
                    vectors=self._numpy_vectors,
                    ids=self._numpy_ids,
                )
