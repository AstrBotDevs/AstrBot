import pytest

from astrbot.core.knowledge_base.chunking.markdown import MarkdownChunker


@pytest.mark.asyncio
@pytest.mark.parametrize("max_depth", range(1, 7))
@pytest.mark.parametrize("separator", [" ", ""])
async def test_heading_depth_limit_preserves_deeper_headings_as_body(
    max_depth: int, separator: str
) -> None:
    deep_heading = f"{'#' * (max_depth + 1)}{separator}Deep"
    peer_heading = f"{'#' * max_depth}{separator}Peer"
    text = (
        f"# Root\n\nIntroduction.\n\n{deep_heading}\n\nDeep body.\n\n"
        f"{peer_heading}\n\nPeer body."
    )

    chunks = await MarkdownChunker(max_heading_depth=max_depth).chunk(text)

    assert chunks == [
        f"# Root\nIntroduction.\n\n{deep_heading}\n\nDeep body.",
        ("Root\n\n" if max_depth > 1 else "") + f"{peer_heading}\nPeer body.",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("separator", [" ", ""])
async def test_heading_context_within_depth_limit(separator: str) -> None:
    text = (
        f"#{separator}Root\n\nIntroduction.\n\n"
        f"##{separator}Child\n\nChild body.\n\n"
        f"###{separator}Grandchild\n\nGrandchild body."
    )

    chunks = await MarkdownChunker(max_heading_depth=3).chunk(text)

    assert chunks == [
        f"#{separator}Root\nIntroduction.",
        f"Root\n\n##{separator}Child\nChild body.",
        f"Root > Child\n\n###{separator}Grandchild\nGrandchild body.",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("fence", ["```", "~~~"])
async def test_heading_depth_limit_preserves_fenced_code(fence: str) -> None:
    code = f"{fence}python\n## Code comment\n{fence}"
    text = f"# Root\n\n{code}\n\n## Child\n\nChild body."

    chunks = await MarkdownChunker(max_heading_depth=2).chunk(text)

    assert chunks == [
        f"# Root\n{code}",
        "Root\n\n## Child\nChild body.",
    ]
