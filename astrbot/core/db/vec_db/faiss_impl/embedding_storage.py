from __future__ import annotations

import os
import shutil
import tempfile
from typing import TYPE_CHECKING

import numpy as np

from astrbot import logger

if TYPE_CHECKING:
    import faiss

# ── Faiss C++ fopen() 在 Windows 上使用 ANSI codepage ──
# Python 传给 Faiss 的路径是 UTF-8 字节，但 Windows fopen 期望 ANSI 编码，
# 导致含非 ASCII 字符的路径（如 C:\Users\中文用户名\...）被解读为乱码而失败。
# 本模块通过"纯 ASCII 临时文件桥接"规避此问题。


#: 模长低于该阈值的行视为零向量，不做缩放，避免放大浮点噪声。
_MIN_NORM = 1e-12


def _l2_normalize(vectors: np.ndarray) -> np.ndarray:
    """把每行缩放到单位长度，让 L2 距离等价于按余弦相似度排序。

    ``IndexFlatL2`` 返回欧氏距离的平方，配合 ``score = 1 - distance / 2``
    只有在向量是单位向量时才等于余弦相似度。部分提供商返回的向量未归一化
    （如 Gemini 在低于 3072 维时），且模长会随文本长度漂移，此时分数由模长
    而非语义主导，检索排序会失效。

    用 float64 计算范数再转回 float32：float32 下对接近上限的值求平方会
    溢出成 ``inf``，导致整行归一化后变成全零。

    Args:
        vectors: 一维或二维数组，最后一维是向量维度。

    Returns:
        与输入形状相同的 float32 单位向量数组；零向量行保持为零。
    """
    array = np.asarray(vectors, dtype=np.float32)
    if array.size == 0:
        return array

    wide = array.astype(np.float64)
    norms = np.linalg.norm(wide, axis=-1, keepdims=True)
    # 零向量与极小模长不参与缩放，否则会产出 inf/NaN。
    norms = np.where(norms < _MIN_NORM, 1.0, norms)
    return (wide / norms).astype(np.float32)


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
        self._pending_save = False
        if path and os.path.exists(path):
            self.index = self._read_index(path)
            self._normalize_loaded_index()
        else:
            if dimension <= 0:
                raise ValueError(
                    f"无效的嵌入向量维度: {dimension}。请检查该知识库使用的 Embedding "
                    "Provider 是否正确配置了 embedding_dimensions。",
                )
            base_index = faiss.IndexFlatL2(dimension)
            self.index = faiss.IndexIDMap(base_index)

    def _normalize_loaded_index(self) -> None:
        """把旧索引里未归一化的向量就地归一化。

        旧版本入库时未做归一化，而检索侧现在会归一化查询向量。两侧标准不
        一致会让相似度整体失真（分数偏移，排序也可能错），因此加载旧索引时
        统一重建为归一化后的向量。

        仅处理 ``IndexIDMap(IndexFlatL2)``；其他索引类型（如已训练的 IVF）
        无法安全地重建向量，直接跳过以保证兼容。
        """
        import faiss

        if self.index is None:
            return

        # AstrBot 只会用 IndexIDMap(IndexFlatL2)；其他布局（如已训练的 IVF）
        # 无法安全重建向量，直接跳过以保证兼容。
        if not isinstance(self.index, faiss.IndexIDMap):
            return

        inner = faiss.downcast_index(self.index.index)
        if not isinstance(inner, faiss.IndexFlat) or inner.ntotal == 0:
            return

        try:
            # IndexFlat 支持按位置取回原始向量。
            vectors = inner.reconstruct_n(0, inner.ntotal)
        except RuntimeError:
            logger.debug("[EmbeddingStorage] 索引不支持 reconstruct，跳过归一化。")
            return

        # 已经全部是单位向量时不重建，避免每次加载都重写索引文件。
        # 零向量的模长是 0 而非 1，必须排除在外，否则会误判成"未归一化"，
        # 导致每次启动都重建一遍索引。
        norms = np.linalg.norm(vectors.astype(np.float64), axis=1)
        nonzero = norms[norms >= _MIN_NORM]
        if nonzero.size == 0 or np.allclose(nonzero, 1.0, atol=1e-5):
            return

        normalized = _l2_normalize(vectors)
        ids = faiss.vector_to_array(self.index.id_map)
        rebuilt = faiss.IndexIDMap(faiss.IndexFlatL2(inner.d))
        rebuilt.add_with_ids(normalized, ids)
        self.index = rebuilt
        self._pending_save = True

        logger.info(
            f"[EmbeddingStorage] 已把 {len(normalized)} 条旧向量归一化为单位向量。",
        )

    async def flush(self) -> None:
        """若加载旧索引时做过归一化重建，则把结果落盘。

        归一化是检索质量优化，不是正确性前提——内存里的索引已经可用。写盘
        失败（磁盘满、只读挂载等）不应该让知识库整个打不开，因此这里只记日志
        不抛异常。
        """
        if not self._pending_save:
            return
        try:
            await self.save_index()
        except Exception as e:
            # 只记异常类型：OSError 等异常文本里常带完整路径，会把本机用户名
            # 等本地信息写进日志。
            logger.warning(
                f"[EmbeddingStorage] 归一化后的索引写盘失败，本次运行使用内存中"
                f"已归一化的索引，稍后会重试: {type(e).__name__}",
            )
            return
        self._pending_save = False

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
        """保存 Faiss 索引，兼容含非 ASCII 字符的 Windows 路径。"""
        import faiss

        dirname = os.path.dirname(path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)

        if not _needs_bridge(path):
            faiss.write_index(index, path)
            return

        tmp = _make_temp_file("_faiss_write")
        try:
            faiss.write_index(index, tmp)
            shutil.move(tmp, path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    async def insert(self, vector: np.ndarray, id: int) -> None:
        """插入向量"""
        assert self.index is not None, "FAISS index is not initialized."
        if vector.shape[0] != self.dimension:
            raise ValueError(
                f"向量维度不匹配, 期望: {self.dimension}, 实际: {vector.shape[0]}",
            )
        self.index.add_with_ids(
            _l2_normalize(vector.reshape(1, -1)), np.array([id], dtype=np.int64)
        )
        await self.save_index()

    async def insert_batch(self, vectors: np.ndarray, ids: list[int]) -> None:
        """批量插入向量"""
        assert self.index is not None, "FAISS index is not initialized."
        if len(vectors.shape) != 2:
            raise ValueError(
                f"向量必须是二维数组, 当前维度: {len(vectors.shape)}",
            )
        if vectors.shape[1] != self.dimension:
            raise ValueError(
                f"向量维度不匹配, 期望: {self.dimension}, 实际: {vectors.shape[1]}",
            )
        self.index.add_with_ids(_l2_normalize(vectors), np.array(ids, dtype=np.int64))
        await self.save_index()

    async def search(self, vector: np.ndarray, k: int) -> tuple:
        """搜索向量

        接受 1D (d,) 或 2D (1, d) 向量，自动展平为 Faiss 期望的 (1, d)。
        """
        assert self.index is not None, "FAISS index is not initialized."
        vector = np.asarray(vector, dtype=np.float32).ravel()
        if vector.shape[0] != self.dimension:
            raise ValueError(
                f"向量维度不匹配, 期望: {self.dimension}, 实际: {vector.shape[0]}",
            )
        distances, indices = self.index.search(_l2_normalize(vector.reshape(1, -1)), k)
        return distances, indices

    async def delete(self, ids: list[int]) -> None:
        """删除向量

        删除不存在的 ID 时 Faiss 会抛 RuntimeError。
        由于 remove_ids 为幂等操作，此处忽略该错误。
        """
        assert self.index is not None, "FAISS index is not initialized."
        try:
            self.index.remove_ids(np.array(ids, dtype=np.int64))
        except RuntimeError:
            # 幂等：删除已不存在的 ID，安全忽略
            pass
        await self.save_index()

    async def save_index(self) -> None:
        """保存索引（兼容含非 ASCII 字符的 Windows 路径）"""
        if self.index is None or not self.path:
            return
        self._write_index(self.index, self.path)
