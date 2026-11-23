"""PDF text, image extraction, and malformed input use the real parser."""

import io
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from pypdf import PdfWriter
from pypdf.errors import PdfReadError

from astrbot.core.knowledge_base.parsers import pdf_parser


@pytest.mark.asyncio
async def test_blank_pdf_has_no_text_or_media():
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.add_blank_page(width=100, height=100)
    content = io.BytesIO()
    writer.write(content)

    result = await pdf_parser.PDFParser().parse(content.getvalue(), "blank.pdf")

    assert result.text == ""
    assert result.media == []


@pytest.mark.asyncio
async def test_pdf_text_preserves_page_order_and_skips_empty_pages(monkeypatch):
    pages = []
    for text in ("first page", None, "", "last page"):
        page = MagicMock()
        page.extract_text.return_value = text
        page.__contains__.return_value = False
        pages.append(page)
    reader = Mock(return_value=SimpleNamespace(pages=pages))
    monkeypatch.setattr(pdf_parser, "PdfReader", reader)

    result = await pdf_parser.PDFParser().parse(b"pdf fixture", "pages.pdf")

    assert reader.call_args.args[0].getvalue() == b"pdf fixture"
    assert result.text == "first page\n\nlast page"
    assert result.media == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("encoding", "extension", "mime_type"),
    [
        ("/DCTDecode", "jpg", "image/jpeg"),
        ("/FlateDecode", "png", "image/png"),
        ("", "png", "image/png"),
    ],
)
async def test_image_failure_does_not_discard_other_media(
    monkeypatch, encoding, extension, mime_type
):
    broken = MagicMock()
    broken.get.return_value = "/Image"
    broken.get_data.side_effect = ValueError("corrupt image")
    image = MagicMock()
    image.get.side_effect = lambda key, default=None: {
        "/Subtype": "/Image",
        "/Filter": encoding,
    }.get(key, default)
    image.get_data.return_value = b"image bytes"
    xobjects = Mock()
    xobjects.get_object.return_value = {"/Broken": broken, "/Valid": image}
    page = MagicMock()
    page.extract_text.return_value = "readable text"
    page.__contains__.side_effect = lambda key: key == "/Resources"
    page.__getitem__.return_value = {"/XObject": xobjects}
    monkeypatch.setattr(
        pdf_parser, "PdfReader", Mock(return_value=SimpleNamespace(pages=[page]))
    )

    result = await pdf_parser.PDFParser().parse(b"fixture", "images.pdf")

    assert result.text == "readable text"
    assert len(result.media) == 1
    item = result.media[0]
    assert (item.media_type, item.file_name, item.content, item.mime_type) == (
        "image",
        f"page_0_img_1.{extension}",
        b"image bytes",
        mime_type,
    )


@pytest.mark.asyncio
async def test_malformed_pdf_reports_reader_error():
    with pytest.raises(PdfReadError):
        await pdf_parser.PDFParser().parse(b"not a PDF", "broken.pdf")
