import asyncio
import traceback
import uuid
from pathlib import Path

from astrbot.core import logger
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.utils.astrbot_path import get_astrbot_knowledge_base_path

# from .chunking.fixed_size import FixedSizeChunker
from .chunking.recursive import RecursiveCharacterChunker
from .index_rebuilder import IndexRebuilder
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
        self.rebuild_tasks: dict[str, dict] = {}
        self.kb_rebuild_task_map: dict[str, str] = {}
        self._running_rebuild_tasks: dict[str, asyncio.Task] = {}
        self.index_rebuilder = IndexRebuilder()

    def _validate_index_mode(self, index_mode: str) -> str:
        normalized = (index_mode or "").strip().lower()
        allowed_modes = {"flat", "structure"}
        if normalized not in allowed_modes:
            raise ValueError(
                f"default_index_mode 必须为 {sorted(allowed_modes)} 之一，实际为: {index_mode}",
            )
        return normalized

    async def initialize(self) -> None:
        """初始化知识库模块"""
        try:
            logger.info("正在初始化知识库模块...")

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
            logger.error(f"知识库模块初始化失败: {e}")
            logger.error(traceback.format_exc())

    async def _init_kb_database(self) -> None:
        self.kb_db = KBSQLiteDatabase(DB_PATH.as_posix())
        await self.kb_db.initialize()
        await self.kb_db.migrate_to_v1()
        await self.kb_db.migrate_to_v2(FILES_PATH)
        await self.kb_db.migrate_to_v3()
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
            await kb_helper.initialize()
            self.kb_insts[record.kb_id] = kb_helper
            if (
                record.embedding_provider_id
                and record.active_index_provider_id
                and record.embedding_provider_id != record.active_index_provider_id
            ):
                await self.start_rebuild_index(
                    record.kb_id, record.embedding_provider_id
                )

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
        default_index_mode: str | None = None,
    ) -> KBHelper:
        """创建新的知识库实例"""
        if embedding_provider_id is None:
            raise ValueError("创建知识库时必须提供embedding_provider_id")
        if default_index_mode is not None:
            default_index_mode = self._validate_index_mode(default_index_mode)
        kb = KnowledgeBase(
            kb_name=kb_name,
            description=description,
            emoji=emoji or "📚",
            embedding_provider_id=embedding_provider_id,
            active_index_provider_id=embedding_provider_id,
            rerank_provider_id=rerank_provider_id,
            chunk_size=chunk_size if chunk_size is not None else 512,
            chunk_overlap=chunk_overlap if chunk_overlap is not None else 50,
            top_k_dense=top_k_dense if top_k_dense is not None else 50,
            top_k_sparse=top_k_sparse if top_k_sparse is not None else 50,
            top_m_final=top_m_final if top_m_final is not None else 5,
            default_index_mode=default_index_mode or "flat",
        )
        try:
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
                self.kb_insts[kb.kb_id] = kb_helper
                return kb_helper
        except Exception as e:
            if "kb_name" in str(e):
                raise ValueError(f"知识库名称 '{kb_name}' 已存在")
            raise

    async def get_kb(self, kb_id: str) -> KBHelper | None:
        """获取知识库实例"""
        if kb_id in self.kb_insts:
            return self.kb_insts[kb_id]

    async def get_kb_by_name(self, kb_name: str) -> KBHelper | None:
        """通过名称获取知识库实例"""
        for kb_helper in self.kb_insts.values():
            if kb_helper.kb.kb_name == kb_name:
                return kb_helper
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
        default_index_mode: str | None = None,
    ) -> KBHelper | None:
        """更新知识库实例"""
        kb_helper = await self.get_kb(kb_id)
        if not kb_helper:
            return None

        kb = kb_helper.kb
        if kb_name is not None:
            kb.kb_name = kb_name
        if description is not None:
            kb.description = description
        if emoji is not None:
            kb.emoji = emoji
        if embedding_provider_id is not None:
            kb.embedding_provider_id = embedding_provider_id
        kb.rerank_provider_id = rerank_provider_id  # 允许设置为 None
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
        if default_index_mode is not None:
            kb.default_index_mode = self._validate_index_mode(default_index_mode)
        async with self.kb_db.get_db() as session:
            session.add(kb)
            await session.commit()
            await session.refresh(kb)

        if (
            embedding_provider_id
            and kb.active_index_provider_id
            and embedding_provider_id != kb.active_index_provider_id
        ):
            await self.start_rebuild_index(kb.kb_id, embedding_provider_id)

        return kb_helper

    async def has_structured_docs_by_names(self, kb_names: list[str]) -> bool:
        for kb_name in kb_names:
            kb_helper = await self.get_kb_by_name(kb_name)
            if not kb_helper:
                continue
            if await self.kb_db.has_structured_docs(kb_helper.kb.kb_id):
                return True
        return False

    async def read_document_section(
        self,
        kb_names: list[str],
        doc_id: str,
        section_path: str,
    ) -> str | None:
        for kb_name in kb_names:
            kb_helper = await self.get_kb_by_name(kb_name)
            if not kb_helper:
                continue
            section = await self.kb_db.get_doc_section(
                kb_id=kb_helper.kb.kb_id,
                doc_id=doc_id,
                section_path=section_path,
            )
            if section:
                return section.section_body
        return None

    async def start_rebuild_index(
        self,
        kb_id: str,
        new_provider_id: str,
        batch_size: int = 32,
    ) -> str:
        kb_helper = await self.get_kb(kb_id)
        if not kb_helper:
            raise ValueError("知识库不存在")

        existing_task_id = self.kb_rebuild_task_map.get(kb_id)
        if existing_task_id:
            existing = self.rebuild_tasks.get(existing_task_id)
            if existing and existing.get("status") == "processing":
                return existing_task_id

        task_id = str(uuid.uuid4())
        kb_helper.last_rebuild_task_id = task_id
        self.kb_rebuild_task_map[kb_id] = task_id
        self.rebuild_tasks[task_id] = {
            "task_id": task_id,
            "kb_id": kb_id,
            "provider_id": new_provider_id,
            "status": "processing",
            "stage": "prepare",
            "current": 0,
            "total": 0,
            "error": None,
        }

        async def _progress(stage: str, current: int, total: int) -> None:
            task = self.rebuild_tasks.get(task_id)
            if not task:
                return
            task["stage"] = stage
            task["current"] = current
            task["total"] = total

        async def _run():
            try:
                await self.index_rebuilder.sync(
                    kb_helper=kb_helper,
                    new_provider_id=new_provider_id,
                    batch_size=batch_size,
                    progress_callback=_progress,
                )
                task = self.rebuild_tasks.get(task_id)
                if task:
                    task["status"] = "completed"
                    task["stage"] = "finished"
            except Exception as e:
                logger.error(
                    "Index rebuild failed for kb %s provider %s: %s",
                    kb_id,
                    new_provider_id,
                    e,
                )
                logger.error(traceback.format_exc())
                task = self.rebuild_tasks.get(task_id)
                if task:
                    task["status"] = "failed"
                    task["error"] = str(e)
            finally:
                self._running_rebuild_tasks.pop(task_id, None)

        task = asyncio.create_task(_run())
        self._running_rebuild_tasks[task_id] = task
        return task_id

    def get_rebuild_progress(
        self,
        kb_id: str | None = None,
        task_id: str | None = None,
    ) -> dict | None:
        target_task_id = task_id
        if not target_task_id and kb_id:
            target_task_id = self.kb_rebuild_task_map.get(kb_id)
        if not target_task_id:
            return None
        return self.rebuild_tasks.get(target_task_id)

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
        for kb_name in kb_names:
            if kb_helper := await self.get_kb_by_name(kb_name):
                kb_ids.append(kb_helper.kb.kb_id)
                kb_id_helper_map[kb_helper.kb.kb_id] = kb_helper

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
                "metadata": r.metadata,
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
            index_mode = result.metadata.get("index_mode", "flat")
            section_path = result.metadata.get("section_path", "")
            if index_mode == "structure" and section_path:
                lines.append(f"内容: [📖 {section_path}]")
                lines.append(
                    f"提示: 如需正文，请调用 astr_kb_read_section(doc_id='{result.doc_id}', section_path='{section_path}')",
                )
            else:
                lines.append(f"内容: {result.content}")
            lines.append(f"相关度: {result.score:.2f}")
            lines.append("")

        return "\n".join(lines)

    async def terminate(self) -> None:
        """终止所有知识库实例,关闭数据库连接"""
        for task_id, task in list(self._running_rebuild_tasks.items()):
            if not task.done():
                task.cancel()
            self._running_rebuild_tasks.pop(task_id, None)

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
