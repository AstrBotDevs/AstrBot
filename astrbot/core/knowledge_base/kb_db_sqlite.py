from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import col, desc

from astrbot.core import logger
from astrbot.core.db.vec_db.faiss_impl import FaissVecDB
from astrbot.core.knowledge_base.index_path import build_index_path
from astrbot.core.knowledge_base.models import (
    BaseKBModel,
    DocSection,
    KBDocument,
    KBMedia,
    KnowledgeBase,
)
from astrbot.core.utils.astrbot_path import get_astrbot_knowledge_base_path


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

                await session.commit()

    async def migrate_to_v2(self, kb_root_dir: str) -> None:
        """执行知识库数据库 v2 迁移

        变更:
        - knowledge_bases.active_index_provider_id
        - 旧 index.faiss 迁移为 index.{provider}.faiss
        """
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                try:
                    await session.execute(
                        text(
                            "ALTER TABLE knowledge_bases "
                            "ADD COLUMN active_index_provider_id VARCHAR(100)",
                        ),
                    )
                except (ProgrammingError, OperationalError) as e:
                    err_msg = str(e).lower()
                    if "duplicate column name" in err_msg:
                        pass
                    else:
                        logger.error(
                            "Failed to alter knowledge_bases for active_index_provider_id: %s",
                            e,
                        )
                        raise

                result = await session.execute(select(KnowledgeBase))
                all_kbs = list(result.scalars().all())
                kb_root = Path(kb_root_dir)
                for kb in all_kbs:
                    if not kb.active_index_provider_id and kb.embedding_provider_id:
                        kb.active_index_provider_id = kb.embedding_provider_id

                    rename_success = True
                    if kb.embedding_provider_id:
                        old_index_path = kb_root / kb.kb_id / "index.faiss"
                        new_index_path = build_index_path(
                            kb_root / kb.kb_id,
                            kb.embedding_provider_id,
                        )
                        if old_index_path.exists() and not new_index_path.exists():
                            try:
                                old_index_path.rename(new_index_path)
                            except OSError as e:
                                logger.warning(
                                    "Rename index failed for kb %s: %s -> %s, error: %s",
                                    kb.kb_id,
                                    old_index_path,
                                    new_index_path,
                                    e,
                                )
                                rename_success = False
                            except Exception as e:
                                logger.warning(
                                    "Unexpected error when renaming index for kb %s: %s -> %s, error: %s",
                                    kb.kb_id,
                                    old_index_path,
                                    new_index_path,
                                    e,
                                )
                                rename_success = False
                    # Only persist KB changes if rename succeeded (or no rename was needed)
                    if rename_success:
                        session.add(kb)

                await session.commit()

    async def migrate_to_v3(self) -> None:
        """执行知识库数据库 v3 迁移

        变更:
        - knowledge_bases.default_index_mode
        - kb_documents.index_mode
        """
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                try:
                    await session.execute(
                        text(
                            "ALTER TABLE knowledge_bases "
                            "ADD COLUMN default_index_mode VARCHAR(20) DEFAULT 'flat'",
                        ),
                    )
                except Exception:
                    pass
                try:
                    await session.execute(
                        text(
                            "ALTER TABLE kb_documents "
                            "ADD COLUMN index_mode VARCHAR(20) DEFAULT 'flat'",
                        ),
                    )
                except Exception:
                    pass
                try:
                    await session.execute(
                        text(
                            "UPDATE knowledge_bases SET default_index_mode = 'flat' "
                            "WHERE default_index_mode IS NULL OR default_index_mode = ''",
                        ),
                    )
                except Exception:
                    pass
                try:
                    await session.execute(
                        text(
                            "UPDATE kb_documents SET index_mode = 'flat' "
                            "WHERE index_mode IS NULL OR index_mode = ''",
                        ),
                    )
                except Exception:
                    pass
                await session.commit()

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

    async def list_kbs(self, offset: int = 0, limit: int = 100) -> list[KnowledgeBase]:
        """列出所有知识库"""
        async with self.get_db() as session:
            stmt = (
                select(KnowledgeBase)
                .offset(offset)
                .limit(limit)
                .order_by(desc(KnowledgeBase.created_at))
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def count_kbs(self) -> int:
        """统计知识库数量"""
        async with self.get_db() as session:
            stmt = select(func.count(col(KnowledgeBase.id)))
            result = await session.execute(stmt)
            return result.scalar() or 0

    # ===== 文档查询 =====

    async def get_document_by_id(self, doc_id: str) -> KBDocument | None:
        """根据 ID 获取文档"""
        async with self.get_db() as session:
            stmt = select(KBDocument).where(col(KBDocument.doc_id) == doc_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_documents_by_kb(
        self,
        kb_id: str,
        offset: int = 0,
        limit: int = 100,
    ) -> list[KBDocument]:
        """列出知识库的所有文档"""
        async with self.get_db() as session:
            stmt = (
                select(KBDocument)
                .where(col(KBDocument.kb_id) == kb_id)
                .offset(offset)
                .limit(limit)
                .order_by(desc(KBDocument.created_at))
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def count_documents_by_kb(self, kb_id: str) -> int:
        """统计知识库的文档数量"""
        async with self.get_db() as session:
            stmt = select(func.count(col(KBDocument.id))).where(
                col(KBDocument.kb_id) == kb_id,
            )
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

    async def delete_document_by_id(self, doc_id: str, vec_db: FaissVecDB) -> None:
        """删除单个文档及其相关数据"""
        # 在知识库表中删除
        async with self.get_db() as session, session.begin():
            # 删除文档记录
            delete_stmt = delete(KBDocument).where(col(KBDocument.doc_id) == doc_id)
            await session.execute(delete_stmt)
            await session.commit()

        # 在 vec db 中删除相关向量
        await vec_db.delete_documents(metadata_filters={"kb_doc_id": doc_id})

    # ===== 多媒体查询 =====

    async def list_media_by_doc(self, doc_id: str) -> list[KBMedia]:
        """列出文档的所有多媒体资源"""
        async with self.get_db() as session:
            stmt = select(KBMedia).where(col(KBMedia.doc_id) == doc_id)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def has_structured_docs(self, kb_id: str) -> bool:
        """Check if kb has any structured indexed documents."""
        async with self.get_db() as session:
            stmt = (
                select(func.count(col(KBDocument.id)))
                .where(col(KBDocument.kb_id) == kb_id)
                .where(col(KBDocument.index_mode) == "structure")
            )
            result = await session.execute(stmt)
            return (result.scalar() or 0) > 0

    async def upsert_doc_section(self, section: DocSection) -> None:
        async with self.get_db() as session:
            async with session.begin():
                await session.merge(section)

    async def get_doc_section(
        self,
        kb_id: str,
        doc_id: str,
        section_path: str,
    ) -> DocSection | None:
        async with self.get_db() as session:
            stmt = (
                select(DocSection)
                .where(col(DocSection.kb_id) == kb_id)
                .where(col(DocSection.doc_id) == doc_id)
                .where(col(DocSection.section_path) == section_path)
            )
            result = await session.execute(stmt)
            section = result.scalar_one_or_none()
            if section:
                return section
            stmt = (
                select(DocSection)
                .where(col(DocSection.kb_id) == kb_id)
                .where(col(DocSection.doc_id) == doc_id)
                .where(DocSection.section_path.contains(section_path, autoescape=True))
                .order_by(DocSection.created_at.asc(), DocSection.id.asc())
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_media_by_id(self, media_id: str) -> KBMedia | None:
        """根据 ID 获取多媒体资源"""
        async with self.get_db() as session:
            stmt = select(KBMedia).where(col(KBMedia.media_id) == media_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def update_kb_stats(self, kb_id: str, vec_db: FaissVecDB) -> None:
        """更新知识库统计信息"""
        chunk_cnt = await vec_db.count_documents()

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
