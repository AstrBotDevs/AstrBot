import pytest

from astrbot.core.knowledge_base.chunking.markdown import MarkdownChunker

LONG_HEADING_DOC = "# " + "A" * 200 + "\n\n## Child\n" + "B" * 600


@pytest.mark.asyncio
async def test_long_heading_prefix_keeps_valid_overlap_configuration():
    """A valid (chunk_size, chunk_overlap) pair must stay valid for the
    recursive fallback even when the heading prefix shrinks the body budget."""
    chunker = MarkdownChunker(chunk_size=256, chunk_overlap=100)

    chunks = await chunker.chunk(LONG_HEADING_DOC)

    assert chunks
    assert "".join(chunks).count("B") >= 600
    # The overlap now scales with the reduced budget instead of exceeding it.
    assert all("B" * 65 not in chunk for chunk in chunks)


@pytest.mark.asyncio
async def test_overlap_override_is_scaled_too():
    chunker = MarkdownChunker(chunk_size=1024, chunk_overlap=50)

    chunks = await chunker.chunk(LONG_HEADING_DOC, chunk_size=256, chunk_overlap=100)

    assert chunks
    assert "".join(chunks).count("B") >= 600


@pytest.mark.asyncio
async def test_without_heading_context_behaviour_is_unchanged():
    chunker = MarkdownChunker(
        chunk_size=256, chunk_overlap=100, include_heading_context=False
    )

    chunks = await chunker.chunk(LONG_HEADING_DOC)

    assert chunks
    assert all(len(chunk) <= 256 for chunk in chunks)


@pytest.mark.parametrize(
    ("overlap", "size", "effective", "expected"),
    [
        (100, 256, 64, 25),  # proportional to the reduced budget
        (100, 256, 256, 100),  # no reduction, untouched
        (100, 256, 300, 100),  # larger budget, untouched
        (255, 256, 64, 63),  # never reaches the effective size
        (0, 256, 64, 0),
    ],
)
def test_scale_overlap(overlap, size, effective, expected):
    assert MarkdownChunker._scale_overlap(overlap, size, effective) == expected
