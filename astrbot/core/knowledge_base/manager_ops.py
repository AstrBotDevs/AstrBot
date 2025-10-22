"""知识库管理器辅助操作

该模块提供文档、块和多媒体的管理操作。
"""

import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import aiofiles
from sqlalchemy import delete, func, select

from astrbot.core.knowledge_base.models import KBChunk, KBDocument, KBMedia

if TYPE_CHECKING:
    from astrbot.core.knowledge_base.manager import KBManager


class KBManagerOps:
    """知识库管理器辅助操作类

    职责:
    - 文档管理操作
    - 块管理操作
    - 多媒体管理操作
    """

    def __init__(self, manager: "KBManager"):
        self.manager = manager
        self.db = manager.db
        self.vec_db_factory = manager.vec_db_factory
        self.media_path = manager.media_path
        self.files_path = manager.files_path

    # ===== 文档操作 =====

    async def list_documents(
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

    async def get_document(self, doc_id: str) -> KBDocument | None:
        """获取文档详情"""
        async with self.db.get_db() as session:
            stmt = select(KBDocument).where(KBDocument.doc_id == doc_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def delete_document(self, doc_id: str) -> bool:
        """删除文档(级联删除块、多媒体、向量)

        采用三阶段删除策略:
        1. 删除向量数据库中的向量(允许部分失败)
        2. 删除SQL数据库中的记录(事务保证原子性)
        3. 删除文件系统中的文件(失败不影响数据一致性)
        """
        from astrbot.core import logger

        # 0. 获取文档信息
        doc = await self.get_document(doc_id)
        if not doc:
            return False

        # 收集所有需要删除的资源
        chunks = await self.list_chunks(doc_id)
        media_list = await self.list_media(doc_id)

        # 获取知识库的向量数据库
        embedding_provider = await self.manager._get_embedding_provider_for_kb(
            doc.kb_id
        )
        vec_db = await self.vec_db_factory.get_vec_db(doc.kb_id, embedding_provider)

        # ===== 第一阶段: 删除向量(可重试) =====
        vec_ids_to_delete = [chunk.vec_doc_id for chunk in chunks]
        deleted_vec_ids = []
        failed_vec_ids = []

        for vec_id in vec_ids_to_delete:
            try:
                await vec_db.delete(vec_id)
                deleted_vec_ids.append(vec_id)
            except Exception as e:
                logger.error(f"删除向量失败: {vec_id}, {e}")
                failed_vec_ids.append(vec_id)

        # 如果向量删除失败过多(超过50%),中止操作
        if len(failed_vec_ids) > len(vec_ids_to_delete) * 0.5:
            logger.error(
                f"向量删除失败过多 ({len(failed_vec_ids)}/{len(vec_ids_to_delete)}), 中止文档删除"
            )
            return False

        # 记录部分失败但继续执行
        if failed_vec_ids:
            logger.warning(
                f"部分向量删除失败 ({len(failed_vec_ids)}/{len(vec_ids_to_delete)}), 但继续执行删除操作"
            )

        # ===== 第二阶段: 删除数据库记录(事务) =====
        async with self.db.get_db() as session:
            async with session.begin():
                # 删除块记录
                await session.execute(delete(KBChunk).where(KBChunk.doc_id == doc_id))

                # 删除多媒体记录
                await session.execute(delete(KBMedia).where(KBMedia.doc_id == doc_id))

                # 删除文档记录
                await session.execute(
                    delete(KBDocument).where(KBDocument.doc_id == doc_id)
                )

                await session.commit()

        # ===== 第三阶段: 删除文件(失败不影响) =====
        # 删除多媒体文件
        for media in media_list:
            try:
                media_path = Path(media.file_path)
                if media_path.exists():
                    media_path.unlink()
            except Exception as e:
                logger.warning(f"删除多媒体文件失败: {media.file_path}, {e}")

        # 删除文档文件
        try:
            file_path = Path(doc.file_path)
            if file_path.exists():
                file_path.unlink()
        except Exception as e:
            logger.warning(f"删除文档文件失败: {doc.file_path}, {e}")

        # ===== 更新统计 =====
        await self.manager._update_kb_stats(doc.kb_id)

        return True

    # ===== 块操作 =====

    async def list_chunks(self, doc_id: str) -> list[KBChunk]:
        """列出文档的所有块"""
        async with self.db.get_db() as session:
            stmt = (
                select(KBChunk)
                .where(KBChunk.doc_id == doc_id)
                .order_by(KBChunk.chunk_index)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def delete_chunk(self, chunk_id: str) -> bool:
        """删除单个块

        流程:
        1. 查询块信息
        2. 删除向量
        3. 删除数据库记录
        4. 更新文档统计
        """
        from astrbot.core import logger

        # 1. 查询块信息
        async with self.db.get_db() as session:
            stmt = select(KBChunk).where(KBChunk.chunk_id == chunk_id)
            result = await session.execute(stmt)
            chunk = result.scalar_one_or_none()
            if not chunk:
                return False

            doc_id = chunk.doc_id
            kb_id = chunk.kb_id
            vec_doc_id = chunk.vec_doc_id

        # 2. 获取知识库的向量数据库并删除向量
        try:
            embedding_provider = await self.manager._get_embedding_provider_for_kb(
                kb_id
            )
            vec_db = await self.vec_db_factory.get_vec_db(kb_id, embedding_provider)
            await vec_db.delete(vec_doc_id)
        except Exception as e:
            logger.error(f"删除向量失败: {vec_doc_id}, {e}")
            return False

        # 3. 删除数据库记录
        async with self.db.get_db() as session:
            async with session.begin():
                await session.execute(
                    delete(KBChunk).where(KBChunk.chunk_id == chunk_id)
                )
                await session.commit()

        # 4. 更新文档统计
        await self._update_doc_stats(doc_id)

        return True

    # ===== 多媒体操作 =====

    async def list_media(self, doc_id: str) -> list[KBMedia]:
        """列出文档的所有多媒体资源"""
        async with self.db.get_db() as session:
            stmt = select(KBMedia).where(KBMedia.doc_id == doc_id)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def delete_media(self, media_id: str) -> bool:
        """删除多媒体资源

        流程:
        1. 查询媒体信息
        2. 删除数据库记录
        3. 删除文件(失败不影响)
        4. 更新文档统计
        """
        from astrbot.core import logger

        # 1. 查询媒体信息
        async with self.db.get_db() as session:
            stmt = select(KBMedia).where(KBMedia.media_id == media_id)
            result = await session.execute(stmt)
            media = result.scalar_one_or_none()
            if not media:
                return False

            doc_id = media.doc_id
            file_path_str = media.file_path

        # 2. 删除数据库记录
        async with self.db.get_db() as session:
            async with session.begin():
                await session.execute(
                    delete(KBMedia).where(KBMedia.media_id == media_id)
                )
                await session.commit()

        # 3. 删除文件(失败不影响)
        try:
            media_path = Path(file_path_str)
            if media_path.exists():
                media_path.unlink()
        except Exception as e:
            logger.warning(f"删除多媒体文件失败: {file_path_str}, {e}")

        # 4. 更新文档统计
        await self._update_doc_stats(doc_id)

        return True

    # ===== 内部辅助方法 =====

    async def _save_media(
        self,
        kb_id: str,
        doc_id: str,
        media_type: str,
        file_name: str,
        content: bytes,
        mime_type: str,
    ) -> KBMedia:
        """保存多媒体资源"""
        media_id = str(uuid.uuid4())
        ext = Path(file_name).suffix

        # 保存文件
        file_path = self.media_path / kb_id / doc_id / f"{media_id}{ext}"
        file_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)

        # 创建记录
        media = KBMedia(
            media_id=media_id,
            doc_id=doc_id,
            kb_id=kb_id,
            media_type=media_type,
            file_name=file_name,
            file_path=str(file_path),
            file_size=len(content),
            mime_type=mime_type,
        )

        return media

    async def _update_doc_stats(self, doc_id: str):
        """更新文档统计信息(事务中执行)"""
        async with self.db.get_db() as session:
            async with session.begin():
                # 统计块数
                chunk_count = (
                    await session.scalar(
                        select(func.count(KBChunk.id)).where(KBChunk.doc_id == doc_id)
                    )
                ) or 0

                # 统计多媒体数
                media_count = (
                    await session.scalar(
                        select(func.count(KBMedia.id)).where(KBMedia.doc_id == doc_id)
                    )
                ) or 0

                # 更新文档
                doc = await session.scalar(
                    select(KBDocument).where(KBDocument.doc_id == doc_id)
                )
                if doc:
                    doc.chunk_count = chunk_count
                    doc.media_count = media_count

                await session.commit()
