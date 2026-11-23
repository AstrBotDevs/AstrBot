"""Regression coverage for Markdown budgets and URL cleaning fallbacks."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

# Import the application entry point to initialize the real provider/KB graph.
import astrbot.core.core_lifecycle  # noqa: F401
from astrbot.core.knowledge_base.chunking.markdown import MarkdownChunker
from astrbot.core.knowledge_base.chunking.recursive import RecursiveCharacterChunker
from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
from astrbot.core.knowledge_base.kb_helper import KBHelper
from astrbot.core.knowledge_base.models import KBDocument, KnowledgeBase
from astrbot.core.provider.manager import ProviderManager


@pytest.mark.asyncio
@pytest.mark.parametrize("override_defaults", [False, True])
async def test_markdown_long_parent_heading_reserves_a_valid_body_budget(
    override_defaults,
):
    """Issue #9998: heading context must fit without invalidating overlap."""
    parent_heading = "P" * 200
    body = "".join(chr(0x4E00 + index) for index in range(300))
    text = f"# {parent_heading}\n\n## Child\n{body}"
    if override_defaults:
        chunker = MarkdownChunker()
        chunks = await chunker.chunk(text, chunk_size=256, chunk_overlap=100)
    else:
        chunker = MarkdownChunker(chunk_size=256, chunk_overlap=100)
        chunks = await chunker.chunk(text)

    assert len(chunks) > 2
    assert all(len(chunk) <= 256 for chunk in chunks)
    assert any("## Child" in chunk for chunk in chunks)
    body_characters = set(body)
    body_chunks = [chunk for chunk in chunks if body_characters.intersection(chunk)]
    assert body_chunks
    assert all(
        chunk.startswith((f"{parent_heading}\n\n", f"... {parent_heading}\n\n"))
        for chunk in body_chunks
    )
    segments = [
        "".join(character for character in chunk if character in body_characters)
        for chunk in body_chunks
    ]
    assert all(segment in body for segment in segments)
    assert set("".join(segments)) == body_characters


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("heading_lengths", "continuation_prefix"),
    [
        ((250,), "..."),
        ((256,), "..."),
        ((512,), "..."),
        ((80, 80, 80, 80, 80), "..."),
        ((32,), "continued " * 32),
    ],
)
async def test_markdown_unfittable_context_preserves_original_content(
    heading_lengths, continuation_prefix
):
    """Keep all original text when repeated ancestor context cannot fit."""
    headings = []
    offset = 0
    for length in heading_lengths:
        headings.append("".join(chr(0x4E00 + offset + i) for i in range(length)))
        offset += length
    leaf_title = "终章"
    body = "".join(chr(0x8000 + index) for index in range(700))
    lines = [f"{'#' * level} {title}" for level, title in enumerate(headings, 1)]
    lines.extend([f"{'#' * (len(headings) + 1)} {leaf_title}", body])
    chunker = MarkdownChunker(
        chunk_size=256,
        chunk_overlap=100,
        max_heading_depth=6,
        min_chunk_size=128,
        continuation_prefix=continuation_prefix,
    )

    chunks = await chunker.chunk("\n\n".join(lines))

    assert chunks
    assert all(chunk and len(chunk) <= 256 for chunk in chunks)
    # Distinct source characters let us verify order through repeated context
    # and overlap without depending on where the chunker chooses boundaries.
    source_characters = iter("".join(headings) + leaf_title + body)
    expected = next(source_characters, None)
    for character in "".join(chunks):
        if character == expected:
            expected = next(source_characters, None)
    assert expected is None


@pytest.mark.asyncio
async def test_recursive_overlap_respects_the_next_paragraph_budget():
    """A nearly full paragraph leaves room for only part of the overlap."""
    first = "A" * 100
    second = "B" * 120
    text = f"{first}\n\n{second}"

    chunks = await RecursiveCharacterChunker(chunk_size=128, chunk_overlap=16).chunk(
        text
    )

    assert len(chunks) == 2
    assert all(len(chunk) <= 128 for chunk in chunks)
    assert chunks[0] == f"{first}\n\n"
    assert chunks[1].endswith(second)
    overlap = len(chunks[0]) + len(chunks[1]) - len(text)
    assert 0 < overlap <= 16
    assert chunks[0][-overlap:] == chunks[1][:overlap]
    assert chunks[0] + chunks[1][overlap:] == text


@pytest.mark.asyncio
async def test_markdown_oversized_context_keeps_paragraph_chunks_bounded():
    """Removing unfit context must also retain the recursive body budget."""
    heading = "H" * 128
    first = "A" * 100
    second = "B" * 120
    text = f"# {heading}\n\n## Child\n{first}\n\n{second}"

    chunks = await MarkdownChunker(chunk_size=128, chunk_overlap=16).chunk(text)

    assert all(chunk and len(chunk) <= 128 for chunk in chunks)
    assert any(heading in chunk for chunk in chunks)
    assert any(first in chunk for chunk in chunks)
    assert any(second in chunk for chunk in chunks)
    assert any("## Child" in chunk for chunk in chunks)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fallback",
    ["disabled", "missing_id", "missing_provider", "invalid_provider", "lookup_error"],
)
async def test_url_cleaning_fallback_preserves_requested_chunking(
    tmp_path, monkeypatch, fallback
):
    """Issue #9999: URL fallbacks must retain the caller's size and overlap."""
    content = "".join(chr(0x4E00 + index) for index in range(700))
    provider_manager = MagicMock(spec=ProviderManager)
    provider_manager.acm = SimpleNamespace(
        default_conf={"provider_settings": {"websearch_tavily_key": ["test-key"]}}
    )
    provider_manager.get_provider_by_id = AsyncMock(return_value=None)
    if fallback == "invalid_provider":
        provider_manager.get_provider_by_id.return_value = object()
    elif fallback == "lookup_error":
        provider_manager.get_provider_by_id.side_effect = RuntimeError(
            "Provider lookup failed"
        )

    helper = KBHelper(
        kb_db=MagicMock(spec=KBSQLiteDatabase),
        kb=KnowledgeBase(kb_name="Chunking regression"),
        provider_manager=provider_manager,
        kb_root_dir=str(tmp_path),
        chunker=RecursiveCharacterChunker(),
    )
    document = KBDocument(
        kb_id=helper.kb.kb_id,
        doc_name="knowledge.url",
        file_type="url",
        file_size=len(content),
        file_path="",
    )
    upload = AsyncMock(return_value=document)
    monkeypatch.setattr(helper, "upload_document", upload)
    extract = AsyncMock(return_value=content)
    monkeypatch.setattr(
        "astrbot.core.knowledge_base.kb_helper.extract_text_from_url", extract
    )

    result = await helper.upload_from_url(
        "https://example.com/knowledge",
        chunk_size=128,
        chunk_overlap=16,
        enable_cleaning=fallback != "disabled",
        cleaning_provider_id=None if fallback == "missing_id" else "cleaner",
    )

    assert result is document
    extract.assert_awaited_once_with("https://example.com/knowledge", ["test-key"])
    upload.assert_awaited_once()
    upload_arguments = upload.await_args.kwargs
    assert upload_arguments["chunk_size"] == 128
    assert upload_arguments["chunk_overlap"] == 16
    chunks = upload_arguments["pre_chunked_text"]
    assert len(chunks) == 7
    assert all(len(chunk) == 128 for chunk in chunks[:-1])
    assert all(
        previous[-16:] == current[:16] for previous, current in zip(chunks, chunks[1:])
    )
    assert chunks[0] + "".join(chunk[16:] for chunk in chunks[1:]) == content
    if fallback in {"disabled", "missing_id"}:
        provider_manager.get_provider_by_id.assert_not_awaited()
    else:
        provider_manager.get_provider_by_id.assert_awaited_once_with("cleaner")
