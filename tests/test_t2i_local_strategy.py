import pytest

from astrbot.core.utils.t2i.local_strategy import (
    CodeBlock,
    FontManager,
    HeadingBlock,
    MarkdownParser,
    MarkdownRenderer,
    MathBlock,
    TableBlock,
    TextMeasurer,
)


def test_text_measurer_uses_content_and_wraps_to_requested_width() -> None:
    """Verify measurement uses real text and wrapping never exceeds the limit."""
    font = FontManager.get_font(24)

    assert (
        TextMeasurer.get_text_size("WWWW", font)[0]
        > TextMeasurer.get_text_size("iiii", font)[0]
    )

    max_width = 180
    lines = TextMeasurer.split_text_to_fit_width(
        "这是一段需要自动换行的中文 mixed-with-a-very-long-English-token 内容。",
        font,
        max_width,
    )

    assert len(lines) > 1
    assert all(TextMeasurer.get_text_size(line, font)[0] <= max_width for line in lines)


@pytest.mark.asyncio
async def test_markdown_parser_recognizes_common_rich_blocks() -> None:
    """Verify headings, tables, code, and display math receive native blocks."""
    markdown = """# Heading

| Name | Value |
| :--- | ---: |
| Wrap | A long table value |

```python
print("hello")
```

$$
E = mc^2
$$
"""

    blocks = await MarkdownParser.parse(markdown)

    assert any(isinstance(block, HeadingBlock) for block in blocks)
    assert any(isinstance(block, TableBlock) for block in blocks)
    assert any(isinstance(block, CodeBlock) for block in blocks)
    assert any(isinstance(block, MathBlock) for block in blocks)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("markdown", "language", "code"),
    [
        pytest.param(
            "~~~python\n# setup\nx = 1\n~~~\n## Next",
            "python",
            ["# setup", "x = 1"],
            id="tilde-fence",
        ),
        pytest.param(
            "````markdown\n```python\n# comment\n```\n````\n## Next",
            "markdown",
            ["```python", "# comment", "```"],
            id="longer-fence-around-example",
        ),
    ],
)
async def test_markdown_parser_keeps_fenced_code_out_of_headings(
    markdown: str, language: str, code: list[str]
) -> None:
    """Verify that "#" lines inside tilde and nested fences stay code."""
    blocks = await MarkdownParser.parse(markdown)

    assert [type(block) for block in blocks] == [CodeBlock, HeadingBlock]
    assert blocks[0].language == language
    assert blocks[0].content == code
    assert blocks[1].content == "Next"


@pytest.mark.asyncio
async def test_markdown_parser_does_not_open_a_fence_on_inline_backticks() -> None:
    """Verify a line starting with ```inline``` code does not swallow the rest."""
    blocks = await MarkdownParser.parse("```inline``` code here\n## Next\nbody")

    assert not any(isinstance(block, CodeBlock) for block in blocks)
    assert any(
        isinstance(block, HeadingBlock) and block.content == "Next" for block in blocks
    )


@pytest.mark.asyncio
async def test_markdown_renderer_produces_requested_width_with_wrapped_content() -> (
    None
):
    """Verify a narrow render completes without allowing long content to expand it."""
    renderer = MarkdownRenderer(font_size=22, width=420)
    markdown = """## 自动换行

正文包含 **粗体**、`inline_code()` 和一个不会自然断开的超长字符串：abcdefghijklmnopqrstuvwxyz0123456789abcdefghijklmnopqrstuvwxyz。

```python
result = "abcdefghijklmnopqrstuvwxyz0123456789abcdefghijklmnopqrstuvwxyz"
```

| 项目 | 说明 |
| --- | --- |
| 表格 | 这一格也需要在固定宽度里自动换行 |
"""

    image = await renderer.render(markdown)

    assert image.width == 420
    assert image.height > 400
