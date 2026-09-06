import builtins
import importlib.util
import math
import sys
from collections.abc import Mapping, Sequence
from io import BytesIO
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from astrbot.core.utils.t2i import local_strategy
from astrbot.core.utils.t2i.local_strategy import (
    CodeBlock,
    FontManager,
    HeadingBlock,
    ImageBlock,
    MarkdownParser,
    MarkdownRenderer,
    MathBlock,
    TableBlock,
    TextMeasurer,
)


def test_text_measurer_uses_content_and_wraps_to_requested_width() -> None:
    """Verify measurement uses real text and wrapping never exceeds the limit."""
    font = FontManager.get_font(24)

    assert TextMeasurer.get_text_size("Measured text", font)[0] == math.ceil(
        font.getlength("Measured text")
    )
    assert TextMeasurer.get_text_size("", font)[0] == 0
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


def test_local_strategy_defers_http_imports(monkeypatch: pytest.MonkeyPatch) -> None:
    """Importing the renderer must not load aiohttp or its eager TLS helper."""
    original_import = builtins.__import__

    def guarded_import(
        name: str,
        globals: Mapping[str, object] | None = None,
        locals: Mapping[str, object] | None = None,
        fromlist: Sequence[str] = (),
        level: int = 0,
    ) -> ModuleType:
        if name == "aiohttp" or name == "astrbot.core.utils.http_ssl":
            raise AssertionError(f"Unexpected eager HTTP import: {name}")
        return original_import(name, globals, locals, fromlist, level)

    spec = importlib.util.spec_from_file_location(
        "_local_t2i_import_check", local_strategy.__file__
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    monkeypatch.setattr(builtins, "__import__", guarded_import)

    spec.loader.exec_module(module)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 404])
async def test_image_download_uses_lazy_client_and_shared_tls(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    """Use the certifi-enabled connector while retaining image failure fallback."""
    import aiohttp

    from astrbot.core.utils import http_ssl

    image_data = BytesIO()
    with Image.new("RGB", (8, 6), (20, 30, 40)) as source:
        source.save(image_data, format="PNG")

    response = MagicMock(status=status)
    response.read = AsyncMock(return_value=image_data.getvalue())
    session = MagicMock()
    session.get.return_value.__aenter__.return_value = response
    client_session = MagicMock()
    client_session.return_value.__aenter__.return_value = session
    connector = MagicMock()
    build_connector = MagicMock(return_value=connector)
    get_aiohttp = MagicMock(return_value=aiohttp)
    monkeypatch.setattr(aiohttp, "ClientSession", client_session)
    monkeypatch.setattr(http_ssl, "build_tls_connector", build_connector)
    monkeypatch.setattr(local_strategy, "_get_aiohttp", get_aiohttp)

    block = ImageBlock("Example", "https://example.invalid/image.png")
    await block.load()

    get_aiohttp.assert_called_once_with()
    build_connector.assert_called_once_with()
    client_session.assert_called_once_with(
        trust_env=True, connector=connector, timeout=aiohttp.ClientTimeout(total=12)
    )
    session.get.assert_called_once_with(block.image_url)
    if status == 200:
        response.read.assert_awaited_once_with()
        assert block.image is not None
        assert block.image.mode == "RGBA"
        assert block.image.size == (8, 6)
    else:
        response.read.assert_not_awaited()
        assert block.image is None
        assert block.measure(300, 22) > 0
        assert "Image unavailable" in " ".join(block.fallback_lines)
