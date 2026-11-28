from __future__ import annotations

import asyncio
import os
import shutil
import stat
import tempfile
import threading
import weakref
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import faiss

_PATH_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[Path, threading.RLock] = {}
_PATH_VERSIONS: dict[Path, int] = {}
_PATH_ASYNC_LOCKS: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, dict[Path, asyncio.Lock]
] = weakref.WeakKeyDictionary()

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
        self._resolved_path = Path(path).resolve(strict=False) if path else None
        if self._resolved_path is not None:
            with _PATH_LOCKS_GUARD:
                self._lock = _PATH_LOCKS.setdefault(
                    self._resolved_path, threading.RLock()
                )
        else:
            self._lock = threading.RLock()
        self._async_lock: asyncio.Lock | None = None
        self._async_lock_loop: asyncio.AbstractEventLoop | None = None
        self._last_disk_state: tuple[tuple[int, int, int] | None, int] = (None, 0)
        self.index = None
        with self._lock:
            target_path = self._resolved_path
            if target_path is not None and target_path.exists():
                self.index = self._read_index(str(target_path))
                self._last_disk_state = self._read_disk_state()
            else:
                if dimension <= 0:
                    raise ValueError(
                        f"无效的嵌入向量维度: {dimension}。请检查该知识库使用的 Embedding "
                        "Provider 是否正确配置了 embedding_dimensions。",
                    )
                base_index = faiss.IndexFlatL2(dimension)
                self.index = faiss.IndexIDMap(base_index)

    def _get_async_lock(self) -> asyncio.Lock:
        """Return the per-event-loop lock serializing async FAISS access.

        Returns:
            asyncio.Lock: Lock bound to the active event loop and shared across
                storages pointing at the same index path.
        """
        loop = asyncio.get_running_loop()
        if self._resolved_path is not None:
            with _PATH_LOCKS_GUARD:
                loop_locks = _PATH_ASYNC_LOCKS.setdefault(loop, {})
                return loop_locks.setdefault(self._resolved_path, asyncio.Lock())
        if self._async_lock is None or self._async_lock_loop is not loop:
            self._async_lock = asyncio.Lock()
            self._async_lock_loop = loop
        return self._async_lock

    def _read_disk_state(self) -> tuple[tuple[int, int, int] | None, int]:
        """Read the stat signature and process version for the configured index path.

        Returns:
            tuple[tuple[int, int, int] | None, int]: Stat tuple and version counter.
        """
        if self._resolved_path is None:
            return (None, 0)
        with _PATH_LOCKS_GUARD:
            version = _PATH_VERSIONS.get(self._resolved_path, 0)
        try:
            st = self._resolved_path.stat()
        except OSError:
            return (None, version)
        return ((st.st_mtime_ns, st.st_size, st.st_ino), version)

    def _reload_if_changed_sync(self) -> None:
        """Reload the FAISS index from disk if another writer updated it."""
        if self._resolved_path is None:
            return
        disk_state = self._read_disk_state()
        if disk_state != self._last_disk_state and disk_state[0] is not None:
            self.index = self._read_index(str(self._resolved_path))
            self._last_disk_state = disk_state

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
    def _write_index(index: faiss.Index, path: str | Path) -> None:
        """Atomically persist a Faiss index, bridging non-ASCII Windows paths.

        Args:
            index: FAISS index object to serialize to disk.
            path: Destination index file path (symlinks are preserved).

        Raises:
            OSError: If writing, syncing, or replacing the index file fails.
            RuntimeError: If FAISS fails to serialize the index.
        """
        import faiss

        raw_path = Path(path)
        target_path = (
            raw_path.resolve(strict=False)
            if raw_path.is_symlink()
            else raw_path.absolute()
        )
        target_path.parent.mkdir(parents=True, exist_ok=True)

        existing_mode: int | None = None
        try:
            existing_mode = stat.S_IMODE(target_path.stat().st_mode)
        except OSError:
            pass

        sibling_fd, sibling_tmp_str = tempfile.mkstemp(
            prefix=".faiss_tmp_", suffix=".faiss", dir=target_path.parent
        )
        os.close(sibling_fd)
        sibling_tmp = Path(sibling_tmp_str)
        bridge_tmp: Path | None = None
        try:
            if not _needs_bridge(str(sibling_tmp)):
                faiss.write_index(index, str(sibling_tmp))
            else:
                bridge_tmp = Path(_make_temp_file("_faiss_write"))
                faiss.write_index(index, str(bridge_tmp))
                shutil.copy2(bridge_tmp, sibling_tmp)

            if existing_mode is not None:
                os.chmod(sibling_tmp, existing_mode)

            if hasattr(os, "getxattr") and hasattr(os, "setxattr"):
                with suppress(OSError):
                    acl = os.getxattr(target_path, "system.posix_acl_access")
                    os.setxattr(sibling_tmp, "system.posix_acl_access", acl)

            with sibling_tmp.open("r+b") as f:
                f.flush()
                os.fsync(f.fileno())

            os.replace(sibling_tmp, target_path)

            if hasattr(os, "O_DIRECTORY"):
                dir_fd: int | None = None
                try:
                    dir_fd = os.open(target_path.parent, os.O_RDONLY | os.O_DIRECTORY)
                except OSError:
                    dir_fd = None
                if dir_fd is not None:
                    try:
                        os.fsync(dir_fd)
                    finally:
                        os.close(dir_fd)
        finally:
            for tmp_path in (bridge_tmp, sibling_tmp):
                if tmp_path is not None:
                    tmp_path.unlink(missing_ok=True)

    def _save_index_sync(self) -> None:
        with self._lock:
            if self.index is None or not self.path:
                return
            self._write_index(self.index, self.path)
            if self._resolved_path is not None:
                with _PATH_LOCKS_GUARD:
                    _PATH_VERSIONS[self._resolved_path] = (
                        _PATH_VERSIONS.get(self._resolved_path, 0) + 1
                    )
                self._last_disk_state = self._read_disk_state()

    def _insert_sync(self, vector: np.ndarray, id: int) -> None:
        with self._lock:
            self._reload_if_changed_sync()
            assert self.index is not None, "FAISS index is not initialized."
            if vector.shape[0] != self.dimension:
                raise ValueError(
                    f"向量维度不匹配, 期望: {self.dimension}, 实际: {vector.shape[0]}",
                )
            self.index.add_with_ids(
                vector.reshape(1, -1), np.array([id], dtype=np.int64)
            )
            try:
                self._save_index_sync()
            except Exception:
                with suppress(RuntimeError):
                    self.index.remove_ids(np.array([id], dtype=np.int64))
                raise

    def _insert_batch_sync(self, vectors: np.ndarray, ids: list[int]) -> None:
        with self._lock:
            self._reload_if_changed_sync()
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
            try:
                self._save_index_sync()
            except Exception:
                with suppress(RuntimeError):
                    self.index.remove_ids(np.array(ids, dtype=np.int64))
                raise

    def _search_sync(self, vector: np.ndarray, k: int) -> tuple:
        with self._lock:
            self._reload_if_changed_sync()
            assert self.index is not None, "FAISS index is not initialized."
            flat = np.asarray(vector, dtype=np.float32).ravel()
            if flat.shape[0] != self.dimension:
                raise ValueError(
                    f"向量维度不匹配, 期望: {self.dimension}, 实际: {flat.shape[0]}",
                )
            return self.index.search(flat.reshape(1, -1), k)

    def _delete_sync(self, ids: list[int]) -> None:
        with self._lock:
            self._reload_if_changed_sync()
            assert self.index is not None, "FAISS index is not initialized."
            try:
                self.index.remove_ids(np.array(ids, dtype=np.int64))
            except RuntimeError:
                # Idempotent: ignore missing IDs when removing from FAISS.
                pass
            self._save_index_sync()

    async def _run_serialized(self, fn, *args):
        """Serialize a FAISS worker call and wait for it on cancellation.

        Args:
            fn: Synchronous helper method to run in a worker thread.
            *args: Positional arguments forwarded to ``fn``.

        Returns:
            The return value of ``fn(*args)``.
        """
        async with self._get_async_lock():
            worker = asyncio.create_task(asyncio.to_thread(fn, *args))
            try:
                return await asyncio.shield(worker)
            except asyncio.CancelledError:
                with suppress(Exception):
                    await worker
                raise

    async def insert(self, vector: np.ndarray, id: int) -> None:
        """插入向量"""
        await self._run_serialized(self._insert_sync, vector, id)

    async def insert_batch(self, vectors: np.ndarray, ids: list[int]) -> None:
        """批量插入向量"""
        await self._run_serialized(self._insert_batch_sync, vectors, ids)

    async def search(self, vector: np.ndarray, k: int) -> tuple:
        """搜索向量

        接受 1D (d,) 或 2D (1, d) 向量，自动展平为 Faiss 期望的 (1, d)。
        """
        return await self._run_serialized(self._search_sync, vector, k)

    async def delete(self, ids: list[int]) -> None:
        """删除向量

        删除不存在的 ID 时 Faiss 会抛 RuntimeError。
        由于 remove_ids 为幂等操作，此处忽略该错误。
        """
        await self._run_serialized(self._delete_sync, ids)

    async def save_index(self) -> None:
        """保存索引（兼容含非 ASCII 字符的 Windows 路径）"""
        await self._run_serialized(self._save_index_sync)
