try:
    import faiss
except ModuleNotFoundError:
    raise ImportError(
        "faiss 未安装。请使用 'pip install faiss-cpu' 或 'pip install faiss-gpu' 安装。",
    )
import asyncio
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def _safe_normalize_l2(vectors: np.ndarray) -> None:
    """L2 归一化，对零向量抛出明确错误

    正常的 embedding 模型不应产生零向量。零向量无法归一化（会产生 NaN），
    说明 embedding provider 返回了异常数据，应当尽早暴露问题。
    """
    # 检测全零行
    if vectors.ndim == 2:
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        zero_count = int((norms < 1e-12).sum())
        if zero_count > 0:
            raise ValueError(
                f"向量归一化失败：检测到 {zero_count} 个零向量。"
                "Embedding Provider 返回了全零向量，这可能说明 API 密钥无效、"
                "模型不支持当前输入、或服务端异常。请检查 Embedding Provider 配置。"
            )
    elif vectors.ndim == 1:
        if np.linalg.norm(vectors) < 1e-12:
            raise ValueError(
                "向量归一化失败：检测到零向量。"
                "Embedding Provider 返回了全零向量，这可能说明 API 密钥无效、"
                "模型不支持当前输入、或服务端异常。请检查 Embedding Provider 配置。"
            )

    faiss.normalize_L2(vectors)


class EmbeddingStorage:
    def __init__(
        self,
        dimension: int,
        path: str | None = None,
        index_type: str = "flat",
    ) -> None:
        self.dimension = dimension
        self.path = path
        self.index = None
        self.index_type = index_type  # "flat" | "hnsw"
        self._write_lock = asyncio.Lock()
        if path and os.path.exists(path):
            self.index = faiss.read_index(path)
            # 验证加载的索引维度是否匹配
            loaded_dim = self.index.d
            if loaded_dim != self.dimension:
                raise ValueError(
                    f"索引维度不匹配: 磁盘索引维度={loaded_dim}, "
                    f"当前 Embedding Provider 维度={self.dimension}。"
                    f"请确认 Embedding Provider 与已有索引一致，"
                    f"或删除旧索引后重新创建知识库。"
                )
            self._migrate_l2_to_ip_if_needed()
        else:
            self.index = self._create_index()

    def _create_index(self):
        """根据 index_type 创建 FAISS 索引"""
        if self.index_type == "hnsw":
            # HNSW32 with Inner Product metric for cosine similarity
            base_index = faiss.index_factory(
                self.dimension,
                "HNSW32",
                faiss.METRIC_INNER_PRODUCT,
            )
            return faiss.IndexIDMap(base_index)
        # 默认: flat (精确搜索)
        return faiss.IndexIDMap(faiss.IndexFlatIP(self.dimension))

    def _migrate_l2_to_ip_if_needed(self) -> None:
        """检测并迁移旧版 L2 索引到 IP (余弦相似度)

        旧版使用 IndexFlatL2，新版使用 IndexFlatIP + 归一化向量。
        迁移过程：保留原 external ids → reconstruct 所有向量 → L2 归一化 → 重建为 IP 索引。
        """
        assert self.index is not None
        # IndexIDMap 包装了 base index，需要解包检查
        base_index = self.index.index if hasattr(self.index, "index") else self.index
        if getattr(base_index, "metric_type", None) != faiss.METRIC_L2:
            return  # 已经是 IP 或其他类型，无需迁移

        import warnings

        ntotal = self.index.ntotal
        if ntotal == 0:
            warnings.warn(
                "检测到空的旧版 L2 索引，将重建为 IP 索引。",
                stacklevel=2,
            )
            base_index = faiss.IndexFlatIP(self.dimension)
            self.index = faiss.IndexIDMap(base_index)
            return

        warnings.warn(
            f"检测到旧版 L2 索引 (含 {ntotal} 个向量)，正在自动迁移到 IP 索引..."
            "这可能需要几秒钟。迁移后旧索引将被覆盖。",
            stacklevel=2,
        )

        # 重建所有向量并归一化
        # 注意: IndexIDMap.reconstruct 在某些 FAISS 构建版本中不可用
        try:
            ids = self._get_index_ids()
            vectors = np.zeros((ntotal, self.dimension), dtype=np.float32)
            reconstruct_index = (
                self.index.index if hasattr(self.index, "index") else self.index
            )
            for pos in range(ntotal):
                vectors[pos] = reconstruct_index.reconstruct(pos)
        except Exception as exc:
            raise RuntimeError(
                "无法从旧索引重建向量（reconstruct 不可用），"
                "已保留旧索引文件未覆盖。请重新上传文档或手动重建知识库索引。"
            ) from exc

        _safe_normalize_l2(vectors)

        # 重建为 IP 索引
        new_index = faiss.IndexIDMap(faiss.IndexFlatIP(self.dimension))
        new_index.add_with_ids(vectors, ids)

        self._backup_existing_index_before_migration()

        # 原子性保存：先写临时文件，成功后再替换
        temp_path = f"{self.path}.migrating"
        try:
            faiss.write_index(new_index, temp_path)
            # 使用 os.replace 确保原子性（POSIX 保证）
            os.replace(temp_path, self.path)
            self.index = new_index
        except Exception as exc:
            # 清理临时文件
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            raise RuntimeError(
                f"FAISS 索引迁移失败: {exc}。旧索引已备份，当前索引保持不变。"
            ) from exc

    def _backup_existing_index_before_migration(self) -> Path:
        if self.path is None:
            raise RuntimeError("无法备份旧索引：索引文件路径为空，已保留旧索引未覆盖。")

        index_path = Path(self.path)
        if not index_path.exists():
            raise RuntimeError(
                f"无法备份旧索引：索引文件不存在 {index_path}，已保留旧索引未覆盖。"
            )

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = index_path.with_name(f"{index_path.name}.bak.{timestamp}")
        counter = 1
        while backup_path.exists():
            backup_path = index_path.with_name(
                f"{index_path.name}.bak.{timestamp}.{counter}"
            )
            counter += 1

        try:
            shutil.copy2(index_path, backup_path)
        except OSError as exc:
            raise RuntimeError(
                f"无法备份旧索引到 {backup_path}，已保留旧索引未覆盖。"
            ) from exc

        return backup_path

    def _get_index_ids(self) -> np.ndarray:
        assert self.index is not None
        ntotal = self.index.ntotal
        id_map = getattr(self.index, "id_map", None)
        if id_map is None:
            return np.arange(ntotal, dtype=np.int64)

        ids = faiss.vector_to_array(id_map).astype(np.int64)
        if len(ids) != ntotal:
            raise RuntimeError(
                f"FAISS IDMap 数量异常: ntotal={ntotal}, id_map={len(ids)}",
            )
        return ids

    async def insert(self, vector: np.ndarray, id: int) -> None:
        """插入向量

        Args:
            vector (np.ndarray): 要插入的向量
            id (int): 向量的ID
        Raises:
            ValueError: 如果向量的维度与存储的维度不匹配

        """
        async with self._write_lock:
            assert self.index is not None, "FAISS index is not initialized."
            if vector.shape[0] != self.dimension:
                raise ValueError(
                    f"向量维度不匹配, 期望: {self.dimension}, 实际: {vector.shape[0]}",
                )
            v_2d = vector.reshape(1, -1)
            _safe_normalize_l2(v_2d)
            self.index.add_with_ids(v_2d, np.array([id]))
            await self._save_index_locked()

    async def insert_batch(self, vectors: np.ndarray, ids: list[int]) -> None:
        """批量插入向量

        Args:
            vectors (np.ndarray): 要插入的向量数组
            ids (list[int]): 向量的ID列表
        Raises:
            ValueError: 如果向量的维度与存储的维度不匹配

        """
        async with self._write_lock:
            assert self.index is not None, "FAISS index is not initialized."
            if vectors.shape[1] != self.dimension:
                raise ValueError(
                    f"向量维度不匹配, 期望: {self.dimension}, 实际: {vectors.shape[1]}",
                )
            _safe_normalize_l2(vectors)
            self.index.add_with_ids(vectors, np.array(ids))
            await self._save_index_locked()

    async def search(self, vector: np.ndarray, k: int) -> tuple:
        """搜索最相似的向量

        Args:
            vector (np.ndarray): 查询向量
            k (int): 返回的最相似向量的数量
        Returns:
            tuple: (距离, 索引)

        """
        assert self.index is not None, "FAISS index is not initialized."
        _safe_normalize_l2(vector)
        distances, indices = self.index.search(vector, k)
        return distances, indices

    async def delete(self, ids: list[int]) -> None:
        """删除向量

        Args:
            ids (list[int]): 要删除的向量ID列表

        """
        async with self._write_lock:
            assert self.index is not None, "FAISS index is not initialized."
            id_array = np.array(ids, dtype=np.int64)
            self.index.remove_ids(id_array)
            await self._save_index_locked()

    async def _save_index_locked(self) -> None:
        """内部方法：在已持有 _write_lock 的情况下原子性保存索引到磁盘。

        调用者必须已经获取 _write_lock。
        使用临时文件 + os.replace() 确保原子性，防止进程崩溃导致索引损坏。
        """
        if self.index is None:
            return
        if self.path is None:
            raise RuntimeError(
                "无法保存 FAISS 索引：索引文件路径未设置。"
                "请确保在创建 EmbeddingStorage 时提供了有效的 path 参数。"
            )

        # 原子性保存：先写临时文件，成功后再替换
        temp_path = f"{self.path}.tmp.{os.getpid()}"
        try:
            await asyncio.to_thread(faiss.write_index, self.index, temp_path)
            # 使用 os.replace 确保原子性（POSIX 保证）
            await asyncio.to_thread(os.replace, temp_path, self.path)
        except Exception as exc:
            # 清理临时文件
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            raise RuntimeError(
                f"保存 FAISS 索引失败: {exc}。索引未更新，保持原有状态。"
            ) from exc

    async def save_index(self) -> None:
        """保存索引（在单独线程中执行以避免阻塞事件循环）

        公共方法，自动获取写锁以确保线程安全。
        """
        async with self._write_lock:
            await self._save_index_locked()
