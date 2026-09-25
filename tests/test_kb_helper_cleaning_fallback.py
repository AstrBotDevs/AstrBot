from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import astrbot.api  # noqa: F401  # Initialize API to avoid circular imports.
from astrbot.core.knowledge_base.chunking.recursive import (
    RecursiveCharacterChunker,
)
from astrbot.core.knowledge_base.kb_helper import KBHelper


@pytest.mark.asyncio
async def test_cleaning_fallback_without_provider_keeps_chunking_parameters():
    helper = object.__new__(KBHelper)
    helper.chunker = RecursiveCharacterChunker()

    chunks = await helper._clean_and_rechunk_content(
        content="x" * 1000,
        url="https://example.invalid/document",
        enable_cleaning=True,
        cleaning_provider_id=None,
        chunk_size=128,
        chunk_overlap=16,
    )

    assert len(chunks) > 1
    assert max(len(chunk) for chunk in chunks) == 128


@pytest.mark.asyncio
async def test_cleaning_fallback_on_provider_error_keeps_chunking_parameters():
    helper = object.__new__(KBHelper)
    helper.chunker = RecursiveCharacterChunker()
    helper.prov_mgr = SimpleNamespace(
        get_provider_by_id=AsyncMock(side_effect=RuntimeError("provider unavailable")),
    )

    chunks = await helper._clean_and_rechunk_content(
        content="x" * 1000,
        url="https://example.invalid/document",
        enable_cleaning=True,
        cleaning_provider_id="broken-provider",
        chunk_size=128,
        chunk_overlap=16,
    )

    assert len(chunks) > 1
    assert max(len(chunk) for chunk in chunks) == 128
