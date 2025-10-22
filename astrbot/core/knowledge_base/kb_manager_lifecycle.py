"""
知识库管理器
负责知识库模块的初始化、配置和资源管理

架构说明:
- 知识库数据存储在独立的数据库 (data/knowledge_base/kb.db)
- 会话配置存储在主数据库 (data/astrbot.db) 以便于会话关联
"""

from pathlib import Path
from astrbot.core import logger
from astrbot.core.provider.manager import ProviderManager
from .injector import KnowledgeBaseInjector
from .retrieval.manager import RetrievalManager
from .retrieval.sparse_retriever import SparseRetriever
from .retrieval.rank_fusion import RankFusion
from .kb_sqlite import KBSQLiteDatabase
from .database import KBDatabase
from .vec_db_factory import VecDBFactory
from .manager import KBManager
from .parsers.text_parser import TextParser
from .parsers.pdf_parser import PDFParser
from .chunking.fixed_size import FixedSizeChunker


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

    kb_db: KBSQLiteDatabase
    vec_db_factory: VecDBFactory
    kb_database: KBDatabase
    kb_manager: KBManager
    retrieval_manager: RetrievalManager
    kb_injector: KnowledgeBaseInjector

    def __init__(
        self,
        config: dict,
        provider_manager: ProviderManager,
    ):
        """初始化知识库管理器

        Args:
            config: 配置字典
            provider_manager: Provider 管理器
        """
        self.config = config.get("knowledge_base", {})
        self.provider_manager = provider_manager
        self._initialized = False
        self._session_deleted_callback_registered = False

    async def initialize(self):
        """初始化知识库模块"""
        if not self.config.get("enabled", False):
            logger.info("知识库功能未启用")
            return

        try:
            logger.info("正在初始化知识库模块...")

            # 初始化数据库
            await self._init_kb_database()

            # 初始化向量数据库工厂
            await self._init_vector_db_factory()

            # 初始化解析器和分块器
            parsers = {
                "txt": TextParser(),
                "md": TextParser(),
                "markdown": TextParser(),
                "pdf": PDFParser(),
            }
            chunking_config = self.config.get("chunking", {})
            chunker = FixedSizeChunker(
                chunk_size=chunking_config.get("chunk_size", 512),
                chunk_overlap=chunking_config.get("chunk_overlap", 50),
            )

            # 初始化知识库管理器
            files_path = self.config.get("storage", {}).get(
                "files_path", "data/knowledge_base"
            )
            self.kb_manager = KBManager(
                db=self.kb_db,
                vec_db_factory=self.vec_db_factory,
                storage_path=files_path,
                parsers=parsers,
                chunker=chunker,
                provider_manager=self.provider_manager,
            )

            # 初始化检索管理器
            sparse_retriever = SparseRetriever(self.kb_database)
            rank_fusion = RankFusion(self.kb_database)
            self.retrieval_manager = RetrievalManager(
                vec_db_factory=self.vec_db_factory,
                sparse_retriever=sparse_retriever,
                rank_fusion=rank_fusion,
                kb_db=self.kb_database,
            )

            # 初始化上下文注入器
            self.kb_injector = KnowledgeBaseInjector(
                kb_db=self.kb_database,
                vec_db_factory=self.vec_db_factory,
                retrieval_manager=self.retrieval_manager,
            )

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
        db_path = self.config.get("storage", {}).get(
            "kb_db_path", "data/knowledge_base/kb.db"
        )
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self.kb_db = KBSQLiteDatabase(db_path)
        await self.kb_db.initialize()
        await self.kb_db.migrate_to_v1()
        self.kb_database = KBDatabase(self.kb_db)
        logger.info(f"KnowledgeBase database initialized: {db_path}")

    async def _init_vector_db_factory(self):
        """初始化向量数据库工厂"""
        storage_path = self.config.get("storage", {}).get(
            "vector_db_path", "data/knowledge_base/vectors"
        )
        Path(storage_path).mkdir(parents=True, exist_ok=True)
        self.vec_db_factory = VecDBFactory(storage_base_path=storage_path)

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

        # 关闭向量数据库工厂(关闭所有向量数据库实例)
        if self.vec_db_factory:
            try:
                await self.vec_db_factory.close_all()
                logger.debug("向量数据库工厂已关闭")
            except Exception as e:
                logger.warning(f"关闭向量数据库工厂时出错: {e}")

        # 关闭知识库独立数据库连接
        if self.kb_db:
            try:
                await self.kb_db.close()
                logger.debug("知识库数据库已关闭")
            except Exception as e:
                logger.warning(f"关闭知识库数据库时出错: {e}")

        self._initialized = False

        logger.info("知识库模块已终止")
