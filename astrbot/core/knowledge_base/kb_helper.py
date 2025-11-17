import asyncio
import json
import re
import time
import uuid
from pathlib import Path

import aiofiles

from astrbot.core import logger
from astrbot.core.db.vec_db.base import BaseVecDB
from astrbot.core.db.vec_db.faiss_impl.vec_db import FaissVecDB
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.provider.provider import (
    EmbeddingProvider,
    RerankProvider,
)
from astrbot.core.provider.provider import (
    Provider as LLMProvider,
)

from .chunking.base import BaseChunker
from .chunking.recursive import RecursiveCharacterChunker
from .kb_db_sqlite import KBSQLiteDatabase
from .models import KBDocument, KBMedia, KnowledgeBase
from .parsers.url_parser import extract_text_from_url
from .parsers.util import select_parser
from .prompts import TEXT_REPAIR_SYSTEM_PROMPT


class RateLimiter:
    """一个简单的速率限制器"""

    def __init__(self, max_rpm: int):
        self.max_per_minute = max_rpm
        self.interval = 60.0 / max_rpm if max_rpm > 0 else 0
        self.last_call_time = 0

    async def __aenter__(self):
        if self.interval == 0:
            return

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


class KBHelper:
    vec_db: BaseVecDB
    kb: KnowledgeBase

    def __init__(
        self,
        kb_db: KBSQLiteDatabase,
        kb: KnowledgeBase,
        provider_manager: ProviderManager,
        kb_root_dir: str,
        chunker: BaseChunker,
    ):
        self.kb_db = kb_db
        self.kb = kb
        self.prov_mgr = provider_manager
        self.kb_root_dir = kb_root_dir
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
        rp: RerankProvider = await self.prov_mgr.get_provider_by_id(
            self.kb.rerank_provider_id,
        )  # type: ignore
        if not rp:
            raise ValueError(
                f"无法找到 ID 为 {self.kb.rerank_provider_id} 的 Rerank Provider",
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
        """删除知识库的向量数据库和所有相关文件"""
        import shutil

        await self.terminate()
        if self.kb_dir.exists():
            shutil.rmtree(self.kb_dir)

    async def terminate(self):
        if self.vec_db:
            await self.vec_db.close()

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
        file_size = 0

        # file_path = self.kb_files_dir / f"{doc_id}.{file_type}"
        # async with aiofiles.open(file_path, "wb") as f:
        #     await f.write(file_content)

        try:
            chunks_text = []
            saved_media = []

            if pre_chunked_text is not None:
                # 如果提供了预分块文本，直接使用
                chunks_text = pre_chunked_text
                file_size = sum(len(chunk) for chunk in chunks_text)
                logger.info(f"使用预分块文本进行上传，共 {len(chunks_text)} 个块。")
            else:
                # 否则，执行标准的文件解析和分块流程
                if file_content is None:
                    raise ValueError(
                        "当未提供 pre_chunked_text 时，file_content 不能为空。"
                    )

                file_size = len(file_content)

                # 阶段1: 解析文档
                if progress_callback:
                    await progress_callback("parsing", 0, 100)

                parser = await select_parser(f".{file_type}")
                parse_result = await parser.parse(file_content, file_name)
                text_content = parse_result.text
                media_items = parse_result.media

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

                chunks_text = await self.chunker.chunk(
                    text_content,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )
            contents = []
            metadatas = []
            for idx, chunk_text in enumerate(chunks_text):
                contents.append(chunk_text)
                metadatas.append(
                    {
                        "kb_id": self.kb.kb_id,
                        "kb_doc_id": doc_id,
                        "chunk_index": idx,
                    },
                )

            if progress_callback:
                await progress_callback("chunking", 100, 100)

            # 阶段3: 生成向量（带进度回调）
            async def embedding_progress_callback(current, total):
                if progress_callback:
                    await progress_callback("embedding", current, total)

            await self.vec_db.insert_batch(
                contents=contents,
                metadatas=metadatas,
                batch_size=batch_size,
                tasks_limit=tasks_limit,
                max_retries=max_retries,
                progress_callback=embedding_progress_callback,
            )

            # 保存文档的元数据
            doc = KBDocument(
                doc_id=doc_id,
                kb_id=self.kb.kb_id,
                doc_name=file_name,
                file_type=file_type,
                file_size=file_size,
                # file_path=str(file_path),
                file_path="",
                chunk_count=len(chunks_text),
                media_count=0,
            )
            async with self.kb_db.get_db() as session:
                async with session.begin():
                    session.add(doc)
                    for media in saved_media:
                        session.add(media)
                    await session.commit()

                await session.refresh(doc)

            vec_db: FaissVecDB = self.vec_db  # type: ignore
            await self.kb_db.update_kb_stats(kb_id=self.kb.kb_id, vec_db=vec_db)
            await self.refresh_kb()
            await self.refresh_document(doc_id)
            return doc
        except Exception as e:
            logger.error(f"上传文档失败: {e}")
            # if file_path.exists():
            #     file_path.unlink()

            for media_path in media_paths:
                try:
                    if media_path.exists():
                        media_path.unlink()
                except Exception as me:
                    logger.warning(f"清理多媒体文件失败 {media_path}: {me}")

            raise e

    async def list_documents(
        self,
        offset: int = 0,
        limit: int = 100,
    ) -> list[KBDocument]:
        """列出知识库的所有文档"""
        docs = await self.kb_db.list_documents_by_kb(self.kb.kb_id, offset, limit)
        return docs

    async def get_document(self, doc_id: str) -> KBDocument | None:
        """获取单个文档"""
        doc = await self.kb_db.get_document_by_id(doc_id)
        return doc

    async def delete_document(self, doc_id: str):
        """删除单个文档及其相关数据"""
        await self.kb_db.delete_document_by_id(
            doc_id=doc_id,
            vec_db=self.vec_db,  # type: ignore
        )
        await self.kb_db.update_kb_stats(
            kb_id=self.kb.kb_id,
            vec_db=self.vec_db,  # type: ignore
        )
        await self.refresh_kb()

    async def delete_chunk(self, chunk_id: str, doc_id: str):
        """删除单个文本块及其相关数据"""
        vec_db: FaissVecDB = self.vec_db  # type: ignore
        await vec_db.delete(chunk_id)
        await self.kb_db.update_kb_stats(
            kb_id=self.kb.kb_id,
            vec_db=self.vec_db,  # type: ignore
        )
        await self.refresh_kb()
        await self.refresh_document(doc_id)

    async def refresh_kb(self):
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
        # 获取 Tavily API 密钥
        config = self.prov_mgr.acm.default_conf
        tavily_keys = config.get("provider_settings", {}).get(
            "websearch_tavily_key", []
        )
        if not tavily_keys:
            raise ValueError(
                "Error: Tavily API key is not configured in provider_settings."
            )

        # 阶段1: 从 URL 提取内容
        if progress_callback:
            await progress_callback("extracting", 0, 100)

        try:
            text_content = await extract_text_from_url(url, tavily_keys)
        except Exception as e:
            logger.error(f"Failed to extract content from URL {url}: {e}")
            raise OSError(f"Failed to extract content from URL {url}: {e}") from e

        if not text_content:
            raise ValueError(f"No content extracted from URL: {url}")

        if progress_callback:
            await progress_callback("extracting", 100, 100)

        # 阶段2: (可选)清洗内容并分块
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

        # 创建一个虚拟文件名
        file_name = url.split("/")[-1] or f"document_from_{url}"
        if not Path(file_name).suffix:
            file_name += ".url"

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
