from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
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
        """Atomically replace an index, including non-ASCII Windows paths.

        Args:
            index: FAISS index to persist.
            path: Destination index file.

        Raises:
            OSError: Writing, syncing, or replacing the index file fails.
        """
        import faiss

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        os.close(fd)
        temporary_path = Path(temporary)
        bridge_path = None
        try:
            if _needs_bridge(str(target)):
                bridge_path = Path(_make_temp_file("_faiss_write"))
                faiss.write_index(index, str(bridge_path))
                shutil.copyfile(bridge_path, temporary_path)
            else:
                faiss.write_index(index, str(temporary_path))
            with temporary_path.open("rb+") as saved:
                os.fsync(saved.fileno())
            temporary_path.replace(target)
        finally:
            temporary_path.unlink(missing_ok=True)
            if bridge_path is not None:
                bridge_path.unlink(missing_ok=True)

    def reload_index(self) -> None:
        """Discard the active index and reload the last persisted version.

        Leaves the index unavailable if reading fails, so subsequent operations
        retry loading rather than use vectors from an interrupted deletion.

        Raises:
            RuntimeError: No persisted index is available.
            OSError: Reading the persisted index fails.
        """
        self.index = None
        if not self.path:
            raise RuntimeError("No persisted FAISS index is available")
        self.index = self._read_index(self.path)

    async def insert(self, vector: np.ndarray, id: int) -> None:
        """插入向量"""
        if self.index is None:
            self.reload_index()
        assert self.index is not None, "FAISS index is not initialized."
        if vector.shape[0] != self.dimension:
            raise ValueError(
                f"向量维度不匹配, 期望: {self.dimension}, 实际: {vector.shape[0]}",
            )
        self.index.add_with_ids(vector.reshape(1, -1), np.array([id], dtype=np.int64))
        await self.save_index()

    async def insert_batch(self, vectors: np.ndarray, ids: list[int]) -> None:
        """批量插入向量"""
        if self.index is None:
            self.reload_index()
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
        await self.save_index()

    async def search(self, vector: np.ndarray, k: int) -> tuple:
        """搜索向量

        接受 1D (d,) 或 2D (1, d) 向量，自动展平为 Faiss 期望的 (1, d)。
        """
        if self.index is None:
            self.reload_index()
        assert self.index is not None, "FAISS index is not initialized."
        vector = np.asarray(vector, dtype=np.float32).ravel()
        if vector.shape[0] != self.dimension:
            raise ValueError(
                f"向量维度不匹配, 期望: {self.dimension}, 实际: {vector.shape[0]}",
            )
        distances, indices = self.index.search(vector.reshape(1, -1), k)
        return distances, indices

    async def delete(self, ids: list[int], *, persist: bool = True) -> None:
        """Remove vectors, optionally deferring persistence for a batch.

        Args:
            ids: Internal vector IDs to remove.
            persist: Save immediately unless the caller will save the whole batch.

        Raises:
            RuntimeError: FAISS cannot remove the requested IDs.
            OSError: Persisting the updated index fails.
        """
        if self.index is None:
            self.reload_index()
        assert self.index is not None, "FAISS index is not initialized."
        self.index.remove_ids(np.array(ids, dtype=np.int64))
        if persist:
            await self.save_index()

    async def save_index(self) -> None:
        """保存索引（兼容含非 ASCII 字符的 Windows 路径）"""
        if self.index is None or not self.path:
            return
        self._write_index(self.index, self.path)
