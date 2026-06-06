import asyncio
import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import aiofiles

from astrbot.core import logger
from astrbot.core.db.vec_db.base import BaseVecDB
from astrbot.core.exceptions import KnowledgeBaseUploadError
from astrbot.core.provider.provider import (
    EmbeddingProvider,
    RerankProvider,
)
from astrbot.core.provider.provider import (
    Provider as LLMProvider,
)

from .capabilities import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_UPLOAD_BATCH_SIZE,
    DEFAULT_UPLOAD_MAX_RETRIES,
    DEFAULT_UPLOAD_TASKS_LIMIT,
)
from .chunking.base import BaseChunker
from .chunking.markdown import MarkdownChunker
from .chunking.recursive import RecursiveCharacterChunker
from .document_metadata import (
    DEFAULT_CHUNKER_VERSION,
    DEFAULT_PARSER_VERSION,
    build_content_hash,
    build_stored_source_path,
    get_chunker_name,
    get_parser_name,
)
from .kb_db_sqlite import KBSQLiteDatabase
from .models import KBDocument, KBMedia, KnowledgeBase
from .parsers.base import TextSegment
from .parsers.url_parser import URLExtractor, extract_text_from_url
from .parsers.util import select_parser
from .prompts import TEXT_REPAIR_SYSTEM_PROMPT

if TYPE_CHECKING:
    from astrbot.core.db.vec_db.faiss_impl.vec_db import FaissVecDB
    from astrbot.core.provider.manager import ProviderManager


DOCUMENT_REBUILD_PAGE_SIZE = 100
CONSISTENCY_CHECK_PAGE_SIZE = 1000
CONSISTENCY_REPAIR_TYPES = frozenset(
    {
        "orphan_vectors",
        "chunk_count_mismatches",
    },
)
NON_PERSISTED_FAILURE_STAGES = frozenset({"deduplication"})
MARKDOWN_AWARE_EXTENSIONS = frozenset(
    {
        ".adoc",
        ".docx",
        ".epub",
        ".md",
        ".markdown",
        ".mdx",
        ".mkd",
        ".rst",
        ".xls",
        ".xlsx",
    },
)


class RateLimiter:
    """一个简单的速率限制器"""

    def __init__(self, max_rpm: int) -> None:
        self.max_per_minute = max_rpm
        self.interval = 60.0 / max_rpm if max_rpm > 0 else 0
        self.last_call_time = 0
        self._lock = asyncio.Lock()

    async def __aenter__(self):
        if self.interval == 0:
            return

        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_call_time

            if elapsed < self.interval:
                await asyncio.sleep(self.interval - elapsed)

            self.last_call_time = time.monotonic()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


async def _repair_and_translate_chunk_with_retry(
    chunk: str,
    repair_llm_service: LLMProvider,
    rate_limiter: RateLimiter,
    max_retries: int = 2,
) -> list[str]:
    """
    Repairs, translates, and optionally re-chunks a single text chunk using the small LLM, with rate limiting.
    """
    # 为了防止 LLM 上下文污染，在 user_prompt 中也加入明确的指令
    user_prompt = f"""IGNORE ALL PREVIOUS INSTRUCTIONS. Your ONLY task is to process the following text chunk according to the system prompt provided.

Text chunk to process:
---
{chunk}
---
"""
    for attempt in range(max_retries + 1):
        try:
            async with rate_limiter:
                response = await repair_llm_service.text_chat(
                    prompt=user_prompt, system_prompt=TEXT_REPAIR_SYSTEM_PROMPT
                )

            llm_output = response.completion_text

            if "<discard_chunk />" in llm_output:
                return []  # Signal to discard this chunk

            # More robust regex to handle potential LLM formatting errors (spaces, newlines in tags)
            matches = re.findall(
                r"<\s*repaired_text\s*>\s*(.*?)\s*<\s*/\s*repaired_text\s*>",
                llm_output,
                re.DOTALL,
            )

            if matches:
                # Further cleaning to ensure no empty strings are returned
                return [m.strip() for m in matches if m.strip()]
            else:
                # If no valid tags and not explicitly discarded, discard it to be safe.
                return []
        except Exception as e:
            logger.warning(
                f"  - LLM call failed on attempt {attempt + 1}/{max_retries + 1}. Error: {str(e)}"
            )

    logger.error(
        f"  - Failed to process chunk after {max_retries + 1} attempts. Using original text."
    )
    return [chunk]


def _compact_chunks(chunks: list[str]) -> list[str]:
    return [chunk.strip() for chunk in chunks if chunk and chunk.strip()]


def _estimate_text_tokens(text: str) -> int:
    chinese_count = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    other_count = len(text) - chinese_count
    return int(chinese_count * 0.6 + other_count * 0.3)


def _build_chunk_metadata(
    *,
    kb_id: str,
    doc_id: str,
    chunks_text: list[str],
    chunk_ids: list[str],
    chunk_extra_metadatas: list[dict] | None = None,
) -> list[dict]:
    if chunk_extra_metadatas is not None and len(chunk_extra_metadatas) != len(
        chunks_text
    ):
        raise ValueError("chunk_extra_metadatas length must match chunks_text length")

    metadatas = []
    start_offset = 0
    for idx, chunk_text in enumerate(chunks_text):
        end_offset = start_offset + len(chunk_text)
        metadata = {
            "kb_id": kb_id,
            "kb_doc_id": doc_id,
            "chunk_index": idx,
            "section_index": idx,
            "content_hash": build_content_hash(chunk_text),
            "char_count": len(chunk_text),
            "token_count_estimate": _estimate_text_tokens(chunk_text),
            "start_offset": start_offset,
            "end_offset": end_offset,
            "previous_chunk_id": chunk_ids[idx - 1] if idx > 0 else None,
            "next_chunk_id": chunk_ids[idx + 1] if idx < len(chunk_ids) - 1 else None,
        }
        if chunk_extra_metadatas is not None:
            metadata.update(chunk_extra_metadatas[idx])
        metadatas.append(metadata)
        start_offset = end_offset
    return metadatas


async def _chunk_text_with_metadata(
    *,
    chunker: BaseChunker,
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    extra_metadata: dict | None = None,
) -> tuple[list[str], list[dict] | None]:
    chunks_text = await chunker.chunk(
        text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    chunks_text = _compact_chunks(chunks_text)
    if not chunks_text:
        return [], [] if extra_metadata is not None else None
    if extra_metadata is None:
        return chunks_text, None
    return chunks_text, [dict(extra_metadata) for _ in chunks_text]


async def _chunk_text_segments_with_metadata(
    *,
    chunker: BaseChunker,
    text_segments: list[TextSegment],
    chunk_size: int,
    chunk_overlap: int,
) -> tuple[list[str], list[dict]]:
    chunks_text: list[str] = []
    chunk_extra_metadatas: list[dict] = []
    for segment in text_segments:
        segment_text = getattr(segment, "text", "")
        segment_metadata = getattr(segment, "metadata", None) or {}
        segment_chunks, segment_metadatas = await _chunk_text_with_metadata(
            chunker=chunker,
            text=segment_text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            extra_metadata=segment_metadata,
        )
        chunks_text.extend(segment_chunks)
        chunk_extra_metadatas.extend(segment_metadatas or [])
    return chunks_text, chunk_extra_metadatas


def _build_duplicate_document_error(
    *,
    file_name: str,
    content_hash: str,
    existing_doc: KBDocument,
) -> KnowledgeBaseUploadError:
    return KnowledgeBaseUploadError(
        stage="deduplication",
        user_message=(
            f"重复文档：{file_name} 与已存在文档 {existing_doc.doc_name} 内容相同。"
        ),
        details={
            "file_name": file_name,
            "content_hash": content_hash,
            "existing_doc_id": existing_doc.doc_id,
            "existing_doc_name": existing_doc.doc_name,
        },
    )


class KBHelper:
    vec_db: BaseVecDB
    kb: KnowledgeBase
    init_error: str | None

    def __init__(
        self,
        kb_db: KBSQLiteDatabase,
        kb: KnowledgeBase,
        provider_manager: "ProviderManager",
        kb_root_dir: str,
        chunker: BaseChunker,
    ) -> None:
        self.kb_db = kb_db
        self.kb = kb
        self.prov_mgr = provider_manager
        self.kb_root_dir = kb_root_dir
        self.chunker = chunker
        self.init_error = None
        self.init_retry_count = 0
        self.last_init_retry_at = 0.0

        self.kb_dir = Path(self.kb_root_dir) / self.kb.kb_id
        self.kb_medias_dir = Path(self.kb_dir) / "medias" / self.kb.kb_id
        self.kb_files_dir = Path(self.kb_dir) / "files" / self.kb.kb_id

        self.kb_medias_dir.mkdir(parents=True, exist_ok=True)
        self.kb_files_dir.mkdir(parents=True, exist_ok=True)

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

    async def _ensure_vec_db(self) -> "FaissVecDB":
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
            index_type=self.kb.index_type or "flat",
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

    async def _ensure_not_duplicate_document(
        self,
        *,
        file_name: str,
        content_hash: str | None,
    ) -> None:
        if not content_hash:
            return
        try:
            existing_doc = await self.kb_db.get_document_by_content_hash(
                kb_id=self.kb.kb_id,
                content_hash=content_hash,
            )
        except KnowledgeBaseUploadError:
            raise
        except Exception as exc:
            raise KnowledgeBaseUploadError(
                stage="deduplication",
                user_message=("重复检测失败：无法确认文档是否已存在，请稍后重试。"),
                details={"file_name": file_name, "content_hash": content_hash},
            ) from exc
        if existing_doc is not None:
            raise _build_duplicate_document_error(
                file_name=file_name,
                content_hash=content_hash,
                existing_doc=existing_doc,
            )

    @staticmethod
    def _get_upload_failure_stage(error: Exception) -> str:
        if isinstance(error, KnowledgeBaseUploadError):
            return error.stage
        return "unknown"

    async def _persist_failed_document(
        self,
        *,
        doc_id: str,
        file_name: str,
        file_type: str,
        file_size: int,
        stored_file_path: Path | None,
        source_type: str,
        source_uri: str,
        content_hash: str | None,
        parser_name: str | None,
        chunker_name: str | None,
        parent_doc_id: str | None,
        document_version: int,
        error: Exception,
    ) -> bool:
        """Persist a failed document record for ingestion diagnostics."""
        error_stage = self._get_upload_failure_stage(error)
        if error_stage in NON_PERSISTED_FAILURE_STAGES:
            return False

        failed_doc = KBDocument(
            doc_id=doc_id,
            kb_id=self.kb.kb_id,
            doc_name=file_name,
            file_type=file_type,
            file_size=file_size,
            file_path=str(stored_file_path) if stored_file_path else "",
            source_type=source_type,
            source_uri=source_uri,
            content_hash=content_hash,
            parser_name=parser_name,
            parser_version=DEFAULT_PARSER_VERSION if parser_name else None,
            chunker_name=chunker_name,
            chunker_version=DEFAULT_CHUNKER_VERSION if chunker_name else None,
            status="failed",
            error_stage=error_stage,
            error_message=str(error).strip() or error.__class__.__name__,
            version=document_version,
            parent_doc_id=parent_doc_id,
        )

        try:
            async with self.kb_db.get_db() as session:
                async with session.begin():
                    session.add(failed_doc)
                    await session.commit()
                await session.refresh(failed_doc)
        except Exception as persist_err:
            logger.warning(
                f"记录失败文档 {doc_id} 的元数据失败: {persist_err}",
            )
            return False

        try:
            await self.kb_db.update_kb_stats(
                kb_id=self.kb.kb_id,
                vec_db=self.vec_db,  # type: ignore[arg-type]
            )
            await self.refresh_kb()
            await self.refresh_document(doc_id)
        except Exception as stats_err:
            logger.warning(
                f"刷新失败文档 {doc_id} 的知识库统计失败: {stats_err}",
            )
        return True

    @staticmethod
    def _build_url_file_name(url: str) -> str:
        file_name = url.split("/")[-1] or f"document_from_{url}"
        if not Path(file_name).suffix:
            file_name += ".url"
        return file_name

    async def _persist_failed_url_document(
        self,
        *,
        url: str,
        text_content: str | None,
        parent_doc_id: str | None,
        document_version: int,
        error: Exception,
    ) -> bool:
        return await self._persist_failed_document(
            doc_id=str(uuid.uuid4()),
            file_name=self._build_url_file_name(url),
            file_type="url",
            file_size=len(text_content) if text_content else 0,
            stored_file_path=None,
            source_type="url",
            source_uri=url,
            content_hash=(
                build_content_hash(text_content) if text_content is not None else None
            ),
            parser_name=URLExtractor.__name__,
            chunker_name=get_chunker_name(self.chunker),
            parent_doc_id=parent_doc_id,
            document_version=document_version,
            error=error,
        )

    async def upload_document(
        self,
        file_name: str,
        file_content: bytes | None,
        file_type: str,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
        batch_size: int = DEFAULT_UPLOAD_BATCH_SIZE,
        tasks_limit: int = DEFAULT_UPLOAD_TASKS_LIMIT,
        max_retries: int = DEFAULT_UPLOAD_MAX_RETRIES,
        progress_callback=None,
        pre_chunked_text: list[str] | None = None,
        source_type: str | None = None,
        source_uri: str | None = None,
        source_content_hash: str | None = None,
        source_parser_name: str | None = None,
        source_chunker_name: str | None = None,
        parent_doc_id: str | None = None,
        document_version: int = 1,
        skip_duplicate_check: bool = False,
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

        Args:
            progress_callback: 进度回调函数，接收参数 (stage, current, total)
                - stage: 当前阶段 ('parsing', 'chunking', 'embedding')
                - current: 当前进度
                - total: 总数

        """
        await self._ensure_vec_db()
        doc_id = str(uuid.uuid4())
        media_paths: list[Path] = []
        stored_file_path: Path | None = None
        file_size = 0
        vectors_stored = False  # 标记向量是否已写入, 用于失败回滚
        metadata_stored = False
        failed_metadata_stored = False
        effective_source_type = source_type or (
            "import" if pre_chunked_text is not None else "file"
        )
        effective_source_uri = source_uri or file_name
        content_hash: str | None = source_content_hash
        parser_name: str | None = source_parser_name
        chunker_name: str | None = source_chunker_name

        try:
            chunks_text = []
            chunk_extra_metadatas: list[dict] | None = None
            saved_media = []

            if pre_chunked_text is not None:
                # 如果提供了预分块文本，直接使用
                chunks_text = _compact_chunks(pre_chunked_text)
                file_size = sum(len(chunk) for chunk in chunks_text)
                if content_hash is None:
                    content_hash = build_content_hash(chunks_text)
                if chunker_name is None:
                    chunker_name = "pre_chunked"
                if not skip_duplicate_check:
                    await self._ensure_not_duplicate_document(
                        file_name=file_name,
                        content_hash=content_hash,
                    )
                logger.info(f"使用预分块文本进行上传，共 {len(chunks_text)} 个块。")
            else:
                # 否则，执行标准的文件解析和分块流程
                if file_content is None:
                    raise ValueError(
                        "当未提供 pre_chunked_text 时，file_content 不能为空。"
                    )

                file_size = len(file_content)
                content_hash = build_content_hash(file_content)
                if not skip_duplicate_check:
                    await self._ensure_not_duplicate_document(
                        file_name=file_name,
                        content_hash=content_hash,
                    )

                stored_file_path = build_stored_source_path(
                    self.kb_files_dir,
                    doc_id=doc_id,
                    file_name=file_name,
                    file_type=file_type,
                )
                stored_file_path.parent.mkdir(parents=True, exist_ok=True)
                async with aiofiles.open(stored_file_path, "wb") as f:
                    await f.write(file_content)

                # 阶段1: 解析文档
                if progress_callback:
                    await progress_callback("parsing", 0, 100)

                try:
                    parser = await select_parser(f".{file_type}")
                    parser_name = get_parser_name(parser)
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
                media_items = parse_result.media
                text_segments = getattr(parse_result, "text_segments", None)
                if not text_content or not text_content.strip():
                    raise KnowledgeBaseUploadError(
                        stage="parsing",
                        user_message=(
                            "文档解析失败：未能从文件中提取可索引文本。"
                            "该文件可能是扫描件、纯图片 PDF，或格式暂不受支持。"
                        ),
                        details={"file_name": file_name},
                    )

                if progress_callback:
                    await progress_callback("parsing", 100, 100)

                # 保存媒体文件
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

                # 阶段2: 分块
                if progress_callback:
                    await progress_callback("chunking", 0, 100)

                try:
                    # Use structure-aware chunking for Markdown and MarkItDown output.
                    effective_chunker = self.chunker
                    file_ext = Path(file_name).suffix.lower() if file_name else ""
                    if file_ext in MARKDOWN_AWARE_EXTENSIONS:
                        effective_chunker = MarkdownChunker(
                            chunk_size=chunk_size,
                            chunk_overlap=chunk_overlap,
                        )
                        logger.info(
                            f"检测到 Markdown 兼容文档 '{file_name}'，使用 MarkdownChunker 进行结构化分块"
                        )

                    chunker_name = get_chunker_name(effective_chunker)
                    if isinstance(effective_chunker, MarkdownChunker):
                        structured_chunks = await effective_chunker.chunk_with_metadata(
                            text_content,
                            chunk_size=chunk_size,
                            chunk_overlap=chunk_overlap,
                        )
                        chunks_text = []
                        chunk_extra_metadatas = []
                        for chunk in structured_chunks:
                            chunk_text = chunk.text.strip()
                            if not chunk_text:
                                continue
                            chunks_text.append(chunk_text)
                            chunk_extra_metadatas.append(
                                {
                                    "title_path": chunk.title_path,
                                    "section_index": chunk.section_index,
                                }
                            )
                    elif text_segments:
                        (
                            chunks_text,
                            chunk_extra_metadatas,
                        ) = await _chunk_text_segments_with_metadata(
                            chunker=effective_chunker,
                            text_segments=text_segments,
                            chunk_size=chunk_size,
                            chunk_overlap=chunk_overlap,
                        )
                    else:
                        (
                            chunks_text,
                            chunk_extra_metadatas,
                        ) = await _chunk_text_with_metadata(
                            chunker=effective_chunker,
                            text=text_content,
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

            if not chunks_text or not any(chunk.strip() for chunk in chunks_text):
                if pre_chunked_text is not None:
                    raise KnowledgeBaseUploadError(
                        stage="validation",
                        user_message=("预分块文本为空，未提供任何可索引文本块。"),
                        details={"file_name": file_name},
                    )
                else:
                    raise KnowledgeBaseUploadError(
                        stage="chunking",
                        user_message=(
                            "分块失败：文档内容为空，未生成任何可索引文本块。"
                        ),
                        details={"file_name": file_name},
                    )

            contents = []
            for idx, chunk_text in enumerate(chunks_text):
                contents.append(chunk_text)
            chunk_ids = [str(uuid.uuid4()) for _ in chunks_text]
            metadatas = _build_chunk_metadata(
                kb_id=self.kb.kb_id,
                doc_id=doc_id,
                chunks_text=chunks_text,
                chunk_ids=chunk_ids,
                chunk_extra_metadatas=chunk_extra_metadatas,
            )

            if progress_callback:
                await progress_callback("chunking", 100, 100)

            # 阶段3: 生成向量（带进度回调）
            async def embedding_progress_callback(current, total) -> None:
                if progress_callback:
                    await progress_callback("embedding", current, total)

            try:
                await self.vec_db.insert_batch(
                    contents=contents,
                    metadatas=metadatas,
                    ids=chunk_ids,
                    batch_size=batch_size,
                    tasks_limit=tasks_limit,
                    max_retries=max_retries,
                    progress_callback=embedding_progress_callback,
                )
                vectors_stored = True
            except KnowledgeBaseUploadError:
                raise
            except Exception as exc:
                raise KnowledgeBaseUploadError(
                    stage="storage",
                    user_message=("存储失败：文本块已生成，但写入知识库索引时出错。"),
                    details={"file_name": file_name},
                ) from exc

            # 保存文档的元数据
            doc = KBDocument(
                doc_id=doc_id,
                kb_id=self.kb.kb_id,
                doc_name=file_name,
                file_type=file_type,
                file_size=file_size,
                file_path=str(stored_file_path) if stored_file_path else "",
                source_type=effective_source_type,
                source_uri=effective_source_uri,
                content_hash=content_hash,
                parser_name=parser_name,
                parser_version=DEFAULT_PARSER_VERSION if parser_name else None,
                chunker_name=chunker_name,
                chunker_version=DEFAULT_CHUNKER_VERSION if chunker_name else None,
                status="ready",
                indexed_at=datetime.now(timezone.utc),
                version=document_version,
                parent_doc_id=parent_doc_id,
                chunk_count=len(chunks_text),
                media_count=len(saved_media),
            )
            try:
                async with self.kb_db.get_db() as session:
                    async with session.begin():
                        session.add(doc)
                        for media in saved_media:
                            session.add(media)
                        await session.commit()
                        metadata_stored = True

                    await session.refresh(doc)
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
                    user_message=(
                        "元数据更新失败：文档已上传，但知识库统计信息刷新失败。"
                    ),
                    details={"file_name": file_name, "doc_id": doc_id},
                ) from exc
            return doc
        except Exception as e:
            if isinstance(e, KnowledgeBaseUploadError):
                logger.warning(f"上传文档失败: {e}", extra={"details": e.details})
            else:
                logger.error(f"上传文档失败: {e}", exc_info=True)

            # 回滚已写入的向量, 防止孤数据
            if vectors_stored and not metadata_stored:
                try:
                    vec_db: FaissVecDB = self.vec_db  # type: ignore
                    await vec_db.delete_documents(
                        metadata_filters={"kb_doc_id": doc_id},
                    )
                    logger.info(f"已清理文档 {doc_id} 的孤数据向量")
                except Exception as cleanup_err:
                    logger.error(
                        f"清理文档 {doc_id} 向量回滚失败: {cleanup_err}",
                    )

            if not metadata_stored:
                failed_metadata_stored = await self._persist_failed_document(
                    doc_id=doc_id,
                    file_name=file_name,
                    file_type=file_type,
                    file_size=file_size,
                    stored_file_path=stored_file_path,
                    source_type=effective_source_type,
                    source_uri=effective_source_uri,
                    content_hash=content_hash,
                    parser_name=parser_name,
                    chunker_name=chunker_name,
                    parent_doc_id=parent_doc_id,
                    document_version=document_version,
                    error=e,
                )

            if (
                stored_file_path
                and stored_file_path.exists()
                and not metadata_stored
                and not failed_metadata_stored
            ):
                try:
                    stored_file_path.unlink()
                    if stored_file_path.parent != self.kb_files_dir:
                        stored_file_path.parent.rmdir()
                except Exception as fe:
                    logger.warning(f"清理原始文件失败 {stored_file_path}: {fe}")

            if not metadata_stored:
                for media_path in media_paths:
                    try:
                        if media_path.exists():
                            media_path.unlink()
                    except Exception as me:
                        logger.warning(f"清理多媒体文件失败 {media_path}: {me}")

            raise

    async def list_documents(
        self,
        offset: int = 0,
        limit: int = 100,
        search: str | None = None,
        status: str | None = None,
        source_type: str | None = None,
    ) -> list[KBDocument]:
        """列出知识库的所有文档"""
        docs = await self.kb_db.list_documents_by_kb(
            self.kb.kb_id,
            offset,
            limit,
            search,
            status=status,
            source_type=source_type,
        )
        return docs

    async def count_documents(
        self,
        search: str | None = None,
        status: str | None = None,
        source_type: str | None = None,
    ) -> int:
        """统计知识库的所有文档数量"""
        return await self.kb_db.count_documents_by_kb(
            self.kb.kb_id,
            search,
            status=status,
            source_type=source_type,
        )

    async def get_document(self, doc_id: str) -> KBDocument | None:
        """获取单个文档"""
        doc = await self.kb_db.get_document_by_id(doc_id)
        if doc and doc.kb_id != self.kb.kb_id:
            return None
        return doc

    async def delete_document(self, doc_id: str) -> None:
        """删除单个文档及其相关数据"""
        doc = await self.get_document(doc_id)
        if not doc:
            raise ValueError(f"无法找到 ID 为 {doc_id} 的文档")
        media_items = await self.kb_db.list_media_by_doc(doc_id)
        deleted = await self.kb_db.delete_document_by_id(
            doc_id=doc_id,
            vec_db=self.vec_db,  # type: ignore
            kb_id=self.kb.kb_id,
        )
        if not deleted:
            raise ValueError(f"无法找到 ID 为 {doc_id} 的文档")
        self._cleanup_document_files(doc, media_items)
        await self.kb_db.update_kb_stats(
            kb_id=self.kb.kb_id,
            vec_db=self.vec_db,  # type: ignore
        )
        await self.refresh_kb()

    async def delete_documents(self, doc_ids: list[str]) -> dict[str, bool]:
        """批量删除文档，单次更新统计。

        vec_db 删除失败不阻塞其他文档（best-effort）。
        """
        docs_by_id = {
            doc_id: doc
            for doc_id in dict.fromkeys(doc_ids)
            if (doc := await self.get_document(doc_id)) is not None
        }
        media_by_doc_id = {
            doc_id: await self.kb_db.list_media_by_doc(doc_id) for doc_id in docs_by_id
        }
        results = await self.kb_db.delete_documents_by_ids(
            doc_ids=doc_ids,
            vec_db=self.vec_db,  # type: ignore
            kb_id=self.kb.kb_id,
        )
        for doc_id, deleted in results.items():
            if deleted and doc_id in docs_by_id:
                self._cleanup_document_files(
                    docs_by_id[doc_id],
                    media_by_doc_id.get(doc_id, []),
                )
        await self.kb_db.update_kb_stats(
            kb_id=self.kb.kb_id,
            vec_db=self.vec_db,  # type: ignore
        )
        await self.refresh_kb()
        return results

    async def rebuild_document(
        self,
        doc_id: str,
        *,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        batch_size: int = DEFAULT_UPLOAD_BATCH_SIZE,
        tasks_limit: int = DEFAULT_UPLOAD_TASKS_LIMIT,
        max_retries: int = DEFAULT_UPLOAD_MAX_RETRIES,
        progress_callback=None,
    ) -> KBDocument:
        doc = await self.get_document(doc_id)
        if not doc:
            raise ValueError(f"无法找到 ID 为 {doc_id} 的文档")
        next_version = (doc.version or 1) + 1
        parent_doc_id = doc.parent_doc_id or doc.doc_id
        effective_chunk_size = (
            chunk_size
            if chunk_size is not None
            else self.kb.chunk_size or DEFAULT_CHUNK_SIZE
        )
        effective_chunk_overlap = (
            chunk_overlap
            if chunk_overlap is not None
            else self.kb.chunk_overlap or DEFAULT_CHUNK_OVERLAP
        )

        if doc.source_type == "file" and doc.file_path:
            source_path = Path(doc.file_path).resolve(strict=False)
            files_root = self.kb_files_dir.resolve(strict=False)
            if not source_path.is_relative_to(files_root) or not source_path.exists():
                raise ValueError("无法找到可用于重建的原始文件")

            rebuilt_doc = await self.upload_document(
                file_name=doc.doc_name,
                file_content=source_path.read_bytes(),
                file_type=doc.file_type,
                chunk_size=effective_chunk_size,
                chunk_overlap=effective_chunk_overlap,
                batch_size=batch_size,
                tasks_limit=tasks_limit,
                max_retries=max_retries,
                progress_callback=progress_callback,
                source_type=doc.source_type,
                source_uri=doc.source_uri or doc.doc_name,
                parent_doc_id=parent_doc_id,
                document_version=next_version,
                skip_duplicate_check=True,
            )
        elif doc.source_type == "url":
            if not doc.source_uri:
                raise ValueError("无法找到可用于重建的 URL 来源")
            rebuilt_doc = await self.upload_from_url(
                url=doc.source_uri,
                chunk_size=effective_chunk_size,
                chunk_overlap=effective_chunk_overlap,
                batch_size=batch_size,
                tasks_limit=tasks_limit,
                max_retries=max_retries,
                progress_callback=progress_callback,
                parent_doc_id=parent_doc_id,
                document_version=next_version,
                skip_duplicate_check=True,
            )
        elif doc.source_type == "import":
            imported_chunks = await self._get_import_rebuild_chunks(doc.doc_id)
            if not imported_chunks:
                raise ValueError("无法找到可用于重建的导入文本块")
            rebuilt_doc = await self.upload_document(
                file_name=doc.doc_name,
                file_content=None,
                file_type=doc.file_type,
                chunk_size=effective_chunk_size,
                chunk_overlap=effective_chunk_overlap,
                batch_size=batch_size,
                tasks_limit=tasks_limit,
                max_retries=max_retries,
                progress_callback=progress_callback,
                pre_chunked_text=imported_chunks,
                source_type="import",
                source_uri=doc.source_uri or doc.doc_name,
                source_content_hash=build_content_hash(imported_chunks),
                source_chunker_name=doc.chunker_name or "pre_chunked",
                parent_doc_id=parent_doc_id,
                document_version=next_version,
                skip_duplicate_check=True,
            )
        else:
            raise ValueError("当前仅支持重建已保存原始文件、URL 或导入来源的文档")

        try:
            await self.delete_document(doc_id)
        except Exception as exc:
            try:
                await self.delete_document(rebuilt_doc.doc_id)
            except Exception as cleanup_exc:
                logger.error(
                    f"重建文档 {doc_id} 后清理新版本失败: {cleanup_exc}",
                )
            raise KnowledgeBaseUploadError(
                stage="rebuild",
                user_message=(
                    "重建失败：新版本已生成，但替换旧文档时失败，已尝试回滚新版本。"
                ),
                details={
                    "doc_id": doc_id,
                    "new_doc_id": rebuilt_doc.doc_id,
                },
            ) from exc
        return rebuilt_doc

    async def _get_import_rebuild_chunks(self, doc_id: str) -> list[str]:
        chunks: list[dict] = []
        offset = 0
        while True:
            page = await self.get_chunks_by_doc_id(
                doc_id,
                offset=offset,
                limit=DOCUMENT_REBUILD_PAGE_SIZE,
            )
            if not page:
                break
            chunks.extend(page)
            if len(page) < DOCUMENT_REBUILD_PAGE_SIZE:
                break
            offset += DOCUMENT_REBUILD_PAGE_SIZE

        chunks.sort(key=lambda chunk: int(chunk.get("chunk_index") or 0))
        return [
            chunk["content"]
            for chunk in chunks
            if isinstance(chunk.get("content"), str) and chunk["content"].strip()
        ]

    async def rebuild_all_documents(
        self,
        *,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        batch_size: int = DEFAULT_UPLOAD_BATCH_SIZE,
        tasks_limit: int = DEFAULT_UPLOAD_TASKS_LIMIT,
        max_retries: int = DEFAULT_UPLOAD_MAX_RETRIES,
        progress_callback=None,
    ) -> dict:
        docs: list[KBDocument] = []
        offset = 0
        while True:
            page = await self.list_documents(
                offset=offset,
                limit=DOCUMENT_REBUILD_PAGE_SIZE,
            )
            docs.extend(page)
            if len(page) < DOCUMENT_REBUILD_PAGE_SIZE:
                break
            offset += DOCUMENT_REBUILD_PAGE_SIZE

        rebuilt_docs = []
        failed_docs = []

        total = len(docs)
        for index, doc in enumerate(docs, start=1):
            if progress_callback:
                await progress_callback("rebuilding", index - 1, total)
            try:
                rebuilt = await self.rebuild_document(
                    doc.doc_id,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                    batch_size=batch_size,
                    tasks_limit=tasks_limit,
                    max_retries=max_retries,
                    progress_callback=progress_callback,
                )
                rebuilt_docs.append(rebuilt.model_dump())
            except Exception as e:
                logger.error(f"重建文档 {doc.doc_id} 失败: {e}")
                failed_docs.append(
                    {
                        "doc_id": doc.doc_id,
                        "doc_name": doc.doc_name,
                        "error": str(e),
                    },
                )

        if progress_callback:
            await progress_callback("rebuilding", total, total)

        return {
            "rebuilt": rebuilt_docs,
            "failed": failed_docs,
            "total": total,
            "success_count": len(rebuilt_docs),
            "failed_count": len(failed_docs),
        }

    async def rebuild_documents(
        self,
        doc_ids: list[str],
        *,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        batch_size: int = DEFAULT_UPLOAD_BATCH_SIZE,
        tasks_limit: int = DEFAULT_UPLOAD_TASKS_LIMIT,
        max_retries: int = DEFAULT_UPLOAD_MAX_RETRIES,
        progress_callback=None,
    ) -> dict:
        rebuilt_docs = []
        failed_docs = []
        normalized_doc_ids = list(dict.fromkeys(doc_ids))

        total = len(normalized_doc_ids)
        for index, doc_id in enumerate(normalized_doc_ids, start=1):
            if progress_callback:
                await progress_callback("rebuilding", index - 1, total)
            try:
                rebuilt = await self.rebuild_document(
                    doc_id,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                    batch_size=batch_size,
                    tasks_limit=tasks_limit,
                    max_retries=max_retries,
                    progress_callback=progress_callback,
                )
                rebuilt_docs.append(rebuilt.model_dump())
            except Exception as e:
                logger.error(f"重建文档 {doc_id} 失败: {e}")
                failed_doc = await self.get_document(doc_id)
                failed_docs.append(
                    {
                        "doc_id": doc_id,
                        "doc_name": failed_doc.doc_name if failed_doc else doc_id,
                        "error": str(e),
                    },
                )

        if progress_callback:
            await progress_callback("rebuilding", total, total)

        return {
            "rebuilt": rebuilt_docs,
            "failed": failed_docs,
            "total": total,
            "success_count": len(rebuilt_docs),
            "failed_count": len(failed_docs),
        }

    def _cleanup_document_files(
        self,
        doc: KBDocument,
        media_items: list[KBMedia],
    ) -> None:
        file_paths: list[Path] = []
        if doc.file_path:
            file_paths.append(Path(doc.file_path))
        file_paths.extend(Path(media.file_path) for media in media_items)

        cleanup_roots = (
            self.kb_files_dir.resolve(strict=False),
            self.kb_medias_dir.resolve(strict=False),
        )
        for file_path in file_paths:
            resolved_path = file_path.resolve(strict=False)
            if not any(resolved_path.is_relative_to(root) for root in cleanup_roots):
                logger.warning(
                    f"跳过清理知识库目录外文件: {resolved_path}",
                )
                continue
            try:
                if resolved_path.exists():
                    resolved_path.unlink()
                    parent = resolved_path.parent
                    if any(parent.is_relative_to(root) for root in cleanup_roots):
                        try:
                            parent.rmdir()
                        except OSError:
                            pass
            except Exception as e:
                logger.warning(f"清理知识库文件失败 {resolved_path}: {e}")

    async def delete_chunk(self, chunk_id: str, doc_id: str) -> None:
        """删除单个文本块及其相关数据"""
        vec_db: FaissVecDB = self.vec_db  # type: ignore
        deleted = await vec_db.delete(chunk_id)
        if not deleted:
            raise ValueError(f"无法找到 ID 为 {chunk_id} 的文本块")
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
        return [self._format_chunk_response(chunk) for chunk in chunks]

    async def search_chunks_by_doc_id(
        self,
        doc_id: str,
        search: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[dict], int]:
        """Search or list chunks for one document with a matching total."""
        if not search:
            chunks = await self.get_chunks_by_doc_id(
                doc_id=doc_id,
                offset=offset,
                limit=limit,
            )
            return chunks, await self.get_chunk_count_by_doc_id(doc_id)

        vec_db: FaissVecDB = self.vec_db  # type: ignore
        search_documents = getattr(vec_db.document_storage, "search_documents", None)
        if search_documents is None:
            return [], 0

        result = await search_documents(
            search,
            metadata_filters={"kb_doc_id": doc_id},
            offset=offset,
            limit=limit,
        )
        if result is None:
            return [], 0
        chunks, total = result
        return [self._format_chunk_response(chunk) for chunk in chunks], total

    @staticmethod
    def _format_chunk_response(chunk: dict) -> dict:
        chunk_md = json.loads(chunk["metadata"])
        char_count = chunk_md.get("char_count", len(chunk["text"]))
        return {
            "chunk_id": chunk["doc_id"],
            "doc_id": chunk_md["kb_doc_id"],
            "kb_id": chunk_md["kb_id"],
            "chunk_index": chunk_md["chunk_index"],
            "section_index": chunk_md.get("section_index"),
            "content": chunk["text"],
            "char_count": char_count,
            "token_count_estimate": chunk_md.get("token_count_estimate"),
            "content_hash": chunk_md.get("content_hash"),
            "start_offset": chunk_md.get("start_offset"),
            "end_offset": chunk_md.get("end_offset"),
            "previous_chunk_id": chunk_md.get("previous_chunk_id"),
            "next_chunk_id": chunk_md.get("next_chunk_id"),
            "title_path": chunk_md.get("title_path"),
            "page_number": chunk_md.get("page_number"),
            "parent_chunk_id": chunk_md.get("parent_chunk_id"),
        }

    async def get_chunk_by_id(
        self,
        chunk_id: str,
        doc_id: str | None = None,
    ) -> dict | None:
        """获取单个文本块及其元数据"""
        vec_db: FaissVecDB = self.vec_db  # type: ignore
        chunk = await vec_db.document_storage.get_document_by_doc_id(chunk_id)
        if not chunk:
            return None
        formatted_chunk = self._format_chunk_response(chunk)
        if doc_id and formatted_chunk["doc_id"] != doc_id:
            return None
        return formatted_chunk

    async def get_chunk_context(self, chunk_id: str, doc_id: str) -> dict:
        """获取文本块和相邻上下文块"""
        current = await self.get_chunk_by_id(chunk_id, doc_id)
        if not current:
            raise ValueError(f"无法找到 ID 为 {chunk_id} 的文本块")

        previous_chunk = None
        next_chunk = None
        if current.get("previous_chunk_id"):
            previous_chunk = await self.get_chunk_by_id(
                current["previous_chunk_id"],
                doc_id,
            )
        if current.get("next_chunk_id"):
            next_chunk = await self.get_chunk_by_id(
                current["next_chunk_id"],
                doc_id,
            )

        return {
            "previous": previous_chunk,
            "current": current,
            "next": next_chunk,
        }

    async def get_chunk_count_by_doc_id(self, doc_id: str) -> int:
        """获取文档的块数量"""
        vec_db: FaissVecDB = self.vec_db  # type: ignore
        count = await vec_db.count_documents(metadata_filter={"kb_doc_id": doc_id})
        return count

    async def check_consistency(self) -> dict:
        """Return a read-only consistency report for document metadata and chunks."""
        docs = await self._list_all_documents_for_consistency()
        doc_by_id = {doc.doc_id: doc for doc in docs}
        stored_chunks = await self._list_all_chunks_for_consistency()

        chunks_by_doc_id: dict[str, list[dict]] = {}
        orphan_vectors: list[dict] = []
        invalid_vector_metadata: list[dict] = []

        for chunk in stored_chunks:
            try:
                metadata = self._parse_stored_chunk_metadata(chunk)
            except ValueError as exc:
                invalid_vector_metadata.append(
                    self._format_vector_issue(chunk, metadata_error=str(exc)),
                )
                continue

            doc_id = metadata.get("kb_doc_id")
            if not isinstance(doc_id, str) or not doc_id:
                invalid_vector_metadata.append(
                    self._format_vector_issue(
                        chunk,
                        metadata=metadata,
                        metadata_error="missing kb_doc_id",
                    ),
                )
                continue

            if doc_id not in doc_by_id:
                orphan_vectors.append(
                    self._format_vector_issue(chunk, metadata=metadata),
                )
                continue

            chunks_by_doc_id.setdefault(doc_id, []).append(chunk)

        missing_vectors: list[dict] = []
        chunk_count_mismatches: list[dict] = []
        for doc in docs:
            expected_chunk_count = int(doc.chunk_count or 0)
            actual_chunk_count = len(chunks_by_doc_id.get(doc.doc_id, []))
            if expected_chunk_count > 0 and actual_chunk_count == 0:
                missing_vectors.append(
                    self._format_document_issue(
                        doc,
                        expected_chunk_count=expected_chunk_count,
                        actual_chunk_count=actual_chunk_count,
                    ),
                )
            if expected_chunk_count != actual_chunk_count:
                chunk_count_mismatches.append(
                    self._format_document_issue(
                        doc,
                        expected_chunk_count=expected_chunk_count,
                        actual_chunk_count=actual_chunk_count,
                    ),
                )

        missing_source_files, unsafe_source_paths, source_file_count = (
            self._check_source_file_consistency(docs)
        )

        status_counts: dict[str, int] = {}
        for doc in docs:
            status = doc.status or "unknown"
            status_counts[status] = status_counts.get(status, 0) + 1

        issues = {
            "missing_vectors": missing_vectors,
            "orphan_vectors": orphan_vectors,
            "missing_source_files": missing_source_files,
            "chunk_count_mismatches": chunk_count_mismatches,
            "invalid_vector_metadata": invalid_vector_metadata,
            "unsafe_source_paths": unsafe_source_paths,
        }
        issue_counts = {name: len(items) for name, items in issues.items()}

        return {
            "kb_id": self.kb.kb_id,
            "kb_name": self.kb.kb_name,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "sqlite_document_count": len(docs),
                "ready_document_count": status_counts.get("ready", 0),
                "failed_document_count": status_counts.get("failed", 0),
                "document_chunk_count": sum(int(doc.chunk_count or 0) for doc in docs),
                "indexed_chunk_count": len(stored_chunks),
                "source_file_count": source_file_count,
                "status_counts": status_counts,
                **issue_counts,
                "healthy": all(count == 0 for count in issue_counts.values()),
            },
            "issues": issues,
        }

    async def repair_consistency(
        self,
        repair_types: list[str] | None = None,
    ) -> dict:
        """Repair low-risk consistency issues and report skipped unsafe issues."""
        selected_repair_types = self._normalize_consistency_repair_types(repair_types)
        pre_check = await self.check_consistency()

        repaired: list[dict] = []
        skipped: list[dict] = []
        failed: list[dict] = []

        if "orphan_vectors" in selected_repair_types:
            orphan_vectors = pre_check["issues"].get("orphan_vectors", [])
            orphan_doc_ids = sorted(
                {
                    issue.get("doc_id")
                    for issue in orphan_vectors
                    if isinstance(issue.get("doc_id"), str) and issue.get("doc_id")
                },
            )
            for doc_id in orphan_doc_ids:
                issue_count = sum(
                    1 for issue in orphan_vectors if issue.get("doc_id") == doc_id
                )
                try:
                    await self.vec_db.delete_documents(  # type: ignore[attr-defined]
                        metadata_filters={
                            "kb_id": self.kb.kb_id,
                            "kb_doc_id": doc_id,
                        },
                    )
                    repaired.append(
                        {
                            "type": "orphan_vectors",
                            "doc_id": doc_id,
                            "count": issue_count,
                            "action": "deleted_vectors",
                        },
                    )
                except Exception as exc:
                    failed.append(
                        {
                            "type": "orphan_vectors",
                            "doc_id": doc_id,
                            "count": issue_count,
                            "action": "delete_vectors",
                            "error": str(exc),
                        },
                    )

        if "chunk_count_mismatches" in selected_repair_types:
            for issue in pre_check["issues"].get("chunk_count_mismatches", []):
                doc_id = issue.get("doc_id")
                expected_count = int(issue.get("expected_chunk_count") or 0)
                actual_count = int(issue.get("actual_chunk_count") or 0)
                if not isinstance(doc_id, str) or not doc_id:
                    skipped.append(
                        {
                            "type": "chunk_count_mismatches",
                            "reason": "missing_doc_id",
                            "issue": issue,
                        },
                    )
                    continue

                if expected_count > actual_count:
                    skipped.append(
                        {
                            "type": "chunk_count_mismatches",
                            "doc_id": doc_id,
                            "reason": "missing_vectors_require_rebuild",
                            "expected_chunk_count": expected_count,
                            "actual_chunk_count": actual_count,
                        },
                    )
                    continue

                try:
                    await self.refresh_document(doc_id)
                    repaired.append(
                        {
                            "type": "chunk_count_mismatches",
                            "doc_id": doc_id,
                            "action": "refreshed_document_chunk_count",
                            "expected_chunk_count": expected_count,
                            "actual_chunk_count": actual_count,
                        },
                    )
                except Exception as exc:
                    failed.append(
                        {
                            "type": "chunk_count_mismatches",
                            "doc_id": doc_id,
                            "action": "refresh_document",
                            "expected_chunk_count": expected_count,
                            "actual_chunk_count": actual_count,
                            "error": str(exc),
                        },
                    )

        for issue_type in (
            "missing_vectors",
            "missing_source_files",
            "invalid_vector_metadata",
            "unsafe_source_paths",
        ):
            for issue in pre_check["issues"].get(issue_type, []):
                skipped.append(
                    {
                        "type": issue_type,
                        "doc_id": issue.get("doc_id"),
                        "chunk_id": issue.get("chunk_id"),
                        "reason": self._get_consistency_repair_skip_reason(
                            issue_type,
                        ),
                        "issue": issue,
                    },
                )

        if repaired or failed:
            await self.kb_db.update_kb_stats(
                kb_id=self.kb.kb_id,
                vec_db=self.vec_db,  # type: ignore
            )
            await self.refresh_kb()

        post_check = await self.check_consistency()
        return {
            "kb_id": self.kb.kb_id,
            "kb_name": self.kb.kb_name,
            "repaired_at": datetime.now(timezone.utc).isoformat(),
            "repair_types": selected_repair_types,
            "summary": {
                "repaired_count": len(repaired),
                "skipped_count": len(skipped),
                "failed_count": len(failed),
                "healthy_after_repair": post_check["summary"]["healthy"],
            },
            "actions": {
                "repaired": repaired,
                "skipped": skipped,
                "failed": failed,
            },
            "pre_check": pre_check,
            "post_check": post_check,
        }

    @staticmethod
    def _normalize_consistency_repair_types(
        repair_types: list[str] | None,
    ) -> list[str]:
        if repair_types is None:
            return sorted(CONSISTENCY_REPAIR_TYPES)

        normalized = list(
            dict.fromkeys(
                repair_type.strip()
                for repair_type in repair_types
                if isinstance(repair_type, str) and repair_type.strip()
            ),
        )
        invalid_types = sorted(set(normalized) - CONSISTENCY_REPAIR_TYPES)
        if invalid_types:
            raise ValueError(
                f"不支持的一致性修复类型: {', '.join(invalid_types)}",
            )
        return normalized

    @staticmethod
    def _get_consistency_repair_skip_reason(issue_type: str) -> str:
        skip_reasons = {
            "missing_vectors": "document_rebuild_required",
            "missing_source_files": "source_file_missing_manual_action_required",
            "invalid_vector_metadata": "invalid_metadata_manual_action_required",
            "unsafe_source_paths": "unsafe_source_path_manual_action_required",
        }
        return skip_reasons.get(issue_type, "manual_action_required")

    async def _list_all_documents_for_consistency(self) -> list[KBDocument]:
        return await self._collect_paginated_documents(
            page_size=CONSISTENCY_CHECK_PAGE_SIZE,
        )

    async def _list_all_chunks_for_consistency(self) -> list[dict]:
        return await self._collect_paginated_vector_documents(
            page_size=CONSISTENCY_CHECK_PAGE_SIZE,
            unsupported_message="当前知识库存储后端不支持一致性检查",
        )

    @staticmethod
    def _parse_stored_chunk_metadata(chunk: dict) -> dict:
        raw_metadata = chunk.get("metadata")
        if raw_metadata is None:
            return {}
        if isinstance(raw_metadata, dict):
            return raw_metadata
        try:
            metadata = json.loads(raw_metadata)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid metadata JSON") from exc
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be a JSON object")
        return metadata

    @staticmethod
    def _format_vector_issue(
        chunk: dict,
        *,
        metadata: dict | None = None,
        metadata_error: str | None = None,
    ) -> dict:
        issue = {
            "chunk_id": chunk.get("doc_id"),
            "storage_id": chunk.get("id"),
        }
        if metadata:
            issue.update(
                {
                    "doc_id": metadata.get("kb_doc_id"),
                    "kb_id": metadata.get("kb_id"),
                    "chunk_index": metadata.get("chunk_index"),
                },
            )
        if metadata_error:
            issue["metadata_error"] = metadata_error
        return issue

    @staticmethod
    def _format_document_issue(
        doc: KBDocument,
        *,
        expected_chunk_count: int | None = None,
        actual_chunk_count: int | None = None,
        reason: str | None = None,
    ) -> dict:
        issue = {
            "doc_id": doc.doc_id,
            "doc_name": doc.doc_name,
            "status": doc.status,
            "source_type": doc.source_type,
            "file_path": doc.file_path,
        }
        if expected_chunk_count is not None:
            issue["expected_chunk_count"] = expected_chunk_count
        if actual_chunk_count is not None:
            issue["actual_chunk_count"] = actual_chunk_count
        if reason:
            issue["reason"] = reason
        return issue

    def _check_source_file_consistency(
        self,
        docs: list[KBDocument],
    ) -> tuple[list[dict], list[dict], int]:
        missing_source_files: list[dict] = []
        unsafe_source_paths: list[dict] = []
        source_file_count = 0
        files_root = self.kb_files_dir.resolve(strict=False)

        for doc in docs:
            if doc.source_type != "file":
                continue

            if not doc.file_path:
                if doc.status == "ready":
                    missing_source_files.append(
                        self._format_document_issue(doc, reason="empty_file_path"),
                    )
                continue

            file_path = Path(doc.file_path).resolve(strict=False)
            if not file_path.is_relative_to(files_root):
                unsafe_source_paths.append(
                    self._format_document_issue(
                        doc,
                        reason="outside_kb_files_dir",
                    ),
                )
                continue
            if file_path.exists():
                source_file_count += 1
            else:
                missing_source_files.append(
                    self._format_document_issue(doc, reason="not_found"),
                )

        return missing_source_files, unsafe_source_paths, source_file_count

    async def _collect_paginated_documents(self, *, page_size: int) -> list[KBDocument]:
        docs: list[KBDocument] = []
        offset = 0
        while True:
            page = await self.list_documents(
                offset=offset,
                limit=page_size,
            )
            docs.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        return docs

    async def _collect_paginated_vector_documents(
        self,
        *,
        page_size: int,
        unsupported_message: str,
    ) -> list[dict]:
        document_storage = getattr(self.vec_db, "document_storage", None)
        get_documents = getattr(document_storage, "get_documents", None)
        if get_documents is None:
            raise ValueError(unsupported_message)

        chunks: list[dict] = []
        offset = 0
        while True:
            page_result = get_documents(
                metadata_filters={"kb_id": self.kb.kb_id},
                offset=offset,
                limit=page_size,
            )
            if not hasattr(page_result, "__await__"):
                raise ValueError(unsupported_message)
            page = await page_result
            chunks.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        return chunks

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
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
        batch_size: int = DEFAULT_UPLOAD_BATCH_SIZE,
        tasks_limit: int = DEFAULT_UPLOAD_TASKS_LIMIT,
        max_retries: int = DEFAULT_UPLOAD_MAX_RETRIES,
        progress_callback=None,
        enable_cleaning: bool = False,
        cleaning_provider_id: str | None = None,
        parent_doc_id: str | None = None,
        document_version: int = 1,
        skip_duplicate_check: bool = False,
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
        text_content: str | None = None
        try:
            # 获取 Tavily API 密钥
            config = self.prov_mgr.acm.default_conf
            tavily_keys = config.get("provider_settings", {}).get(
                "websearch_tavily_key", []
            )
            if not tavily_keys:
                raise KnowledgeBaseUploadError(
                    stage="configuration",
                    user_message=(
                        "URL 导入失败：Tavily API key 未配置。"
                        "请先在 provider_settings 中配置 websearch_tavily_key。"
                    ),
                    details={"url": url},
                )

            # 阶段1: 从 URL 提取内容
            if progress_callback:
                await progress_callback("extracting", 0, 100)

            try:
                text_content = await extract_text_from_url(url, tavily_keys)
            except KnowledgeBaseUploadError:
                raise
            except Exception as e:
                logger.error(f"Failed to extract content from URL {url}: {e}")
                raise KnowledgeBaseUploadError(
                    stage="extracting",
                    user_message=(
                        "URL 导入失败：无法提取网页内容。"
                        "请确认 URL 可访问且 Tavily 配置有效。"
                    ),
                    details={"url": url},
                ) from e

            if not text_content or not text_content.strip():
                raise KnowledgeBaseUploadError(
                    stage="extracting",
                    user_message=(
                        "URL 导入失败：未能从网页中提取可索引文本。"
                        "请确认页面存在正文内容，或尝试更换 URL。"
                    ),
                    details={"url": url},
                )

            if progress_callback:
                await progress_callback("extracting", 100, 100)

            # 阶段2: (可选)清洗内容并分块
            try:
                final_chunks = await self._clean_and_rechunk_content(
                    content=text_content,
                    url=url,
                    progress_callback=progress_callback,
                    enable_cleaning=enable_cleaning,
                    cleaning_provider_id=cleaning_provider_id,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )
            except KnowledgeBaseUploadError:
                raise
            except Exception as e:
                stage = "cleaning" if enable_cleaning else "chunking"
                raise KnowledgeBaseUploadError(
                    stage=stage,
                    user_message=(
                        "URL 导入失败：网页内容切分失败。"
                        "请稍后重试，或调整分块参数后再次导入。"
                    ),
                    details={"url": url},
                ) from e

            if enable_cleaning and not final_chunks:
                raise KnowledgeBaseUploadError(
                    stage="cleaning",
                    user_message=(
                        "URL 导入失败：内容清洗后未提取到有效文本。"
                        "请尝试关闭内容清洗功能，或更换更高性能的 LLM 模型后重试。"
                    ),
                    details={"url": url},
                )
        except Exception as e:
            await self._persist_failed_url_document(
                url=url,
                text_content=text_content,
                parent_doc_id=parent_doc_id,
                document_version=document_version,
                error=e,
            )
            raise

        # 创建一个虚拟文件名
        file_name = self._build_url_file_name(url)

        # 复用现有的 upload_document 方法，但传入预分块文本
        return await self.upload_document(
            file_name=file_name,
            file_content=None,
            file_type="url",  # 使用 'url' 作为特殊文件类型
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            batch_size=batch_size,
            tasks_limit=tasks_limit,
            max_retries=max_retries,
            progress_callback=progress_callback,
            pre_chunked_text=final_chunks,
            source_type="url",
            source_uri=url,
            source_content_hash=build_content_hash(text_content),
            source_parser_name=URLExtractor.__name__,
            source_chunker_name=get_chunker_name(self.chunker),
            parent_doc_id=parent_doc_id,
            document_version=document_version,
            skip_duplicate_check=skip_duplicate_check,
        )

    async def _clean_and_rechunk_content(
        self,
        content: str,
        url: str,
        progress_callback=None,
        enable_cleaning: bool = False,
        cleaning_provider_id: str | None = None,
        repair_max_rpm: int = 60,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> list[str]:
        """
        对从 URL 获取的内容进行清洗、修复、翻译和重新分块。
        """
        if not enable_cleaning:
            # 如果不启用清洗，则使用从前端传递的参数进行分块
            logger.info(
                f"内容清洗未启用，使用指定参数进行分块: chunk_size={chunk_size}, chunk_overlap={chunk_overlap}"
            )
            return await self.chunker.chunk(
                content, chunk_size=chunk_size, chunk_overlap=chunk_overlap
            )

        if not cleaning_provider_id:
            logger.warning(
                "启用了内容清洗，但未提供 cleaning_provider_id，跳过清洗并使用默认分块。"
            )
            return await self.chunker.chunk(content)

        if progress_callback:
            await progress_callback("cleaning", 0, 100)

        try:
            # 获取指定的 LLM Provider
            llm_provider = await self.prov_mgr.get_provider_by_id(cleaning_provider_id)
            if not llm_provider or not isinstance(llm_provider, LLMProvider):
                raise ValueError(
                    f"无法找到 ID 为 {cleaning_provider_id} 的 LLM Provider 或类型不正确"
                )

            # 初步分块
            # 优化分隔符，优先按段落分割，以获得更高质量的文本块
            text_splitter = RecursiveCharacterChunker(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                separators=["\n\n", "\n", " "],  # 优先使用段落分隔符
            )
            initial_chunks = await text_splitter.chunk(content)
            logger.info(f"初步分块完成，生成 {len(initial_chunks)} 个块用于修复。")

            # 并发处理所有块
            rate_limiter = RateLimiter(repair_max_rpm)
            tasks = [
                _repair_and_translate_chunk_with_retry(
                    chunk, llm_provider, rate_limiter
                )
                for chunk in initial_chunks
            ]

            repaired_results = await asyncio.gather(*tasks, return_exceptions=True)

            final_chunks = []
            for i, result in enumerate(repaired_results):
                if isinstance(result, Exception):
                    logger.warning(f"块 {i} 处理异常: {str(result)}. 回退到原始块。")
                    final_chunks.append(initial_chunks[i])
                elif isinstance(result, list):
                    final_chunks.extend(result)

            final_chunks = _compact_chunks(final_chunks)

            logger.info(
                f"文本修复完成: {len(initial_chunks)} 个原始块 -> {len(final_chunks)} 个最终块。"
            )

            if progress_callback:
                await progress_callback("cleaning", 100, 100)

            return final_chunks

        except Exception as e:
            logger.error(f"使用 Provider '{cleaning_provider_id}' 清洗内容失败: {e}")
            # 清洗失败，返回默认分块结果，保证流程不中断
            return await self.chunker.chunk(content)
