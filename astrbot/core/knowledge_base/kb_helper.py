import uuid
import aiofiles
from pathlib import Path
from .models import KnowledgeBase, KBDocument, KBChunk, KBMedia
from .kb_db_sqlite import KBSQLiteDatabase
from astrbot.core.db.vec_db.base import BaseVecDB
from astrbot.core.db.vec_db.faiss_impl.vec_db import FaissVecDB
from astrbot.core.provider.provider import EmbeddingProvider, RerankProvider
from astrbot.core.provider.manager import ProviderManager
from .parsers.base import BaseParser
from .chunking.base import BaseChunker
from astrbot.core import logger


class KBHelper:
    vec_db: BaseVecDB

    def __init__(
        self,
        kb_db: KBSQLiteDatabase,
        kb: KnowledgeBase,
        provider_manager: ProviderManager,
        kb_root_dir: str,
        chunker: BaseChunker,
        parsers: dict[str, BaseParser],
    ):
        self.kb_db = kb_db
        self.kb = kb
        self.prov_mgr = provider_manager
        self.kb_root_dir = kb_root_dir
        self.parsers = parsers
        self.chunker = chunker

        self.kb_dir = Path(self.kb_root_dir) / self.kb.kb_id
        self.kb_medias_dir = Path(self.kb_dir) / "medias" / self.kb.kb_id
        self.kb_files_dir = Path(self.kb_dir) / "files" / self.kb.kb_id

        self.kb_medias_dir.mkdir(parents=True, exist_ok=True)
        self.kb_files_dir.mkdir(parents=True, exist_ok=True)

    async def initialize(self):
        await self._ensure_vec_db()

    async def get_ep(self) -> EmbeddingProvider:
        if not self.kb.embedding_provider_id:
            raise ValueError(f"知识库 {self.kb.kb_name} 未配置 Embedding Provider")
        ep: EmbeddingProvider = await self.prov_mgr.get_provider_by_id(
            self.kb.embedding_provider_id
        )  # type: ignore
        if not ep:
            raise ValueError(
                f"无法找到 ID 为 {self.kb.embedding_provider_id} 的 Embedding Provider"
            )
        return ep

    async def get_rp(self) -> RerankProvider | None:
        if not self.kb.rerank_provider_id:
            return None
        rp: RerankProvider = await self.prov_mgr.get_provider_by_id(
            self.kb.rerank_provider_id
        )  # type: ignore
        if not rp:
            raise ValueError(
                f"无法找到 ID 为 {self.kb.rerank_provider_id} 的 Rerank Provider"
            )
        return rp

    async def _ensure_vec_db(self) -> FaissVecDB:
        if not self.kb.embedding_provider_id:
            raise ValueError(f"知识库 {self.kb.kb_name} 未配置 Embedding Provider")

        ep = await self.get_ep()
        rp = await self.get_rp()

        vec_db = FaissVecDB(
            doc_store_path=str(self.kb_dir / "doc.db"),
            index_store_path=str(self.kb_dir / "index.faiss"),
            embedding_provider=ep,
            rerank_provider=rp,
        )
        await vec_db.initialize()
        self.vec_db = vec_db
        return vec_db

    async def delete_vec_db(self):
        await self.terminate()
        if self.kb_dir.exists():
            for item in self.kb_dir.iterdir():
                if item.is_file():
                    item.unlink()
            self.kb_dir.rmdir()

    async def terminate(self):
        if self.vec_db:
            await self.vec_db.close()

    async def upload_document(
        self,
        file_name: str,
        file_content: bytes,
        file_type: str,
    ) -> KBDocument:
        """上传并处理文档（带原子性保证和失败清理）

        流程:
        1. 保存原始文件
        2. 解析文档内容
        3. 提取多媒体资源 (TODO)
        4. 分块处理
        5. 生成向量并存储
        6. 保存元数据（事务）
        7. 更新统计
        """
        await self._ensure_vec_db()
        doc_id = str(uuid.uuid4())
        media_paths: list[Path] = []
        vec_doc_ids = []

        file_path = self.kb_files_dir / f"{doc_id}.{file_type}"
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_content)

        try:
            parser = self.parsers.get(file_type)
            if not parser:
                raise ValueError(f"不支持的文件类型: {file_type}")
            parse_result = await parser.parse(file_content, file_name)
            text_content = parse_result.text
            media_items = parse_result.media

            # 保存媒体文件
            saved_media = []
            for media_item in media_items:
                media = await self._save_media(
                    doc_id=doc_id,
                    media_type=media_item.media_type,
                    file_name=media_item.file_name,
                    content=media_item.content,
                    mime_type=media_item.mime_type,
                )
                saved_media.append(media)
                media_paths.append(Path(media.file_path))

            # 分块并生成向量
            saved_chunks = []
            chunks_text = await self.chunker.chunk(text_content)
            for idx, chunk_text in enumerate(chunks_text):
                vec_doc_id = await self.vec_db.insert(
                    content=chunk_text,
                    metadata={
                        "kb_id": self.kb.kb_id,
                        "doc_id": doc_id,
                        "chunk_index": idx,
                    },
                )
                vec_doc_ids.append(str(vec_doc_id))

                chunk = KBChunk(
                    doc_id=doc_id,
                    kb_id=self.kb.kb_id,
                    chunk_index=idx,
                    content=chunk_text,
                    char_count=len(chunk_text),
                    vec_doc_id=str(vec_doc_id),
                )
                saved_chunks.append(chunk)

            # 保存文档和块的元数据
            doc = KBDocument(
                doc_id=doc_id,
                kb_id=self.kb.kb_id,
                doc_name=file_name,
                file_type=file_type,
                file_size=len(file_content),
                file_path=str(file_path),
                chunk_count=len(saved_chunks),
                media_count=0,
            )
            async with self.kb_db.get_db() as session:
                async with session.begin():
                    session.add(doc)
                    for chunk in saved_chunks:
                        session.add(chunk)
                    for media in saved_media:
                        session.add(media)
                    await session.commit()

                await session.refresh(doc)

            await self.kb_db.update_kb_stats(kb_id=self.kb.kb_id)

            return doc
        except Exception as e:
            logger.error(f"上传文档失败: {e}")
            if file_path.exists():
                file_path.unlink()

            for media_path in media_paths:
                try:
                    if media_path.exists():
                        media_path.unlink()
                except Exception as me:
                    logger.warning(f"清理多媒体文件失败 {media_path}: {me}")

            raise e

    async def list_documents(
        self, offset: int = 0, limit: int = 100
    ) -> list[KBDocument]:
        """列出知识库的所有文档"""
        docs = await self.kb_db.list_documents_by_kb(self.kb.kb_id, offset, limit)
        return docs

    async def get_document(self, doc_id: str) -> KBDocument | None:
        """获取单个文档"""
        doc = await self.kb_db.get_document_by_id(doc_id)
        return doc

    async def _save_media(
        self,
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
        file_path = self.kb_medias_dir / doc_id / f"{media_id}{ext}"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)

        media = KBMedia(
            media_id=media_id,
            doc_id=doc_id,
            kb_id=self.kb.kb_id,
            media_type=media_type,
            file_name=file_name,
            file_path=str(file_path),
            file_size=len(content),
            mime_type=mime_type,
        )

        return media
