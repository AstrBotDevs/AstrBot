import pytest

from astrbot.core.knowledge_base.chunking.markdown import MarkdownChunker


@pytest.mark.asyncio
async def test_long_heading_prefix_clamps_overlap_to_body_budget():
    """外部合法的 chunk_overlap 在标题预算压缩后不得导致分块失败。

    复现 #9998：200 字符父标题 + 600 字符正文，chunk_size=256、
    chunk_overlap=100 是合法配置；标题上下文把正文预算压到 64 后，
    旧实现原样传入 overlap=100，递归分块器抛出
    "chunk_overlap must be less than chunk_size"。
    """
    text = "# " + "A" * 200 + "\n\n## Child\n" + "B" * 600

    chunks = await MarkdownChunker(chunk_size=256, chunk_overlap=100).chunk(text)

    assert chunks
    assert any("B" in chunk for chunk in chunks)


@pytest.mark.asyncio
async def test_without_heading_context_control_still_works():
    """关闭标题上下文的对照路径保持原有行为。"""
    text = "# " + "A" * 200 + "\n\n## Child\n" + "B" * 600

    chunks = await MarkdownChunker(
        chunk_size=256,
        chunk_overlap=100,
        include_heading_context=False,
    ).chunk(text)

    assert chunks
    assert any("B" in chunk for chunk in chunks)
