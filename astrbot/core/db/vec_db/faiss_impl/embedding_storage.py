from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import threading
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import faiss

# ── Faiss C++ fopen() 在 Windows 上使用 ANSI codepage ──
# Python 传给 Faiss 的路径是 UTF-8 字节，但 Windows fopen 期望 ANSI 编码，
# 导致含非 ASCII 字符的路径（如 C:\Users\中文用户名\...）被解读为乱码而失败。
# 本模块通过"纯 ASCII 临时文件桥接"规避此问题。


def _needs_bridge(path: str) -> bool:
    """判断是否需要 ASCII 临时文件桥接。"""
    return os.name == "nt" and not path.isascii()


def _safe_temp_dir() -> str:
    """返回保证纯 ASCII 且可写的临时目录，用于 Faiss I/O 桥接。

    优先级:
    1. %SystemRoot%\\Temp（Windows 系统临时目录）
    2. tempfile.gettempdir()（当其为纯 ASCII 时）
    3. 非 Windows 平台使用 tempfile.gettempdir()
    """
    if os.name == "nt":
        root = os.environ.get("SystemRoot", r"C:\Windows")
        temp_dir = os.path.join(root, "Temp")
        if (
            temp_dir.isascii()
            and os.path.isdir(temp_dir)
            and os.access(temp_dir, os.W_OK)
        ):
            return temp_dir

        tmp = tempfile.gettempdir()
        if tmp.isascii():
            return tmp

        raise OSError(
            "_safe_temp_dir: 无法找到可写的纯 ASCII 临时目录。"
            f" 检查过 SystemRoot\\Temp={temp_dir}, gettempdir={tmp}"
        )

    return tempfile.gettempdir()


def _make_temp_file(prefix: str) -> str:
    """创建用于 Faiss 桥接的临时文件，返回路径。"""
    safe_dir = _safe_temp_dir()
    fd, path = tempfile.mkstemp(prefix=f"{prefix}_", suffix=".faiss", dir=safe_dir)
    os.close(fd)
    return path


class EmbeddingStorage:
    def __init__(self, dimension: int, path: str | None = None) -> None:
        try:
            import faiss
        except ImportError:
            raise ImportError(
                "faiss 未安装。请使用 'pip install faiss-cpu' 或 'pip install faiss-gpu' 安装。",
            )
        self.dimension = dimension
        self.path = path
        self._lock = threading.RLock()
        self._async_lock: asyncio.Lock | None = None
        self._async_lock_loop: asyncio.AbstractEventLoop | None = None
        self.index = None
        if path and os.path.exists(path):
            self.index = self._read_index(path)
        else:
            if dimension <= 0:
                raise ValueError(
                    f"无效的嵌入向量维度: {dimension}。请检查该知识库使用的 Embedding "
                    "Provider 是否正确配置了 embedding_dimensions。",
                )
            base_index = faiss.IndexFlatL2(dimension)
            self.index = faiss.IndexIDMap(base_index)

    def _get_async_lock(self) -> asyncio.Lock:
        """Return the per-event-loop lock serializing async FAISS access."""
        loop = asyncio.get_running_loop()
        if self._async_lock is None or self._async_lock_loop is not loop:
            self._async_lock = asyncio.Lock()
            self._async_lock_loop = loop
        return self._async_lock

    @staticmethod
    def _read_index(path: str) -> faiss.Index:
        """读取 Faiss 索引，兼容含非 ASCII 字符的 Windows 路径。"""
        import faiss

        try:
            return faiss.read_index(path)
        except RuntimeError:
            if not _needs_bridge(path):
                raise

        tmp = _make_temp_file("_faiss_read")
        try:
            shutil.copy2(path, tmp)
            return faiss.read_index(tmp)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    @staticmethod
    def _write_index(index: faiss.Index, path: str) -> None:
        """Atomically persist a Faiss index, bridging non-ASCII Windows paths."""
        import faiss

        target_dir = os.path.dirname(os.path.abspath(path))
        os.makedirs(target_dir, exist_ok=True)

        sibling_fd, sibling_tmp = tempfile.mkstemp(
            prefix=".faiss_tmp_", suffix=".faiss", dir=target_dir
        )
        os.close(sibling_fd)
        bridge_tmp: str | None = None
        try:
            if not _needs_bridge(path):
                faiss.write_index(index, sibling_tmp)
            else:
                bridge_tmp = _make_temp_file("_faiss_write")
                faiss.write_index(index, bridge_tmp)
                shutil.copy2(bridge_tmp, sibling_tmp)
            os.replace(sibling_tmp, path)
        finally:
            for tmp_path in (bridge_tmp, sibling_tmp):
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass

    def _save_index_sync(self) -> None:
        with self._lock:
            if self.index is None or not self.path:
                return
            self._write_index(self.index, self.path)

    def _insert_sync(self, vector: np.ndarray, id: int) -> None:
        with self._lock:
            assert self.index is not None, "FAISS index is not initialized."
            if vector.shape[0] != self.dimension:
                raise ValueError(
                    f"向量维度不匹配, 期望: {self.dimension}, 实际: {vector.shape[0]}",
                )
            self.index.add_with_ids(
                vector.reshape(1, -1), np.array([id], dtype=np.int64)
            )
            self._save_index_sync()

    def _insert_batch_sync(self, vectors: np.ndarray, ids: list[int]) -> None:
        with self._lock:
            assert self.index is not None, "FAISS index is not initialized."
            if len(vectors.shape) != 2:
                raise ValueError(
                    f"向量必须是二维数组, 当前维度: {len(vectors.shape)}",
                )
            if vectors.shape[1] != self.dimension:
                raise ValueError(
                    f"向量维度不匹配, 期望: {self.dimension}, 实际: {vectors.shape[1]}",
                )
            self.index.add_with_ids(vectors, np.array(ids, dtype=np.int64))
            self._save_index_sync()

    def _search_sync(self, vector: np.ndarray, k: int) -> tuple:
        with self._lock:
            assert self.index is not None, "FAISS index is not initialized."
            flat = np.asarray(vector, dtype=np.float32).ravel()
            if flat.shape[0] != self.dimension:
                raise ValueError(
                    f"向量维度不匹配, 期望: {self.dimension}, 实际: {flat.shape[0]}",
                )
            return self.index.search(flat.reshape(1, -1), k)

    def _delete_sync(self, ids: list[int]) -> None:
        with self._lock:
            assert self.index is not None, "FAISS index is not initialized."
            try:
                self.index.remove_ids(np.array(ids, dtype=np.int64))
            except RuntimeError:
                # Idempotent: ignore missing IDs when removing from FAISS.
                pass
            self._save_index_sync()

    async def insert(self, vector: np.ndarray, id: int) -> None:
        """插入向量"""
        async with self._get_async_lock():
            await asyncio.to_thread(self._insert_sync, vector, id)

    async def insert_batch(self, vectors: np.ndarray, ids: list[int]) -> None:
        """批量插入向量"""
        async with self._get_async_lock():
            await asyncio.to_thread(self._insert_batch_sync, vectors, ids)

    async def search(self, vector: np.ndarray, k: int) -> tuple:
        """搜索向量

        接受 1D (d,) 或 2D (1, d) 向量，自动展平为 Faiss 期望的 (1, d)。
        """
        async with self._get_async_lock():
            return await asyncio.to_thread(self._search_sync, vector, k)

    async def delete(self, ids: list[int]) -> None:
        """删除向量

        删除不存在的 ID 时 Faiss 会抛 RuntimeError。
        由于 remove_ids 为幂等操作，此处忽略该错误。
        """
        async with self._get_async_lock():
            await asyncio.to_thread(self._delete_sync, ids)

    async def save_index(self) -> None:
        """保存索引（兼容含非 ASCII 字符的 Windows 路径）"""
        async with self._get_async_lock():
            await asyncio.to_thread(self._save_index_sync)
