import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import col, desc

from astrbot.core import logger
from astrbot.core.knowledge_base.models import (
    BaseKBModel,
    KBDocument,
    KBIngestionTask,
    KBMedia,
    KnowledgeBase,
)
from astrbot.core.utils.astrbot_path import get_astrbot_knowledge_base_path

if TYPE_CHECKING:
    from astrbot.core.db.vec_db.faiss_impl import FaissVecDB

_UNSET = object()


class KBSQLiteDatabase:
    def __init__(self, db_path: str | None = None) -> None:
        """初始化知识库数据库

        Args:
            db_path: 数据库文件路径, 默认位于 AstrBot 数据目录下的 knowledge_base/kb.db

        """
        if db_path is None:
            db_path = str(Path(get_astrbot_knowledge_base_path()) / "kb.db")
        self.db_path = db_path
        self.DATABASE_URL = f"sqlite+aiosqlite:///{db_path}"
        self.inited = False

        # 确保目录存在
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # 创建异步引擎
        self.engine = create_async_engine(
            self.DATABASE_URL,
            echo=False,
            pool_pre_ping=True,
            pool_recycle=3600,
        )

        # 创建会话工厂
        self.async_session = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @asynccontextmanager
    async def get_db(self):
        """获取数据库会话

        用法:
            async with kb_db.get_db() as session:
                # 执行数据库操作
                result = await session.execute(stmt)
        """
        async with self.async_session() as session:
            yield session

    async def initialize(self) -> None:
        """初始化数据库,创建表并配置 SQLite 参数"""
        async with self.engine.begin() as conn:
            # 创建所有知识库相关表
            await conn.run_sync(BaseKBModel.metadata.create_all)

            # 配置 SQLite 性能优化参数
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA synchronous=NORMAL"))
            await conn.execute(text("PRAGMA cache_size=20000"))
            await conn.execute(text("PRAGMA temp_store=MEMORY"))
            await conn.execute(text("PRAGMA mmap_size=134217728"))
            await conn.execute(text("PRAGMA optimize"))
            await conn.commit()

        self.inited = True

    async def migrate_to_v1(self) -> None:
        """执行知识库数据库 v1 迁移

        创建所有必要的索引以优化查询性能
        """
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await self._ensure_column(
                    session,
                    table_name="knowledge_bases",
                    column_name="index_type",
                    column_sql="index_type TEXT DEFAULT 'flat'",
                )
                await self._ensure_document_governance_columns(session)
                await self._ensure_ingestion_task_table(session)

                # 创建知识库表索引
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_kb_kb_id "
                        "ON knowledge_bases(kb_id)",
                    ),
                )
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_kb_name "
                        "ON knowledge_bases(kb_name)",
                    ),
                )
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_kb_created_at "
                        "ON knowledge_bases(created_at)",
                    ),
                )

                # 创建文档表索引
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_doc_doc_id "
                        "ON kb_documents(doc_id)",
                    ),
                )
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_doc_kb_id "
                        "ON kb_documents(kb_id)",
                    ),
                )
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_doc_name "
                        "ON kb_documents(doc_name)",
                    ),
                )
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_doc_type "
                        "ON kb_documents(file_type)",
                    ),
                )
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_doc_created_at "
                        "ON kb_documents(created_at)",
                    ),
                )
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_doc_content_hash "
                        "ON kb_documents(content_hash)",
                    ),
                )
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_doc_status "
                        "ON kb_documents(status)",
                    ),
                )
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_doc_parent_doc_id "
                        "ON kb_documents(parent_doc_id)",
                    ),
                )

                # 创建多媒体表索引
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_media_media_id "
                        "ON kb_media(media_id)",
                    ),
                )
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_media_doc_id "
                        "ON kb_media(doc_id)",
                    ),
                )
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_media_kb_id ON kb_media(kb_id)",
                    ),
                )
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_media_type "
                        "ON kb_media(media_type)",
                    ),
                )
                await self._ensure_ingestion_task_indexes(session)

                await session.commit()

    async def _ensure_column(
        self,
        session: AsyncSession,
        *,
        table_name: str,
        column_name: str,
        column_sql: str,
    ) -> None:
        """Add a column when upgrading an existing SQLite table."""
        result = await session.execute(text(f"PRAGMA table_xinfo({table_name})"))
        columns = {row[1] for row in result.fetchall()}
        if column_name in columns:
            return
        logger.info(
            f"知识库数据库迁移: 为表 {table_name} 添加列 {column_name}",
        )
        await session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}"))

    async def _ensure_document_governance_columns(
        self,
        session: AsyncSession,
    ) -> None:
        columns = {
            "source_type": "source_type TEXT NOT NULL DEFAULT 'file'",
            "source_uri": "source_uri TEXT",
            "content_hash": "content_hash VARCHAR(64)",
            "parser_name": "parser_name VARCHAR(100)",
            "parser_version": "parser_version VARCHAR(50)",
            "chunker_name": "chunker_name VARCHAR(100)",
            "chunker_version": "chunker_version VARCHAR(50)",
            "status": "status TEXT NOT NULL DEFAULT 'ready'",
            "error_stage": "error_stage VARCHAR(50)",
            "error_message": "error_message TEXT",
            "version": "version INTEGER NOT NULL DEFAULT 1",
            "parent_doc_id": "parent_doc_id VARCHAR(36)",
            "indexed_at": "indexed_at DATETIME",
        }
        for column_name, column_sql in columns.items():
            await self._ensure_column(
                session,
                table_name="kb_documents",
                column_name=column_name,
                column_sql=column_sql,
            )

    async def _ensure_ingestion_task_table(self, session: AsyncSession) -> None:
        await session.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS kb_ingestion_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id VARCHAR(36) NOT NULL UNIQUE,
                    kb_id VARCHAR(36) NOT NULL,
                    task_type VARCHAR(30) NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    progress_stage VARCHAR(50),
                    progress_current INTEGER NOT NULL DEFAULT 0,
                    progress_total INTEGER NOT NULL DEFAULT 100,
                    progress TEXT,
                    result TEXT,
                    error TEXT,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """,
            ),
        )

    async def _ensure_ingestion_task_indexes(self, session: AsyncSession) -> None:
        indexes = {
            "idx_task_task_id": "task_id",
            "idx_task_kb_id": "kb_id",
            "idx_task_type": "task_type",
            "idx_task_status": "status",
            "idx_task_created_at": "created_at",
        }
        for index_name, column_name in indexes.items():
            await session.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS {index_name} "
                    f"ON kb_ingestion_tasks({column_name})",
                ),
            )

    @staticmethod
    def _encode_json(value) -> str | None:
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False, default=str)

    @staticmethod
    def _decode_json(value: str | None):
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    @classmethod
    def _task_to_dict(cls, task: KBIngestionTask) -> dict:
        return {
            "task_id": task.task_id,
            "kb_id": task.kb_id,
            "task_type": task.task_type,
            "status": task.status,
            "progress_stage": task.progress_stage,
            "progress_current": task.progress_current,
            "progress_total": task.progress_total,
            "progress": cls._decode_json(task.progress),
            "result": cls._decode_json(task.result),
            "error": cls._decode_json(task.error),
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        }

    async def close(self) -> None:
        """关闭数据库连接"""
        await self.engine.dispose()
        logger.info(f"知识库数据库已关闭: {self.db_path}")

    async def get_kb_by_id(self, kb_id: str) -> KnowledgeBase | None:
        """根据 ID 获取知识库"""
        async with self.get_db() as session:
            stmt = select(KnowledgeBase).where(col(KnowledgeBase.kb_id) == kb_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_kb_by_name(self, kb_name: str) -> KnowledgeBase | None:
        """根据名称获取知识库"""
        async with self.get_db() as session:
            stmt = select(KnowledgeBase).where(col(KnowledgeBase.kb_name) == kb_name)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_kbs(
        self,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[KnowledgeBase]:
        """列出所有知识库"""
        async with self.get_db() as session:
            stmt = (
                select(KnowledgeBase)
                .offset(offset)
                .order_by(
                    desc(KnowledgeBase.created_at),
                )
            )
            if limit is not None:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def count_kbs(self) -> int:
        """统计知识库数量"""
        async with self.get_db() as session:
            stmt = select(func.count(col(KnowledgeBase.id)))
            result = await session.execute(stmt)
            return result.scalar() or 0

    # ===== 任务查询 =====

    async def create_ingestion_task(
        self,
        *,
        task_id: str,
        kb_id: str,
        task_type: str,
        status: str = "pending",
        progress_stage: str | None = None,
        progress_current: int = 0,
        progress_total: int = 100,
        progress: dict | None = None,
    ) -> dict:
        task = KBIngestionTask(
            task_id=task_id,
            kb_id=kb_id,
            task_type=task_type,
            status=status,
            progress_stage=progress_stage,
            progress_current=progress_current,
            progress_total=progress_total,
            progress=self._encode_json(progress),
        )
        async with self.get_db() as session:
            session.add(task)
            await session.commit()
            await session.refresh(task)
            return self._task_to_dict(task)

    async def update_ingestion_task(
        self,
        task_id: str,
        *,
        status: str | object = _UNSET,
        progress_stage: str | None | object = _UNSET,
        progress_current: int | object = _UNSET,
        progress_total: int | object = _UNSET,
        progress: dict | None | object = _UNSET,
        result: dict | None | object = _UNSET,
        error: str | None | object = _UNSET,
    ) -> dict | None:
        async with self.get_db() as session:
            stmt = select(KBIngestionTask).where(
                col(KBIngestionTask.task_id) == task_id,
            )
            query_result = await session.execute(stmt)
            task = query_result.scalar_one_or_none()
            if task is None:
                return None

            if status is not _UNSET:
                task.status = status  # type: ignore[assignment]
            if progress_stage is not _UNSET:
                task.progress_stage = progress_stage  # type: ignore[assignment]
            if progress_current is not _UNSET:
                task.progress_current = progress_current  # type: ignore[assignment]
            if progress_total is not _UNSET:
                task.progress_total = progress_total  # type: ignore[assignment]
            if progress is not _UNSET:
                task.progress = self._encode_json(progress)
            if result is not _UNSET:
                task.result = self._encode_json(result)
            if error is not _UNSET:
                task.error = self._encode_json(error)
            task.updated_at = datetime.now(timezone.utc)

            session.add(task)
            await session.commit()
            await session.refresh(task)
            return self._task_to_dict(task)

    async def get_ingestion_task(self, task_id: str) -> dict | None:
        async with self.get_db() as session:
            stmt = select(KBIngestionTask).where(
                col(KBIngestionTask.task_id) == task_id,
            )
            result = await session.execute(stmt)
            task = result.scalar_one_or_none()
            return self._task_to_dict(task) if task is not None else None

    @staticmethod
    def _build_ingestion_task_conditions(
        *,
        kb_id: str | None = None,
        status: str | None = None,
        task_type: str | None = None,
    ) -> list:
        conditions = []
        if kb_id is not None:
            conditions.append(col(KBIngestionTask.kb_id) == kb_id)
        if status is not None:
            conditions.append(col(KBIngestionTask.status) == status)
        if task_type is not None:
            conditions.append(col(KBIngestionTask.task_type) == task_type)
        return conditions

    async def list_ingestion_tasks(
        self,
        *,
        kb_id: str | None = None,
        status: str | None = None,
        task_type: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[dict]:
        conditions = self._build_ingestion_task_conditions(
            kb_id=kb_id,
            status=status,
            task_type=task_type,
        )

        async with self.get_db() as session:
            stmt = (
                select(KBIngestionTask)
                .where(*conditions)
                .offset(offset)
                .limit(limit)
                .order_by(desc(KBIngestionTask.created_at))
            )
            result = await session.execute(stmt)
            return [self._task_to_dict(task) for task in result.scalars().all()]

    async def count_ingestion_tasks(
        self,
        *,
        kb_id: str | None = None,
        status: str | None = None,
        task_type: str | None = None,
    ) -> int:
        conditions = self._build_ingestion_task_conditions(
            kb_id=kb_id,
            status=status,
            task_type=task_type,
        )
        async with self.get_db() as session:
            stmt = select(func.count(col(KBIngestionTask.id))).where(*conditions)
            result = await session.execute(stmt)
            return result.scalar() or 0

    # ===== 文档查询 =====

    async def get_document_by_id(self, doc_id: str) -> KBDocument | None:
        """根据 ID 获取文档"""
        async with self.get_db() as session:
            stmt = select(KBDocument).where(col(KBDocument.doc_id) == doc_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_document_by_content_hash(
        self,
        *,
        kb_id: str,
        content_hash: str,
    ) -> KBDocument | None:
        """Return an existing active document with the same source content hash."""
        async with self.get_db() as session:
            stmt = (
                select(KBDocument)
                .where(
                    col(KBDocument.kb_id) == kb_id,
                    col(KBDocument.content_hash) == content_hash,
                    col(KBDocument.status) != "failed",
                )
                .order_by(desc(KBDocument.created_at))
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    @staticmethod
    def _build_document_filters(
        *,
        kb_id: str,
        search: str | None = None,
        status: str | None = None,
        source_type: str | None = None,
    ) -> list:
        conditions = [col(KBDocument.kb_id) == kb_id]
        if search:
            pattern = f"%{search}%"
            conditions.append(
                or_(
                    col(KBDocument.doc_name).ilike(pattern),
                    col(KBDocument.file_type).ilike(pattern),
                ),
            )
        if status:
            conditions.append(col(KBDocument.status) == status)
        if source_type:
            conditions.append(col(KBDocument.source_type) == source_type)
        return conditions

    async def list_documents_by_kb(
        self,
        kb_id: str,
        offset: int = 0,
        limit: int = 100,
        search: str | None = None,
        status: str | None = None,
        source_type: str | None = None,
    ) -> list[KBDocument]:
        """列出知识库的所有文档"""
        async with self.get_db() as session:
            conditions = self._build_document_filters(
                kb_id=kb_id,
                search=search,
                status=status,
                source_type=source_type,
            )
            stmt = (
                select(KBDocument)
                .where(*conditions)
                .offset(offset)
                .limit(limit)
                .order_by(desc(KBDocument.created_at))
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def count_documents_by_kb(
        self,
        kb_id: str,
        search: str | None = None,
        status: str | None = None,
        source_type: str | None = None,
    ) -> int:
        """统计知识库的文档数量"""
        async with self.get_db() as session:
            conditions = self._build_document_filters(
                kb_id=kb_id,
                search=search,
                status=status,
                source_type=source_type,
            )
            stmt = select(func.count(col(KBDocument.id))).where(*conditions)
            result = await session.execute(stmt)
            return result.scalar() or 0

    async def get_document_with_metadata(self, doc_id: str) -> dict | None:
        async with self.get_db() as session:
            stmt = (
                select(KBDocument, KnowledgeBase)
                .join(KnowledgeBase, col(KBDocument.kb_id) == col(KnowledgeBase.kb_id))
                .where(col(KBDocument.doc_id) == doc_id)
            )
            result = await session.execute(stmt)
            row = result.first()

            if not row:
                return None

            return {
                "document": row[0],
                "knowledge_base": row[1],
            }

    async def get_documents_with_metadata_batch(
        self, doc_ids: set[str]
    ) -> dict[str, dict]:
        """批量获取文档及其所属知识库元数据

        Args:
            doc_ids: 文档 ID 集合

        Returns:
            dict: doc_id -> {"document": KBDocument, "knowledge_base": KnowledgeBase}

        """
        if not doc_ids:
            return {}

        metadata_map: dict[str, dict] = {}
        # SQLite 参数上限为 999，分片查询避免超限
        chunk_size = 900
        doc_id_list = list(doc_ids)

        async with self.get_db() as session:
            for i in range(0, len(doc_id_list), chunk_size):
                chunk = doc_id_list[i : i + chunk_size]
                stmt = (
                    select(KBDocument, KnowledgeBase)
                    .join(
                        KnowledgeBase,
                        col(KBDocument.kb_id) == col(KnowledgeBase.kb_id),
                    )
                    .where(col(KBDocument.doc_id).in_(chunk))
                )
                result = await session.execute(stmt)
                for row in result.all():
                    metadata_map[row[0].doc_id] = {
                        "document": row[0],
                        "knowledge_base": row[1],
                    }

        return metadata_map

    async def delete_document_by_id(
        self,
        doc_id: str,
        vec_db: "FaissVecDB",
        kb_id: str | None = None,
    ) -> bool:
        """删除单个文档及其相关数据"""
        doc = await self.get_document_by_id(doc_id)
        if not doc or (kb_id is not None and doc.kb_id != kb_id):
            return False

        metadata_filters = {"kb_doc_id": doc_id}
        if kb_id is not None:
            metadata_filters["kb_id"] = kb_id

        # 先删向量库；如果失败，保留 metadata 以便重试/修复。
        await vec_db.delete_documents(metadata_filters=metadata_filters)

        async with self.get_db() as session, session.begin():
            delete_stmt = delete(KBDocument).where(col(KBDocument.doc_id) == doc_id)
            if kb_id is not None:
                delete_stmt = delete_stmt.where(col(KBDocument.kb_id) == kb_id)
            await session.execute(delete_stmt)
            await session.execute(delete(KBMedia).where(col(KBMedia.doc_id) == doc_id))

        return True

    async def delete_documents_by_ids(
        self,
        doc_ids: list[str],
        vec_db: "FaissVecDB",
        kb_id: str | None = None,
    ) -> dict[str, bool]:
        """批量删除文档及其向量数据。

        先删除向量数据，再删除 metadata；单个文档的 vec_db 删除失败
        不影响其他文档（best-effort），失败项保留 metadata 以便重试。
        """
        if not doc_ids:
            return {}

        requested_doc_ids = list(dict.fromkeys(doc_ids))
        results = dict.fromkeys(requested_doc_ids, False)

        candidates = requested_doc_ids
        if kb_id is not None:
            async with self.get_db() as session:
                stmt = select(KBDocument.doc_id).where(
                    col(KBDocument.doc_id).in_(requested_doc_ids),
                    col(KBDocument.kb_id) == kb_id,
                )
                result = await session.execute(stmt)
                candidates = [row[0] for row in result.fetchall()]

        if not candidates:
            return results

        # 限制并发删除数量，避免 FAISS 写锁竞争
        semaphore = asyncio.Semaphore(10)

        async def _delete_one(doc_id: str) -> tuple[str, bool]:
            async with semaphore:
                metadata_filters = {"kb_doc_id": doc_id}
                if kb_id is not None:
                    metadata_filters["kb_id"] = kb_id
                try:
                    await vec_db.delete_documents(metadata_filters=metadata_filters)
                    return doc_id, True
                except Exception as e:
                    logger.error(
                        f"删除文档 {doc_id} 的向量数据失败: {e}",
                    )
                    return doc_id, False

        vec_results = await asyncio.gather(
            *[_delete_one(doc_id) for doc_id in candidates],
        )
        successful_doc_ids = []
        for doc_id, success in vec_results:
            results[doc_id] = success
            if success:
                successful_doc_ids.append(doc_id)

        if successful_doc_ids:
            async with self.get_db() as session, session.begin():
                delete_stmt = delete(KBDocument).where(
                    col(KBDocument.doc_id).in_(successful_doc_ids),
                )
                if kb_id is not None:
                    delete_stmt = delete_stmt.where(col(KBDocument.kb_id) == kb_id)
                await session.execute(delete_stmt)
                await session.execute(
                    delete(KBMedia).where(col(KBMedia.doc_id).in_(successful_doc_ids)),
                )

        return results

    # ===== 多媒体查询 =====

    async def list_media_by_doc(self, doc_id: str) -> list[KBMedia]:
        """列出文档的所有多媒体资源"""
        async with self.get_db() as session:
            stmt = select(KBMedia).where(col(KBMedia.doc_id) == doc_id)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_media_by_id(self, media_id: str) -> KBMedia | None:
        """根据 ID 获取多媒体资源"""
        async with self.get_db() as session:
            stmt = select(KBMedia).where(col(KBMedia.media_id) == media_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def update_kb_stats(self, kb_id: str, vec_db: "FaissVecDB") -> None:
        """更新知识库统计信息"""
        chunk_cnt = await vec_db.count_documents(metadata_filter={"kb_id": kb_id})

        async with self.get_db() as session, session.begin():
            update_stmt = (
                update(KnowledgeBase)
                .where(col(KnowledgeBase.kb_id) == kb_id)
                .values(
                    doc_count=select(func.count(col(KBDocument.id)))
                    .where(col(KBDocument.kb_id) == kb_id)
                    .scalar_subquery(),
                    chunk_count=chunk_cnt,
                )
            )

            await session.execute(update_stmt)
            await session.commit()

    async def get_kb_stats(self, kb_id: str) -> dict | None:
        """Return persisted document statistics for a knowledge base."""
        async with self.get_db() as session:
            kb_result = await session.execute(
                select(KnowledgeBase).where(col(KnowledgeBase.kb_id) == kb_id),
            )
            kb = kb_result.scalar_one_or_none()
            if kb is None:
                return None

            status_result = await session.execute(
                select(KBDocument.status, func.count(col(KBDocument.id)))
                .where(col(KBDocument.kb_id) == kb_id)
                .group_by(KBDocument.status),
            )
            status_counts = {
                status or "unknown": count for status, count in status_result.all()
            }

            chunk_result = await session.execute(
                select(func.coalesce(func.sum(col(KBDocument.chunk_count)), 0)).where(
                    col(KBDocument.kb_id) == kb_id,
                ),
            )
            document_chunk_count = int(chunk_result.scalar() or 0)

            media_result = await session.execute(
                select(func.count(col(KBMedia.id))).where(col(KBMedia.kb_id) == kb_id),
            )
            media_count = int(media_result.scalar() or 0)
            source_file_count_result = await session.execute(
                select(func.count(col(KBDocument.id))).where(
                    col(KBDocument.kb_id) == kb_id,
                    col(KBDocument.source_type) == "file",
                    col(KBDocument.file_path) != "",
                ),
            )
            source_file_count = int(source_file_count_result.scalar() or 0)
            document_storage_result = await session.execute(
                select(func.coalesce(func.sum(col(KBDocument.file_size)), 0)).where(
                    col(KBDocument.kb_id) == kb_id,
                    col(KBDocument.file_path) != "",
                ),
            )
            document_storage_bytes = int(document_storage_result.scalar() or 0)
            media_storage_result = await session.execute(
                select(func.coalesce(func.sum(col(KBMedia.file_size)), 0)).where(
                    col(KBMedia.kb_id) == kb_id,
                ),
            )
            media_storage_bytes = int(media_storage_result.scalar() or 0)

            document_count = sum(status_counts.values())
            ready_document_count = status_counts.get("ready", 0)
            failed_document_count = status_counts.get("failed", 0)
            pending_document_count = status_counts.get("pending", 0)
            processing_document_count = sum(
                status_counts.get(status, 0)
                for status in ("parsing", "chunking", "embedding")
            )

            return {
                "kb_id": kb.kb_id,
                "kb_name": kb.kb_name,
                "doc_count": kb.doc_count,
                "chunk_count": kb.chunk_count,
                "document_count": document_count,
                "ready_document_count": ready_document_count,
                "failed_document_count": failed_document_count,
                "pending_document_count": pending_document_count,
                "processing_document_count": processing_document_count,
                "indexed_chunk_count": kb.chunk_count,
                "document_chunk_count": document_chunk_count,
                "media_count": media_count,
                "source_file_count": source_file_count,
                "storage_bytes": document_storage_bytes + media_storage_bytes,
                "status_counts": status_counts,
                "created_at": kb.created_at.isoformat(),
                "updated_at": kb.updated_at.isoformat(),
            }
