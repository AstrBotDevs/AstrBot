"""
知识库管理器
负责知识库模块的初始化、配置和资源管理

架构说明:
- 知识库数据存储在独立的数据库 (data/knowledge_base/kb.db)
- 会话配置存储在主数据库 (data/astrbot.db) 以便于会话关联
"""

from pathlib import Path
from astrbot.core import logger
from astrbot.core.db import BaseDatabase
from astrbot.core.provider.manager import ProviderManager


class KnowledgeBaseManager:
    """知识库管理器

    职责:
    - 知识库模块的初始化
    - Embedding Provider 和 Rerank Provider 的选择
    - 各个子组件的协调管理
    - 注册会话删除回调，实现级联清理

    架构说明:
    - 知识库数据存储在独立数据库 (kb.db)
    - 会话配置存储在独立数据库 (kb.db)，会话ID来自主数据库
    - 通过回调机制实现与主数据库的生命周期同步
    """

    def __init__(
        self,
        config: dict,
        main_db: BaseDatabase,
        provider_manager: ProviderManager,
    ):
        """初始化知识库管理器

        Args:
            config: 配置字典
            main_db: 主数据库实例 (不直接使用，仅用于类型引用)
            provider_manager: Provider 管理器
        """
        self.config = config.get("knowledge_base", {})
        self.provider_manager = provider_manager

        # 知识库独立数据库
        self.kb_db = None

        # 组件实例
        self.kb_database = None
        self.kb_manager = None
        self.kb_vec_db = None
        self.retrieval_manager = None
        self.kb_injector = None

        self._initialized = False
        self._session_deleted_callback_registered = False

    async def initialize(self):
        """初始化知识库模块"""
        if not self.config.get("enabled", False):
            logger.info("知识库功能未启用")
            return

        try:
            logger.info("正在初始化知识库模块...")

            # 1. 检查并选择 Embedding Provider
            embedding_provider = self._select_embedding_provider()
            if not embedding_provider:
                logger.warning("未配置 Embedding Provider，知识库功能无法使用")
                return

            # 2. 初始化数据库
            await self._init_kb_database()
            await self._init_database()

            # 3. 初始化向量数据库
            await self._init_vector_db(embedding_provider)

            # 4. 初始化解析器和分块器
            parsers = self._init_parsers()
            chunker = self._init_chunker()

            # 5. 初始化知识库管理器
            await self._init_kb_manager(parsers, chunker)

            # 6. 初始化检索管理器
            await self._init_retrieval_manager()

            # 7. 初始化上下文注入器
            await self._init_injector()

            self._initialized = True
            logger.info("知识库模块初始化完成")

        except ImportError as e:
            logger.error(f"知识库模块导入失败: {e}")
            logger.warning("请确保已安装所需依赖: pypdf, aiofiles, Pillow, rank-bm25")
        except Exception as e:
            logger.error(f"知识库模块初始化失败: {e}")
            import traceback

            logger.error(traceback.format_exc())

    async def _init_kb_database(self):
        """初始化知识库独立数据库"""
        from astrbot.core.knowledge_base.kb_sqlite import KBSQLiteDatabase

        db_path = self.config.get("storage", {}).get(
            "kb_db_path", "data/knowledge_base/kb.db"
        )
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self.kb_db = KBSQLiteDatabase(db_path)
        await self.kb_db.initialize()
        await self.kb_db.migrate_to_v1()

        logger.info(f"知识库独立数据库已初始化: {db_path}")

    async def _init_database(self):
        """初始化知识库数据库操作类"""
        from astrbot.core.knowledge_base.database import KBDatabase

        self.kb_database = KBDatabase(self.kb_db)

    async def _init_vector_db(self, embedding_provider):
        """初始化向量数据库"""
        from astrbot.core.db.vec_db.faiss_impl import FaissVecDB

        storage_path = self.config.get("storage", {}).get(
            "vector_db_path", "data/knowledge_base/vectors"
        )
        Path(storage_path).mkdir(parents=True, exist_ok=True)

        self.kb_vec_db = FaissVecDB(
            doc_store_path=f"{storage_path}/documents.db",
            index_store_path=f"{storage_path}/index.faiss",
            embedding_provider=embedding_provider,
        )
        await self.kb_vec_db.initialize()

    def _init_parsers(self) -> dict:
        """初始化文档解析器"""
        from astrbot.core.knowledge_base.parsers.text_parser import TextParser
        from astrbot.core.knowledge_base.parsers.pdf_parser import PDFParser

        return {
            "txt": TextParser(),
            "md": TextParser(),
            "markdown": TextParser(),
            "pdf": PDFParser(),
        }

    def _init_chunker(self):
        """初始化分块器"""
        from astrbot.core.knowledge_base.chunking.fixed_size import FixedSizeChunker

        chunking_config = self.config.get("chunking", {})
        return FixedSizeChunker(
            chunk_size=chunking_config.get("chunk_size", 512),
            chunk_overlap=chunking_config.get("chunk_overlap", 50),
        )

    async def _init_kb_manager(self, parsers: dict, chunker):
        """初始化知识库管理器"""
        from astrbot.core.knowledge_base.manager import KBManager

        files_path = self.config.get("storage", {}).get(
            "files_path", "data/knowledge_base"
        )

        self.kb_manager = KBManager(
            db=self.kb_db,  # 使用独立的知识库数据库
            vec_db=self.kb_vec_db,
            storage_path=files_path,
            parsers=parsers,
            chunker=chunker,
        )

    async def _init_retrieval_manager(self):
        """初始化检索管理器"""
        from astrbot.core.knowledge_base.retrieval.manager import RetrievalManager
        from astrbot.core.knowledge_base.retrieval.sparse_retriever import (
            SparseRetriever,
        )
        from astrbot.core.knowledge_base.retrieval.rank_fusion import RankFusion

        sparse_retriever = SparseRetriever(self.kb_database)
        rank_fusion = RankFusion(self.kb_database)

        # 选择 Rerank Provider (可选)
        rerank_provider = self._select_rerank_provider()

        self.retrieval_manager = RetrievalManager(
            vec_db=self.kb_vec_db,
            sparse_retriever=sparse_retriever,
            rank_fusion=rank_fusion,
            kb_db=self.kb_database,
            rerank_provider=rerank_provider,
        )

    async def _init_injector(self):
        """初始化上下文注入器"""
        from astrbot.core.knowledge_base.injector import KnowledgeBaseInjector

        self.kb_injector = KnowledgeBaseInjector(
            kb_db=self.kb_database,
            retrieval_manager=self.retrieval_manager,
        )

    def _select_embedding_provider(self):
        """选择 Embedding Provider

        逻辑:
        - 如果配置了 embedding_provider_id，则使用指定的 provider
        - 如果没有配置，但有 embedding provider，则使用第一个
        - 如果有多个 embedding provider 但没有指定，则警告并使用第一个
        """
        embedding_providers = self.provider_manager.embedding_provider_insts

        if not embedding_providers:
            return None

        configured_provider_id = self.config.get("embedding_provider_id")

        if configured_provider_id:
            # 按 ID 查找
            for provider in embedding_providers:
                provider_id = provider.meta().id
                if provider_id == configured_provider_id:
                    logger.info(f"知识库使用 Embedding Provider: {provider_id}")
                    return provider
            logger.warning(
                f"未找到配置的 Embedding Provider ID: {configured_provider_id}，"
                f"将使用第一个可用的"
            )

        if len(embedding_providers) > 1 and not configured_provider_id:
            provider = embedding_providers[0]
            provider_id = provider.meta().id
            logger.info(
                f"检测到 {len(embedding_providers)} 个 Embedding Provider，"
                f"未在配置文件中指定 embedding_provider_id，将使用第一个: {provider_id}"
            )
            return provider

        provider = embedding_providers[0]
        provider_id = provider.meta().id
        logger.info(f"知识库使用 Embedding Provider: {provider_id}")
        return provider

    def _select_rerank_provider(self):
        """选择 Rerank Provider (可选)"""
        if not self.config.get("retrieval", {}).get("enable_rerank", True):
            return None

        rerank_providers = self.provider_manager.rerank_provider_insts
        if not rerank_providers:
            return None

        configured_provider_id = self.config.get("rerank_provider_id")

        if configured_provider_id:
            for provider in rerank_providers:
                provider_id = provider.meta().id
                if provider_id == configured_provider_id:
                    logger.info(f"知识库使用 Rerank Provider: {provider_id}")
                    return provider
            logger.warning(f"未找到配置的 Rerank Provider ID: {configured_provider_id}")

        if len(rerank_providers) > 0:
            provider = rerank_providers[0]
            provider_id = provider.meta().id
            logger.info(f"知识库使用 Rerank Provider: {provider_id}")
            return provider

        return None

    @property
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized

    def get_kb_manager(self):
        """获取知识库管理器"""
        return self.kb_manager if self._initialized else None

    def get_kb_injector(self):
        """获取知识库上下文注入器"""
        return self.kb_injector if self._initialized else None

    def register_session_lifecycle_hooks(self, conversation_manager):
        """注册会话生命周期钩子

        在会话删除时自动清理知识库配置，实现零侵入的级联清理。

        Args:
            conversation_manager: 会话管理器实例
        """
        if self._session_deleted_callback_registered or not self._initialized:
            return

        async def on_session_deleted(session_id: str):
            """会话删除回调：清理知识库配置"""
            try:
                await self.kb_database.delete_session_kb_config_by_session_id(
                    session_id
                )
                logger.info(f"已清理会话知识库配置: {session_id}")
            except Exception as e:
                logger.error(f"清理会话知识库配置失败 ({session_id}): {e}")

        conversation_manager.register_on_session_deleted(on_session_deleted)
        self._session_deleted_callback_registered = True
        logger.info("已注册知识库会话删除回调")

    async def reinitialize(self):
        """重新初始化知识库模块

        用于在运行时动态初始化知识库模块（例如用户添加了 embedding provider 后）
        """
        if self._initialized:
            logger.info("知识库模块已初始化，将重新初始化")
            await self.terminate()

        await self.initialize()
        return self._initialized

    async def terminate(self):
        """终止知识库模块，清理资源"""
        if not self._initialized:
            return

        logger.info("正在终止知识库模块...")

        # 关闭向量数据库连接
        if self.kb_vec_db:
            try:
                await self.kb_vec_db.close()
                logger.debug("向量数据库已关闭")
            except Exception as e:
                logger.warning(f"关闭向量数据库时出错: {e}")

        # 关闭知识库独立数据库连接
        if self.kb_db:
            try:
                await self.kb_db.close()
                logger.debug("知识库数据库已关闭")
            except Exception as e:
                logger.warning(f"关闭知识库数据库时出错: {e}")

        # 清理资源
        self._initialized = False
        self.kb_db = None
        self.kb_database = None
        self.kb_manager = None
        self.kb_vec_db = None
        self.retrieval_manager = None
        self.kb_injector = None

        logger.info("知识库模块已终止")
