"""
Unit tests for knowledge base parser selection and missing-dependency errors.

Covers:
1. .txt / .md / .markdown are routed to the stdlib TextParser (no third-party
   dependency required), so plain-text uploads work without markitdown.
2. .rst / .adoc keep routing to MarkitdownParser (requires markitdown).
3. upload_document surfaces a clear missing-dependency message when
   markitdown-no-magika is absent, instead of the generic parse failure.
4. A missing unrelated module (e.g. pypdf) is not mislabeled as a markitdown
   problem.
"""

import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.exceptions import KnowledgeBaseUploadError
from astrbot.core.knowledge_base.models import KnowledgeBase
from astrbot.core.knowledge_base.parsers.text_parser import TextParser
from astrbot.core.knowledge_base.parsers.util import select_parser


@pytest.fixture
def stub_provider_manager_module():
    """Stub provider manager module to avoid circular imports in unit tests."""
    original_module = sys.modules.get("astrbot.core.provider.manager")
    stub_module = types.ModuleType("astrbot.core.provider.manager")

    class ProviderManager: ...

    setattr(stub_module, "ProviderManager", ProviderManager)
    sys.modules["astrbot.core.provider.manager"] = stub_module

    # Drop already-imported modules that transitively need ProviderManager so
    # they re-import against the stub.
    to_drop = [
        name
        for name in list(sys.modules)
        if name.startswith("astrbot.core.knowledge_base.kb_helper")
        or name.startswith("astrbot.core.knowledge_base.kb_mgr")
    ]
    for name in to_drop:
        sys.modules.pop(name, None)

    try:
        yield
    finally:
        if original_module is not None:
            sys.modules["astrbot.core.provider.manager"] = original_module
        else:
            sys.modules.pop("astrbot.core.provider.manager", None)


def _import_kb_helper():
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    return KBHelper


@pytest.mark.asyncio
@pytest.mark.parametrize("ext", [".txt", ".md", ".markdown"])
async def test_select_parser_routes_plain_text_to_text_parser(ext):
    parser = await select_parser(ext)

    assert isinstance(parser, TextParser)


@pytest.mark.asyncio
@pytest.mark.parametrize("ext", [".rst", ".adoc"])
async def test_select_parser_keeps_markup_formats_on_markitdown(ext):
    pytest.importorskip("markitdown_no_magika")

    from astrbot.core.knowledge_base.parsers.markitdown_parser import MarkitdownParser

    parser = await select_parser(ext)

    assert isinstance(parser, MarkitdownParser)


@pytest.mark.asyncio
async def test_text_parser_decodes_plain_text_file():
    result = await TextParser().parse("你好 world\nsecond line".encode(), "note.txt")
    assert result.media == []
    assert result.text == "你好 world\nsecond line"

    gbk_result = await TextParser().parse("中文内容".encode("gbk"), "note.txt")
    assert gbk_result.text == "中文内容"


def _make_upload_helper(tmp_path: Path):
    KBHelper = _import_kb_helper()

    helper = KBHelper.__new__(KBHelper)
    helper.kb = KnowledgeBase(
        kb_name="Test KB",
        description="",
        embedding_provider_id="emb",
    )
    helper.kb_db = MagicMock()
    helper.vec_db = AsyncMock()
    helper.vec_db.delete_documents = AsyncMock()
    helper.kb_medias_dir = tmp_path / "medias"
    helper.chunker = AsyncMock()
    return helper


@pytest.mark.asyncio
async def test_upload_document_reports_missing_markitdown_dependency(
    tmp_path: Path,
    stub_provider_manager_module,
) -> None:
    helper = _make_upload_helper(tmp_path)

    with (
        patch(
            "astrbot.core.knowledge_base.kb_helper.select_parser",
            new=AsyncMock(
                side_effect=ModuleNotFoundError(
                    "No module named 'markitdown_no_magika'",
                    name="markitdown_no_magika",
                ),
            ),
        ),
        patch.object(helper, "_ensure_vec_db", new=AsyncMock()),
        pytest.raises(KnowledgeBaseUploadError) as exc_info,
    ):
        await helper.upload_document(
            file_name="guide.docx",
            file_content=b"fake",
            file_type="docx",
        )

    assert exc_info.value.stage == "parsing"
    assert "markitdown-no-magika" in exc_info.value.user_message


@pytest.mark.asyncio
async def test_upload_document_passes_through_unrelated_missing_module(
    tmp_path: Path,
    stub_provider_manager_module,
) -> None:
    helper = _make_upload_helper(tmp_path)

    with (
        patch(
            "astrbot.core.knowledge_base.kb_helper.select_parser",
            new=AsyncMock(
                side_effect=ModuleNotFoundError(
                    "No module named 'pypdf'",
                    name="pypdf",
                ),
            ),
        ),
        patch.object(helper, "_ensure_vec_db", new=AsyncMock()),
        pytest.raises(ModuleNotFoundError) as exc_info,
    ):
        await helper.upload_document(
            file_name="guide.pdf",
            file_content=b"fake",
            file_type="pdf",
        )

    assert exc_info.value.name == "pypdf"
