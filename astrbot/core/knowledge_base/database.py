"""知识库数据库操作类

该模块封装知识库、文档、块、多媒体和会话配置相关的数据库查询操作。

注意:
- 该模块操作的是独立的知识库数据库 (data/knowledge_base/kb.db)
- 会话配置也存储在此数据库中，会话ID来源于主数据库
"""

import json
from typing import Optional

from sqlalchemy import func, select

from astrbot.core.knowledge_base.kb_sqlite import KBSQLiteDatabase
from astrbot.core.knowledge_base.models import (
    KBChunk,
    KBDocument,
    KBMedia,
    KBSessionConfig,
    KnowledgeBase,
)


class KBDatabase:
    """知识库数据库操作类

    职责:
    - 封装知识库、文档、块、多媒体和会话配置的数据库查询操作
    - 统一异常处理

    注意:
    - 该类操作独立的知识库数据库 (kb.db)
    - 会话配置存储会话ID与知识库的绑定关系，会话ID来源于主数据库
    """

    def __init__(self, kb_db: KBSQLiteDatabase):
        """初始化知识库数据库操作类

        Args:
            kb_db: 知识库独立数据库实例,而非主数据库
        """
        self.db = kb_db

    # ===== 知识库查询 =====

    async def get_kb_by_id(self, kb_id: str) -> Optional[KnowledgeBase]:
        """根据 ID 获取知识库"""
        async with self.db.get_db() as session:
            stmt = select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_kb_by_name(self, kb_name: str) -> Optional[KnowledgeBase]:
        """根据名称获取知识库"""
        async with self.db.get_db() as session:
            stmt = select(KnowledgeBase).where(KnowledgeBase.kb_name == kb_name)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_kbs(self, offset: int = 0, limit: int = 100) -> list[KnowledgeBase]:
        """列出所有知识库"""
        async with self.db.get_db() as session:
            stmt = (
                select(KnowledgeBase)
                .offset(offset)
                .limit(limit)
                .order_by(KnowledgeBase.created_at.desc())
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def count_kbs(self) -> int:
        """统计知识库数量"""
        async with self.db.get_db() as session:
            stmt = select(func.count(KnowledgeBase.id))
            result = await session.execute(stmt)
            return result.scalar() or 0

    # ===== 文档查询 =====

    async def get_document_by_id(self, doc_id: str) -> Optional[KBDocument]:
        """根据 ID 获取文档"""
        async with self.db.get_db() as session:
            stmt = select(KBDocument).where(KBDocument.doc_id == doc_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_documents_by_kb(
        self, kb_id: str, offset: int = 0, limit: int = 100
    ) -> list[KBDocument]:
        """列出知识库的所有文档"""
        async with self.db.get_db() as session:
            stmt = (
                select(KBDocument)
                .where(KBDocument.kb_id == kb_id)
                .offset(offset)
                .limit(limit)
                .order_by(KBDocument.created_at.desc())
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def count_documents_by_kb(self, kb_id: str) -> int:
        """统计知识库的文档数量"""
        async with self.db.get_db() as session:
            stmt = select(func.count(KBDocument.id)).where(KBDocument.kb_id == kb_id)
            result = await session.execute(stmt)
            return result.scalar() or 0

    # ===== 块查询 =====

    async def get_chunk_by_id(self, chunk_id: str) -> Optional[KBChunk]:
        """根据 ID 获取块"""
        async with self.db.get_db() as session:
            stmt = select(KBChunk).where(KBChunk.chunk_id == chunk_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_chunks_by_kb_ids(self, kb_ids: list[str]) -> list[KBChunk]:
        """根据知识库 ID 列表获取所有块"""
        async with self.db.get_db() as session:
            stmt = select(KBChunk).where(KBChunk.kb_id.in_(kb_ids))
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_chunk_by_vec_doc_id(self, vec_doc_id: str) -> Optional[KBChunk]:
        """根据向量文档 ID 获取块"""
        async with self.db.get_db() as session:
            stmt = select(KBChunk).where(KBChunk.vec_doc_id == vec_doc_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_chunk_with_metadata(self, chunk_id: str) -> Optional[dict]:
        """获取块及其关联的文档和知识库元数据"""
        async with self.db.get_db() as session:
            stmt = (
                select(KBChunk, KBDocument, KnowledgeBase)
                .join(KBDocument, KBChunk.doc_id == KBDocument.doc_id)
                .join(KnowledgeBase, KBChunk.kb_id == KnowledgeBase.kb_id)
                .where(KBChunk.chunk_id == chunk_id)
            )
            result = await session.execute(stmt)
            row = result.first()

            if not row:
                return None

            chunk, doc, kb = row
            return {
                "chunk": chunk,
                "document": doc,
                "knowledge_base": kb,
            }

    async def list_chunks_by_doc(
        self, doc_id: str, offset: int = 0, limit: int = 100
    ) -> list[KBChunk]:
        """列出文档的所有块"""
        async with self.db.get_db() as session:
            stmt = (
                select(KBChunk)
                .where(KBChunk.doc_id == doc_id)
                .offset(offset)
                .limit(limit)
                .order_by(KBChunk.chunk_index)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    # ===== 多媒体查询 =====

    async def list_media_by_doc(self, doc_id: str) -> list[KBMedia]:
        """列出文档的所有多媒体资源"""
        async with self.db.get_db() as session:
            stmt = select(KBMedia).where(KBMedia.doc_id == doc_id)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_media_by_id(self, media_id: str) -> Optional[KBMedia]:
        """根据 ID 获取多媒体资源"""
        async with self.db.get_db() as session:
            stmt = select(KBMedia).where(KBMedia.media_id == media_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    # ===== 会话配置查询 =====

    async def get_session_kb_ids(self, session_id: str) -> list[str]:
        """获取会话关联的知识库 ID 列表

        查找顺序:
        1. 会话级别配置 (优先)
        2. 平台级别配置
        3. 返回空列表

        Args:
            session_id: 会话ID（来自主数据库）

        Returns:
            知识库ID列表
        """
        async with self.db.get_db() as session:
            # 1. 查找会话级别配置
            stmt = select(KBSessionConfig).where(
                KBSessionConfig.scope == "session",
                KBSessionConfig.scope_id == session_id,
            )
            result = await session.execute(stmt)
            config = result.scalar_one_or_none()

            if config:
                return json.loads(config.kb_ids)

            # 2. 提取平台 ID (格式: platform:xxx:session_id)
            parts = session_id.split(":")
            if len(parts) >= 2:
                platform_id = parts[0]

                # 查找平台级别配置
                stmt = select(KBSessionConfig).where(
                    KBSessionConfig.scope == "platform",
                    KBSessionConfig.scope_id == platform_id,
                )
                result = await session.execute(stmt)
                config = result.scalar_one_or_none()

                if config:
                    return json.loads(config.kb_ids)

            # 3. 无配置
            return []

    async def set_session_kb_ids(
        self,
        scope: str,
        scope_id: str,
        kb_ids: list[str],
        top_k: Optional[int] = None,
        enable_rerank: Optional[bool] = None,
    ) -> KBSessionConfig:
        """设置会话知识库配置

        Args:
            scope: 配置范围 (session/platform)
            scope_id: 范围标识 (会话 ID 或平台 ID，来自主数据库)
            kb_ids: 知识库 ID 列表
            top_k: 返回结果数量 (可选)
            enable_rerank: 是否启用 Rerank (可选)

        Returns:
            配置对象
        """
        async with self.db.get_db() as session:
            # 查找现有配置
            stmt = select(KBSessionConfig).where(
                KBSessionConfig.scope == scope,
                KBSessionConfig.scope_id == scope_id,
            )
            result = await session.execute(stmt)
            config = result.scalar_one_or_none()

            if config:
                # 更新现有配置
                config.kb_ids = json.dumps(kb_ids)
                if top_k is not None:
                    config.top_k = top_k
                if enable_rerank is not None:
                    config.enable_rerank = enable_rerank
            else:
                # 创建新配置
                config = KBSessionConfig(
                    scope=scope,
                    scope_id=scope_id,
                    kb_ids=json.dumps(kb_ids),
                    top_k=top_k,
                    enable_rerank=enable_rerank,
                )
                session.add(config)

            await session.commit()
            await session.refresh(config)
            return config

    async def delete_session_kb_config(self, scope: str, scope_id: str) -> bool:
        """删除会话知识库配置

        Args:
            scope: 配置范围 (session/platform)
            scope_id: 范围标识 (会话 ID 或平台 ID)

        Returns:
            是否删除成功
        """
        async with self.db.get_db() as session:
            stmt = select(KBSessionConfig).where(
                KBSessionConfig.scope == scope,
                KBSessionConfig.scope_id == scope_id,
            )
            result = await session.execute(stmt)
            config = result.scalar_one_or_none()

            if not config:
                return False

            await session.delete(config)
            await session.commit()
            return True

    async def delete_session_kb_config_by_session_id(self, session_id: str) -> bool:
        """根据会话ID删除会话配置（用于主数据库会话删除时的级联清理）

        Args:
            session_id: 会话ID（来自主数据库）

        Returns:
            是否删除成功
        """
        return await self.delete_session_kb_config("session", session_id)

    async def list_all_session_configs(
        self, offset: int = 0, limit: int = 100, scope: Optional[str] = None
    ) -> list[KBSessionConfig]:
        """列出所有会话配置

        Args:
            offset: 偏移量
            limit: 限制数量
            scope: 可选的范围过滤 (session/platform)

        Returns:
            会话配置列表
        """
        async with self.db.get_db() as session:
            stmt = select(KBSessionConfig)

            if scope:
                stmt = stmt.where(KBSessionConfig.scope == scope)

            stmt = (
                stmt.offset(offset)
                .limit(limit)
                .order_by(KBSessionConfig.created_at.desc())
            )

            result = await session.execute(stmt)
            return list(result.scalars().all())
