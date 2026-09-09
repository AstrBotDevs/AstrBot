from unittest.mock import AsyncMock

import pytest

from astrbot.core.knowledge_base.kb_helper import KBHelper


class _RecordingChunker:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def chunk(self, text: str, **kwargs) -> list[str]:
        self.calls.append(kwargs)
        size = kwargs.get("chunk_size", 500)
        return [text[i : i + size] for i in range(0, len(text), size)]


def _helper(chunker: _RecordingChunker, provider_error: Exception | None = None):
    helper = KBHelper.__new__(KBHelper)
    helper.chunker = chunker
    helper.prov_mgr = AsyncMock()
    helper.prov_mgr.get_provider_by_id = AsyncMock(side_effect=provider_error)
    return helper


CONTENT = "x" * 1000
PARAMS = {"chunk_size": 128, "chunk_overlap": 16}


@pytest.mark.asyncio
async def test_missing_cleaning_provider_keeps_requested_chunk_params():
    chunker = _RecordingChunker()
    helper = _helper(chunker)

    chunks = await helper._clean_and_rechunk_content(
        CONTENT, "https://example.com", enable_cleaning=True, **PARAMS
    )

    assert chunker.calls == [PARAMS]
    assert max(len(c) for c in chunks) <= 128


@pytest.mark.asyncio
async def test_failed_cleaning_provider_lookup_keeps_requested_chunk_params():
    chunker = _RecordingChunker()
    helper = _helper(chunker, provider_error=RuntimeError("provider unavailable"))

    chunks = await helper._clean_and_rechunk_content(
        CONTENT,
        "https://example.com",
        enable_cleaning=True,
        cleaning_provider_id="llm-1",
        **PARAMS,
    )

    assert chunker.calls == [PARAMS]
    assert max(len(c) for c in chunks) <= 128


@pytest.mark.asyncio
async def test_cleaning_disabled_still_passes_chunk_params():
    chunker = _RecordingChunker()
    helper = _helper(chunker)

    await helper._clean_and_rechunk_content(
        CONTENT, "https://example.com", enable_cleaning=False, **PARAMS
    )

    assert chunker.calls == [PARAMS]
