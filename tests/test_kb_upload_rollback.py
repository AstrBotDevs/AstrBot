"""Tests for upload metadata persistence and failure rollback."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest


def _build_helper():
    from astrbot.core.knowledge_base.kb_helper import KBHelper
    from astrbot.core.knowledge_base.models import KnowledgeBase

    kb = KnowledgeBase(
        kb_name="test-kb",
        kb_id="kb-test-1",
        embedding_provider_id="emb-1",
        chunk_size=512,
        chunk_overlap=50,
    )
    helper = KBHelper.__new__(KBHelper)
    helper.kb = kb
    helper.kb_db = MagicMock()
    helper.kb_db.get_document_by_content_hash = AsyncMock(return_value=None)
    helper.kb_db.get_db.side_effect = RuntimeError("test db is not configured")
    helper.kb_dir = MagicMock()
    helper.kb_medias_dir = MagicMock()
    helper.kb_files_dir = MagicMock()
    helper.prov_mgr = MagicMock()
    helper.chunker = AsyncMock()
    helper.vec_db = AsyncMock()
    helper._ensure_vec_db = AsyncMock()
    helper.init_error = None
    return helper


def _build_helper_with_real_dirs(tmp_path):
    helper = _build_helper()
    helper.kb_files_dir = tmp_path / "files"
    helper.kb_medias_dir = tmp_path / "medias"
    helper.kb_files_dir.mkdir(parents=True)
    helper.kb_medias_dir.mkdir(parents=True)
    return helper


def _mock_parser(mock_select, text="hello world test content", text_segments=None):
    parser = AsyncMock()
    result = MagicMock()
    type(result).text = PropertyMock(return_value=text)
    type(result).media = PropertyMock(return_value=[])
    type(result).text_segments = PropertyMock(return_value=text_segments)
    parser.parse = AsyncMock(return_value=result)
    mock_select.return_value = parser


def _make_session_context():
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.begin = MagicMock(return_value=session)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _existing_doc():
    from astrbot.core.knowledge_base.models import KBDocument

    return KBDocument(
        doc_id="existing-doc",
        kb_id="kb-test-1",
        doc_name="existing.txt",
        file_type="txt",
        file_size=11,
        file_path="",
        content_hash="existing-hash",
        status="ready",
    )


def _chunk_doc(
    *,
    chunk_id: str,
    text: str,
    doc_id: str = "doc-1",
    index: int = 0,
    previous_chunk_id: str | None = None,
    next_chunk_id: str | None = None,
):
    import json

    return {
        "doc_id": chunk_id,
        "text": text,
        "metadata": json.dumps(
            {
                "kb_id": "kb-test-1",
                "kb_doc_id": doc_id,
                "chunk_index": index,
                "previous_chunk_id": previous_chunk_id,
                "next_chunk_id": next_chunk_id,
            },
        ),
    }


class TestUploadDocumentRollback:
    """Verify vectors are cleaned up when metadata save fails after insert."""

    @pytest.mark.asyncio
    async def test_rollback_when_metadata_save_fails(self):
        from astrbot.core.exceptions import KnowledgeBaseUploadError

        with (
            patch(
                "astrbot.core.knowledge_base.kb_helper.select_parser",
                new_callable=AsyncMock,
            ) as mock_select,
            patch(
                "astrbot.core.knowledge_base.kb_helper._compact_chunks",
                return_value=["chunk 1", "chunk 2", "chunk 3"],
            ),
        ):
            _mock_parser(mock_select)
            helper = _build_helper()
            helper.vec_db.insert_batch = AsyncMock(return_value=[1, 2, 3])
            helper.vec_db.delete_documents = AsyncMock()
            helper.kb_db.get_db.side_effect = RuntimeError("DB connection lost")

            with pytest.raises(KnowledgeBaseUploadError) as exc_info:
                await helper.upload_document(
                    file_name="test.txt",
                    file_content=b"hello world",
                    file_type="txt",
                )

            assert exc_info.value.stage == "metadata"
            helper.vec_db.delete_documents.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_rollback_when_insert_fails(self):
        from astrbot.core.exceptions import KnowledgeBaseUploadError

        with (
            patch(
                "astrbot.core.knowledge_base.kb_helper.select_parser",
                new_callable=AsyncMock,
            ) as mock_select,
            patch(
                "astrbot.core.knowledge_base.kb_helper._compact_chunks",
                return_value=["chunk 1"],
            ),
        ):
            _mock_parser(mock_select)
            helper = _build_helper()
            helper.vec_db.insert_batch.side_effect = KnowledgeBaseUploadError(
                stage="embedding",
                user_message="模拟失败",
                details={},
            )
            helper.vec_db.delete_documents = AsyncMock()

            with pytest.raises(KnowledgeBaseUploadError) as exc_info:
                await helper.upload_document(
                    file_name="test.txt",
                    file_content=b"hello",
                    file_type="txt",
                )

            assert exc_info.value.stage == "embedding"
            helper.vec_db.delete_documents.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_parse_failure_persists_failed_document_record(self, tmp_path):
        from astrbot.core.exceptions import KnowledgeBaseUploadError
        from astrbot.core.knowledge_base.document_metadata import build_content_hash

        with patch(
            "astrbot.core.knowledge_base.kb_helper.select_parser",
            new_callable=AsyncMock,
        ) as mock_select:
            parser = AsyncMock()
            parser.parse = AsyncMock(side_effect=RuntimeError("broken parser"))
            mock_select.return_value = parser

            helper = _build_helper_with_real_dirs(tmp_path)
            session = _make_session_context()
            helper.kb_db.get_db = MagicMock(return_value=session)
            helper.kb_db.update_kb_stats = AsyncMock()
            helper.refresh_kb = AsyncMock()
            helper.refresh_document = AsyncMock()
            helper.vec_db.insert_batch = AsyncMock()
            helper.vec_db.delete_documents = AsyncMock()
            helper.vec_db.count_documents = AsyncMock(return_value=0)

            with pytest.raises(KnowledgeBaseUploadError) as exc_info:
                await helper.upload_document(
                    file_name="broken.txt",
                    file_content=b"not parseable",
                    file_type="txt",
                )

            failed_doc = session.add.call_args.args[0]
            assert exc_info.value.stage == "parsing"
            assert failed_doc.status == "failed"
            assert failed_doc.error_stage == "parsing"
            assert "文档解析失败" in failed_doc.error_message
            assert failed_doc.source_type == "file"
            assert failed_doc.source_uri == "broken.txt"
            assert failed_doc.content_hash == build_content_hash(b"not parseable")
            assert failed_doc.file_size == len(b"not parseable")
            assert Path(failed_doc.file_path).exists()
            assert Path(failed_doc.file_path).read_bytes() == b"not parseable"
            helper.vec_db.insert_batch.assert_not_awaited()
            helper.vec_db.delete_documents.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_pre_chunked_import_persists_failed_document_record(
        self,
        tmp_path,
    ):
        from astrbot.core.exceptions import KnowledgeBaseUploadError
        from astrbot.core.knowledge_base.document_metadata import build_content_hash

        helper = _build_helper_with_real_dirs(tmp_path)
        session = _make_session_context()
        helper.kb_db.get_db = MagicMock(return_value=session)
        helper.kb_db.update_kb_stats = AsyncMock()
        helper.refresh_kb = AsyncMock()
        helper.refresh_document = AsyncMock()
        helper.vec_db.insert_batch = AsyncMock()
        helper.vec_db.delete_documents = AsyncMock()
        helper.vec_db.count_documents = AsyncMock(return_value=0)

        with pytest.raises(KnowledgeBaseUploadError) as exc_info:
            await helper.upload_document(
                file_name="empty-import.txt",
                file_content=None,
                file_type="txt",
                pre_chunked_text=[" ", ""],
                source_type="import",
                source_uri="manual-import",
            )

        failed_doc = session.add.call_args.args[0]
        assert exc_info.value.stage == "validation"
        assert failed_doc.status == "failed"
        assert failed_doc.error_stage == "validation"
        assert "预分块文本为空" in failed_doc.error_message
        assert failed_doc.source_type == "import"
        assert failed_doc.source_uri == "manual-import"
        assert failed_doc.file_path == ""
        assert failed_doc.file_size == 0
        assert failed_doc.content_hash == build_content_hash([])
        assert failed_doc.chunker_name == "pre_chunked"
        helper.vec_db.insert_batch.assert_not_awaited()
        helper.vec_db.delete_documents.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cleanup_failure_does_not_suppress_original_error(self):
        from astrbot.core.exceptions import KnowledgeBaseUploadError

        with (
            patch(
                "astrbot.core.knowledge_base.kb_helper.select_parser",
                new_callable=AsyncMock,
            ) as mock_select,
            patch(
                "astrbot.core.knowledge_base.kb_helper._compact_chunks",
                return_value=["chunk 1"],
            ),
        ):
            _mock_parser(mock_select)
            helper = _build_helper()
            helper.vec_db.insert_batch = AsyncMock(return_value=[1])
            helper.vec_db.delete_documents.side_effect = RuntimeError("cleanup fail")
            helper.kb_db.get_db.side_effect = RuntimeError("DB lost")

            with pytest.raises(KnowledgeBaseUploadError) as exc_info:
                await helper.upload_document(
                    file_name="test.txt",
                    file_content=b"hello",
                    file_type="txt",
                )

            assert exc_info.value.stage == "metadata"
            helper.vec_db.delete_documents.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_metadata_refresh_failure_preserves_committed_source_file(
        self,
        tmp_path,
    ):
        from astrbot.core.exceptions import KnowledgeBaseUploadError

        with (
            patch(
                "astrbot.core.knowledge_base.kb_helper.select_parser",
                new_callable=AsyncMock,
            ) as mock_select,
            patch(
                "astrbot.core.knowledge_base.kb_helper._compact_chunks",
                return_value=["chunk 1"],
            ),
        ):
            _mock_parser(mock_select)
            helper = _build_helper_with_real_dirs(tmp_path)

            session = _make_session_context()
            helper.kb_db.get_db = MagicMock(return_value=session)
            helper.kb_db.update_kb_stats = AsyncMock(
                side_effect=RuntimeError("stats fail"),
            )
            helper.vec_db.insert_batch = AsyncMock(return_value=[1])
            helper.vec_db.delete_documents = AsyncMock()
            helper.vec_db.count_documents = AsyncMock(return_value=1)
            helper.refresh_kb = AsyncMock()
            helper.refresh_document = AsyncMock()

            with pytest.raises(KnowledgeBaseUploadError) as exc_info:
                await helper.upload_document(
                    file_name="committed.txt",
                    file_content=b"hello world",
                    file_type="txt",
                )

            assert exc_info.value.stage == "metadata"
            saved_files = list(helper.kb_files_dir.glob("*/committed.txt"))
            assert len(saved_files) == 1
            assert saved_files[0].read_bytes() == b"hello world"
            helper.vec_db.delete_documents.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_rollback_on_success(self):
        with (
            patch(
                "astrbot.core.knowledge_base.kb_helper.select_parser",
                new_callable=AsyncMock,
            ) as mock_select,
            patch(
                "astrbot.core.knowledge_base.kb_helper._compact_chunks",
                return_value=["chunk 1", "chunk 2"],
            ),
        ):
            _mock_parser(mock_select)
            helper = _build_helper()

            session = _make_session_context()
            helper.kb_db.get_db = MagicMock(return_value=session)
            helper.kb_db.update_kb_stats = AsyncMock()
            helper.vec_db.insert_batch = AsyncMock(return_value=[1, 2])
            helper.vec_db.delete_documents = AsyncMock()
            helper.vec_db.count_documents = AsyncMock(return_value=2)
            helper.refresh_kb = AsyncMock()
            helper.refresh_document = AsyncMock()

            doc = await helper.upload_document(
                file_name="test.txt",
                file_content=b"hello world",
                file_type="txt",
            )

            assert doc is not None
            helper.vec_db.delete_documents.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_upload_document_persists_source_metadata_and_original_file(
        self,
        tmp_path,
    ):
        from astrbot.core.knowledge_base.document_metadata import build_content_hash

        with (
            patch(
                "astrbot.core.knowledge_base.kb_helper.select_parser",
                new_callable=AsyncMock,
            ) as mock_select,
            patch(
                "astrbot.core.knowledge_base.kb_helper._compact_chunks",
                return_value=["chunk 1", "chunk 2"],
            ),
        ):
            _mock_parser(mock_select)
            helper = _build_helper_with_real_dirs(tmp_path)

            session = _make_session_context()
            helper.kb_db.get_db = MagicMock(return_value=session)
            helper.kb_db.update_kb_stats = AsyncMock()
            helper.vec_db.insert_batch = AsyncMock(return_value=[1, 2])
            helper.vec_db.delete_documents = AsyncMock()
            helper.vec_db.count_documents = AsyncMock(return_value=2)
            helper.refresh_kb = AsyncMock()
            helper.refresh_document = AsyncMock()

            doc = await helper.upload_document(
                file_name="../../unsafe.md",
                file_content=b"# Title\nhello world",
                file_type="md",
            )

            saved_path = Path(doc.file_path)
            assert doc.source_type == "file"
            assert doc.source_uri == "../../unsafe.md"
            assert doc.content_hash == build_content_hash(b"# Title\nhello world")
            assert doc.parser_name is not None
            assert doc.parser_version == "1"
            assert doc.chunker_name == "MarkdownChunker"
            assert doc.chunker_version == "1"
            assert doc.status == "ready"
            assert doc.indexed_at is not None
            assert saved_path.exists()
            assert saved_path.read_bytes() == b"# Title\nhello world"
            assert saved_path.name == "unsafe.md"
            assert saved_path.is_relative_to(helper.kb_files_dir)
            helper.vec_db.delete_documents.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_upload_document_stores_chunk_metadata(self, tmp_path):
        from astrbot.core.knowledge_base.document_metadata import build_content_hash

        with (
            patch(
                "astrbot.core.knowledge_base.kb_helper.select_parser",
                new_callable=AsyncMock,
            ) as mock_select,
            patch(
                "astrbot.core.knowledge_base.kb_helper._compact_chunks",
                return_value=["first chunk", "second"],
            ),
        ):
            _mock_parser(mock_select)
            helper = _build_helper_with_real_dirs(tmp_path)

            session = _make_session_context()
            helper.kb_db.get_db = MagicMock(return_value=session)
            helper.kb_db.update_kb_stats = AsyncMock()
            helper.vec_db.insert_batch = AsyncMock(return_value=[1, 2])
            helper.vec_db.delete_documents = AsyncMock()
            helper.vec_db.count_documents = AsyncMock(return_value=2)
            helper.refresh_kb = AsyncMock()
            helper.refresh_document = AsyncMock()

            await helper.upload_document(
                file_name="chunks.txt",
                file_content=b"source",
                file_type="txt",
            )

        kwargs = helper.vec_db.insert_batch.await_args.kwargs
        chunk_ids = kwargs["ids"]
        metadatas = kwargs["metadatas"]
        assert len(chunk_ids) == 2
        assert len(set(chunk_ids)) == 2
        assert metadatas == [
            {
                "kb_id": "kb-test-1",
                "kb_doc_id": session.add.call_args.args[0].doc_id,
                "chunk_index": 0,
                "section_index": 0,
                "content_hash": build_content_hash("first chunk"),
                "char_count": len("first chunk"),
                "token_count_estimate": 3,
                "start_offset": 0,
                "end_offset": len("first chunk"),
                "previous_chunk_id": None,
                "next_chunk_id": chunk_ids[1],
            },
            {
                "kb_id": "kb-test-1",
                "kb_doc_id": session.add.call_args.args[0].doc_id,
                "chunk_index": 1,
                "section_index": 1,
                "content_hash": build_content_hash("second"),
                "char_count": len("second"),
                "token_count_estimate": 1,
                "start_offset": len("first chunk"),
                "end_offset": len("first chunk") + len("second"),
                "previous_chunk_id": chunk_ids[0],
                "next_chunk_id": None,
            },
        ]

    @pytest.mark.asyncio
    async def test_upload_markdown_document_stores_title_path_metadata(self, tmp_path):
        with patch(
            "astrbot.core.knowledge_base.kb_helper.select_parser",
            new_callable=AsyncMock,
        ) as mock_select:
            _mock_parser(
                mock_select,
                text=("# Guide\nIntro\n\n## Install\nStep one\n\n## Usage\nStep two"),
            )
            helper = _build_helper_with_real_dirs(tmp_path)

            session = _make_session_context()
            helper.kb_db.get_db = MagicMock(return_value=session)
            helper.kb_db.update_kb_stats = AsyncMock()
            helper.vec_db.insert_batch = AsyncMock(return_value=[1, 2, 3])
            helper.vec_db.delete_documents = AsyncMock()
            helper.vec_db.count_documents = AsyncMock(return_value=3)
            helper.refresh_kb = AsyncMock()
            helper.refresh_document = AsyncMock()

            await helper.upload_document(
                file_name="guide.md",
                file_content=b"# Guide\nIntro",
                file_type="md",
            )

        metadatas = helper.vec_db.insert_batch.await_args.kwargs["metadatas"]
        assert [metadata.get("title_path") for metadata in metadatas] == [
            ["Guide"],
            ["Guide", "Install"],
            ["Guide", "Usage"],
        ]
        assert [metadata.get("section_index") for metadata in metadatas] == [0, 1, 2]
        assert all(
            metadata.get("token_count_estimate") is not None for metadata in metadatas
        )

    @pytest.mark.asyncio
    async def test_upload_markdown_document_keeps_title_path_on_split_chunks(
        self,
        tmp_path,
    ):
        markdown_text = "# Guide\n" + "\n".join(
            f"Long installation paragraph {idx}." for idx in range(16)
        )

        with patch(
            "astrbot.core.knowledge_base.kb_helper.select_parser",
            new_callable=AsyncMock,
        ) as mock_select:
            _mock_parser(mock_select, text=markdown_text)
            helper = _build_helper_with_real_dirs(tmp_path)

            session = _make_session_context()
            helper.kb_db.get_db = MagicMock(return_value=session)
            helper.kb_db.update_kb_stats = AsyncMock()
            helper.vec_db.insert_batch = AsyncMock(return_value=[1])
            helper.vec_db.delete_documents = AsyncMock()
            helper.vec_db.count_documents = AsyncMock(return_value=1)
            helper.refresh_kb = AsyncMock()
            helper.refresh_document = AsyncMock()

            await helper.upload_document(
                file_name="guide.md",
                file_content=markdown_text.encode(),
                file_type="md",
                chunk_size=90,
                chunk_overlap=0,
            )

        metadatas = helper.vec_db.insert_batch.await_args.kwargs["metadatas"]
        assert len(metadatas) > 1
        assert all(metadata.get("title_path") == ["Guide"] for metadata in metadatas)
        assert all(metadata.get("section_index") == 0 for metadata in metadatas)

    @pytest.mark.asyncio
    async def test_upload_xlsx_uses_markdown_chunker_for_table_protection(
        self,
        tmp_path,
    ):
        table_text = "# Sheet1\n| Name | Value |\n| --- | --- |\n" + "\n".join(
            f"| row-{idx} | value-{idx} |" for idx in range(8)
        )

        with patch(
            "astrbot.core.knowledge_base.kb_helper.select_parser",
            new_callable=AsyncMock,
        ) as mock_select:
            _mock_parser(mock_select, text=table_text)
            helper = _build_helper_with_real_dirs(tmp_path)

            session = _make_session_context()
            helper.kb_db.get_db = MagicMock(return_value=session)
            helper.kb_db.update_kb_stats = AsyncMock()
            helper.vec_db.insert_batch = AsyncMock(return_value=[1, 2, 3])
            helper.vec_db.delete_documents = AsyncMock()
            helper.vec_db.count_documents = AsyncMock(return_value=3)
            helper.refresh_kb = AsyncMock()
            helper.refresh_document = AsyncMock()

            doc = await helper.upload_document(
                file_name="sheet.xlsx",
                file_content=b"xlsx-bytes",
                file_type="xlsx",
                chunk_size=90,
                chunk_overlap=0,
            )

        contents = helper.vec_db.insert_batch.await_args.kwargs["contents"]
        table_chunks = [
            content for content in contents if "| Name | Value |" in content
        ]

        assert doc.chunker_name == "MarkdownChunker"
        assert len(table_chunks) > 1
        assert all("| --- | --- |" in content for content in table_chunks)

    @pytest.mark.asyncio
    async def test_upload_document_stores_page_number_from_text_segments(
        self,
        tmp_path,
    ):
        from astrbot.core.knowledge_base.chunking.recursive import (
            RecursiveCharacterChunker,
        )
        from astrbot.core.knowledge_base.parsers.base import TextSegment

        with patch(
            "astrbot.core.knowledge_base.kb_helper.select_parser",
            new_callable=AsyncMock,
        ) as mock_select:
            _mock_parser(
                mock_select,
                text="Page one text\n\nPage two text",
                text_segments=[
                    TextSegment(text="Page one text", metadata={"page_number": 1}),
                    TextSegment(text="Page two text", metadata={"page_number": 2}),
                ],
            )
            helper = _build_helper_with_real_dirs(tmp_path)
            helper.chunker = RecursiveCharacterChunker()

            session = _make_session_context()
            helper.kb_db.get_db = MagicMock(return_value=session)
            helper.kb_db.update_kb_stats = AsyncMock()
            helper.vec_db.insert_batch = AsyncMock(return_value=[1, 2])
            helper.vec_db.delete_documents = AsyncMock()
            helper.vec_db.count_documents = AsyncMock(return_value=2)
            helper.refresh_kb = AsyncMock()
            helper.refresh_document = AsyncMock()

            await helper.upload_document(
                file_name="guide.pdf",
                file_content=b"%PDF-1.7",
                file_type="pdf",
            )

        metadatas = helper.vec_db.insert_batch.await_args.kwargs["metadatas"]
        assert [metadata.get("page_number") for metadata in metadatas] == [1, 2]
        assert [metadata["chunk_index"] for metadata in metadatas] == [0, 1]
        assert [metadata["section_index"] for metadata in metadatas] == [0, 1]

    @pytest.mark.asyncio
    async def test_get_chunks_by_doc_id_returns_chunk_metadata(self):
        import json

        helper = _build_helper()
        helper.vec_db = MagicMock()
        helper.vec_db.document_storage = MagicMock()
        helper.vec_db.document_storage.get_documents = AsyncMock(
            return_value=[
                {
                    "doc_id": "chunk-1",
                    "text": "first chunk",
                    "metadata": json.dumps(
                        {
                            "kb_id": "kb-test-1",
                            "kb_doc_id": "doc-1",
                            "chunk_index": 0,
                            "section_index": 0,
                            "content_hash": "hash-1",
                            "char_count": 11,
                            "token_count_estimate": 3,
                            "start_offset": 0,
                            "end_offset": 11,
                            "previous_chunk_id": None,
                            "next_chunk_id": "chunk-2",
                        },
                    ),
                },
                {
                    "doc_id": "legacy-chunk",
                    "text": "legacy",
                    "metadata": json.dumps(
                        {
                            "kb_id": "kb-test-1",
                            "kb_doc_id": "doc-1",
                            "chunk_index": 1,
                        },
                    ),
                },
            ],
        )

        chunks = await helper.get_chunks_by_doc_id("doc-1", offset=2, limit=3)

        helper.vec_db.document_storage.get_documents.assert_awaited_once_with(
            metadata_filters={"kb_doc_id": "doc-1"},
            offset=2,
            limit=3,
        )
        assert chunks[0] == {
            "chunk_id": "chunk-1",
            "doc_id": "doc-1",
            "kb_id": "kb-test-1",
            "chunk_index": 0,
            "section_index": 0,
            "content": "first chunk",
            "char_count": 11,
            "token_count_estimate": 3,
            "content_hash": "hash-1",
            "start_offset": 0,
            "end_offset": 11,
            "previous_chunk_id": None,
            "next_chunk_id": "chunk-2",
            "title_path": None,
            "page_number": None,
            "parent_chunk_id": None,
        }
        assert chunks[1]["chunk_id"] == "legacy-chunk"
        assert chunks[1]["char_count"] == len("legacy")
        assert chunks[1]["section_index"] is None
        assert chunks[1]["token_count_estimate"] is None
        assert chunks[1]["content_hash"] is None

    @pytest.mark.asyncio
    async def test_search_chunks_by_doc_id_uses_document_storage_search(self):
        import json

        helper = _build_helper()
        helper.vec_db = MagicMock()
        helper.vec_db.document_storage = MagicMock()
        helper.vec_db.document_storage.search_documents = AsyncMock(
            return_value=(
                [
                    {
                        "doc_id": "chunk-1",
                        "text": "matched chunk",
                        "metadata": json.dumps(
                            {
                                "kb_id": "kb-test-1",
                                "kb_doc_id": "doc-1",
                                "chunk_index": 0,
                            },
                        ),
                    },
                ],
                3,
            ),
        )

        chunks, total = await helper.search_chunks_by_doc_id(
            "doc-1",
            search="matched",
            offset=2,
            limit=1,
        )

        helper.vec_db.document_storage.search_documents.assert_awaited_once_with(
            "matched",
            metadata_filters={"kb_doc_id": "doc-1"},
            offset=2,
            limit=1,
        )
        assert total == 3
        assert chunks[0]["chunk_id"] == "chunk-1"

    @pytest.mark.asyncio
    async def test_get_chunk_context_returns_adjacent_chunks(self):
        helper = _build_helper()
        helper.vec_db = MagicMock()
        helper.vec_db.document_storage = MagicMock()

        docs = {
            "chunk-1": _chunk_doc(
                chunk_id="chunk-1",
                text="previous",
                index=0,
                next_chunk_id="chunk-2",
            ),
            "chunk-2": _chunk_doc(
                chunk_id="chunk-2",
                text="current",
                index=1,
                previous_chunk_id="chunk-1",
                next_chunk_id="chunk-3",
            ),
            "chunk-3": _chunk_doc(
                chunk_id="chunk-3",
                text="next",
                index=2,
                previous_chunk_id="chunk-2",
            ),
        }
        helper.vec_db.document_storage.get_document_by_doc_id = AsyncMock(
            side_effect=lambda chunk_id: docs.get(chunk_id),
        )

        context = await helper.get_chunk_context("chunk-2", "doc-1")

        assert context["previous"]["chunk_id"] == "chunk-1"
        assert context["current"]["chunk_id"] == "chunk-2"
        assert context["next"]["chunk_id"] == "chunk-3"
        assert (
            helper.vec_db.document_storage.get_document_by_doc_id.await_args_list[
                0
            ].args[0]
            == "chunk-2"
        )

    @pytest.mark.asyncio
    async def test_get_chunk_context_filters_adjacent_chunks_from_other_docs(self):
        helper = _build_helper()
        helper.vec_db = MagicMock()
        helper.vec_db.document_storage = MagicMock()

        docs = {
            "chunk-2": _chunk_doc(
                chunk_id="chunk-2",
                text="current",
                index=1,
                previous_chunk_id="other-doc-chunk",
            ),
            "other-doc-chunk": _chunk_doc(
                chunk_id="other-doc-chunk",
                text="wrong document",
                doc_id="doc-2",
                index=0,
            ),
        }
        helper.vec_db.document_storage.get_document_by_doc_id = AsyncMock(
            side_effect=lambda chunk_id: docs.get(chunk_id),
        )

        context = await helper.get_chunk_context("chunk-2", "doc-1")

        assert context["current"]["chunk_id"] == "chunk-2"
        assert context["previous"] is None
        assert context["next"] is None

    @pytest.mark.asyncio
    async def test_get_chunk_context_raises_when_chunk_is_missing(self):
        helper = _build_helper()
        helper.vec_db = MagicMock()
        helper.vec_db.document_storage = MagicMock()
        helper.vec_db.document_storage.get_document_by_doc_id = AsyncMock(
            return_value=None,
        )

        with pytest.raises(ValueError, match="无法找到"):
            await helper.get_chunk_context("missing", "doc-1")

    @pytest.mark.asyncio
    async def test_upload_document_rejects_duplicate_before_storage(self, tmp_path):
        from astrbot.core.exceptions import KnowledgeBaseUploadError
        from astrbot.core.knowledge_base.document_metadata import build_content_hash

        helper = _build_helper_with_real_dirs(tmp_path)
        helper.kb_db.get_document_by_content_hash = AsyncMock(
            return_value=_existing_doc(),
        )
        helper.vec_db.insert_batch = AsyncMock()
        helper.vec_db.delete_documents = AsyncMock()

        with pytest.raises(KnowledgeBaseUploadError) as exc_info:
            await helper.upload_document(
                file_name="duplicate.txt",
                file_content=b"hello world",
                file_type="txt",
            )

        assert exc_info.value.stage == "deduplication"
        assert exc_info.value.details == {
            "file_name": "duplicate.txt",
            "content_hash": build_content_hash(b"hello world"),
            "existing_doc_id": "existing-doc",
            "existing_doc_name": "existing.txt",
        }
        helper.kb_db.get_document_by_content_hash.assert_awaited_once_with(
            kb_id="kb-test-1",
            content_hash=build_content_hash(b"hello world"),
        )
        assert list(helper.kb_files_dir.glob("**/*")) == []
        helper.vec_db.insert_batch.assert_not_awaited()
        helper.vec_db.delete_documents.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_upload_document_wraps_duplicate_lookup_failure(self, tmp_path):
        from astrbot.core.exceptions import KnowledgeBaseUploadError

        helper = _build_helper_with_real_dirs(tmp_path)
        helper.kb_db.get_document_by_content_hash = AsyncMock(
            side_effect=RuntimeError("db unavailable"),
        )
        helper.vec_db.insert_batch = AsyncMock()
        helper.vec_db.delete_documents = AsyncMock()

        with pytest.raises(KnowledgeBaseUploadError) as exc_info:
            await helper.upload_document(
                file_name="lookup-fails.txt",
                file_content=b"hello world",
                file_type="txt",
            )

        assert exc_info.value.stage == "deduplication"
        assert "重复检测失败" in exc_info.value.user_message
        assert list(helper.kb_files_dir.glob("**/*")) == []
        helper.vec_db.insert_batch.assert_not_awaited()
        helper.vec_db.delete_documents.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pre_chunked_upload_persists_import_metadata(self, tmp_path):
        from astrbot.core.knowledge_base.document_metadata import build_content_hash

        helper = _build_helper_with_real_dirs(tmp_path)

        session = _make_session_context()
        helper.kb_db.get_db = MagicMock(return_value=session)
        helper.kb_db.update_kb_stats = AsyncMock()
        helper.vec_db.insert_batch = AsyncMock(return_value=[1, 2])
        helper.vec_db.delete_documents = AsyncMock()
        helper.vec_db.count_documents = AsyncMock(return_value=2)
        helper.refresh_kb = AsyncMock()
        helper.refresh_document = AsyncMock()

        doc = await helper.upload_document(
            file_name="imported.txt",
            file_content=None,
            file_type="txt",
            pre_chunked_text=["chunk 1", "chunk 2"],
            source_type="import",
            source_uri="manual-import",
        )

        assert doc.source_type == "import"
        assert doc.source_uri == "manual-import"
        assert doc.file_path == ""
        assert doc.file_size == len("chunk 1") + len("chunk 2")
        assert doc.content_hash == build_content_hash(["chunk 1", "chunk 2"])
        assert doc.parser_name is None
        assert doc.parser_version is None
        assert doc.chunker_name == "pre_chunked"
        assert doc.chunker_version == "1"
        assert doc.status == "ready"
        assert doc.indexed_at is not None
        helper.vec_db.delete_documents.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pre_chunked_upload_rejects_duplicate_before_embedding(
        self,
        tmp_path,
    ):
        from astrbot.core.exceptions import KnowledgeBaseUploadError
        from astrbot.core.knowledge_base.document_metadata import build_content_hash

        helper = _build_helper_with_real_dirs(tmp_path)
        helper.kb_db.get_document_by_content_hash = AsyncMock(
            return_value=_existing_doc(),
        )
        helper.vec_db.insert_batch = AsyncMock()
        helper.vec_db.delete_documents = AsyncMock()

        with pytest.raises(KnowledgeBaseUploadError) as exc_info:
            await helper.upload_document(
                file_name="duplicate-import.txt",
                file_content=None,
                file_type="txt",
                pre_chunked_text=["chunk 1", "chunk 2"],
                source_type="import",
            )

        assert exc_info.value.stage == "deduplication"
        helper.kb_db.get_document_by_content_hash.assert_awaited_once_with(
            kb_id="kb-test-1",
            content_hash=build_content_hash(["chunk 1", "chunk 2"]),
        )
        assert list(helper.kb_files_dir.glob("**/*")) == []
        helper.vec_db.insert_batch.assert_not_awaited()
        helper.vec_db.delete_documents.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pre_chunked_upload_uses_explicit_url_metadata(self, tmp_path):
        from astrbot.core.knowledge_base.document_metadata import build_content_hash
        from astrbot.core.knowledge_base.parsers.url_parser import URLExtractor

        helper = _build_helper_with_real_dirs(tmp_path)

        session = _make_session_context()
        helper.kb_db.get_db = MagicMock(return_value=session)
        helper.kb_db.update_kb_stats = AsyncMock()
        helper.vec_db.insert_batch = AsyncMock(return_value=[1])
        helper.vec_db.delete_documents = AsyncMock()
        helper.vec_db.count_documents = AsyncMock(return_value=1)
        helper.refresh_kb = AsyncMock()
        helper.refresh_document = AsyncMock()

        doc = await helper.upload_document(
            file_name="example.url",
            file_content=None,
            file_type="url",
            pre_chunked_text=["cleaned chunk"],
            source_type="url",
            source_uri="https://example.com/a",
            source_content_hash=build_content_hash("raw page text"),
            source_parser_name=URLExtractor.__name__,
            source_chunker_name="RecursiveCharacterChunker",
        )

        assert doc.source_type == "url"
        assert doc.source_uri == "https://example.com/a"
        assert doc.content_hash == build_content_hash("raw page text")
        assert doc.parser_name == URLExtractor.__name__
        assert doc.parser_version == "1"
        assert doc.chunker_name == "RecursiveCharacterChunker"
        assert doc.chunker_version == "1"
        assert doc.file_path == ""

    @pytest.mark.asyncio
    async def test_url_upload_missing_tavily_key_persists_failed_document(
        self,
        tmp_path,
    ):
        from astrbot.core.exceptions import KnowledgeBaseUploadError

        helper = _build_helper_with_real_dirs(tmp_path)
        helper.prov_mgr.acm.default_conf = {"provider_settings": {}}
        session = _make_session_context()
        helper.kb_db.get_db = MagicMock(return_value=session)
        helper.kb_db.update_kb_stats = AsyncMock()
        helper.refresh_kb = AsyncMock()
        helper.refresh_document = AsyncMock()
        helper.vec_db.count_documents = AsyncMock(return_value=0)

        with (
            patch(
                "astrbot.core.knowledge_base.kb_helper.extract_text_from_url",
                new_callable=AsyncMock,
            ) as mock_extract,
            pytest.raises(KnowledgeBaseUploadError) as exc_info,
        ):
            await helper.upload_from_url("https://example.com/page")

        failed_doc = session.add.call_args.args[0]
        assert exc_info.value.stage == "configuration"
        assert failed_doc.status == "failed"
        assert failed_doc.error_stage == "configuration"
        assert "Tavily API key" in failed_doc.error_message
        assert failed_doc.source_type == "url"
        assert failed_doc.source_uri == "https://example.com/page"
        assert failed_doc.doc_name == "page.url"
        assert failed_doc.file_type == "url"
        assert failed_doc.file_size == 0
        assert failed_doc.file_path == ""
        assert failed_doc.content_hash is None
        mock_extract.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_url_upload_extract_failure_persists_failed_document(
        self,
        tmp_path,
    ):
        from astrbot.core.exceptions import KnowledgeBaseUploadError

        helper = _build_helper_with_real_dirs(tmp_path)
        helper.prov_mgr.acm.default_conf = {
            "provider_settings": {"websearch_tavily_key": ["key-1"]},
        }
        session = _make_session_context()
        helper.kb_db.get_db = MagicMock(return_value=session)
        helper.kb_db.update_kb_stats = AsyncMock()
        helper.refresh_kb = AsyncMock()
        helper.refresh_document = AsyncMock()
        helper.vec_db.count_documents = AsyncMock(return_value=0)

        with (
            patch(
                "astrbot.core.knowledge_base.kb_helper.extract_text_from_url",
                new_callable=AsyncMock,
                side_effect=RuntimeError("network down"),
            ) as mock_extract,
            pytest.raises(KnowledgeBaseUploadError) as exc_info,
        ):
            await helper.upload_from_url("https://example.com/a")

        failed_doc = session.add.call_args.args[0]
        assert exc_info.value.stage == "extracting"
        assert failed_doc.status == "failed"
        assert failed_doc.error_stage == "extracting"
        assert "无法提取网页内容" in failed_doc.error_message
        assert failed_doc.source_type == "url"
        assert failed_doc.source_uri == "https://example.com/a"
        assert failed_doc.content_hash is None
        mock_extract.assert_awaited_once_with("https://example.com/a", ["key-1"])

    @pytest.mark.asyncio
    async def test_url_upload_empty_cleaning_result_persists_failed_document(
        self,
        tmp_path,
    ):
        from astrbot.core.exceptions import KnowledgeBaseUploadError
        from astrbot.core.knowledge_base.document_metadata import build_content_hash

        helper = _build_helper_with_real_dirs(tmp_path)
        helper.prov_mgr.acm.default_conf = {
            "provider_settings": {"websearch_tavily_key": ["key-1"]},
        }
        helper._clean_and_rechunk_content = AsyncMock(return_value=[])
        helper.upload_document = AsyncMock()
        session = _make_session_context()
        helper.kb_db.get_db = MagicMock(return_value=session)
        helper.kb_db.update_kb_stats = AsyncMock()
        helper.refresh_kb = AsyncMock()
        helper.refresh_document = AsyncMock()
        helper.vec_db.count_documents = AsyncMock(return_value=0)

        with (
            patch(
                "astrbot.core.knowledge_base.kb_helper.extract_text_from_url",
                new_callable=AsyncMock,
                return_value="raw page text",
            ) as mock_extract,
            pytest.raises(KnowledgeBaseUploadError) as exc_info,
        ):
            await helper.upload_from_url(
                "https://example.com/docs",
                enable_cleaning=True,
                cleaning_provider_id="llm-1",
            )

        failed_doc = session.add.call_args.args[0]
        assert exc_info.value.stage == "cleaning"
        assert failed_doc.status == "failed"
        assert failed_doc.error_stage == "cleaning"
        assert "内容清洗后未提取到有效文本" in failed_doc.error_message
        assert failed_doc.source_type == "url"
        assert failed_doc.source_uri == "https://example.com/docs"
        assert failed_doc.file_size == len("raw page text")
        assert failed_doc.content_hash == build_content_hash("raw page text")
        mock_extract.assert_awaited_once_with("https://example.com/docs", ["key-1"])
        helper.upload_document.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rebuild_document_reuploads_saved_source_as_next_version(
        self,
        tmp_path,
    ):
        from astrbot.core.knowledge_base.models import KBDocument

        helper = _build_helper_with_real_dirs(tmp_path)
        source_path = helper.kb_files_dir / "old-doc" / "source.md"
        source_path.parent.mkdir(parents=True)
        source_path.write_bytes(b"# Title\nhello")
        old_doc = KBDocument(
            doc_id="old-doc",
            kb_id="kb-test-1",
            doc_name="source.md",
            file_type="md",
            file_size=13,
            file_path=str(source_path),
            source_type="file",
            source_uri="source.md",
            version=2,
        )
        new_doc = KBDocument(
            doc_id="new-doc",
            kb_id="kb-test-1",
            doc_name="source.md",
            file_type="md",
            file_size=13,
            file_path="",
            version=3,
            parent_doc_id="old-doc",
        )
        helper.kb_db.get_document_by_id = AsyncMock(return_value=old_doc)
        helper.delete_document = AsyncMock()
        helper.upload_document = AsyncMock(return_value=new_doc)

        rebuilt = await helper.rebuild_document("old-doc", batch_size=8)

        assert rebuilt is new_doc
        helper.upload_document.assert_awaited_once_with(
            file_name="source.md",
            file_content=b"# Title\nhello",
            file_type="md",
            chunk_size=512,
            chunk_overlap=50,
            batch_size=8,
            tasks_limit=3,
            max_retries=3,
            progress_callback=None,
            source_type="file",
            source_uri="source.md",
            parent_doc_id="old-doc",
            document_version=3,
            skip_duplicate_check=True,
        )
        helper.delete_document.assert_awaited_once_with("old-doc")

    @pytest.mark.asyncio
    async def test_rebuild_url_document_reimports_source_as_next_version(self):
        from astrbot.core.knowledge_base.models import KBDocument

        helper = _build_helper()
        old_doc = KBDocument(
            doc_id="old-url-doc",
            kb_id="kb-test-1",
            doc_name="page.url",
            file_type="url",
            file_size=13,
            file_path="",
            source_type="url",
            source_uri="https://example.com/page",
            version=4,
        )
        new_doc = KBDocument(
            doc_id="new-url-doc",
            kb_id="kb-test-1",
            doc_name="page.url",
            file_type="url",
            file_size=15,
            file_path="",
            source_type="url",
            source_uri="https://example.com/page",
            version=5,
            parent_doc_id="old-url-doc",
        )
        helper.kb_db.get_document_by_id = AsyncMock(return_value=old_doc)
        helper.delete_document = AsyncMock()
        helper.upload_from_url = AsyncMock(return_value=new_doc)

        rebuilt = await helper.rebuild_document(
            "old-url-doc",
            chunk_size=256,
            chunk_overlap=32,
            batch_size=8,
        )

        assert rebuilt is new_doc
        helper.upload_from_url.assert_awaited_once_with(
            url="https://example.com/page",
            chunk_size=256,
            chunk_overlap=32,
            batch_size=8,
            tasks_limit=3,
            max_retries=3,
            progress_callback=None,
            parent_doc_id="old-url-doc",
            document_version=5,
            skip_duplicate_check=True,
        )
        helper.delete_document.assert_awaited_once_with("old-url-doc")

    @pytest.mark.asyncio
    async def test_rebuild_url_document_rejects_missing_source_uri(self):
        from astrbot.core.knowledge_base.models import KBDocument

        helper = _build_helper()
        doc = KBDocument(
            doc_id="old-url-doc",
            kb_id="kb-test-1",
            doc_name="page.url",
            file_type="url",
            file_size=13,
            file_path="",
            source_type="url",
            source_uri=None,
        )
        helper.kb_db.get_document_by_id = AsyncMock(return_value=doc)
        helper.delete_document = AsyncMock()
        helper.upload_from_url = AsyncMock()

        with pytest.raises(ValueError, match="URL 来源"):
            await helper.rebuild_document("old-url-doc")

        helper.delete_document.assert_not_awaited()
        helper.upload_from_url.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_upload_from_url_forwards_rebuild_version_metadata(self):
        from astrbot.core.knowledge_base.document_metadata import build_content_hash

        helper = _build_helper()
        helper.prov_mgr.acm.default_conf = {
            "provider_settings": {"websearch_tavily_key": ["key-1"]},
        }
        helper._clean_and_rechunk_content = AsyncMock(return_value=["new chunk"])
        helper.upload_document = AsyncMock(return_value=object())

        with patch(
            "astrbot.core.knowledge_base.kb_helper.extract_text_from_url",
            new_callable=AsyncMock,
            return_value="fresh page text",
        ):
            await helper.upload_from_url(
                "https://example.com/page",
                parent_doc_id="old-url-doc",
                document_version=5,
                skip_duplicate_check=True,
            )

        helper.upload_document.assert_awaited_once()
        upload_kwargs = helper.upload_document.await_args.kwargs
        assert upload_kwargs["pre_chunked_text"] == ["new chunk"]
        assert upload_kwargs["source_type"] == "url"
        assert upload_kwargs["source_uri"] == "https://example.com/page"
        assert upload_kwargs["source_content_hash"] == build_content_hash(
            "fresh page text",
        )
        assert upload_kwargs["parent_doc_id"] == "old-url-doc"
        assert upload_kwargs["document_version"] == 5
        assert upload_kwargs["skip_duplicate_check"] is True

    @pytest.mark.asyncio
    async def test_rebuild_import_document_reuses_indexed_chunks_as_next_version(
        self,
    ):
        from astrbot.core.knowledge_base.document_metadata import build_content_hash
        from astrbot.core.knowledge_base.models import KBDocument

        helper = _build_helper()
        old_doc = KBDocument(
            doc_id="old-import-doc",
            kb_id="kb-test-1",
            doc_name="manual.txt",
            file_type="txt",
            file_size=18,
            file_path="",
            source_type="import",
            source_uri="manual-import",
            chunker_name="pre_chunked",
            version=2,
        )
        new_doc = KBDocument(
            doc_id="new-import-doc",
            kb_id="kb-test-1",
            doc_name="manual.txt",
            file_type="txt",
            file_size=18,
            file_path="",
            source_type="import",
            source_uri="manual-import",
            version=3,
            parent_doc_id="old-import-doc",
        )
        helper.kb_db.get_document_by_id = AsyncMock(return_value=old_doc)
        helper.get_chunks_by_doc_id = AsyncMock(
            return_value=[
                {"chunk_index": 1, "content": "second chunk"},
                {"chunk_index": 0, "content": "first chunk"},
            ],
        )
        helper.upload_document = AsyncMock(return_value=new_doc)
        helper.delete_document = AsyncMock()

        rebuilt = await helper.rebuild_document("old-import-doc", batch_size=8)

        assert rebuilt is new_doc
        helper.upload_document.assert_awaited_once_with(
            file_name="manual.txt",
            file_content=None,
            file_type="txt",
            chunk_size=512,
            chunk_overlap=50,
            batch_size=8,
            tasks_limit=3,
            max_retries=3,
            progress_callback=None,
            pre_chunked_text=["first chunk", "second chunk"],
            source_type="import",
            source_uri="manual-import",
            source_content_hash=build_content_hash(["first chunk", "second chunk"]),
            source_chunker_name="pre_chunked",
            parent_doc_id="old-import-doc",
            document_version=3,
            skip_duplicate_check=True,
        )
        helper.delete_document.assert_awaited_once_with("old-import-doc")

    @pytest.mark.asyncio
    async def test_rebuild_import_document_rejects_missing_indexed_chunks(self):
        from astrbot.core.knowledge_base.models import KBDocument

        helper = _build_helper()
        doc = KBDocument(
            doc_id="old-import-doc",
            kb_id="kb-test-1",
            doc_name="manual.txt",
            file_type="txt",
            file_size=18,
            file_path="",
            source_type="import",
            source_uri="manual-import",
        )
        helper.kb_db.get_document_by_id = AsyncMock(return_value=doc)
        helper.get_chunks_by_doc_id = AsyncMock(return_value=[])
        helper.upload_document = AsyncMock()
        helper.delete_document = AsyncMock()

        with pytest.raises(ValueError, match="导入文本块"):
            await helper.rebuild_document("old-import-doc")

        helper.upload_document.assert_not_awaited()
        helper.delete_document.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_import_rebuild_chunks_reads_every_page(self):
        from astrbot.core.knowledge_base.kb_helper import DOCUMENT_REBUILD_PAGE_SIZE

        helper = _build_helper()
        first_page = [
            {"chunk_index": index + 1, "content": f"chunk {index + 1}"}
            for index in range(DOCUMENT_REBUILD_PAGE_SIZE)
        ]
        second_page = [{"chunk_index": 0, "content": "chunk 0"}]
        helper.get_chunks_by_doc_id = AsyncMock(side_effect=[first_page, second_page])

        chunks = await helper._get_import_rebuild_chunks("doc-1")

        assert chunks == ["chunk 0", *[f"chunk {index + 1}" for index in range(100)]]
        assert helper.get_chunks_by_doc_id.await_args_list[0].kwargs == {
            "offset": 0,
            "limit": DOCUMENT_REBUILD_PAGE_SIZE,
        }
        assert helper.get_chunks_by_doc_id.await_args_list[1].kwargs == {
            "offset": DOCUMENT_REBUILD_PAGE_SIZE,
            "limit": DOCUMENT_REBUILD_PAGE_SIZE,
        }

    @pytest.mark.asyncio
    async def test_rebuild_document_rejects_missing_source_file(self, tmp_path):
        from astrbot.core.knowledge_base.models import KBDocument

        helper = _build_helper_with_real_dirs(tmp_path)
        doc = KBDocument(
            doc_id="old-doc",
            kb_id="kb-test-1",
            doc_name="missing.txt",
            file_type="txt",
            file_size=1,
            file_path=str(helper.kb_files_dir / "missing" / "missing.txt"),
            source_type="file",
        )
        helper.kb_db.get_document_by_id = AsyncMock(return_value=doc)
        helper.delete_document = AsyncMock()
        helper.upload_document = AsyncMock()

        with pytest.raises(ValueError, match="原始文件"):
            await helper.rebuild_document("old-doc")

        helper.delete_document.assert_not_awaited()
        helper.upload_document.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rebuild_document_keeps_old_doc_when_upload_fails(self, tmp_path):
        from astrbot.core.exceptions import KnowledgeBaseUploadError
        from astrbot.core.knowledge_base.models import KBDocument

        helper = _build_helper_with_real_dirs(tmp_path)
        source_path = helper.kb_files_dir / "old-doc" / "source.txt"
        source_path.parent.mkdir(parents=True)
        source_path.write_bytes(b"hello")
        old_doc = KBDocument(
            doc_id="old-doc",
            kb_id="kb-test-1",
            doc_name="source.txt",
            file_type="txt",
            file_size=5,
            file_path=str(source_path),
            source_type="file",
        )
        helper.kb_db.get_document_by_id = AsyncMock(return_value=old_doc)
        helper.upload_document = AsyncMock(
            side_effect=KnowledgeBaseUploadError(
                stage="embedding",
                user_message="embedding failed",
            ),
        )
        helper.delete_document = AsyncMock()

        with pytest.raises(KnowledgeBaseUploadError) as exc_info:
            await helper.rebuild_document("old-doc")

        assert exc_info.value.stage == "embedding"
        helper.delete_document.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rebuild_document_rolls_back_new_doc_when_replace_fails(
        self,
        tmp_path,
    ):
        from astrbot.core.exceptions import KnowledgeBaseUploadError
        from astrbot.core.knowledge_base.models import KBDocument

        helper = _build_helper_with_real_dirs(tmp_path)
        source_path = helper.kb_files_dir / "old-doc" / "source.txt"
        source_path.parent.mkdir(parents=True)
        source_path.write_bytes(b"hello")
        old_doc = KBDocument(
            doc_id="old-doc",
            kb_id="kb-test-1",
            doc_name="source.txt",
            file_type="txt",
            file_size=5,
            file_path=str(source_path),
            source_type="file",
        )
        new_doc = KBDocument(
            doc_id="new-doc",
            kb_id="kb-test-1",
            doc_name="source.txt",
            file_type="txt",
            file_size=5,
            file_path="",
        )
        helper.kb_db.get_document_by_id = AsyncMock(return_value=old_doc)
        helper.upload_document = AsyncMock(return_value=new_doc)
        helper.delete_document = AsyncMock(
            side_effect=[RuntimeError("old delete failed"), None],
        )

        with pytest.raises(KnowledgeBaseUploadError) as exc_info:
            await helper.rebuild_document("old-doc")

        assert exc_info.value.stage == "rebuild"
        assert exc_info.value.details == {
            "doc_id": "old-doc",
            "new_doc_id": "new-doc",
        }
        assert helper.delete_document.await_args_list[0].args == ("old-doc",)
        assert helper.delete_document.await_args_list[1].args == ("new-doc",)

    @pytest.mark.asyncio
    async def test_rebuild_all_documents_preserves_partial_failures(self, tmp_path):
        from astrbot.core.knowledge_base.models import KBDocument

        helper = _build_helper_with_real_dirs(tmp_path)
        docs = [
            KBDocument(
                doc_id="doc-ok",
                kb_id="kb-test-1",
                doc_name="ok.txt",
                file_type="txt",
                file_size=2,
                file_path="",
            ),
            KBDocument(
                doc_id="doc-fail",
                kb_id="kb-test-1",
                doc_name="fail.txt",
                file_type="txt",
                file_size=4,
                file_path="",
            ),
        ]
        rebuilt_doc = KBDocument(
            doc_id="doc-new",
            kb_id="kb-test-1",
            doc_name="ok.txt",
            file_type="txt",
            file_size=2,
            file_path="",
        )
        helper.list_documents = AsyncMock(return_value=docs)
        helper.rebuild_document = AsyncMock(
            side_effect=[rebuilt_doc, ValueError("missing source")],
        )

        result = await helper.rebuild_all_documents(batch_size=6)

        assert result["total"] == 2
        assert result["success_count"] == 1
        assert result["failed_count"] == 1
        assert result["rebuilt"][0]["doc_id"] == "doc-new"
        assert result["failed"] == [
            {
                "doc_id": "doc-fail",
                "doc_name": "fail.txt",
                "error": "missing source",
            },
        ]
        assert helper.rebuild_document.await_args_list[0].kwargs["batch_size"] == 6
        assert helper.rebuild_document.await_args_list[1].kwargs["batch_size"] == 6

    @pytest.mark.asyncio
    async def test_rebuild_all_documents_reads_every_page(self, tmp_path):
        from astrbot.core.knowledge_base.kb_helper import DOCUMENT_REBUILD_PAGE_SIZE
        from astrbot.core.knowledge_base.models import KBDocument

        helper = _build_helper_with_real_dirs(tmp_path)
        docs = [
            KBDocument(
                doc_id=f"doc-{index}",
                kb_id="kb-test-1",
                doc_name=f"doc-{index}.txt",
                file_type="txt",
                file_size=2,
                file_path="",
            )
            for index in range(DOCUMENT_REBUILD_PAGE_SIZE + 1)
        ]

        async def list_documents(offset=0, limit=100, search=None):
            return docs[offset : offset + limit]

        helper.list_documents = AsyncMock(side_effect=list_documents)
        helper.rebuild_document = AsyncMock(
            side_effect=[
                KBDocument(
                    doc_id=f"rebuilt-{index}",
                    kb_id="kb-test-1",
                    doc_name=f"doc-{index}.txt",
                    file_type="txt",
                    file_size=2,
                    file_path="",
                )
                for index in range(DOCUMENT_REBUILD_PAGE_SIZE + 1)
            ],
        )

        result = await helper.rebuild_all_documents()

        assert result["total"] == DOCUMENT_REBUILD_PAGE_SIZE + 1
        assert result["success_count"] == DOCUMENT_REBUILD_PAGE_SIZE + 1
        assert helper.list_documents.await_args_list[0].kwargs == {
            "offset": 0,
            "limit": DOCUMENT_REBUILD_PAGE_SIZE,
        }
        assert helper.list_documents.await_args_list[1].kwargs == {
            "offset": DOCUMENT_REBUILD_PAGE_SIZE,
            "limit": DOCUMENT_REBUILD_PAGE_SIZE,
        }

    @pytest.mark.asyncio
    async def test_rebuild_documents_preserves_partial_failures(self, tmp_path):
        from astrbot.core.knowledge_base.models import KBDocument

        helper = _build_helper_with_real_dirs(tmp_path)
        failed_doc = KBDocument(
            doc_id="doc-fail",
            kb_id="kb-test-1",
            doc_name="fail.txt",
            file_type="txt",
            file_size=4,
            file_path="",
        )
        rebuilt_doc = KBDocument(
            doc_id="doc-new",
            kb_id="kb-test-1",
            doc_name="ok.txt",
            file_type="txt",
            file_size=2,
            file_path="",
        )
        helper.rebuild_document = AsyncMock(
            side_effect=[rebuilt_doc, ValueError("missing source")],
        )
        helper.get_document = AsyncMock(return_value=failed_doc)

        result = await helper.rebuild_documents(
            ["doc-ok", "doc-fail", "doc-ok"],
            batch_size=6,
        )

        assert result["total"] == 2
        assert result["success_count"] == 1
        assert result["failed_count"] == 1
        assert result["rebuilt"][0]["doc_id"] == "doc-new"
        assert result["failed"] == [
            {
                "doc_id": "doc-fail",
                "doc_name": "fail.txt",
                "error": "missing source",
            },
        ]
        assert helper.rebuild_document.await_args_list[0].args == ("doc-ok",)
        assert helper.rebuild_document.await_args_list[1].args == ("doc-fail",)
        assert helper.rebuild_document.await_args_list[0].kwargs["batch_size"] == 6
        assert helper.rebuild_document.await_args_list[1].kwargs["batch_size"] == 6
