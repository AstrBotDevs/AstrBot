"""向量数据库工厂

负责为每个知识库创建和管理独立的向量数据库实例。

架构说明:
- 每个知识库拥有独立的向量数据库实例
- 向量数据库文件以 kb_id 命名
- 工厂类负责实例的创建、缓存和生命周期管理
"""

from pathlib import Path
from typing import Dict, Optional

from astrbot.core import logger
from astrbot.core.db.vec_db.base import BaseVecDB
from astrbot.core.db.vec_db.faiss_impl.vec_db import FaissVecDB
from astrbot.core.provider.provider import EmbeddingProvider


class VecDBFactory:
    """向量数据库工厂

    职责:
    - 为每个知识库创建独立的向量数据库实例
    - 缓存已创建的实例以提高性能
    - 管理向量数据库的生命周期
    """

    def __init__(
        self,
        storage_base_path: str,
    ):
        """初始化向量数据库工厂

        Args:
            storage_base_path: 向量数据库存储基础路径
        """
        self.storage_base_path = Path(storage_base_path)
        self._instances: Dict[str, BaseVecDB] = {}

        # 确保基础路径存在
        self.storage_base_path.mkdir(parents=True, exist_ok=True)

    async def get_vec_db(
        self, kb_id: str, embedding_provider: EmbeddingProvider
    ) -> BaseVecDB:
        """获取或创建指定知识库的向量数据库实例

        Args:
            kb_id: 知识库 ID
            embedding_provider: Embedding Provider 实例

        Returns:
            BaseVecDB: 向量数据库实例
        """
        # 如果已经创建过,直接返回缓存的实例
        if kb_id in self._instances:
            return self._instances[kb_id]

        # 创建新实例
        vec_db = await self._create_vec_db(kb_id, embedding_provider)
        self._instances[kb_id] = vec_db

        logger.debug(f"创建知识库 {kb_id} 的向量数据库实例")

        return vec_db

    async def _create_vec_db(
        self, kb_id: str, embedding_provider: EmbeddingProvider
    ) -> BaseVecDB:
        """创建向量数据库实例

        Args:
            kb_id: 知识库 ID
            embedding_provider: Embedding Provider 实例

        Returns:
            BaseVecDB: 向量数据库实例
        """
        # 为每个知识库创建独立的存储路径
        kb_storage_path = self.storage_base_path / kb_id
        kb_storage_path.mkdir(parents=True, exist_ok=True)

        doc_store_path = str(kb_storage_path / "documents.db")
        index_store_path = str(kb_storage_path / "index.faiss")

        vec_db = FaissVecDB(
            doc_store_path=doc_store_path,
            index_store_path=index_store_path,
            embedding_provider=embedding_provider,
        )

        await vec_db.initialize()

        return vec_db

    async def delete_vec_db(self, kb_id: str) -> bool:
        """删除指定知识库的向量数据库

        Args:
            kb_id: 知识库 ID

        Returns:
            bool: 是否删除成功
        """
        # 关闭并移除缓存的实例
        if kb_id in self._instances:
            try:
                await self._instances[kb_id].close()
            except Exception as e:
                logger.warning(f"关闭向量数据库失败 ({kb_id}): {e}")

            del self._instances[kb_id]

        # 删除文件系统中的向量数据库文件
        kb_storage_path = self.storage_base_path / kb_id
        if kb_storage_path.exists():
            try:
                import shutil

                shutil.rmtree(kb_storage_path)
                logger.info(f"已删除知识库 {kb_id} 的向量数据库文件")
                return True
            except Exception as e:
                logger.error(f"删除向量数据库文件失败 ({kb_id}): {e}")
                return False

        return True

    async def close_all(self):
        """关闭所有向量数据库实例"""
        for kb_id, vec_db in list(self._instances.items()):
            try:
                await vec_db.close()
                logger.debug(f"已关闭知识库 {kb_id} 的向量数据库")
            except Exception as e:
                logger.warning(f"关闭向量数据库失败 ({kb_id}): {e}")

        self._instances.clear()

    def has_instance(self, kb_id: str) -> bool:
        """检查是否已创建指定知识库的向量数据库实例

        Args:
            kb_id: 知识库 ID

        Returns:
            bool: 是否已创建实例
        """
        return kb_id in self._instances

    def get_cached_instance(self, kb_id: str) -> Optional[BaseVecDB]:
        """获取已缓存的向量数据库实例(不创建新实例)

        Args:
            kb_id: 知识库 ID

        Returns:
            Optional[BaseVecDB]: 向量数据库实例,如果不存在则返回 None
        """
        return self._instances.get(kb_id)
