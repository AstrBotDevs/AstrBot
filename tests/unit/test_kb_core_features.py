import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.db.vec_db.base import Result
from astrbot.core.knowledge_base.capabilities import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_INDEX_TYPE,
    DEFAULT_TOP_K_DENSE,
    DEFAULT_TOP_K_SPARSE,
    DEFAULT_TOP_M_FINAL,
)
from astrbot.core.knowledge_base.chunking.markdown import MarkdownChunker
from astrbot.core.knowledge_base.kb_helper import (
    CONSISTENCY_CHECK_PAGE_SIZE,
    CONSISTENCY_REPAIR_TYPES,
    KBHelper,
)
from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
from astrbot.core.knowledge_base.models import KBDocument, KnowledgeBase
from astrbot.core.knowledge_base.parsers import pdf_parser
from astrbot.core.knowledge_base.parsers.pdf_parser import PDFParser
from astrbot.core.knowledge_base.retrieval.manager import (
    RetrievalManager,
    RetrievalResult,
)
from astrbot.core.knowledge_base.retrieval.rank_fusion import RankFusion
from astrbot.core.knowledge_base.retrieval.sparse_retriever import SparseResult


def test_knowledge_base_model_defaults_match_capabilities():
    kb = KnowledgeBase(kb_name="defaults", embedding_provider_id="emb-1")

    assert kb.chunk_size == DEFAULT_CHUNK_SIZE
    assert kb.chunk_overlap == DEFAULT_CHUNK_OVERLAP
    assert kb.top_k_dense == DEFAULT_TOP_K_DENSE
    assert kb.top_k_sparse == DEFAULT_TOP_K_SPARSE
    assert kb.top_m_final == DEFAULT_TOP_M_FINAL
    assert kb.index_type == DEFAULT_INDEX_TYPE


@pytest.mark.asyncio
async def test_create_kb_uses_capability_defaults(monkeypatch):
    from astrbot.core.knowledge_base.kb_helper import KBHelper
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

    manager = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    manager.provider_manager = MagicMock()
    manager.kb_db = MagicMock()
    manager.kb_insts = {}
    manager._kb_name_index = {}

    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)
    manager.kb_db.get_db.return_value = context

    async def initialize(self):
        return None

    monkeypatch.setattr(KBHelper, "initialize", initialize)

    kb_helper = await manager.create_kb(
        kb_name="defaults",
        embedding_provider_id="emb-1",
    )

    created_kb = session.add.call_args.args[0]
    assert created_kb is kb_helper.kb
    assert created_kb.chunk_size == DEFAULT_CHUNK_SIZE
    assert created_kb.chunk_overlap == DEFAULT_CHUNK_OVERLAP
    assert created_kb.top_k_dense == DEFAULT_TOP_K_DENSE
    assert created_kb.top_k_sparse == DEFAULT_TOP_K_SPARSE
    assert created_kb.top_m_final == DEFAULT_TOP_M_FINAL
    assert created_kb.index_type == DEFAULT_INDEX_TYPE


@pytest.mark.asyncio
async def test_markdown_chunk_returns_text_only_compatibility() -> None:
    chunker = MarkdownChunker(chunk_size=200, chunk_overlap=0)
    text = "# Guide\nIntro\n\n## Install\nStep one"

    chunks = await chunker.chunk(text)
    chunks_with_metadata = await chunker.chunk_with_metadata(text)

    assert chunks == [chunk.text for chunk in chunks_with_metadata]
    assert [chunk.title_path for chunk in chunks_with_metadata] == [
        ["Guide"],
        ["Guide", "Install"],
    ]
    assert [chunk.section_index for chunk in chunks_with_metadata] == [0, 1]


@pytest.mark.asyncio
async def test_markdown_split_chunks_keep_current_title_path() -> None:
    chunker = MarkdownChunker(chunk_size=80, chunk_overlap=0)
    text = "# Guide\n" + "\n".join(
        f"Long installation paragraph {idx}." for idx in range(12)
    )

    chunks = await chunker.chunk_with_metadata(text)

    assert len(chunks) > 1
    assert all(chunk.title_path == ["Guide"] for chunk in chunks)
    assert all(chunk.section_index == 0 for chunk in chunks)


@pytest.mark.asyncio
async def test_markdown_chunker_skips_front_matter() -> None:
    chunker = MarkdownChunker(chunk_size=200, chunk_overlap=0)
    text = "---\noutline: deep\n---\n\n# Guide\nVisible content"

    chunks = await chunker.chunk_with_metadata(text)

    assert len(chunks) == 1
    assert "outline: deep" not in chunks[0].text
    assert chunks[0].text.startswith("# Guide")


@pytest.mark.asyncio
async def test_markdown_chunker_splits_long_tables_with_header() -> None:
    chunker = MarkdownChunker(chunk_size=90, chunk_overlap=0)
    table_rows = "\n".join(f"| row-{idx} | value-{idx} |" for idx in range(8))
    text = "# Data\n| Name | Value |\n| --- | --- |\n" + table_rows

    chunks = await chunker.chunk_with_metadata(text)
    table_chunks = [chunk.text for chunk in chunks if "| Name | Value |" in chunk.text]

    assert len(table_chunks) > 1
    assert all("| --- | --- |" in chunk for chunk in table_chunks)
    assert all("| Name | Value |" in chunk for chunk in table_chunks)


@pytest.mark.asyncio
async def test_markdown_chunker_keeps_code_fences_when_splitting() -> None:
    chunker = MarkdownChunker(chunk_size=90, chunk_overlap=0)
    code = "\n".join(f"print('line {idx}')" for idx in range(12))
    text = f"# Code\n```python\n{code}\n```"

    chunks = await chunker.chunk_with_metadata(text)
    code_chunks = [chunk.text for chunk in chunks if "```python" in chunk.text]

    assert len(code_chunks) > 1
    assert all(chunk.count("```") == 2 for chunk in code_chunks)
    assert all(chunk.rstrip().endswith("```") for chunk in code_chunks)


@pytest.mark.asyncio
async def test_markdown_chunker_preserves_links_inside_long_paragraphs() -> None:
    chunker = MarkdownChunker(chunk_size=90, chunk_overlap=0)
    url = "https://example.com/docs/plugin-development-reference"
    text = (
        "# Links\nRead the official guide at "
        f"[plugin docs]({url}) "
        + "before changing provider settings. " * 5
    )

    chunks = await chunker.chunk_with_metadata(text)
    link_chunks = [chunk.text for chunk in chunks if "plugin docs" in chunk.text]

    assert len(link_chunks) == 1
    assert f"[plugin docs]({url})" in link_chunks[0]
    assert sum(chunk.text.count("[plugin docs](") for chunk in chunks) == 1


@pytest.mark.asyncio
async def test_markdown_chunker_keeps_callout_blocks_together() -> None:
    chunker = MarkdownChunker(chunk_size=200, chunk_overlap=0)
    text = (
        "# Notice\n"
        "> [!WARNING]\n"
        "> Keep the provider settings unchanged during migration.\n"
        "> Rebuild only new documents.\n\n"
        "Normal paragraph after the callout."
    )

    chunks = await chunker.chunk_with_metadata(text)
    callout_chunks = [chunk.text for chunk in chunks if "[!WARNING]" in chunk.text]

    assert len(callout_chunks) == 1
    assert "Rebuild only new documents." in callout_chunks[0]


@pytest.mark.asyncio
async def test_markdown_chunker_keeps_math_block_wrapped_when_splitting() -> None:
    chunker = MarkdownChunker(chunk_size=90, chunk_overlap=0)
    formula_lines = "\n".join(
        rf"a_{{{idx}}} = b_{{{idx}}} + c_{{{idx}}}" for idx in range(10)
    )
    text = f"# Math\n$$\n{formula_lines}\n$$"

    chunks = await chunker.chunk_with_metadata(text)
    math_chunks = [chunk.text for chunk in chunks if "$$" in chunk.text]

    assert len(math_chunks) > 1
    assert all(chunk.startswith("$$") or "\n$$" in chunk for chunk in math_chunks)
    assert all(chunk.rstrip().endswith("$$") for chunk in math_chunks)


@pytest.mark.asyncio
async def test_markdown_chunker_preserves_inline_math_spans() -> None:
    chunker = MarkdownChunker(chunk_size=80, chunk_overlap=0)
    formula = r"$E = mc^2 + \alpha + \beta + \gamma$"
    bracket_formula = r"\(a^2 + b^2 = c^2\)"
    text = (
        "# Math\n"
        "Use "
        f"{formula} and {bracket_formula} "
        + "inside a paragraph with enough surrounding words to split. " * 4
    )

    chunks = await chunker.chunk_with_metadata(text)
    inline_math_chunks = [
        chunk.text for chunk in chunks if "E = mc^2" in chunk.text
    ]
    bracket_math_chunks = [
        chunk.text for chunk in chunks if "a^2 + b^2" in chunk.text
    ]

    assert len(inline_math_chunks) == 1
    assert formula in inline_math_chunks[0]
    assert len(bracket_math_chunks) == 1
    assert bracket_formula in bracket_math_chunks[0]


@pytest.mark.asyncio
async def test_pdf_parser_preserves_page_number_segments(monkeypatch) -> None:
    page_one = MagicMock()
    page_one.extract_text.return_value = "Page one"
    page_two = MagicMock()
    page_two.extract_text.return_value = "Page two"
    reader = MagicMock()
    reader.pages = [page_one, page_two]
    monkeypatch.setattr(pdf_parser, "PdfReader", MagicMock(return_value=reader))

    result = await PDFParser().parse(b"pdf bytes", "guide.pdf")

    assert result.text == "Page one\n\nPage two"
    assert [segment.text for segment in result.text_segments or []] == [
        "Page one",
        "Page two",
    ]
    assert [segment.metadata for segment in result.text_segments or []] == [
        {"page_number": 1},
        {"page_number": 2},
    ]


def _manager() -> KnowledgeBaseManager:
    return KnowledgeBaseManager.__new__(KnowledgeBaseManager)


def test_format_result_source_includes_structural_metadata():
    manager = _manager()
    result = RetrievalResult(
        chunk_id="chunk-1",
        doc_id="doc-1",
        doc_name="guide.md",
        kb_id="kb-1",
        kb_name="Docs",
        content="content",
        score=0.9,
        metadata={
            "chunk_index": 3,
            "section_index": 2,
            "title_path": ["Plugin", "Install"],
            "page_number": 5,
            "parent_chunk_id": "parent-1",
        },
    )

    assert manager._format_result_source(result) == {
        "kb_name": "Docs",
        "document_name": "guide.md",
        "chunk_index": 3,
        "section_index": 2,
        "title_path": ["Plugin", "Install"],
        "page_number": 5,
        "parent_chunk_id": "parent-1",
    }


def test_format_context_includes_source_location_details():
    manager = _manager()
    result = RetrievalResult(
        chunk_id="chunk-1",
        doc_id="doc-1",
        doc_name="guide.md",
        kb_id="kb-1",
        kb_name="Docs",
        content="Install steps",
        score=0.91,
        metadata={
            "chunk_index": 0,
            "section_index": 2,
            "title_path": ["Plugin", "Install"],
            "page_number": 5,
        },
    )

    context = manager._format_context([result])

    assert "Docs / guide.md (Plugin > Install; 第 5 页; 章节 2)" in context
    assert "Install steps" in context


def _dense_result(
    *,
    chunk_id: str,
    doc_id: str,
    kb_id: str = "kb-1",
    chunk_index: int = 0,
    text: str,
    similarity: float,
    metadata: dict | None = None,
) -> Result:
    chunk_metadata = {
        "chunk_index": chunk_index,
        "kb_doc_id": doc_id,
        "kb_id": kb_id,
    }
    if metadata:
        chunk_metadata.update(metadata)
    return Result(
        similarity=similarity,
        data={
            "doc_id": chunk_id,
            "text": text,
            "metadata": json.dumps(chunk_metadata),
        },
    )


def _metadata(doc_id: str, kb_id: str = "kb-1") -> dict:
    return {
        "document": SimpleNamespace(doc_id=doc_id, doc_name=f"{doc_id}.md"),
        "knowledge_base": SimpleNamespace(kb_id=kb_id, kb_name="kb"),
    }


def test_build_kb_options_uses_capability_defaults_for_empty_kb_values():
    manager = RetrievalManager(
        sparse_retriever=SimpleNamespace(),
        rank_fusion=SimpleNamespace(),
        kb_db=SimpleNamespace(),
    )
    kb_helper = SimpleNamespace(
        kb=SimpleNamespace(
            top_k_dense=None,
            top_k_sparse=None,
            top_m_final=None,
            rerank_provider_id=None,
        ),
        vec_db=SimpleNamespace(),
    )

    kb_ids, kb_options = manager._build_kb_options(
        ["kb-1"],
        {"kb-1": kb_helper},
    )

    assert kb_ids == ["kb-1"]
    assert kb_options["kb-1"]["top_k_dense"] == DEFAULT_TOP_K_DENSE
    assert kb_options["kb-1"]["top_k_sparse"] == DEFAULT_TOP_K_SPARSE
    assert kb_options["kb-1"]["top_m_final"] == DEFAULT_TOP_M_FINAL


@pytest.mark.asyncio
async def test_retrieve_with_trace_exposes_pipeline_stages_and_ranks():
    dense_results = [
        _dense_result(
            chunk_id="chunk-b",
            doc_id="doc-b",
            chunk_index=1,
            text="dense only content",
            similarity=0.92,
        ),
        _dense_result(
            chunk_id="chunk-a",
            doc_id="doc-a",
            chunk_index=0,
            text="hybrid dense content",
            similarity=0.81,
        ),
    ]
    sparse_results = [
        SparseResult(
            chunk_id="chunk-a",
            chunk_index=0,
            doc_id="doc-a",
            kb_id="kb-1",
            content="hybrid sparse content",
            score=0.0,
            metadata={
                "chunk_index": 0,
                "kb_doc_id": "doc-a",
                "kb_id": "kb-1",
                "title_path": ["Guide", "Install"],
                "page_number": 2,
            },
        ),
        SparseResult(
            chunk_id="chunk-c",
            chunk_index=2,
            doc_id="doc-c",
            kb_id="kb-1",
            content="sparse only content",
            score=4.0,
        ),
    ]

    vec_db = SimpleNamespace(retrieve=AsyncMock(return_value=dense_results))
    kb_helper = SimpleNamespace(
        kb=SimpleNamespace(
            top_k_dense=2,
            top_k_sparse=2,
            top_m_final=2,
            rerank_provider_id=None,
        ),
        vec_db=vec_db,
    )
    sparse_retriever = SimpleNamespace(
        retrieve=AsyncMock(return_value=sparse_results),
    )
    kb_db = SimpleNamespace(
        get_documents_with_metadata_batch=AsyncMock(
            return_value={
                "doc-a": _metadata("doc-a"),
                "doc-b": _metadata("doc-b"),
                "doc-c": _metadata("doc-c"),
            },
        ),
    )
    manager = RetrievalManager(
        sparse_retriever=sparse_retriever,
        rank_fusion=RankFusion(kb_db),
        kb_db=kb_db,
    )

    response = await manager.retrieve_with_trace(
        query="hybrid",
        kb_ids=["kb-1"],
        kb_id_helper_map={"kb-1": kb_helper},
        top_k_fusion=3,
        top_m_final=2,
    )

    assert [result.chunk_id for result in response.results] == [
        "chunk-a",
        "chunk-b",
    ]
    trace = response.trace.to_dict()
    assert set(trace) == {
        "dense",
        "sparse",
        "fusion",
        "dedup",
        "dedup_removed",
        "rerank",
        "final",
    }
    assert [item["chunk_id"] for item in trace["dense"]] == ["chunk-b", "chunk-a"]
    assert [item["chunk_id"] for item in trace["sparse"]] == ["chunk-a", "chunk-c"]

    hybrid_trace = trace["fusion"][0]
    assert hybrid_trace["chunk_id"] == "chunk-a"
    assert hybrid_trace["dense_rank"] == 2
    assert hybrid_trace["sparse_rank"] == 1
    assert hybrid_trace["dense_score"] == 0.81
    assert hybrid_trace["sparse_score"] == 0.0
    assert hybrid_trace["rrf_score"] == hybrid_trace["score"]
    assert hybrid_trace["doc_name"] == "doc-a.md"
    assert hybrid_trace["score"] > trace["fusion"][1]["score"]
    assert hybrid_trace["title_path"] == ["Guide", "Install"]
    assert hybrid_trace["page_number"] == 2

    assert [item["chunk_id"] for item in trace["dedup"]] == [
        "chunk-a",
        "chunk-b",
        "chunk-c",
    ]
    assert trace["dedup_removed"] == []
    assert trace["rerank"] == []
    assert [item["chunk_id"] for item in trace["final"]] == ["chunk-a", "chunk-b"]
    assert trace["final"][0]["title_path"] == ["Guide", "Install"]
    assert trace["final"][0]["page_number"] == 2
    assert trace["final"][0]["dense_score"] == 0.81
    assert trace["final"][0]["sparse_score"] == 0.0
    assert trace["final"][0]["rrf_score"] == trace["final"][0]["score"]


@pytest.mark.asyncio
async def test_retrieve_with_trace_deduplicates_near_identical_contexts():
    dense_results = [
        _dense_result(
            chunk_id="chunk-a",
            doc_id="doc-a",
            chunk_index=0,
            text="Install AstrBot plugin with pip and restart the service.",
            similarity=0.95,
        ),
        _dense_result(
            chunk_id="chunk-b",
            doc_id="doc-b",
            chunk_index=1,
            text="Install AstrBot plugin with pip and restart the service.",
            similarity=0.93,
        ),
        _dense_result(
            chunk_id="chunk-c",
            doc_id="doc-c",
            chunk_index=2,
            text="Configure the provider in the dashboard settings.",
            similarity=0.75,
        ),
    ]

    vec_db = SimpleNamespace(retrieve=AsyncMock(return_value=dense_results))
    kb_helper = SimpleNamespace(
        kb=SimpleNamespace(
            top_k_dense=3,
            top_k_sparse=1,
            top_m_final=3,
            rerank_provider_id=None,
        ),
        vec_db=vec_db,
    )
    sparse_retriever = SimpleNamespace(retrieve=AsyncMock(return_value=[]))
    kb_db = SimpleNamespace(
        get_documents_with_metadata_batch=AsyncMock(
            return_value={
                "doc-a": _metadata("doc-a"),
                "doc-b": _metadata("doc-b"),
                "doc-c": _metadata("doc-c"),
            },
        ),
    )
    manager = RetrievalManager(
        sparse_retriever=sparse_retriever,
        rank_fusion=RankFusion(kb_db),
        kb_db=kb_db,
    )

    response = await manager.retrieve_with_trace(
        query="install plugin",
        kb_ids=["kb-1"],
        kb_id_helper_map={"kb-1": kb_helper},
        top_k_fusion=3,
        top_m_final=3,
    )

    trace = response.trace.to_dict()
    assert [item["chunk_id"] for item in trace["fusion"]] == [
        "chunk-a",
        "chunk-b",
        "chunk-c",
    ]
    assert [item["chunk_id"] for item in trace["dedup"]] == [
        "chunk-a",
        "chunk-c",
    ]
    assert [item["chunk_id"] for item in trace["dedup_removed"]] == ["chunk-b"]
    assert trace["dedup_removed"][0]["duplicate_of_chunk_id"] == "chunk-a"
    assert trace["dedup_removed"][0]["duplicate_of_doc_id"] == "doc-a"
    assert trace["dedup_removed"][0]["dedup_similarity"] == 1.0
    assert [result.chunk_id for result in response.results] == [
        "chunk-a",
        "chunk-c",
    ]


@pytest.mark.asyncio
async def test_retrieve_with_trace_applies_temporary_retrieval_overrides():
    dense_results = [
        _dense_result(
            chunk_id="chunk-a",
            doc_id="doc-a",
            text="temporary override content",
            similarity=0.9,
        ),
    ]
    vec_db = SimpleNamespace(retrieve=AsyncMock(return_value=dense_results))
    kb = SimpleNamespace(
        top_k_dense=10,
        top_k_sparse=10,
        top_m_final=5,
        rerank_provider_id="rerank-1",
    )
    kb_helper = SimpleNamespace(kb=kb, vec_db=vec_db)
    sparse_retriever = SimpleNamespace(retrieve=AsyncMock(return_value=[]))
    kb_db = SimpleNamespace(
        get_documents_with_metadata_batch=AsyncMock(
            return_value={"doc-a": _metadata("doc-a")},
        ),
    )
    manager = RetrievalManager(
        sparse_retriever=sparse_retriever,
        rank_fusion=RankFusion(kb_db),
        kb_db=kb_db,
    )

    response = await manager.retrieve_with_trace(
        query="override",
        kb_ids=["kb-1"],
        kb_id_helper_map={"kb-1": kb_helper},
        top_k_fusion=3,
        top_m_final=2,
        retrieval_overrides={
            "top_k_dense": 2,
            "top_k_sparse": 3,
            "top_m_final": 2,
            "rerank_provider_id": None,
        },
    )

    assert [result.chunk_id for result in response.results] == ["chunk-a"]
    vec_db.retrieve.assert_awaited_once()
    assert vec_db.retrieve.await_args.kwargs["k"] == 2
    assert vec_db.retrieve.await_args.kwargs["fetch_k"] == 4
    sparse_retriever.retrieve.assert_awaited_once()
    assert (
        sparse_retriever.retrieve.await_args.kwargs["kb_options"]["kb-1"][
            "top_k_sparse"
        ]
        == 3
    )
    assert (
        sparse_retriever.retrieve.await_args.kwargs["kb_options"]["kb-1"][
            "rerank_provider_id"
        ]
        is None
    )
    assert kb.top_k_dense == 10
    assert kb.top_k_sparse == 10
    assert kb.rerank_provider_id == "rerank-1"


@pytest.mark.asyncio
async def test_retrieve_with_trace_preserves_rerank_and_rrf_scores():
    dense_results = [
        _dense_result(
            chunk_id="chunk-a",
            doc_id="doc-a",
            text="alpha content",
            similarity=0.9,
        ),
        _dense_result(
            chunk_id="chunk-b",
            doc_id="doc-b",
            text="beta content",
            similarity=0.8,
        ),
    ]

    class FakeRerankProvider:
        def meta(self):
            return SimpleNamespace(id="rerank-1")

        async def rerank(self, *, query, documents):
            assert query == "rerank"
            assert documents == ["alpha content", "beta content"]
            return [
                SimpleNamespace(index=1, relevance_score=0.95),
                SimpleNamespace(index=0, relevance_score=0.4),
            ]

    vec_db = SimpleNamespace(
        retrieve=AsyncMock(return_value=dense_results),
        rerank_provider=FakeRerankProvider(),
    )
    kb_helper = SimpleNamespace(
        kb=SimpleNamespace(
            top_k_dense=2,
            top_k_sparse=0,
            top_m_final=2,
            rerank_provider_id="rerank-1",
        ),
        vec_db=vec_db,
    )
    sparse_retriever = SimpleNamespace(retrieve=AsyncMock(return_value=[]))
    kb_db = SimpleNamespace(
        get_documents_with_metadata_batch=AsyncMock(
            return_value={
                "doc-a": _metadata("doc-a"),
                "doc-b": _metadata("doc-b"),
            },
        ),
    )
    manager = RetrievalManager(
        sparse_retriever=sparse_retriever,
        rank_fusion=RankFusion(kb_db),
        kb_db=kb_db,
    )

    response = await manager.retrieve_with_trace(
        query="rerank",
        kb_ids=["kb-1"],
        kb_id_helper_map={"kb-1": kb_helper},
        top_k_fusion=2,
        top_m_final=2,
    )

    trace = response.trace.to_dict()
    assert [result.chunk_id for result in response.results] == [
        "chunk-b",
        "chunk-a",
    ]
    assert [item["chunk_id"] for item in trace["rerank"]] == [
        "chunk-b",
        "chunk-a",
    ]
    assert trace["final"][0]["chunk_id"] == "chunk-b"
    assert trace["final"][0]["score"] == 0.95
    assert trace["final"][0]["rerank_score"] == 0.95
    assert trace["final"][0]["rrf_score"] != trace["final"][0]["rerank_score"]
    assert trace["final"][0]["dense_score"] == 0.8


def _build_doc(
    *,
    doc_id: str,
    file_path: str,
    chunk_count: int,
    status: str = "ready",
    source_type: str = "file",
) -> KBDocument:
    return KBDocument(
        doc_id=doc_id,
        kb_id="kb-1",
        doc_name=f"{doc_id}.md",
        file_type="md",
        file_size=1,
        file_path=file_path,
        source_type=source_type,
        status=status,
        chunk_count=chunk_count,
    )


@pytest.mark.asyncio
async def test_check_consistency_reports_metadata_file_and_vector_issues(tmp_path):
    files_root = tmp_path / "files" / "kb-1"
    source_path = files_root / "doc-ok" / "ok.md"
    source_path.parent.mkdir(parents=True)
    source_path.write_text("hello", encoding="utf-8")
    outside_source_path = tmp_path / "outside.md"
    outside_source_path.write_text("outside", encoding="utf-8")

    docs = [
        _build_doc(
            doc_id="doc-ok",
            file_path=str(source_path),
            chunk_count=2,
        ),
        _build_doc(
            doc_id="doc-missing",
            file_path=str(files_root / "doc-missing" / "missing.md"),
            chunk_count=1,
        ),
        _build_doc(
            doc_id="doc-unsafe",
            file_path=str(outside_source_path),
            chunk_count=0,
        ),
    ]
    chunks = [
        {
            "id": 1,
            "doc_id": "chunk-ok-1",
            "text": "hello",
            "metadata": json.dumps(
                {"kb_id": "kb-1", "kb_doc_id": "doc-ok", "chunk_index": 0},
            ),
        },
        {
            "id": 2,
            "doc_id": "chunk-orphan",
            "text": "orphan",
            "metadata": json.dumps(
                {"kb_id": "kb-1", "kb_doc_id": "doc-gone", "chunk_index": 0},
            ),
        },
        {
            "id": 3,
            "doc_id": "chunk-invalid",
            "text": "bad",
            "metadata": "{not-json",
        },
    ]

    storage = MagicMock()
    storage.get_documents = AsyncMock(return_value=chunks)
    vec_db = MagicMock()
    vec_db.document_storage = storage

    helper = KBHelper.__new__(KBHelper)
    helper.kb = KnowledgeBase(
        kb_id="kb-1",
        kb_name="kb",
        embedding_provider_id="emb-1",
    )
    helper.kb_files_dir = files_root
    helper.vec_db = vec_db
    helper.list_documents = AsyncMock(return_value=docs)

    report = await KBHelper.check_consistency(helper)

    assert report["kb_id"] == "kb-1"
    assert report["summary"]["sqlite_document_count"] == 3
    assert report["summary"]["document_chunk_count"] == 3
    assert report["summary"]["indexed_chunk_count"] == 3
    assert report["summary"]["source_file_count"] == 1
    assert report["summary"]["missing_vectors"] == 1
    assert report["summary"]["orphan_vectors"] == 1
    assert report["summary"]["missing_source_files"] == 1
    assert report["summary"]["chunk_count_mismatches"] == 2
    assert report["summary"]["invalid_vector_metadata"] == 1
    assert report["summary"]["unsafe_source_paths"] == 1
    assert report["summary"]["healthy"] is False
    assert report["issues"]["missing_vectors"][0]["doc_id"] == "doc-missing"
    assert report["issues"]["orphan_vectors"][0]["doc_id"] == "doc-gone"
    assert report["issues"]["unsafe_source_paths"][0]["doc_id"] == "doc-unsafe"
    assert (
        report["issues"]["invalid_vector_metadata"][0]["metadata_error"]
        == "invalid metadata JSON"
    )

    helper.list_documents.assert_awaited_once_with(offset=0, limit=1000)
    storage.get_documents.assert_awaited_once_with(
        metadata_filters={"kb_id": "kb-1"},
        offset=0,
        limit=1000,
    )


@pytest.mark.asyncio
async def test_check_consistency_reads_all_document_and_chunk_pages(tmp_path):
    docs = [
        _build_doc(
            doc_id=f"doc-{index}",
            file_path="",
            chunk_count=0,
        )
        for index in range(CONSISTENCY_CHECK_PAGE_SIZE + 1)
    ]
    chunks = [
        {
            "id": index,
            "doc_id": f"chunk-{index}",
            "text": "hello",
            "metadata": json.dumps(
                {
                    "kb_id": "kb-1",
                    "kb_doc_id": f"doc-{index}",
                    "chunk_index": 0,
                },
            ),
        }
        for index in range(CONSISTENCY_CHECK_PAGE_SIZE + 1)
    ]

    async def list_documents(offset=0, limit=100):
        return docs[offset : offset + limit]

    async def list_chunks(metadata_filters=None, offset=0, limit=100):
        return chunks[offset : offset + limit]

    storage = MagicMock()
    storage.get_documents = AsyncMock(side_effect=list_chunks)
    vec_db = MagicMock()
    vec_db.document_storage = storage

    helper = KBHelper.__new__(KBHelper)
    helper.kb = KnowledgeBase(
        kb_id="kb-1",
        kb_name="kb",
        embedding_provider_id="emb-1",
    )
    helper.kb_files_dir = tmp_path
    helper.vec_db = vec_db
    helper.list_documents = AsyncMock(side_effect=list_documents)

    report = await KBHelper.check_consistency(helper)

    assert report["summary"]["sqlite_document_count"] == len(docs)
    assert report["summary"]["indexed_chunk_count"] == len(chunks)
    assert helper.list_documents.await_args_list[0].kwargs == {
        "offset": 0,
        "limit": CONSISTENCY_CHECK_PAGE_SIZE,
    }
    assert helper.list_documents.await_args_list[1].kwargs == {
        "offset": CONSISTENCY_CHECK_PAGE_SIZE,
        "limit": CONSISTENCY_CHECK_PAGE_SIZE,
    }
    assert storage.get_documents.await_args_list[0].kwargs == {
        "metadata_filters": {"kb_id": "kb-1"},
        "offset": 0,
        "limit": CONSISTENCY_CHECK_PAGE_SIZE,
    }
    assert storage.get_documents.await_args_list[1].kwargs == {
        "metadata_filters": {"kb_id": "kb-1"},
        "offset": CONSISTENCY_CHECK_PAGE_SIZE,
        "limit": CONSISTENCY_CHECK_PAGE_SIZE,
    }


@pytest.mark.asyncio
async def test_check_consistency_reports_unsupported_storage_backend():
    helper = KBHelper.__new__(KBHelper)
    helper.kb = KnowledgeBase(
        kb_id="kb-1",
        kb_name="kb",
        embedding_provider_id="emb-1",
    )
    helper.vec_db = MagicMock()
    helper.list_documents = AsyncMock(return_value=[])

    with pytest.raises(ValueError, match="不支持一致性检查"):
        await KBHelper.check_consistency(helper)


@pytest.mark.asyncio
async def test_repair_consistency_repairs_safe_issues_and_skips_rebuild_cases():
    pre_report = {
        "kb_id": "kb-1",
        "kb_name": "kb",
        "checked_at": "2026-06-01T00:00:00+00:00",
        "summary": {"healthy": False},
        "issues": {
            "orphan_vectors": [
                {"doc_id": "doc-gone", "chunk_id": "chunk-1"},
                {"doc_id": "doc-gone", "chunk_id": "chunk-2"},
            ],
            "chunk_count_mismatches": [
                {
                    "doc_id": "doc-extra-indexed",
                    "expected_chunk_count": 1,
                    "actual_chunk_count": 2,
                },
                {
                    "doc_id": "doc-missing-index",
                    "expected_chunk_count": 3,
                    "actual_chunk_count": 1,
                },
            ],
            "missing_vectors": [{"doc_id": "doc-missing-index"}],
            "missing_source_files": [{"doc_id": "doc-missing-file"}],
            "invalid_vector_metadata": [{"chunk_id": "chunk-invalid"}],
            "unsafe_source_paths": [{"doc_id": "doc-unsafe"}],
        },
    }
    post_report = copy.deepcopy(pre_report)
    post_report["summary"] = {"healthy": True}
    post_report["issues"] = {
        "orphan_vectors": [],
        "chunk_count_mismatches": [],
        "missing_vectors": [],
        "missing_source_files": [],
        "invalid_vector_metadata": [],
        "unsafe_source_paths": [],
    }

    vec_db = MagicMock()
    vec_db.delete_documents = AsyncMock()
    kb_db = MagicMock()
    kb_db.update_kb_stats = AsyncMock()

    helper = KBHelper.__new__(KBHelper)
    helper.kb = KnowledgeBase(
        kb_id="kb-1",
        kb_name="kb",
        embedding_provider_id="emb-1",
    )
    helper.vec_db = vec_db
    helper.kb_db = kb_db
    helper.check_consistency = AsyncMock(side_effect=[pre_report, post_report])
    helper.refresh_document = AsyncMock()
    helper.refresh_kb = AsyncMock()

    result = await KBHelper.repair_consistency(helper)

    assert result["repair_types"] == sorted(CONSISTENCY_REPAIR_TYPES)
    assert result["summary"] == {
        "repaired_count": 2,
        "skipped_count": 5,
        "failed_count": 0,
        "healthy_after_repair": True,
    }
    vec_db.delete_documents.assert_awaited_once_with(
        metadata_filters={"kb_id": "kb-1", "kb_doc_id": "doc-gone"},
    )
    helper.refresh_document.assert_awaited_once_with("doc-extra-indexed")
    kb_db.update_kb_stats.assert_awaited_once_with(
        kb_id="kb-1",
        vec_db=vec_db,
    )
    helper.refresh_kb.assert_awaited_once_with()
    assert result["actions"]["repaired"][0]["type"] == "orphan_vectors"
    assert result["actions"]["repaired"][0]["count"] == 2
    assert any(
        action["type"] == "chunk_count_mismatches"
        and action["reason"] == "missing_vectors_require_rebuild"
        for action in result["actions"]["skipped"]
    )
    assert any(
        action["type"] == "missing_vectors"
        and action["reason"] == "document_rebuild_required"
        for action in result["actions"]["skipped"]
    )


@pytest.mark.asyncio
async def test_repair_consistency_only_runs_selected_repair_types():
    pre_report = {
        "kb_id": "kb-1",
        "kb_name": "kb",
        "checked_at": "2026-06-01T00:00:00+00:00",
        "summary": {"healthy": False},
        "issues": {
            "orphan_vectors": [{"doc_id": "doc-gone", "chunk_id": "chunk-1"}],
            "chunk_count_mismatches": [
                {
                    "doc_id": "doc-extra-indexed",
                    "expected_chunk_count": 1,
                    "actual_chunk_count": 2,
                },
            ],
            "missing_vectors": [],
            "missing_source_files": [],
            "invalid_vector_metadata": [],
            "unsafe_source_paths": [],
        },
    }
    post_report = copy.deepcopy(pre_report)

    vec_db = MagicMock()
    vec_db.delete_documents = AsyncMock()
    kb_db = MagicMock()
    kb_db.update_kb_stats = AsyncMock()

    helper = KBHelper.__new__(KBHelper)
    helper.kb = KnowledgeBase(
        kb_id="kb-1",
        kb_name="kb",
        embedding_provider_id="emb-1",
    )
    helper.vec_db = vec_db
    helper.kb_db = kb_db
    helper.check_consistency = AsyncMock(side_effect=[pre_report, post_report])
    helper.refresh_document = AsyncMock()
    helper.refresh_kb = AsyncMock()

    result = await KBHelper.repair_consistency(
        helper,
        repair_types=["chunk_count_mismatches"],
    )

    assert result["repair_types"] == ["chunk_count_mismatches"]
    vec_db.delete_documents.assert_not_awaited()
    helper.refresh_document.assert_awaited_once_with("doc-extra-indexed")


def test_normalize_consistency_repair_types_rejects_unknown_types():
    with pytest.raises(ValueError, match="unsupported"):
        KBHelper._normalize_consistency_repair_types(["unsupported"])
