import pytest

from astrbot.core.knowledge_base.chunking.markdown import MarkdownChunker


@pytest.mark.asyncio
async def test_markdown_headings_between_fenced_code_blocks():
    sections = [
        "# First\ntext",
        "## Example\n````py\n# inside\n```\n# still inside\n````",
        "## More\n~~~\n## also inside\n~~~\n```\n# another block\n```",
        "# Last\n```\n# unclosed",
    ]
    chunks = await MarkdownChunker(include_heading_context=False).chunk(
        "\n".join(sections)
    )
    assert chunks == sections
