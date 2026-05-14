try:
    import faiss
except ModuleNotFoundError:
    raise ImportError(
        "faiss 未安装。请使用 'pip install faiss-cpu' 或 'pip install faiss-gpu' 安装。",
    )
import os
import shutil
import tempfile
import uuid

import numpy as np


# ── Faiss C++ fopen() 在 Windows 上使用 ANSI codepage ──
# Python 传给 Faiss 的路径是 UTF-8 字节，但 Windows fopen 期望 ANSI 编码，
# 导致含非 ASCII 字符的路径（如 C:\Users\中文用户名\...）被解读为乱码而失败。
# 本模块通过"纯 ASCII 临时文件桥接"规避此问题。
#
# tempfile.gettempdir() 可能返回含中文用户的路径（取决于 TEMP 环境变量），
# 所以 _safe_temp_dir() 硬编码一个保证纯 ASCII 且可写的目录。


def _safe_temp_dir() -> str:
    """返回保证纯 ASCII 且可写的临时目录，用于 Faiss I/O 桥接。

    优先级:
    1. %SystemRoot%\\Temp（Windows 系统临时目录，如 C:\\WINDOWS\\TEMP）
    2. tempfile.gettempdir()（当其为纯 ASCII 时）
    3. 当前工作目录
    4. 非 Windows 平台使用 tempfile.gettempdir()
    """
    # Windows 专属硬编码
    if os.name == "nt":
        candidates = []
        root = os.environ.get("SystemRoot", r"C:\Windows")
        candidates.append(os.path.join(root, "Temp"))
        candidates.append(tempfile.gettempdir())
        try:
            candidates.append(os.getcwd())
        except OSError:
            pass

        for d in candidates:
            if d.isascii() and os.path.isdir(d) and os.access(d, os.W_OK):
                return d

        # 所有候选都不行时抛异常，不再静默兜底
        raise OSError(
            f"_safe_temp_dir: 无法找到可写的纯 ASCII 临时目录。"
            f"检查过: {candidates}"
        )

    # 非 Windows（Linux / macOS）：tempfile 足够
    return tempfile.gettempdir()


def _make_temp_file(prefix: str) -> str:
    """创建用于 Faiss 桥接的唯一临时文件，返回路径。

    使用 tempfile.mkstemp + UUID 保证多线程/多协程并发安全。
    """
    safe_dir = _safe_temp_dir()
    fd, path = tempfile.mkstemp(
        prefix=f"{prefix}_{uuid.uuid4().hex[:8]}_",
        suffix=".faiss",
        dir=safe_dir,
    )
    os.close(fd)
    return path


class EmbeddingStorage:
    def __init__(self, dimension: int, path: str | None = None) -> None:
        self.dimension = dimension
        self.path = path
        self.index = None
        if path and os.path.exists(path):
            self.index = self._read_index(path)
        else:
            base_index = faiss.IndexFlatL2(dimension)
            self.index = faiss.IndexIDMap(base_index)

    @staticmethod
    def _read_index(path: str) -> "faiss.Index":
        """读取 Faiss 索引，兼容含非 ASCII 字符的 Windows 路径。

        Faiss C++ fopen() 使用 ANSI codepage，无法处理 Python 传入的
        UTF-8 编码非 ASCII 路径。应对：先尝试直接读；失败则用 Python
        shutil.copy2 复制到纯 ASCII 临时文件再读。
        """
        try:
            return faiss.read_index(path)
        except RuntimeError:
            pass  # 不吞其他异常类型

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
    def _write_index(index: "faiss.Index", path: str) -> None:
        """保存 Faiss 索引，兼容含非 ASCII 字符的 Windows 路径。

        先写入纯 ASCII 临时文件，再用 Python shutil.move 移动到位。
        Python 文件操作使用 Windows wide-char API (CreateFileW)，
        正确支持 Unicode 路径。

        写入前先确保目标目录存在，防止 shutil.move 时目录缺失。
        """
        dirname = os.path.dirname(path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)

        tmp = _make_temp_file("_faiss_write")
        try:
            faiss.write_index(index, tmp)
            # Windows 同盘 move 是原子 rename，跨盘则走 copy+delete
            shutil.move(tmp, path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

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
        self.index.add_with_ids(vector.reshape(1, -1), np.array([id], dtype=np.int64))
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
        self.index.add_with_ids(vectors, np.array(ids, dtype=np.int64))
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
        # IndexFlatL2 是欧氏距离索引，不进行归一化，
        # 确保与 insert/insert_batch 的一致性
        distances, indices = self.index.search(vector.reshape(1, -1), k)
        return distances, indices

    async def delete(self, ids: list[int]) -> None:
        """删除向量

        Args:
            ids (list[int]): 要删除的向量ID列表

        """
        assert self.index is not None, "FAISS index is not initialized."
        id_array = np.array(ids, dtype=np.int64)
        self.index.remove_ids(id_array)
        await self.save_index()

    async def save_index(self) -> None:
        """保存索引（兼容含非 ASCII 字符的 Windows 路径）"""
        if self.index is None or not self.path:
            return
        self._write_index(self.index, self.path)
