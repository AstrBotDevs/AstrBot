from pathlib import Path

from sqlalchemy.exc import IntegrityError  # type: ignore

from astrbot import logger
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.utils.astrbot_path import get_astrbot_knowledge_base_path
from astrbot.core.utils.error_redaction import safe_error

# from .chunking.fixed_size import FixedSizeChunker
from .chunking.recursive import RecursiveCharacterChunker
from .kb_db_sqlite import KBSQLiteDatabase
from .kb_helper import KBHelper
from .models import KBDocument, KnowledgeBase
from .retrieval.manager import RetrievalManager, RetrievalResult
from .retrieval.rank_fusion import RankFusion
from .retrieval.sparse_retriever import SparseRetriever

FILES_PATH = get_astrbot_knowledge_base_path()
DB_PATH = Path(FILES_PATH) / "kb.db"
"""Knowledge Base storage root directory"""
CHUNKER = RecursiveCharacterChunker()
_KB_INITIALIZATION_ERROR = "Knowledge base initialization failed"


class KnowledgeBaseManager:
    kb_db: KBSQLiteDatabase
    retrieval_manager: RetrievalManager

    def __init__(
        self,
        provider_manager: ProviderManager,
    ) -> None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.provider_manager = provider_manager
        self._session_deleted_callback_registered = False

        self.kb_insts: dict[str, KBHelper] = {}

    async def initialize(self) -> None:
        """初始化知识库模块"""
        try:
            # 初始化数据库
            await self._init_kb_database()

            # 初始化检索管理器
            sparse_retriever = SparseRetriever(self.kb_db)
            rank_fusion = RankFusion(self.kb_db)
            self.retrieval_manager = RetrievalManager(
                sparse_retriever=sparse_retriever,
                rank_fusion=rank_fusion,
                kb_db=self.kb_db,
            )
            await self.load_kbs()

        except ImportError as exc:
            logger.error("知识库模块导入失败: %s", safe_error("", exc))
            logger.warning("请确保已安装所需依赖: pypdf, aiofiles, Pillow, rank-bm25")
        except Exception as exc:
            logger.error("知识库模块初始化失败: %s", safe_error("", exc))

    async def _init_kb_database(self) -> None:
        self.kb_db = KBSQLiteDatabase(DB_PATH.as_posix())
        await self.kb_db.initialize()
        logger.info(f"KnowledgeBase database initialized: {DB_PATH}")

    async def load_kbs(self) -> None:
        """加载所有知识库实例"""
        kb_records = await self.kb_db.list_kbs()
        for record in kb_records:
            kb_helper = self._build_kb_helper(record)
            try:
                await kb_helper.initialize()
            except Exception as exc:
                kb_helper.init_error = _KB_INITIALIZATION_ERROR
                logger.error("知识库初始化失败: %s", safe_error("", exc))
            self.kb_insts[record.kb_id] = kb_helper

    async def create_kb(
        self,
        kb_name: str,
        description: str | None = None,
        emoji: str | None = None,
        embedding_provider_id: str | None = None,
        rerank_provider_id: str | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        top_k_dense: int | None = None,
        top_k_sparse: int | None = None,
        top_m_final: int | None = None,
    ) -> KBHelper:
        """创建新的知识库实例"""
        if embedding_provider_id is None:
            raise ValueError("创建知识库时必须提供embedding_provider_id")
        # 预先检查名称是否已存在，避免依赖异常字符串匹配
        existing = await self.kb_db.get_kb_by_name(kb_name)
        if existing:
            raise ValueError(f"知识库名称 '{kb_name}' 已存在")

        kb = KnowledgeBase(
            kb_name=kb_name,
            description=description,
            emoji=emoji or "📚",
            embedding_provider_id=embedding_provider_id,
            rerank_provider_id=rerank_provider_id,
            chunk_size=chunk_size if chunk_size is not None else 512,
            chunk_overlap=chunk_overlap if chunk_overlap is not None else 50,
            top_k_dense=top_k_dense if top_k_dense is not None else 50,
            top_k_sparse=top_k_sparse if top_k_sparse is not None else 50,
            top_m_final=top_m_final if top_m_final is not None else 5,
        )
        try:
            async with self.kb_db.get_db() as session:
                session.add(kb)
                await session.flush()

                kb_helper = self._build_kb_helper(kb)
                await kb_helper.initialize()
                await session.commit()
                self.kb_insts[kb.kb_id] = kb_helper
                return kb_helper
        except IntegrityError as e:
            logger.exception("创建知识库失败：唯一约束冲突")
            raise ValueError(f"知识库名称 '{kb_name}' 已存在") from e
        except Exception:
            logger.exception("创建知识库失败")
            raise

    async def get_kb(self, kb_id: str) -> KBHelper | None:
        """获取知识库实例"""
        if kb_id in self.kb_insts:
            return self.kb_insts[kb_id]

    async def get_kb_by_name(self, kb_name: str) -> KBHelper | None:
        """通过名称获取知识库实例

        Args:
            kb_name: 知识库名称或 UUID

        Returns:
            KBHelper | None: 知识库实例，未找到返回 None
        """
        # 首先按名称匹配
        for kb_helper in self.kb_insts.values():
            if kb_helper.kb.kb_name == kb_name:
                return kb_helper

        # 如果没找到，尝试按 UUID 匹配（兼容旧配置）
        if kb_name in self.kb_insts:
            return self.kb_insts[kb_name]

        return None

    async def delete_kb(self, kb_id: str) -> bool:
        """删除知识库实例"""
        kb_helper = await self.get_kb(kb_id)
        if not kb_helper:
            return False

        await kb_helper.delete_vec_db()
        async with self.kb_db.get_db() as session:
            await session.delete(kb_helper.kb)
            await session.commit()

        self.kb_insts.pop(kb_id, None)
        return True

    async def list_kbs(self) -> list[KnowledgeBase]:
        """列出所有知识库实例"""
        kbs = [kb_helper.kb for kb_helper in self.kb_insts.values()]
        return kbs

    @staticmethod
    def _snapshot_kb_state(kb: KnowledgeBase) -> dict[str, object]:
        return {
            "kb_name": kb.kb_name,
            "description": kb.description,
            "emoji": kb.emoji,
            "embedding_provider_id": kb.embedding_provider_id,
            "rerank_provider_id": kb.rerank_provider_id,
            "chunk_size": kb.chunk_size,
            "chunk_overlap": kb.chunk_overlap,
            "top_k_dense": kb.top_k_dense,
            "top_k_sparse": kb.top_k_sparse,
            "top_m_final": kb.top_m_final,
        }

    @staticmethod
    def _restore_kb_state(kb: KnowledgeBase, previous_state: dict[str, object]) -> None:
        kb.kb_name = str(previous_state["kb_name"])
        kb.description = previous_state["description"]  # type: ignore[assignment]
        kb.emoji = previous_state["emoji"]  # type: ignore[assignment]
        kb.embedding_provider_id = previous_state["embedding_provider_id"]  # type: ignore[assignment]
        kb.rerank_provider_id = previous_state["rerank_provider_id"]  # type: ignore[assignment]
        kb.chunk_size = previous_state["chunk_size"]  # type: ignore[assignment]
        kb.chunk_overlap = previous_state["chunk_overlap"]  # type: ignore[assignment]
        kb.top_k_dense = previous_state["top_k_dense"]  # type: ignore[assignment]
        kb.top_k_sparse = previous_state["top_k_sparse"]  # type: ignore[assignment]
        kb.top_m_final = previous_state["top_m_final"]  # type: ignore[assignment]

    @staticmethod
    def _apply_kb_updates(
        kb: KnowledgeBase,
        *,
        kb_name: str | None,
        description: str | None,
        emoji: str | None,
        embedding_provider_id: str | None,
        rerank_provider_id: str | None,
        chunk_size: int | None,
        chunk_overlap: int | None,
        top_k_dense: int | None,
        top_k_sparse: int | None,
        top_m_final: int | None,
    ) -> None:
        if kb_name is not None:
            kb.kb_name = kb_name
        if description is not None:
            kb.description = description
        if emoji is not None:
            kb.emoji = emoji
        if embedding_provider_id is not None:
            kb.embedding_provider_id = embedding_provider_id
        kb.rerank_provider_id = rerank_provider_id
        if chunk_size is not None:
            kb.chunk_size = chunk_size
        if chunk_overlap is not None:
            kb.chunk_overlap = chunk_overlap
        if top_k_dense is not None:
            kb.top_k_dense = top_k_dense
        if top_k_sparse is not None:
            kb.top_k_sparse = top_k_sparse
        if top_m_final is not None:
            kb.top_m_final = top_m_final

    def _build_kb_helper(self, kb: KnowledgeBase) -> KBHelper:
        kb_helper = KBHelper(
            kb_db=self.kb_db,
            kb=kb,
            provider_manager=self.provider_manager,
            kb_root_dir=FILES_PATH,
            chunker=CHUNKER,
        )
        retrieval_manager = getattr(self, "retrieval_manager", None)
        if retrieval_manager is not None:
            kb_helper.sparse_retriever = retrieval_manager.sparse_retriever
        return kb_helper

    async def _persist_kb_changes(self, kb: KnowledgeBase) -> None:
        async with self.kb_db.get_db() as session:
            session.add(kb)
            await session.commit()
            await session.refresh(kb)

    async def update_kb(
        self,
        kb_id: str,
        kb_name: str,
        description: str | None = None,
        emoji: str | None = None,
        embedding_provider_id: str | None = None,
        rerank_provider_id: str | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        top_k_dense: int | None = None,
        top_k_sparse: int | None = None,
        top_m_final: int | None = None,
    ) -> KBHelper | None:
        """更新知识库实例"""
        kb_helper = await self.get_kb(kb_id)
        if not kb_helper:
            return None

        kb = kb_helper.kb
        previous_state = self._snapshot_kb_state(kb)
        previous_init_error = kb_helper.init_error

        self._apply_kb_updates(
            kb,
            kb_name=kb_name,
            description=description,
            emoji=emoji,
            embedding_provider_id=embedding_provider_id,
            rerank_provider_id=rerank_provider_id,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            top_k_dense=top_k_dense,
            top_k_sparse=top_k_sparse,
            top_m_final=top_m_final,
        )

        # Build a new helper first. Keep current vec_db alive until new init succeeds.
        new_helper = self._build_kb_helper(kb)

        try:
            await new_helper.initialize()
        except Exception as exc:
            # Roll back in-memory settings and keep current helper available.
            self._restore_kb_state(kb, previous_state)
            kb_helper.init_error = previous_init_error
            logger.error(
                "知识库重新初始化失败，继续使用旧实例: %s", safe_error("", exc)
            )
            return kb_helper

        await self._persist_kb_changes(kb)
        old_helper = kb_helper
        self.kb_insts[kb_id] = new_helper
        await old_helper.terminate()
        new_helper.init_error = None
        return new_helper

    async def retrieve(
        self,
        query: str,
        kb_names: list[str],
        top_k_fusion: int = 20,
        top_m_final: int = 5,
    ) -> dict | None:
        """从指定知识库中检索相关内容"""
        kb_ids = []
        kb_id_helper_map = {}
        unavailable_kbs = []
        for kb_name in kb_names:
            if kb_helper := await self.get_kb_by_name(kb_name):
                if kb_helper.init_error:
                    unavailable_kbs.append(kb_name)
                    logger.warning("知识库不可用")
                    continue
                kb_ids.append(kb_helper.kb.kb_id)
                kb_id_helper_map[kb_helper.kb.kb_id] = kb_helper

        # all requested KBs are unavailable
        if not kb_ids and unavailable_kbs:
            raise ValueError("所有请求的知识库均不可用")

        if not kb_ids:
            return {}

        results = await self.retrieval_manager.retrieve(
            query=query,
            kb_ids=kb_ids,
            kb_id_helper_map=kb_id_helper_map,
            top_k_fusion=top_k_fusion,
            top_m_final=top_m_final,
        )
        if not results:
            return None

        context_text = self._format_context(results)

        results_dict = [
            {
                "chunk_id": r.chunk_id,
                "doc_id": r.doc_id,
                "kb_id": r.kb_id,
                "kb_name": r.kb_name,
                "doc_name": r.doc_name,
                "chunk_index": r.metadata.get("chunk_index", 0),
                "content": r.content,
                "score": r.score,
                "char_count": r.metadata.get("char_count", 0),
            }
            for r in results
        ]

        return {
            "context_text": context_text,
            "results": results_dict,
        }

    def _format_context(self, results: list[RetrievalResult]) -> str:
        """格式化知识上下文

        Args:
            results: 检索结果列表

        Returns:
            str: 格式化的上下文文本

        """
        lines = ["以下是相关的知识库内容,请参考这些信息回答用户的问题:\n"]

        for i, result in enumerate(results, 1):
            lines.append(f"【知识 {i}】")
            lines.append(f"来源: {result.kb_name} / {result.doc_name}")
            lines.append(f"内容: {result.content}")
            lines.append(f"相关度: {result.score:.2f}")
            lines.append("")

        return "\n".join(lines)

    async def terminate(self) -> None:
        """终止所有知识库实例,关闭数据库连接"""
        for kb_id, kb_helper in self.kb_insts.items():
            try:
                await kb_helper.terminate()
            except Exception as e:
                logger.error(f"关闭知识库 {kb_id} 失败: {e}")

        self.kb_insts.clear()

        # 关闭元数据数据库
        if hasattr(self, "kb_db") and self.kb_db:
            try:
                await self.kb_db.close()
            except Exception as e:
                logger.error(f"关闭知识库元数据数据库失败: {e}")

    async def upload_from_url(
        self,
        kb_id: str,
        url: str,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        batch_size: int = 32,
        tasks_limit: int = 3,
        max_retries: int = 3,
        progress_callback=None,
    ) -> KBDocument:
        """从 URL 上传文档到指定的知识库

        Args:
            kb_id: 知识库 ID
            url: 要提取内容的网页 URL
            chunk_size: 文本块大小
            chunk_overlap: 文本块重叠大小
            batch_size: 批处理大小
            tasks_limit: 并发任务限制
            max_retries: 最大重试次数
            progress_callback: 进度回调函数

        Returns:
            KBDocument: 上传的文档对象

        Raises:
            ValueError: 如果知识库不存在或 URL 为空
            IOError: 如果网络请求失败
        """
        kb_helper = await self.get_kb(kb_id)
        if not kb_helper:
            raise ValueError(f"Knowledge base with id {kb_id} not found.")

        return await kb_helper.upload_from_url(
            url=url,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            batch_size=batch_size,
            tasks_limit=tasks_limit,
            max_retries=max_retries,
            progress_callback=progress_callback,
        )
