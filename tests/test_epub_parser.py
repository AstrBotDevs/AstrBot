from __future__ import annotations

import io
import zipfile

import pytest

from astrbot.core.knowledge_base.parsers.epub_parser import EpubParser
from astrbot.core.knowledge_base.parsers.util import select_parser


def _make_epub_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        archive.writestr(
            "mimetype",
            "application/epub+zip",
            compress_type=zipfile.ZIP_STORED,
        )
        archive.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
""",
        )
        archive.writestr(
            "OEBPS/nav.xhtml",
            """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head>
    <title>Navigation</title>
  </head>
  <body>
    <nav epub:type="toc" xmlns:epub="http://www.idpf.org/2007/ops">
      <ol>
        <li><a href="chapter2.xhtml">Chapter 2</a></li>
        <li><a href="chapter1.xhtml">Chapter 1</a></li>
      </ol>
    </nav>
  </body>
</html>
""",
        )
        archive.writestr(
            "OEBPS/chapter2.xhtml",
            """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head>
    <title>Chapter 2</title>
  </head>
  <body>
    <h2>Second</h2>
    <p>Beta paragraph.</p>
  </body>
</html>
""",
        )
        archive.writestr(
            "OEBPS/chapter1.xhtml",
            """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head>
    <title>Chapter 1</title>
  </head>
  <body>
    <h1>First</h1>
    <p>Alpha paragraph.</p>
    <ul>
      <li>Point A</li>
      <li>Point B</li>
    </ul>
  </body>
</html>
""",
        )
        archive.writestr(
            "OEBPS/content.opf",
            """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">test-book</dc:identifier>
    <dc:title>Test Book</dc:title>
    <dc:language>en</dc:language>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="chapter2" href="chapter2.xhtml" media-type="application/xhtml+xml"/>
    <item id="chapter1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="nav"/>
    <itemref idref="chapter2"/>
    <itemref idref="chapter1"/>
  </spine>
</package>
""",
        )

    return buffer.getvalue()


def _make_epub_bytes_with_generic_content() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        archive.writestr(
            "mimetype",
            "application/epub+zip",
            compress_type=zipfile.ZIP_STORED,
        )
        archive.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
""",
        )
        archive.writestr(
            "OEBPS/chapter1.xhtml",
            """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head>
    <title>Chapter 1</title>
  </head>
  <body>
    <h1>First</h1>
    Lead text
    <p>Piura<a href="text00000.html#filepos0000045863">*5</a>, continued.</p>
    <img src="Image00000.jpg" alt="" />
    <div>Inside div</div>
    <section>Inside section</section>
    <table>
      <tr>
        <td>Cell A</td>
        <td>Cell B</td>
      </tr>
    </table>
  </body>
</html>
""",
        )
        archive.writestr(
            "OEBPS/content.opf",
            """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">test-book</dc:identifier>
    <dc:title>Test Book</dc:title>
    <dc:language>en</dc:language>
  </metadata>
  <manifest>
    <item id="chapter1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="chapter1"/>
  </spine>
</package>
""",
        )

    return buffer.getvalue()


@pytest.mark.asyncio
async def test_select_parser_supports_epub():
    parser = await select_parser(".epub")

    assert isinstance(parser, EpubParser)


@pytest.mark.asyncio
async def test_epub_parser_reads_spine_order_as_text():
    result = await EpubParser().parse(_make_epub_bytes(), "book.epub")

    assert result.media == []
    assert "**Title:**" not in result.text
    assert "[Chapter 2](chapter2.xhtml)" not in result.text
    assert result.text.startswith("1. Chapter 2")
    assert "2. Chapter 1" in result.text
    assert "Beta paragraph." in result.text
    assert "# First" in result.text
    assert "* Point A" in result.text
    assert result.text.index("1. Chapter 2") < result.text.index("## Second")
    assert result.text.index("## Second") < result.text.index("# First")


@pytest.mark.asyncio
async def test_epub_parser_preserves_generic_container_text():
    result = await EpubParser().parse(
        _make_epub_bytes_with_generic_content(),
        "book.epub",
    )

    assert "**Title:**" not in result.text
    assert "# First" in result.text
    assert "Lead text" in result.text
    assert r"Piura\*5, continued." in result.text
    assert "filepos" not in result.text
    assert r"[\*5]" not in result.text
    assert "Image00000.jpg" not in result.text
    assert "![](" not in result.text
    assert "\n\n\n" not in result.text
    assert "Inside div" in result.text
    assert "Inside section" in result.text
    assert "| Cell A | Cell B |" in result.text
