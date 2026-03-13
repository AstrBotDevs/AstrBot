from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlalchemy.exc import OperationalError

import os


class DBManager:
    """数据库管理器，负责异步连接和会话管理"""

    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

        self.db_url = f"sqlite+aiosqlite:///{db_path}"

        # 创建异步引擎
        self.engine = create_async_engine(
            self.db_url,
            echo=False,
            pool_pre_ping=True,
            pool_recycle=3600,
            # pool_size=5,
            # max_overflow=5,
        )

        # 创建会话工厂
        self.async_session = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self.async_session_factory = self.async_session

    async def init_db(self):
        """初始化数据库，创建所有定义的表"""

        async with self.engine.begin() as conn:
            try:
                await conn.run_sync(SQLModel.metadata.create_all)
            except OperationalError as e:
                if "already exists" not in str(e):
                    raise

        async with self.engine.begin() as conn:
            try:
                await conn.execute(text(
                    "ALTER TABLE match ADD COLUMN question_limit INTEGER DEFAULT 0"
                ))
            except OperationalError:
                pass
            try:
                await conn.execute(text(
                    "ALTER TABLE match ADD COLUMN time_limit INTEGER DEFAULT 0"
                ))
            except OperationalError:
                pass
            try:
                await conn.execute(text(
                    "ALTER TABLE match ADD COLUMN started_at TIMESTAMP"
                ))
            except OperationalError:
                pass
            try:
                await conn.execute(text(
                    "ALTER TABLE match_participant ADD COLUMN wrong_count INTEGER DEFAULT 0"
                ))
            except OperationalError:
                pass
            try:
                await conn.execute(text(
                    "ALTER TABLE match_participant ADD COLUMN score REAL DEFAULT 0.0"
                ))
            except OperationalError:
                pass
            try:
                await conn.execute(text(
                    "ALTER TABLE match_honor ADD COLUMN wrong_count INTEGER DEFAULT 0"
                ))
            except OperationalError:
                pass
            try:
                await conn.execute(text(
                    "ALTER TABLE match_honor ADD COLUMN score REAL DEFAULT 0.0"
                ))
            except OperationalError:
                pass

        # SQLite 优化 PRAGMA
        async with self.engine.connect() as conn:
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA synchronous=NORMAL"))
            await conn.execute(text("PRAGMA cache_size=-20000"))
            await conn.execute(text("PRAGMA temp_store=MEMORY"))
            await conn.execute(text("PRAGMA mmap_size=134217728"))
            await conn.execute(text("PRAGMA optimize"))
            await conn.commit()

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """异步获取数据库会话的上下文管理器"""
        session = self.async_session_factory()
        try:
            async with session.begin():
                yield session
        finally:
            await session.close()
