import io
from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import NameObject
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from astrbot.core.knowledge_base.parsers.pdf_parser import PDFParser


def _make_pdf(
    image_format: str = "PNG",
    *,
    transparent: bool = False,
    nested: bool = False,
    pages: int = 1,
) -> bytes:
    """Build a PDF with text and an encoded image on each page.

    Args:
        image_format: Encoding of the source image.
        transparent: Whether to include a soft alpha mask.
        nested: Whether to place the image inside a Form XObject.
        pages: Number of pages to generate.

    Returns:
        Complete PDF bytes.
    """
    image_buffer = io.BytesIO()
    mode = "RGBA" if transparent else "RGB"
    color = (20, 80, 140, 128) if transparent else (20, 80, 140)
    Image.new(mode, (8, 6), color).save(image_buffer, format=image_format)
    image_buffer.seek(0)
    source = ImageReader(image_buffer)
    pdf_buffer = io.BytesIO()
    canvas = Canvas(pdf_buffer, pagesize=(200, 200))
    for page_num in range(pages):
        canvas.drawString(10, 180, f"Page {page_num + 1} text survives.")
        if nested:
            canvas.beginForm(f"Figure{page_num}")
        canvas.drawImage(source, 10, 10, width=80, height=60, mask="auto")
        if nested:
            canvas.endForm()
            canvas.doForm(f"Figure{page_num}")
        canvas.showPage()
    canvas.save()
    return pdf_buffer.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize("image_format", ["PNG", "JPEG"])
async def test_pdf_images_have_decodable_content_and_matching_metadata(image_format):
    result = await PDFParser().parse(_make_pdf(image_format), "image.pdf")

    assert "Page 1 text survives." in result.text
    assert len(result.media) == 1
    media = result.media[0]
    assert media.media_type == "image"
    with Image.open(io.BytesIO(media.content)) as image:
        image.load()
        assert image.size == (8, 6)
        assert image.format == image_format
        assert media.mime_type == Image.MIME[image.format]
        assert Path(media.file_name).suffix == (
            ".jpg" if image_format == "JPEG" else ".png"
        )
        if image_format == "PNG":
            assert image.getpixel((0, 0)) == (20, 80, 140)


@pytest.mark.asyncio
async def test_pdf_images_preserve_soft_mask_transparency():
    result = await PDFParser().parse(_make_pdf(transparent=True), "alpha.pdf")

    assert len(result.media) == 1
    with Image.open(io.BytesIO(result.media[0].content)) as image:
        image.load()
        assert image.mode == "RGBA"
        assert image.getpixel((0, 0)) == (20, 80, 140, 128)


@pytest.mark.asyncio
async def test_pdf_images_inside_forms_are_extracted():
    result = await PDFParser().parse(_make_pdf(nested=True), "nested.pdf")

    assert "Page 1 text survives." in result.text
    assert len(result.media) == 1
    with Image.open(io.BytesIO(result.media[0].content)) as image:
        image.load()
        assert image.getpixel((0, 0)) == (20, 80, 140)


@pytest.mark.asyncio
async def test_pdf_images_have_unique_names_across_pages():
    result = await PDFParser().parse(_make_pdf(pages=2), "pages.pdf")

    assert "Page 1 text survives." in result.text
    assert "Page 2 text survives." in result.text
    assert [media.file_name for media in result.media] == [
        "page_0_img_1.png",
        "page_1_img_2.png",
    ]


@pytest.mark.asyncio
async def test_pdf_bad_image_does_not_discard_text_or_other_images(monkeypatch):
    warning = Mock()
    monkeypatch.setattr(
        "astrbot.core.knowledge_base.parsers.pdf_parser.logger.warning", warning
    )
    writer = PdfWriter(clone_from=io.BytesIO(_make_pdf()))
    xobjects = writer.pages[0]["/Resources"]["/XObject"]
    image_name = next(iter(xobjects))
    # Put a malformed image before the valid one on the same page.
    invalid = xobjects[image_name].clone(writer, force_duplicate=True)
    del invalid["/Width"]
    valid = xobjects.raw_get(image_name)
    xobjects.clear()
    xobjects[NameObject("/Broken")] = invalid.indirect_reference
    xobjects[image_name] = valid
    buffer = io.BytesIO()
    writer.write(buffer)

    result = await PDFParser().parse(buffer.getvalue(), "broken.pdf")

    assert "Page 1 text survives." in result.text
    assert len(result.media) == 1
    warning.assert_called_once_with(
        "Failed to extract image %r on PDF page %d in %r",
        "/Broken",
        1,
        "broken.pdf",
        exc_info=True,
    )
    with Image.open(io.BytesIO(result.media[0].content)) as image:
        image.load()
        assert image.size == (8, 6)


@pytest.mark.asyncio
async def test_pdf_page_image_error_is_logged_and_later_pages_survive(monkeypatch):
    from pypdf._page import PageObject

    warning = Mock()
    monkeypatch.setattr(
        "astrbot.core.knowledge_base.parsers.pdf_parser.logger.warning", warning
    )
    images_property = PageObject.images
    calls = 0

    def images(page):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("broken image resources")
        return images_property.fget(page)

    monkeypatch.setattr(PageObject, "images", property(images))
    result = await PDFParser().parse(_make_pdf(pages=2), "broken-page.pdf")

    assert "Page 1 text survives." in result.text
    assert "Page 2 text survives." in result.text
    assert len(result.media) == 1
    warning.assert_called_once_with(
        "Failed to enumerate images on PDF page %d in %r",
        1,
        "broken-page.pdf",
        exc_info=True,
    )


@pytest.mark.asyncio
async def test_pdf_without_images_still_returns_text():
    buffer = io.BytesIO()
    canvas = Canvas(buffer)
    canvas.drawString(10, 180, "Page 1 text survives.")
    canvas.save()

    result = await PDFParser().parse(buffer.getvalue(), "text.pdf")

    assert "Page 1 text survives." in result.text
    assert result.media == []
