"""知识库管理器

该模块提供知识库的CRUD操作和文档上传处理流程。
"""

import uuid
from pathlib import Path
from typing import Optional

import aiofiles
from sqlalchemy import func, select, update

from .kb_sqlite import KBSQLiteDatabase
from astrbot.core.knowledge_base.chunking.base import BaseChunker
from astrbot.core.knowledge_base.models import KBChunk, KBDocument, KnowledgeBase
from astrbot.core.knowledge_base.parsers.base import BaseParser
from .vec_db_factory import VecDBFactory

class KBManager:
    """知识库管理器

    职责:
    - 知识库的 CRUD 操作
    - 文档上传与解析
    - 文档块生成与存储
    - 多媒体资源管理
    """

    def __init__(
        self,
        db: KBSQLiteDatabase,
        vec_db_factory: VecDBFactory,
        storage_path: str,
        parsers: dict[str, BaseParser],
        chunker: BaseChunker,
        provider_manager=None,
    ):
        self.db = db
        self.vec_db_factory = vec_db_factory
        self.storage_path = Path(storage_path)
        self.media_path = self.storage_path / "media"
        self.files_path = self.storage_path / "files"
        self.parsers = parsers
        self.chunker = chunker
        self.provider_manager = provider_manager

        # 确保目录存在
        self.media_path.mkdir(parents=True, exist_ok=True)
        self.files_path.mkdir(parents=True, exist_ok=True)

    async def _get_embedding_provider_for_kb(self, kb_id: str):
        """根据知识库配置获取 Embedding Provider

        Args:
            kb_id: 知识库 ID

        Returns:
            EmbeddingProvider: Embedding Provider 实例

        Raises:
            ValueError: 如果找不到合适的 embedding provider
        """
        from astrbot.core.knowledge_base.database import KBDatabase

        # 获取知识库配置
        kb_database = KBDatabase(self.db)
        kb = await kb_database.get_kb_by_id(kb_id)
        if not kb:
            raise ValueError(f"知识库不存在: {kb_id}")

        embedding_provider_id = kb.embedding_provider_id

        # 如果没有 provider_manager,使用默认的第一个
        if not self.provider_manager:
            raise ValueError("Provider Manager 未初始化")

        embedding_providers = self.provider_manager.embedding_provider_insts
        if not embedding_providers:
            raise ValueError("系统中没有可用的 Embedding Provider")

        # 如果指定了 provider ID,则查找该 provider
        if embedding_provider_id:
            for provider in embedding_providers:
                if provider.meta().id == embedding_provider_id:
                    return provider
            raise ValueError(
                f"未找到配置的 Embedding Provider: {embedding_provider_id}"
            )

        # 使用第一个可用的 provider
        return embedding_providers[0]

    # ===== 知识库操作 =====

    async def create_kb(
        self,
        kb_name: str,
        description: Optional[str] = None,
        emoji: Optional[str] = None,
        embedding_provider_id: Optional[str] = None,
        rerank_provider_id: Optional[str] = None,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        top_k_dense: Optional[int] = None,
        top_k_sparse: Optional[int] = None,
        top_m_final: Optional[int] = None,
        enable_rerank: Optional[bool] = None,
    ) -> KnowledgeBase:
        """创建知识库

        Args:
            enable_rerank: 是否启用重排序。
                - 如果明确传入 True/False，则使用该值
                - 如果为 None，则根据是否有可用的 rerank provider 自动决定
        """
        # 智能决定 enable_rerank 的默认值
        if enable_rerank is None:
            # 检查是否有可用的 rerank provider
            has_rerank_provider = (
                self.provider_manager
                and hasattr(self.provider_manager, "rerank_provider_insts")
                and len(self.provider_manager.rerank_provider_insts) > 0
            )
            enable_rerank = has_rerank_provider

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
            enable_rerank=enable_rerank,
        )
        async with self.db.get_db() as session:
            session.add(kb)
            await session.commit()
            await session.refresh(kb)
        return kb

    async def get_kb(self, kb_id: str) -> Optional[KnowledgeBase]:
        """获取知识库"""
        async with self.db.get_db() as session:
            stmt = select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id)
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

    async def update_kb(
        self,
        kb_id: str,
        kb_name: Optional[str] = None,
        description: Optional[str] = None,
        emoji: Optional[str] = None,
        embedding_provider_id: Optional[str] = None,
        rerank_provider_id: Optional[str] = None,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        top_k_dense: Optional[int] = None,
        top_k_sparse: Optional[int] = None,
        top_m_final: Optional[int] = None,
        enable_rerank: Optional[bool] = None,
    ) -> Optional[KnowledgeBase]:
        """更新知识库"""
        async with self.db.get_db() as session:
            stmt = select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id)
            result = await session.execute(stmt)
            kb = result.scalar_one_or_none()
            if not kb:
                return None

            if kb_name is not None:
                kb.kb_name = kb_name
            if description is not None:
                kb.description = description
            if emoji is not None:
                kb.emoji = emoji
            if embedding_provider_id is not None:
                kb.embedding_provider_id = embedding_provider_id
            if rerank_provider_id is not None:
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
            if enable_rerank is not None:
                kb.enable_rerank = enable_rerank

            await session.commit()
            await session.refresh(kb)
            return kb

    async def delete_kb(self, kb_id: str) -> bool:
        """删除知识库(级联删除所有文档和资源)"""
        # 1. 获取所有文档
        from astrbot.core.knowledge_base.manager_ops import KBManagerOps

        ops = KBManagerOps(self)
        docs = await ops.list_documents(kb_id)

        # 2. 删除所有文档(包括文件和向量)
        for doc in docs:
            await ops.delete_document(doc.doc_id)

        # 3. 删除向量数据库
        await self.vec_db_factory.delete_vec_db(kb_id)

        # 4. 删除知识库记录
        async with self.db.get_db() as session:
            stmt = select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id)
            result = await session.execute(stmt)
            kb = result.scalar_one_or_none()
            if not kb:
                return False

            await session.delete(kb)
            await session.commit()

        return True

    # ===== 文档上传 =====

    async def upload_document(
        self,
        kb_id: str,
        file_name: str,
        file_content: bytes,
        file_type: str,
    ) -> KBDocument:
        """上传并处理文档（带原子性保证和失败清理）

        流程:
        1. 保存原始文件
        2. 解析文档内容
        3. 提取多媒体资源
        4. 分块处理
        5. 生成向量并存储
        6. 保存元数据（事务）
        7. 更新统计
        """
        doc_id = str(uuid.uuid4())
        file_path = None
        media_paths = []
        vec_doc_ids = []

        try:
            # 1. 保存原始文件
            file_path = self.files_path / kb_id / f"{doc_id}.{file_type}"
            file_path.parent.mkdir(parents=True, exist_ok=True)

            async with aiofiles.open(file_path, "wb") as f:
                await f.write(file_content)

            # 2. 解析文档
            parser = self.parsers.get(file_type)
            if not parser:
                raise ValueError(f"不支持的文件类型: {file_type}")

            parse_result = await parser.parse(file_content, file_name)
            text_content = parse_result.text
            media_items = parse_result.media

            # 3. 保存多媒体资源
            from astrbot.core.knowledge_base.manager_ops import KBManagerOps

            ops = KBManagerOps(self)
            saved_media = []
            for media_item in media_items:
                media = await ops._save_media(
                    kb_id=kb_id,
                    doc_id=doc_id,
                    media_type=media_item.media_type,
                    file_name=media_item.file_name,
                    content=media_item.content,
                    mime_type=media_item.mime_type,
                )
                saved_media.append(media)
                media_paths.append(Path(media.file_path))

            # 4. 文档分块
            chunks_text = await self.chunker.chunk(text_content)

            # 5. 获取 Embedding Provider 和向量数据库
            embedding_provider = await self._get_embedding_provider_for_kb(kb_id)
            vec_db = await self.vec_db_factory.get_vec_db(kb_id, embedding_provider)

            # 6. 生成向量并存储
            saved_chunks = []
            for idx, chunk_text in enumerate(chunks_text):
                # 存储到向量数据库
                vec_doc_id = await vec_db.insert(
                    content=chunk_text,
                    metadata={
                        "kb_id": kb_id,
                        "doc_id": doc_id,
                        "chunk_index": idx,
                    },
                )
                vec_doc_ids.append(str(vec_doc_id))

                # 保存块元数据
                chunk = KBChunk(
                    doc_id=doc_id,
                    kb_id=kb_id,
                    chunk_index=idx,
                    content=chunk_text,
                    char_count=len(chunk_text),
                    vec_doc_id=str(vec_doc_id),
                )
                saved_chunks.append(chunk)

            # 7. 保存文档元数据（事务）
            doc = KBDocument(
                doc_id=doc_id,
                kb_id=kb_id,
                doc_name=file_name,
                file_type=file_type,
                file_size=len(file_content),
                file_path=str(file_path),
                chunk_count=len(saved_chunks),
                media_count=len(saved_media),
            )

            async with self.db.get_db() as session:
                async with session.begin():
                    session.add(doc)
                    for chunk in saved_chunks:
                        session.add(chunk)
                    for media in saved_media:
                        session.add(media)
                    await session.commit()

                await session.refresh(doc)

            # 8. 更新知识库统计
            await self._update_kb_stats(kb_id)

            return doc

        except Exception as e:
            # 失败清理：删除已创建的资源
            from astrbot.core import logger

            logger.error(f"文档上传失败，开始清理资源: {e}")

            # 获取知识库的向量数据库
            try:
                embedding_provider = await self._get_embedding_provider_for_kb(kb_id)
                vec_db = await self.vec_db_factory.get_vec_db(kb_id, embedding_provider)

                # 清理向量数据库
                for vec_id in vec_doc_ids:
                    try:
                        await vec_db.delete(vec_id)
                    except Exception as ve:
                        logger.warning(f"清理向量失败 {vec_id}: {ve}")
            except Exception as vfe:
                logger.error(f"获取向量数据库失败: {vfe}")

            # 清理多媒体文件
            for media_path in media_paths:
                try:
                    if media_path.exists():
                        media_path.unlink()
                except Exception as me:
                    logger.warning(f"清理多媒体文件失败 {media_path}: {me}")

            # 清理文档文件
            if file_path and file_path.exists():
                try:
                    file_path.unlink()
                except Exception as fe:
                    logger.warning(f"清理文档文件失败 {file_path}: {fe}")

            # 重新抛出原始异常
            raise

    # ===== 统计更新 =====

    async def _update_kb_stats(self, kb_id: str):
        """更新知识库统计信息（事务中执行）"""
        async with self.db.get_db() as session:
            async with session.begin():
                # 统计文档数（在事务中查询）
                doc_count = (
                    await session.scalar(
                        select(func.count(KBDocument.id)).where(
                            KBDocument.kb_id == kb_id
                        )
                    )
                    or 0
                )

                # 统计块数（在事务中查询）
                chunk_count = (
                    await session.scalar(
                        select(func.count(KBChunk.id)).where(KBChunk.kb_id == kb_id)
                    )
                    or 0
                )

                # 更新知识库（在同一事务中）
                await session.execute(
                    update(KnowledgeBase)
                    .where(KnowledgeBase.kb_id == kb_id)
                    .values(doc_count=doc_count, chunk_count=chunk_count)
                )

                await session.commit()
