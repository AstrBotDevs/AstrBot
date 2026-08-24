import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiofiles

from astrbot import logger
from astrbot.core.db.vec_db.base import BaseVecDB
from astrbot.core.exceptions import KnowledgeBaseUploadError
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.provider.provider import (
    EmbeddingProvider,
    RerankProvider,
)
from astrbot.core.provider.provider import (
    Provider as LLMProvider,
)

from ._kb_helper_cleaning import (
    RateLimiter as _CleaningRateLimiter,
)
from ._kb_helper_cleaning import (
    chunk_content_without_cleaning,
    clean_and_rechunk_content,
    compact_chunks,
    get_cleaning_provider,
    repair_and_translate_chunk_with_retry,
    repair_chunks_with_provider,
)
from ._kb_helper_url_import import (
    build_url_document_name,
    extract_url_content,
    get_tavily_keys,
)
from .chunking.base import BaseChunker
from .chunking.markdown import MarkdownChunker
from .kb_db_sqlite import KBSQLiteDatabase
from .models import KBDocument, KBMedia, KnowledgeBase
from .parsers.util import select_parser

if TYPE_CHECKING:
    from astrbot.core.db.vec_db.faiss_impl.vec_db import FaissVecDB


class RateLimiter:
    """一个简单的速率限制器"""

    def __init__(self, max_rpm: int) -> None:
        self._inner = _CleaningRateLimiter(max_rpm)

    async def __aenter__(self):
        return await self._inner.__aenter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await self._inner.__aexit__(exc_type, exc_val, exc_tb)


async def _repair_and_translate_chunk_with_retry(
    chunk: str,
    repair_llm_service: LLMProvider,
    rate_limiter: RateLimiter,
    max_retries: int = 2,
) -> list[str]:
    return await repair_and_translate_chunk_with_retry(
        chunk=chunk,
        repair_llm_service=repair_llm_service,
        rate_limiter=rate_limiter._inner,
        max_retries=max_retries,
    )


def _compact_chunks(chunks: list[str]) -> list[str]:
    return compact_chunks(chunks)


class KBHelper:
    vec_db: BaseVecDB
    kb: KnowledgeBase
    init_error: str | None

    def __init__(
        self,
        kb_db: KBSQLiteDatabase,
        kb: KnowledgeBase,
        provider_manager: ProviderManager,
        kb_root_dir: str,
        chunker: BaseChunker,
    ) -> None:
        self.kb_db = kb_db
        self.kb = kb
        self.prov_mgr = provider_manager
        self.kb_root_dir = kb_root_dir
        self.chunker = chunker
        self.init_error = None

        self.kb_dir = Path(self.kb_root_dir) / self.kb.kb_id
        self.kb_medias_dir = Path(self.kb_dir) / "medias" / self.kb.kb_id
        self.kb_files_dir = Path(self.kb_dir) / "files" / self.kb.kb_id

        self.kb_medias_dir.mkdir(parents=True, exist_ok=True)
        self.kb_files_dir.mkdir(parents=True, exist_ok=True)
        self.sparse_retriever = None

    def _invalidate_bm25_cache(self) -> None:
        retriever = self.sparse_retriever
        if retriever is not None:
            retriever.invalidate(self.kb.kb_id)

    async def initialize(self) -> None:
        await self._ensure_vec_db()

    async def get_ep(self) -> EmbeddingProvider:
        if not self.kb.embedding_provider_id:
            raise ValueError(f"知识库 {self.kb.kb_name} 未配置 Embedding Provider")
        ep: EmbeddingProvider = await self.prov_mgr.get_provider_by_id(
            self.kb.embedding_provider_id,
        )  # type: ignore
        if not ep:
            raise ValueError(
                f"无法找到 ID 为 {self.kb.embedding_provider_id} 的 Embedding Provider",
            )
        return ep

    async def get_rp(self) -> RerankProvider | None:
        if not self.kb.rerank_provider_id:
            return None
        rp: RerankProvider | None = await self.prov_mgr.get_provider_by_id(
            self.kb.rerank_provider_id,
        )  # type: ignore
        if not rp:
            logger.warning(
                f"知识库 {self.kb.kb_name}({self.kb.kb_id}) 的 Rerank Provider({self.kb.rerank_provider_id}) 不可用，将跳过重排序。",
            )
            return None
        return rp

    async def _ensure_vec_db(self) -> FaissVecDB:
        if not self.kb.embedding_provider_id:
            raise ValueError(f"知识库 {self.kb.kb_name} 未配置 Embedding Provider")

        ep = await self.get_ep()
        rp: RerankProvider | None = None
        try:
            rp = await self.get_rp()
        except Exception as e:
            logger.warning(
                f"知识库 {self.kb.kb_name}({self.kb.kb_id}) 初始化重排序能力失败，将跳过重排序: {e}",
            )

        from astrbot.core.db.vec_db.faiss_impl.vec_db import FaissVecDB

        vec_db = FaissVecDB(
            doc_store_path=str(self.kb_dir / "doc.db"),
            index_store_path=str(self.kb_dir / "index.faiss"),
            embedding_provider=ep,
            rerank_provider=rp,
        )
        await vec_db.initialize()
        self.vec_db = vec_db
        # Clear stale init_error once initialization succeeds.
        self.init_error = None
        return vec_db

    async def delete_vec_db(self) -> None:
        """删除知识库的向量数据库和所有相关文件"""
        import shutil

        await self.terminate()
        if self.kb_dir.exists():
            shutil.rmtree(self.kb_dir)

    async def terminate(self) -> None:
        if hasattr(self, "vec_db") and self.vec_db:
            await self.vec_db.close()

    async def _report_upload_progress(
        self,
        progress_callback,
        stage: str,
        current: int,
        total: int,
    ) -> None:
        if progress_callback:
            await progress_callback(stage, current, total)

    async def _prepare_document_chunks(
        self,
        *,
        doc_id: str,
        file_name: str,
        file_content: bytes | None,
        file_type: str,
        media_paths: list[Path],
        chunk_size: int,
        chunk_overlap: int,
        progress_callback,
        pre_chunked_text: list[str] | None,
    ) -> tuple[list[str], list[KBMedia], int]:
        if pre_chunked_text is not None:
            chunks_text = _compact_chunks(pre_chunked_text)
            file_size = sum(len(chunk) for chunk in chunks_text)
            logger.info(f"使用预分块文本进行上传，共 {len(chunks_text)} 个块。")
            return chunks_text, [], file_size

        if file_content is None:
            raise ValueError("当未提供 pre_chunked_text 时，file_content 不能为空。")

        file_size = len(file_content)
        parse_result = await self._parse_document_content(
            file_name=file_name,
            file_content=file_content,
            file_type=file_type,
            progress_callback=progress_callback,
        )
        saved_media = await self._save_media_items(
            doc_id=doc_id,
            media_items=parse_result.media,
            media_paths=media_paths,
        )
        chunks_text = await self._chunk_document_content(
            file_name=file_name,
            text_content=parse_result.text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            progress_callback=progress_callback,
        )
        return chunks_text, saved_media, file_size

    async def _parse_document_content(
        self,
        *,
        file_name: str,
        file_content: bytes,
        file_type: str,
        progress_callback,
    ):
        await self._report_upload_progress(progress_callback, "parsing", 0, 100)
        try:
            parser = await select_parser(f".{file_type}")
            parse_result = await parser.parse(file_content, file_name)
        except KnowledgeBaseUploadError:
            raise
        except Exception as exc:
            raise KnowledgeBaseUploadError(
                stage="parsing",
                user_message=(
                    "文档解析失败：无法读取或解析上传文件。"
                    "请确认文件格式受支持且文件内容未损坏。"
                ),
                details={"file_name": file_name},
            ) from exc

        text_content = parse_result.text
        if not text_content or not text_content.strip():
            raise KnowledgeBaseUploadError(
                stage="parsing",
                user_message=(
                    "文档解析失败：未能从文件中提取可索引文本。"
                    "该文件可能是扫描件、纯图片 PDF，或格式暂不受支持。"
                ),
                details={"file_name": file_name},
            )

        await self._report_upload_progress(progress_callback, "parsing", 100, 100)
        return parse_result

    async def _save_media_items(
        self,
        *,
        doc_id: str,
        media_items: list[Any],
        media_paths: list[Path],
    ) -> list[KBMedia]:
        saved_media: list[KBMedia] = []
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
        return saved_media

    async def _chunk_document_content(
        self,
        *,
        file_name: str,
        text_content: str,
        chunk_size: int,
        chunk_overlap: int,
        progress_callback,
    ) -> list[str]:
        await self._report_upload_progress(progress_callback, "chunking", 0, 100)
        try:
            effective_chunker = self._select_chunker_for_file(
                file_name=file_name,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            chunks_text = await effective_chunker.chunk(
                text_content,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        except KnowledgeBaseUploadError:
            raise
        except Exception as exc:
            raise KnowledgeBaseUploadError(
                stage="chunking",
                user_message=(
                    "分块失败：文档内容在切分文本块时发生错误。"
                    "请稍后重试，或调整分块参数后再次上传。"
                ),
                details={"file_name": file_name},
            ) from exc

        return _compact_chunks(chunks_text)

    def _select_chunker_for_file(
        self,
        *,
        file_name: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> BaseChunker:
        file_ext = Path(file_name).suffix.lower() if file_name else ""
        if file_ext not in (".md", ".markdown", ".mkd", ".mdx"):
            return self.chunker

        logger.info(
            f"检测到 Markdown 文件 '{file_name}'，使用 MarkdownChunker 进行结构化分块"
        )
        return MarkdownChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def _validate_chunks_text(
        self,
        *,
        chunks_text: list[str],
        file_name: str,
        pre_chunked_text: list[str] | None,
    ) -> None:
        if chunks_text and any(chunk.strip() for chunk in chunks_text):
            return
        if pre_chunked_text is not None:
            raise KnowledgeBaseUploadError(
                stage="validation",
                user_message=("预分块文本为空，未提供任何可索引文本块。"),
                details={"file_name": file_name},
            )
        raise KnowledgeBaseUploadError(
            stage="chunking",
            user_message=("分块失败：文档内容为空，未生成任何可索引文本块。"),
            details={"file_name": file_name},
        )

    def _build_embedding_payload(
        self,
        *,
        doc_id: str,
        chunks_text: list[str],
    ) -> tuple[list[str], list[dict[str, Any]]]:
        contents: list[str] = []
        metadatas: list[dict[str, Any]] = []
        for idx, chunk_text in enumerate(chunks_text):
            contents.append(chunk_text)
            metadatas.append(
                {
                    "kb_id": self.kb.kb_id,
                    "kb_doc_id": doc_id,
                    "chunk_index": idx,
                },
            )
        return contents, metadatas

    async def _insert_document_embeddings(
        self,
        *,
        file_name: str,
        contents: list[str],
        metadatas: list[dict[str, Any]],
        batch_size: int,
        tasks_limit: int,
        max_retries: int,
        progress_callback,
    ) -> None:
        async def embedding_progress_callback(current, total) -> None:
            await self._report_upload_progress(
                progress_callback, "embedding", current, total
            )

        try:
            await self.vec_db.insert_batch(
                contents=contents,
                metadatas=metadatas,
                batch_size=batch_size,
                tasks_limit=tasks_limit,
                max_retries=max_retries,
                progress_callback=embedding_progress_callback,
            )
            self._invalidate_bm25_cache()
        except KnowledgeBaseUploadError:
            raise
        except Exception as exc:
            raise KnowledgeBaseUploadError(
                stage="storage",
                user_message=("存储失败：文本块已生成，但写入知识库索引时出错。"),
                details={"file_name": file_name},
            ) from exc

    async def _save_document_metadata(
        self,
        *,
        doc_id: str,
        file_name: str,
        file_type: str,
        file_size: int,
        chunks_text: list[str],
        saved_media: list[KBMedia],
    ) -> KBDocument:
        doc = KBDocument(
            doc_id=doc_id,
            kb_id=self.kb.kb_id,
            doc_name=file_name,
            file_type=file_type,
            file_size=file_size,
            file_path="",
            chunk_count=len(chunks_text),
            media_count=0,
        )
        try:
            async with self.kb_db.get_db() as session:
                async with session.begin():
                    session.add(doc)
                    for media in saved_media:
                        session.add(media)
                    await session.commit()
        except KnowledgeBaseUploadError:
            raise
        except Exception as exc:
            raise KnowledgeBaseUploadError(
                stage="metadata",
                user_message=(
                    "元数据保存失败：文本块已写入知识库，但文档记录保存失败。"
                ),
                details={"file_name": file_name, "doc_id": doc_id},
            ) from exc
        return doc

    async def _refresh_uploaded_document_state(
        self,
        *,
        doc_id: str,
        file_name: str,
    ) -> None:
        vec_db: FaissVecDB = self.vec_db  # type: ignore
        try:
            await self.kb_db.update_kb_stats(kb_id=self.kb.kb_id, vec_db=vec_db)
            await self.refresh_kb()
            await self.refresh_document(doc_id)
        except KnowledgeBaseUploadError:
            raise
        except Exception as exc:
            raise KnowledgeBaseUploadError(
                stage="metadata",
                user_message=("元数据更新失败：文档已上传，但知识库统计信息刷新失败。"),
                details={"file_name": file_name, "doc_id": doc_id},
            ) from exc

    async def _cleanup_failed_upload(
        self,
        *,
        doc_id: str,
        media_paths: list[Path],
    ) -> None:
        """Best-effort cleanup after an upload fails before metadata commits."""
        from sqlalchemy import delete
        from sqlmodel import col

        try:
            await self.vec_db.delete_documents(metadata_filters={"kb_doc_id": doc_id})
            self._invalidate_bm25_cache()
        except Exception as exc:
            logger.warning(
                "Failed to roll back chunks and vectors for document %s: %s",
                doc_id,
                exc,
            )

        try:
            async with self.kb_db.get_db() as session, session.begin():
                await session.execute(
                    delete(KBMedia).where(col(KBMedia.doc_id) == doc_id),
                )
                await session.execute(
                    delete(KBDocument).where(col(KBDocument.doc_id) == doc_id),
                )
        except Exception as exc:
            logger.warning(
                "Failed to roll back metadata for document %s: %s",
                doc_id,
                exc,
            )

        for media_path in media_paths:
            try:
                if media_path.exists():
                    media_path.unlink()
            except Exception as media_error:
                logger.warning(
                    "Failed to remove media file %s: %s", media_path, media_error
                )

        try:
            media_dir = self.kb_medias_dir / doc_id
            if media_dir.is_dir():
                media_dir.rmdir()
        except Exception as exc:
            logger.warning(
                "Failed to remove media directory for document %s: %s",
                doc_id,
                exc,
            )

    async def upload_document(
        self,
        file_name: str,
        file_content: bytes | None,
        file_type: str,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        batch_size: int = 32,
        tasks_limit: int = 3,
        max_retries: int = 3,
        progress_callback=None,
        pre_chunked_text: list[str] | None = None,
    ) -> KBDocument:
        """Upload and process a document with compensating cleanup on failure.

        Args:
            progress_callback: Progress callback ``(stage, current, total)``.
        """
        await self._ensure_vec_db()
        doc_id = str(uuid.uuid4())
        media_paths: list[Path] = []
        metadata_committed = False

        try:
            chunks_text, saved_media, file_size = await self._prepare_document_chunks(
                doc_id=doc_id,
                file_name=file_name,
                file_content=file_content,
                file_type=file_type,
                media_paths=media_paths,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                progress_callback=progress_callback,
                pre_chunked_text=pre_chunked_text,
            )
            self._validate_chunks_text(
                chunks_text=chunks_text,
                file_name=file_name,
                pre_chunked_text=pre_chunked_text,
            )
            contents, metadatas = self._build_embedding_payload(
                doc_id=doc_id,
                chunks_text=chunks_text,
            )
            await self._report_upload_progress(progress_callback, "chunking", 100, 100)
            await self._insert_document_embeddings(
                file_name=file_name,
                contents=contents,
                metadatas=metadatas,
                batch_size=batch_size,
                tasks_limit=tasks_limit,
                max_retries=max_retries,
                progress_callback=progress_callback,
            )
            doc = await self._save_document_metadata(
                doc_id=doc_id,
                file_name=file_name,
                file_type=file_type,
                file_size=file_size,
                chunks_text=chunks_text,
                saved_media=saved_media,
            )
            metadata_committed = True
            await self._refresh_uploaded_document_state(
                doc_id=doc_id,
                file_name=file_name,
            )
            return doc
        except Exception as exc:
            if isinstance(exc, KnowledgeBaseUploadError):
                logger.warning(
                    "Document upload failed: %s", exc, extra={"details": exc.details}
                )
            else:
                logger.error("Document upload failed", exc_info=True)
            if not metadata_committed:
                await self._cleanup_failed_upload(
                    doc_id=doc_id,
                    media_paths=media_paths,
                )
            raise

    async def list_documents(
        self,
        offset: int = 0,
        limit: int = 100,
        search: str | None = None,
    ) -> list[KBDocument]:
        """List documents in the knowledge base.

        Args:
            offset: Number of documents to skip.
            limit: Maximum number of documents to return.
            search: Optional partial match on document name; disabled when None or empty.

        Returns:
            List of matching KBDocument rows.
        """
        docs = await self.kb_db.list_documents_by_kb(
            self.kb.kb_id,
            offset,
            limit,
            search=search,
        )
        return docs

    async def count_documents(self, search: str | None = None) -> int:
        """Count documents in the knowledge base.

        Args:
            search: Optional partial match on document name; disabled when None or empty.

        Returns:
            Total number of matching documents.
        """
        return await self.kb_db.count_documents_by_kb(self.kb.kb_id, search=search)

    async def get_document(self, doc_id: str) -> KBDocument | None:
        """获取单个文档"""
        doc = await self.kb_db.get_document_by_id(doc_id)
        return doc

    async def delete_document(self, doc_id: str) -> None:
        """删除单个文档及其相关数据"""
        await self.kb_db.delete_document_by_id(
            doc_id=doc_id,
            vec_db=self.vec_db,  # type: ignore
        )
        self._invalidate_bm25_cache()
        await self.kb_db.update_kb_stats(
            kb_id=self.kb.kb_id,
            vec_db=self.vec_db,  # type: ignore
        )
        await self.refresh_kb()

    async def delete_chunk(self, chunk_id: str, doc_id: str) -> None:
        """删除单个文本块及其相关数据"""
        vec_db: FaissVecDB = self.vec_db  # type: ignore
        await vec_db.delete(chunk_id)
        self._invalidate_bm25_cache()
        await self.kb_db.update_kb_stats(
            kb_id=self.kb.kb_id,
            vec_db=self.vec_db,  # type: ignore
        )
        await self.refresh_kb()
        await self.refresh_document(doc_id)

    async def refresh_kb(self) -> None:
        if self.kb:
            kb = await self.kb_db.get_kb_by_id(self.kb.kb_id)
            if kb:
                self.kb = kb

    async def refresh_document(self, doc_id: str) -> None:
        """更新文档的元数据"""
        doc = await self.get_document(doc_id)
        if not doc:
            raise ValueError(f"无法找到 ID 为 {doc_id} 的文档")
        chunk_count = await self.get_chunk_count_by_doc_id(doc_id)
        doc.chunk_count = chunk_count
        async with self.kb_db.get_db() as session:
            async with session.begin():
                session.add(doc)
                await session.commit()
            await session.refresh(doc)

    async def get_chunks_by_doc_id(
        self,
        doc_id: str,
        offset: int = 0,
        limit: int = 100,
    ) -> list[dict]:
        """获取文档的所有块及其元数据"""
        vec_db: FaissVecDB = self.vec_db  # type: ignore
        chunks = await vec_db.document_storage.get_documents(
            metadata_filters={"kb_doc_id": doc_id},
            offset=offset,
            limit=limit,
        )
        result = []
        for chunk in chunks:
            chunk_md = json.loads(chunk["metadata"])
            result.append(
                {
                    "chunk_id": chunk["doc_id"],
                    "doc_id": chunk_md["kb_doc_id"],
                    "kb_id": chunk_md["kb_id"],
                    "chunk_index": chunk_md["chunk_index"],
                    "content": chunk["text"],
                    "char_count": len(chunk["text"]),
                },
            )
        return result

    async def get_chunk_count_by_doc_id(self, doc_id: str) -> int:
        """获取文档的块数量"""
        vec_db: FaissVecDB = self.vec_db  # type: ignore
        count = await vec_db.count_documents(metadata_filter={"kb_doc_id": doc_id})
        return count

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

    async def upload_from_url(
        self,
        url: str,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        batch_size: int = 32,
        tasks_limit: int = 3,
        max_retries: int = 3,
        progress_callback=None,
        enable_cleaning: bool = False,
        cleaning_provider_id: str | None = None,
    ) -> KBDocument:
        """从 URL 上传并处理文档（带原子性保证和失败清理）
        Args:
            url: 要提取内容的网页 URL
            chunk_size: 文本块大小
            chunk_overlap: 文本块重叠大小
            batch_size: 批处理大小
            tasks_limit: 并发任务限制
            max_retries: 最大重试次数
            progress_callback: 进度回调函数，接收参数 (stage, current, total)
                - stage: 当前阶段 ('extracting', 'cleaning', 'parsing', 'chunking', 'embedding')
                - current: 当前进度
                - total: 总数
        Returns:
            KBDocument: 上传的文档对象
        Raises:
            ValueError: 如果 URL 为空或无法提取内容
            IOError: 如果网络请求失败
        """
        tavily_keys = get_tavily_keys(self.prov_mgr.acm.default_conf)
        text_content = await extract_url_content(
            url=url,
            tavily_keys=tavily_keys,
            progress_callback=progress_callback,
        )
        final_chunks = await self._clean_and_rechunk_content(
            content=text_content,
            url=url,
            progress_callback=progress_callback,
            enable_cleaning=enable_cleaning,
            cleaning_provider_id=cleaning_provider_id,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        if enable_cleaning and not final_chunks:
            raise ValueError(
                "内容清洗后未提取到有效文本。请尝试关闭内容清洗功能，或更换更高性能的LLM模型后重试。"
            )

        return await self.upload_document(
            file_name=build_url_document_name(url),
            file_content=None,
            file_type="url",
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            batch_size=batch_size,
            tasks_limit=tasks_limit,
            max_retries=max_retries,
            progress_callback=progress_callback,
            pre_chunked_text=final_chunks,
        )

    async def _chunk_content_without_cleaning(
        self,
        *,
        content: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[str]:
        return await chunk_content_without_cleaning(
            content=content,
            chunker=self.chunker,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    async def _get_cleaning_provider(self, cleaning_provider_id: str) -> LLMProvider:
        return await get_cleaning_provider(self.prov_mgr, cleaning_provider_id)

    async def _repair_chunks_with_provider(
        self,
        *,
        content: str,
        llm_provider: LLMProvider,
        repair_max_rpm: int,
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[str]:
        return await repair_chunks_with_provider(
            content=content,
            llm_provider=llm_provider,
            repair_max_rpm=repair_max_rpm,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    async def _clean_and_rechunk_content(
        self,
        content: str,
        url: str,
        progress_callback=None,
        enable_cleaning: bool = False,
        cleaning_provider_id: str | None = None,
        repair_max_rpm: int = 60,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
    ) -> list[str]:
        return await clean_and_rechunk_content(
            content=content,
            url=url,
            chunker=self.chunker,
            provider_manager=self.prov_mgr,
            progress_callback=progress_callback,
            report_progress=self._report_upload_progress,
            enable_cleaning=enable_cleaning,
            cleaning_provider_id=cleaning_provider_id,
            repair_max_rpm=repair_max_rpm,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
