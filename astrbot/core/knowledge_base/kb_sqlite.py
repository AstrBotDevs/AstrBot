"""
知识库独立 SQLite 数据库

该模块提供知识库专用的独立 SQLite 数据库,与主数据库 (astrbot.db) 完全隔离。
职责:
- 管理知识库相关表 (knowledge_bases, kb_documents, kb_chunks, kb_media)
- 提供数据库连接和会话管理
- 执行数据库迁移和初始化
"""

from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from astrbot.core import logger


class KBSQLiteDatabase:
    """知识库独立 SQLite 数据库

    与主数据库 (astrbot.db) 完全隔离的独立数据库,专门用于存储知识库数据。

    特点:
    - 数据隔离: 知识库数据不会影响主数据库格式
    - 独立备份: 可以单独备份和恢复知识库数据
    - 性能隔离: 大量知识库查询不会影响主业务性能
    """

    def __init__(self, db_path: str = "data/knowledge_base/kb.db") -> None:
        """初始化知识库数据库

        Args:
            db_path: 数据库文件路径,默认为 data/knowledge_base/kb.db
        """
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
        from astrbot.core.knowledge_base.models import (
            KBChunk,
            KBDocument,
            KBMedia,
            KBSessionConfig,
            KnowledgeBase,
        )
        from sqlmodel import SQLModel

        async with self.engine.begin() as conn:
            # 创建所有知识库相关表
            await conn.run_sync(SQLModel.metadata.create_all)

            # 配置 SQLite 性能优化参数
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA synchronous=NORMAL"))
            await conn.execute(text("PRAGMA cache_size=20000"))
            await conn.execute(text("PRAGMA temp_store=MEMORY"))
            await conn.execute(text("PRAGMA mmap_size=134217728"))
            await conn.execute(text("PRAGMA optimize"))
            await conn.commit()

        self.inited = True
        logger.info(f"知识库数据库已初始化: {self.db_path}")

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
                        "ON knowledge_bases(kb_id)"
                    )
                )
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_kb_name "
                        "ON knowledge_bases(kb_name)"
                    )
                )
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_kb_created_at "
                        "ON knowledge_bases(created_at)"
                    )
                )

                # 创建文档表索引
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_doc_doc_id "
                        "ON kb_documents(doc_id)"
                    )
                )
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_doc_kb_id "
                        "ON kb_documents(kb_id)"
                    )
                )
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_doc_name "
                        "ON kb_documents(doc_name)"
                    )
                )
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_doc_type "
                        "ON kb_documents(file_type)"
                    )
                )
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_doc_created_at "
                        "ON kb_documents(created_at)"
                    )
                )

                # 创建块表索引
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_chunk_chunk_id "
                        "ON kb_chunks(chunk_id)"
                    )
                )
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_chunk_doc_id "
                        "ON kb_chunks(doc_id)"
                    )
                )
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_chunk_kb_id "
                        "ON kb_chunks(kb_id)"
                    )
                )
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_chunk_vec_doc_id "
                        "ON kb_chunks(vec_doc_id)"
                    )
                )

                # 创建多媒体表索引
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_media_media_id "
                        "ON kb_media(media_id)"
                    )
                )
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_media_doc_id "
                        "ON kb_media(doc_id)"
                    )
                )
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_media_kb_id "
                        "ON kb_media(kb_id)"
                    )
                )
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_media_type "
                        "ON kb_media(media_type)"
                    )
                )

                # 创建会话配置表索引
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_session_config_scope_id "
                        "ON kb_session_config(scope_id)"
                    )
                )
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_session_config_scope "
                        "ON kb_session_config(scope)"
                    )
                )

                await session.commit()

        logger.info("知识库数据库迁移 v1 完成")

    async def close(self) -> None:
        """关闭数据库连接"""
        await self.engine.dispose()
        logger.info(f"知识库数据库已关闭: {self.db_path}")
