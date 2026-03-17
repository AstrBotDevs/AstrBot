import base64
import traceback
from io import BytesIO

from astrbot.api import logger
from astrbot.core.db.vec_db.faiss_impl import FaissVecDB
from astrbot.core.knowledge_base.kb_helper import KBHelper
from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager


async def generate_tsne_visualization(
    query: str,
    kb_names: list[str],
    kb_manager: KnowledgeBaseManager,
) -> str | None:
    """生成 t-SNE 可视化图片

    Args:
        query: 查询文本
        kb_names: 知识库名称列表
        kb_manager: 知识库管理器

    Returns:
        图片路径或 None

    """
    try:
        import faiss
        import matplotlib
        import numpy as np

        matplotlib.use("Agg")  # 使用非交互式后端
        import matplotlib.pyplot as plt
        from sklearn.manifold import TSNE
    except ImportError as e:
        raise Exception(
            "缺少必要的库以生成 t-SNE 可视化。请安装 matplotlib 和 scikit-learn: {e}",
        ) from e

    try:
        # 获取第一个知识库的向量数据
        kb_helper: KBHelper | None = None
        for kb_name in kb_names:
            kb_helper = await kb_manager.get_kb_by_name(kb_name)
            if kb_helper:
                break

        if not kb_helper:
            logger.warning("未找到知识库")
            return None

        kb = kb_helper.kb
        index_path = kb_helper.kb_dir / "index.faiss"

        # 读取 FAISS 索引
        if not index_path.exists():
            logger.warning(f"FAISS 索引不存在: {index_path!s}")
            return None

        index = faiss.read_index(str(index_path))

        if index.ntotal == 0:
            logger.warning("索引为空")
            return None

        # 提取所有向量
        logger.info(f"提取 {index.ntotal} 个向量用于可视化...")
        if isinstance(index, faiss.IndexIDMap):
            base_index = faiss.downcast_index(index.index)
            if hasattr(base_index, "reconstruct_n"):
                vectors = base_index.reconstruct_n(0, index.ntotal)
            else:
                vectors = np.zeros((index.ntotal, index.d), dtype=np.float32)
                for i in range(index.ntotal):
                    base_index.reconstruct(i, vectors[i])
        elif hasattr(index, "reconstruct_n"):
            vectors = index.reconstruct_n(0, index.ntotal)
        else:
            vectors = np.zeros((index.ntotal, index.d), dtype=np.float32)
            for i in range(index.ntotal):
                index.reconstruct(i, vectors[i])

        # 获取查询向量
        vec_db: FaissVecDB = kb_helper.vec_db  # type: ignore
        embedding_provider = vec_db.embedding_provider
        query_embedding = await embedding_provider.get_embedding(query)
        query_vector = np.array([query_embedding], dtype=np.float32)

        # 合并所有向量和查询向量
        all_vectors = np.vstack([vectors, query_vector])

        # t-SNE 降维
        logger.info("开始 t-SNE 降维...")
        perplexity = min(30, all_vectors.shape[0] - 1)
        tsne = TSNE(n_components=2, random_state=42, perplexity=perplexity)
        vectors_2d = tsne.fit_transform(all_vectors)

        # 分离知识库向量和查询向量
        kb_vectors_2d = vectors_2d[:-1]
        query_vector_2d = vectors_2d[-1]

        # 可视化
        logger.info("生成可视化图表...")
        plt.figure(figsize=(14, 10))

        # 绘制知识库向量
        scatter = plt.scatter(
            kb_vectors_2d[:, 0],
            kb_vectors_2d[:, 1],
            alpha=0.5,
            s=40,
            c=range(len(kb_vectors_2d)),
            cmap="viridis",
            label="Knowledge Base Vectors",
        )

        # 绘制查询向量（红色 X）
        plt.scatter(
            query_vector_2d[0],
            query_vector_2d[1],
            c="red",
            s=300,
            marker="X",
            edgecolors="black",
            linewidths=2,
            label="Query",
            zorder=5,
        )

        # 添加查询文本标注
        plt.annotate(
            "Query",
            (query_vector_2d[0], query_vector_2d[1]),
            xytext=(10, 10),
            textcoords="offset points",
            fontsize=10,
            bbox={"boxstyle": "round,pad=0.5", "fc": "yellow", "alpha": 0.7},
            arrowprops={"arrowstyle": "->", "connectionstyle": "arc3,rad=0"},
        )

        plt.colorbar(scatter, label="Vector Index")
        plt.title(
            f"t-SNE Visualization: Query in Knowledge Base\n"
            f"({index.ntotal} vectors, {index.d} dimensions, KB: {kb.kb_name})",
            fontsize=14,
            pad=20,
        )
        plt.xlabel("t-SNE Dimension 1", fontsize=12)
        plt.ylabel("t-SNE Dimension 2", fontsize=12)
        plt.grid(True, alpha=0.3)
        plt.legend(fontsize=10, loc="upper right")

        # base64 编码图片返回
        buffer = BytesIO()
        plt.savefig(buffer, format="png", dpi=150, bbox_inches="tight")
        plt.close()
        buffer.seek(0)
        img_base64 = base64.b64encode(buffer.read()).decode("utf-8")
        return img_base64

    except Exception as e:
        logger.error(f"生成 t-SNE 可视化时出错: {e}")
        logger.error(traceback.format_exc())
        return None
