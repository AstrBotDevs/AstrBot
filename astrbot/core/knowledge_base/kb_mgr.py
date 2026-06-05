import asyncio
import time
from pathlib import Path

from sqlalchemy import delete
from sqlmodel import col

from astrbot.core import logger
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.utils.astrbot_path import get_astrbot_knowledge_base_path

# from .chunking.fixed_size import FixedSizeChunker
from .chunking.recursive import RecursiveCharacterChunker
from .kb_db_sqlite import KBSQLiteDatabase
from .kb_helper import KBHelper
from .models import KBDocument, KBMedia, KnowledgeBase
from .retrieval.manager import RetrievalManager, RetrievalResult
from .retrieval.rank_fusion import RankFusion
from .retrieval.sparse_retriever import SparseRetriever

FILES_PATH = get_astrbot_knowledge_base_path()
DB_PATH = Path(FILES_PATH) / "kb.db"
"""Knowledge Base storage root directory"""
CHUNKER = RecursiveCharacterChunker()
_UNSET = object()
INIT_RETRY_COOLDOWN_SECONDS = 60.0
INIT_RETRY_MAX_ATTEMPTS = 3


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
        self._kb_name_index: dict[str, str] = {}
        self._kb_instances_lock = asyncio.Lock()

    def _ensure_kb_name_index(self) -> None:
        if not hasattr(self, "kb_insts"):
            self.kb_insts = {}
        if not hasattr(self, "_kb_name_index"):
            self._kb_name_index = {}
        known_ids = set(self.kb_insts)
        self._kb_name_index = {
            name: kb_id
            for name, kb_id in self._kb_name_index.items()
            if kb_id in known_ids
        }
        for kb_id, kb_helper in self.kb_insts.items():
            self._kb_name_index[kb_helper.kb.kb_name] = kb_id

    def _ensure_kb_instances_lock(self) -> asyncio.Lock:
        if not hasattr(self, "_kb_instances_lock"):
            self._kb_instances_lock = asyncio.Lock()
        return self._kb_instances_lock

    def _set_kb_instance(self, kb_id: str, kb_helper: KBHelper) -> None:
        self._ensure_kb_name_index()
        self.kb_insts[kb_id] = kb_helper
        self._kb_name_index = {
            name: indexed_kb_id
            for name, indexed_kb_id in self._kb_name_index.items()
            if indexed_kb_id != kb_id
        }
        self._kb_name_index[kb_helper.kb.kb_name] = kb_id

    def _get_kb_unlocked(self, kb_id: str) -> KBHelper | None:
        if not hasattr(self, "kb_insts"):
            self.kb_insts = {}
        return self.kb_insts.get(kb_id)

    def _can_retry_helper_init(self, kb_helper: KBHelper) -> bool:
        if not kb_helper.init_error:
            return False
        retry_count = getattr(kb_helper, "init_retry_count", 0)
        if retry_count >= INIT_RETRY_MAX_ATTEMPTS:
            return False
        last_retry_at = getattr(kb_helper, "last_init_retry_at", 0.0)
        return time.monotonic() - last_retry_at >= INIT_RETRY_COOLDOWN_SECONDS

    async def _retry_helper_init_if_due(self, kb_helper: KBHelper) -> None:
        if not self._can_retry_helper_init(kb_helper):
            return

        kb_helper.init_retry_count = getattr(kb_helper, "init_retry_count", 0) + 1
        kb_helper.last_init_retry_at = time.monotonic()
        try:
            await kb_helper.initialize()
            kb_helper.init_error = None
            kb_helper.init_retry_count = 0
            kb_helper.last_init_retry_at = 0.0
        except Exception as e:
            kb_helper.init_error = str(e)
            logger.warning(
                f"知识库 {kb_helper.kb.kb_name}({kb_helper.kb.kb_id}) "
                f"第 {kb_helper.init_retry_count} 次重新初始化失败: {e}",
                exc_info=True,
            )

    def _remove_kb_instance(self, kb_id: str) -> None:
        self._ensure_kb_name_index()
        self.kb_insts.pop(kb_id, None)
        self._kb_name_index = {
            name: indexed_kb_id
            for name, indexed_kb_id in self._kb_name_index.items()
            if indexed_kb_id != kb_id
        }

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

        except ImportError as e:
            logger.error(f"知识库模块导入失败: {e}")
            logger.warning("请确保已安装所需依赖: pypdf, aiofiles, Pillow, rank-bm25")
        except Exception as e:
            logger.error(f"知识库模块初始化失败: {e}", exc_info=True)

    async def _init_kb_database(self) -> None:
        self.kb_db = KBSQLiteDatabase(DB_PATH.as_posix())
        await self.kb_db.initialize()
        await self.kb_db.migrate_to_v1()
        logger.info(f"KnowledgeBase database initialized: {DB_PATH}")

    async def load_kbs(self) -> None:
        """加载所有知识库实例"""
        kb_records = await self.kb_db.list_kbs()
        for record in kb_records:
            kb_helper = KBHelper(
                kb_db=self.kb_db,
                kb=record,
                provider_manager=self.provider_manager,
                kb_root_dir=FILES_PATH,
                chunker=CHUNKER,
            )
            try:
                await kb_helper.initialize()
            except Exception as e:
                kb_helper.init_error = str(e)
                kb_helper.init_retry_count = 0
                kb_helper.last_init_retry_at = time.monotonic()
                logger.error(
                    f"知识库 {record.kb_name}({record.kb_id}) 初始化失败: {e}",
                    exc_info=True,
                )
            self._set_kb_instance(record.kb_id, kb_helper)

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
        index_type: str | None = None,
    ) -> KBHelper:
        """创建新的知识库实例"""
        if embedding_provider_id is None:
            raise ValueError("创建知识库时必须提供embedding_provider_id")
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
            index_type=index_type if index_type is not None else "flat",
        )
        kb_helper: KBHelper | None = None
        try:
            async with self._ensure_kb_instances_lock():
                async with self.kb_db.get_db() as session:
                    session.add(kb)
                    await session.flush()

                    kb_helper = KBHelper(
                        kb_db=self.kb_db,
                        kb=kb,
                        provider_manager=self.provider_manager,
                        kb_root_dir=FILES_PATH,
                        chunker=CHUNKER,
                    )
                    await kb_helper.initialize()
                    await session.commit()
                    self._set_kb_instance(kb.kb_id, kb_helper)
                    return kb_helper
        except Exception as e:
            if kb_helper is not None:
                try:
                    await kb_helper.delete_vec_db()
                except Exception as cleanup_err:
                    logger.warning(
                        f"创建知识库 {kb_name} 失败后清理文件目录失败: {cleanup_err}",
                    )
            if "kb_name" in str(e):
                raise ValueError(f"知识库名称 '{kb_name}' 已存在")
            raise

    async def get_kb(self, kb_id: str) -> KBHelper | None:
        """获取知识库实例"""
        async with self._ensure_kb_instances_lock():
            kb_helper = self._get_kb_unlocked(kb_id)
            if kb_helper is not None:
                await self._retry_helper_init_if_due(kb_helper)
            return kb_helper

    async def get_kb_by_name(self, kb_name: str) -> KBHelper | None:
        """通过名称获取知识库实例"""
        async with self._ensure_kb_instances_lock():
            self._ensure_kb_name_index()
            kb_id = self._kb_name_index.get(kb_name)
            if kb_id:
                return self.kb_insts.get(kb_id)
            return None

    async def delete_kb(self, kb_id: str) -> bool:
        """删除知识库实例"""
        async with self._ensure_kb_instances_lock():
            kb_helper = self._get_kb_unlocked(kb_id)
            if not kb_helper:
                return False

            async with self.kb_db.get_db() as session:
                await session.execute(
                    delete(KBMedia).where(col(KBMedia.kb_id) == kb_id)
                )
                await session.execute(
                    delete(KBDocument).where(col(KBDocument.kb_id) == kb_id)
                )
                await session.execute(
                    delete(KnowledgeBase).where(col(KnowledgeBase.kb_id) == kb_id)
                )
                await session.commit()

            try:
                await kb_helper.delete_vec_db()
            except Exception as e:
                logger.warning(
                    f"知识库 {kb_id} 数据库记录已删除，但文件目录清理失败: {e}"
                )

            self._remove_kb_instance(kb_id)
            return True

    async def list_kbs(self) -> list[KnowledgeBase]:
        """列出所有知识库实例"""
        async with self._ensure_kb_instances_lock():
            kbs = [kb_helper.kb for kb_helper in self.kb_insts.values()]
            return kbs

    async def update_kb(
        self,
        kb_id: str,
        kb_name: str | None = None,
        description: str | None = None,
        emoji: str | None = None,
        embedding_provider_id: str | None = None,
        rerank_provider_id: str | None | object = _UNSET,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        top_k_dense: int | None = None,
        top_k_sparse: int | None = None,
        top_m_final: int | None = None,
        index_type: str | None = None,
    ) -> KBHelper | None:
        """更新知识库实例"""
        async with self._ensure_kb_instances_lock():
            kb_helper = self._get_kb_unlocked(kb_id)
            if not kb_helper:
                return None

            kb = kb_helper.kb
            previous_state = {
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
                "index_type": kb.index_type,
            }
            previous_init_error = kb_helper.init_error

            if kb_name is not None:
                kb.kb_name = kb_name
            if description is not None:
                kb.description = description
            if emoji is not None:
                kb.emoji = emoji
            if embedding_provider_id is not None:
                kb.embedding_provider_id = embedding_provider_id
            if rerank_provider_id is not _UNSET:
                kb.rerank_provider_id = rerank_provider_id  # type: ignore[assignment]
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
            if index_type is not None:
                kb.index_type = index_type

            # Build a new helper first. Keep current vec_db alive until new init succeeds.
            new_helper = KBHelper(
                kb_db=self.kb_db,
                kb=kb,
                provider_manager=self.provider_manager,
                kb_root_dir=FILES_PATH,
                chunker=CHUNKER,
            )

            try:
                await new_helper.initialize()
            except Exception as e:
                # Roll back in-memory settings and keep current helper available.
                kb.kb_name = previous_state["kb_name"]
                kb.description = previous_state["description"]
                kb.emoji = previous_state["emoji"]
                kb.embedding_provider_id = previous_state["embedding_provider_id"]
                kb.rerank_provider_id = previous_state["rerank_provider_id"]
                kb.chunk_size = previous_state["chunk_size"]
                kb.chunk_overlap = previous_state["chunk_overlap"]
                kb.top_k_dense = previous_state["top_k_dense"]
                kb.top_k_sparse = previous_state["top_k_sparse"]
                kb.top_m_final = previous_state["top_m_final"]
                kb.index_type = previous_state["index_type"]
                kb_helper.init_error = previous_init_error
                logger.error(
                    f"知识库 {kb.kb_name}({kb.kb_id}) 重新初始化失败，继续使用旧实例: {e}",
                    exc_info=True,
                )
                return kb_helper

            async with self.kb_db.get_db() as session:
                session.add(kb)
                await session.commit()
                await session.refresh(kb)

            old_helper = kb_helper
            self._set_kb_instance(kb_id, new_helper)
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
                    unavailable_kbs.append((kb_name, kb_helper.init_error))
                    logger.warning(f"知识库 {kb_name} 不可用: {kb_helper.init_error}")
                    continue
                kb_ids.append(kb_helper.kb.kb_id)
                kb_id_helper_map[kb_helper.kb.kb_id] = kb_helper

        # all requested KBs are unavailable
        if not kb_ids and unavailable_kbs:
            errors = "; ".join(f"{n}: {e}" for n, e in unavailable_kbs)
            raise ValueError(f"所有请求的知识库均不可用: {errors}")

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
