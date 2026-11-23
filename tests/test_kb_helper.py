"""Text repair consumes provider results without invoking a live provider."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.knowledge_base.kb_helper import (
    RateLimiter,
    _repair_and_translate_chunk_with_retry,
)
from astrbot.core.knowledge_base.prompts import TEXT_REPAIR_SYSTEM_PROMPT


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (
            "<repaired_text> first </repaired_text>\n<repaired_text>second</repaired_text>",
            ["first", "second"],
        ),
        ("< repaired_text >\n valid text \n< / repaired_text >", ["valid text"]),
        ("<repaired_text>  </repaired_text>", []),
        ("<discard_chunk />", []),
        ("unstructured provider output", []),
    ],
)
async def test_repair_returns_only_nonempty_tagged_chunks(response, expected):
    provider = SimpleNamespace(
        text_chat=AsyncMock(return_value=SimpleNamespace(completion_text=response))
    )
    result = await _repair_and_translate_chunk_with_retry(
        "source paragraph", provider, RateLimiter(0)
    )
    assert result == expected
    provider.text_chat.assert_awaited_once()
    arguments = provider.text_chat.await_args.kwargs
    assert "source paragraph" in arguments["prompt"]
    assert arguments["system_prompt"] == TEXT_REPAIR_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_repair_retries_and_preserves_original_after_exhaustion():
    provider = SimpleNamespace(
        text_chat=AsyncMock(side_effect=RuntimeError("unavailable"))
    )
    assert await _repair_and_translate_chunk_with_retry(
        "original text", provider, RateLimiter(0), max_retries=2
    ) == ["original text"]
    assert provider.text_chat.await_count == 3


@pytest.mark.asyncio
async def test_repair_stops_retrying_after_success():
    provider = SimpleNamespace(
        text_chat=AsyncMock(
            side_effect=[
                RuntimeError("retry"),
                SimpleNamespace(
                    completion_text="<repaired_text>recovered</repaired_text>"
                ),
            ]
        )
    )
    assert await _repair_and_translate_chunk_with_retry(
        "original", provider, RateLimiter(0), max_retries=3
    ) == ["recovered"]
    assert provider.text_chat.await_count == 2
