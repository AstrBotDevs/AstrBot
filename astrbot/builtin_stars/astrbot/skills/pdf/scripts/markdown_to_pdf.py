#!/usr/bin/env python3
"""Convert a deliberately limited Markdown subset into a PDF."""

from __future__ import annotations

import argparse
import html
import os
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_ORDERED_LIST_RE = re.compile(r"^\s*(\d+)[.)]\s+(.+)$")
_UNORDERED_LIST_RE = re.compile(r"^\s*[-+*]\s+(.+)$")
_HORIZONTAL_RULE_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_PAGEBREAK = "<!-- pagebreak -->"
_SUPPORTED_CJK_RANGES = (
    (0x3000, 0x303F),
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0xFF00, 0xFFEF),
)


@dataclass(frozen=True)
class MarkdownBlock:
    """A parsed block from the supported Markdown subset."""

    kind: str
    text: str = ""
    level: int = 0
    start: int = 1


def _is_supported_character(character: str) -> bool:
    """Return whether the default font strategy supports a character.

    Args:
        character: A single Unicode character.

    Returns:
        True when the character is Latin-compatible or Simplified Chinese.
    """
    if character in "\n\r\t":
        return True
    try:
        character.encode("cp1252")
        return True
    except UnicodeEncodeError:
        codepoint = ord(character)
        return any(start <= codepoint <= end for start, end in _SUPPORTED_CJK_RANGES)


def _validate_default_font_text(text: str) -> None:
    """Reject characters that would silently render as missing glyphs.

    Args:
        text: Markdown source text.

    Raises:
        ValueError: If the default font strategy cannot render a character.
    """
    for character in text:
        if _is_supported_character(character):
            continue
        raise ValueError(
            "The default PDF font supports Latin text and Simplified Chinese, "
            f"but not U+{ord(character):04X} ({character!r}). "
            "Pass --font with a TrueType font that supports this character."
        )


def _join_paragraph_lines(lines: list[str]) -> str:
    """Join Markdown paragraph lines without adding spaces around CJK text.

    Args:
        lines: Consecutive non-empty paragraph lines.

    Returns:
        A single paragraph string.
    """
    result = ""
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if not result:
            result = stripped
            continue
        if result[-1].isascii() and stripped[0].isascii():
            result += " "
        result += stripped
    return result


def parse_markdown(text: str) -> list[MarkdownBlock]:
    """Parse block-level constructs from the supported Markdown subset.

    Args:
        text: Markdown source.

    Returns:
        Parsed blocks in document order.

    Raises:
        ValueError: If a fenced code block is not closed.
    """
    blocks: list[MarkdownBlock] = []
    paragraph_lines: list[str] = []
    code_lines: list[str] = []
    in_code = False

    def flush_paragraph() -> None:
        if paragraph_lines:
            blocks.append(
                MarkdownBlock("paragraph", _join_paragraph_lines(paragraph_lines))
            )
            paragraph_lines.clear()

    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.rstrip()
        if line.lstrip().startswith("```"):
            if in_code:
                blocks.append(MarkdownBlock("code", "\n".join(code_lines)))
                code_lines.clear()
                in_code = False
            else:
                flush_paragraph()
                in_code = True
            continue
        if in_code:
            code_lines.append(raw_line.expandtabs(4))
            continue
        if not line.strip():
            flush_paragraph()
            continue
        if line.strip().lower() == _PAGEBREAK:
            flush_paragraph()
            blocks.append(MarkdownBlock("pagebreak"))
            continue
        if match := _HEADING_RE.match(line):
            flush_paragraph()
            blocks.append(
                MarkdownBlock("heading", match.group(2), level=len(match.group(1)))
            )
            continue
        if _HORIZONTAL_RULE_RE.match(line):
            flush_paragraph()
            blocks.append(MarkdownBlock("rule"))
            continue
        if match := _ORDERED_LIST_RE.match(line):
            flush_paragraph()
            blocks.append(
                MarkdownBlock("ordered-list", match.group(2), start=int(match.group(1)))
            )
            continue
        if match := _UNORDERED_LIST_RE.match(line):
            flush_paragraph()
            blocks.append(MarkdownBlock("unordered-list", match.group(1)))
            continue
        if line.lstrip().startswith(">"):
            flush_paragraph()
            blocks.append(MarkdownBlock("quote", line.lstrip()[1:].lstrip()))
            continue
        paragraph_lines.append(line)

    if in_code:
        raise ValueError("Unclosed fenced code block.")
    flush_paragraph()
    return blocks


def _safe_link(url: str) -> str | None:
    """Return an allowed link target.

    Args:
        url: Markdown link target.

    Returns:
        The original URL for allowed schemes, otherwise None.
    """
    parsed = urlparse(url.strip())
    return url.strip() if parsed.scheme.lower() in {"http", "https", "mailto"} else None


def render_inline_markdown(text: str, code_font: str) -> str:
    """Convert supported inline Markdown to safe ReportLab markup.

    Args:
        text: Inline Markdown text.
        code_font: Registered font name used for inline code.

    Returns:
        Escaped ReportLab paragraph markup.
    """
    output: list[str] = []
    cursor = 0
    while cursor < len(text):
        if text.startswith("**", cursor) or text.startswith("__", cursor):
            marker = text[cursor : cursor + 2]
            end = text.find(marker, cursor + 2)
            if end != -1:
                output.append(f"<b>{html.escape(text[cursor + 2 : end])}</b>")
                cursor = end + 2
                continue
        if text[cursor] in {"*", "_"}:
            marker = text[cursor]
            end = text.find(marker, cursor + 1)
            if end != -1:
                output.append(f"<i>{html.escape(text[cursor + 1 : end])}</i>")
                cursor = end + 1
                continue
        if text[cursor] == "`":
            end = text.find("`", cursor + 1)
            if end != -1:
                code = html.escape(text[cursor + 1 : end])
                output.append(f'<font name="{code_font}">{code}</font>')
                cursor = end + 1
                continue
        if text[cursor] == "[":
            label_end = text.find("](", cursor + 1)
            if label_end != -1:
                url_end = text.find(")", label_end + 2)
                if url_end != -1:
                    label = html.escape(text[cursor + 1 : label_end])
                    url = _safe_link(text[label_end + 2 : url_end])
                    if url:
                        escaped_url = html.escape(url, quote=True)
                        output.append(
                            f'<a href="{escaped_url}" color="#2563eb">{label}</a>'
                        )
                    else:
                        output.append(label)
                    cursor = url_end + 1
                    continue
        output.append(html.escape(text[cursor]))
        cursor += 1
    return "".join(output)


def _plain_inline_text(text: str) -> str:
    """Remove supported inline markers for metadata and validation.

    Args:
        text: Inline Markdown.

    Returns:
        Human-readable text without supported markers.
    """
    text = re.sub(r"\[([^]]+)]\(([^)]+)\)", r"\1 (\2)", text)
    text = re.sub(r"(\*\*|__)(.+?)\1", r"\2", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", text)
    text = re.sub(r"(?<!_)_([^_]+)_(?!_)", r"\1", text)
    return re.sub(r"`([^`]+)`", r"\1", text)


def _register_fonts(font_path: Path | None, source: str) -> tuple[str, str]:
    """Register the body and code fonts used by ReportLab.

    Args:
        font_path: Optional TrueType font supplied by the user.
        source: Markdown source used to verify glyph coverage.

    Returns:
        A tuple of body font name and code font name.

    Raises:
        FileNotFoundError: If the supplied font does not exist.
        ValueError: If the supplied font cannot be registered.
    """
    if font_path is not None:
        resolved = font_path.expanduser().resolve(strict=False)
        if not resolved.is_file():
            raise FileNotFoundError(f"Font not found: {resolved}")
        try:
            pdfmetrics.registerFont(TTFont("AstrBotPDF", str(resolved)))
        except Exception as exc:
            raise ValueError(f"Unable to load TrueType font {resolved}: {exc}") from exc
        pdfmetrics.registerFontFamily(
            "AstrBotPDF",
            normal="AstrBotPDF",
            bold="AstrBotPDF",
            italic="AstrBotPDF",
            boldItalic="AstrBotPDF",
        )
        glyphs = pdfmetrics.getFont("AstrBotPDF").face.charToGlyph
        for character in source:
            if character not in "\n\r\t" and ord(character) not in glyphs:
                raise ValueError(
                    f"Font {resolved} does not contain U+{ord(character):04X} "
                    f"({character!r}). Choose a font that covers the document text."
                )
        return "AstrBotPDF", "AstrBotPDF"

    system_root = Path(os.environ.get("WINDIR", "C:/Windows"))
    candidates = (
        Path("/System/Library/Fonts/STHeiti Medium.ttc"),
        Path("/System/Library/Fonts/STHeiti Light.ttc"),
        Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        Path("/usr/share/fonts/truetype/arphic/uming.ttc"),
        system_root / "Fonts" / "msyh.ttc",
        system_root / "Fonts" / "simhei.ttf",
        system_root / "Fonts" / "simsun.ttc",
    )
    for index, candidate in enumerate(candidates):
        if not candidate.is_file():
            continue
        font_name = f"AstrBotPDFSystem{index}"
        try:
            pdfmetrics.registerFont(TTFont(font_name, str(candidate)))
        except Exception:
            continue
        glyphs = pdfmetrics.getFont(font_name).face.charToGlyph
        if any(
            character not in "\n\r\t" and ord(character) not in glyphs
            for character in source
        ):
            continue
        pdfmetrics.registerFontFamily(
            font_name,
            normal=font_name,
            bold=font_name,
            italic=font_name,
            boldItalic=font_name,
        )
        return font_name, font_name

    _validate_default_font_text(source)
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    pdfmetrics.registerFontFamily(
        "STSong-Light",
        normal="STSong-Light",
        bold="STSong-Light",
        italic="STSong-Light",
        boldItalic="STSong-Light",
    )
    return "STSong-Light", "Courier"


def _build_styles(body_font: str, code_font: str) -> dict[str, ParagraphStyle]:
    """Build document styles.

    Args:
        body_font: Registered body font name.
        code_font: Registered code font name.

    Returns:
        Named paragraph styles used by the converter.
    """
    sample = getSampleStyleSheet()
    styles: dict[str, ParagraphStyle] = {
        "body": ParagraphStyle(
            "AstrBotBody",
            parent=sample["BodyText"],
            fontName=body_font,
            fontSize=10.5,
            leading=16,
            textColor=colors.HexColor("#242424"),
            spaceAfter=8,
            wordWrap="CJK",
        ),
        "quote": ParagraphStyle(
            "AstrBotQuote",
            parent=sample["BodyText"],
            fontName=body_font,
            fontSize=10.5,
            leading=16,
            leftIndent=12,
            rightIndent=8,
            borderColor=colors.HexColor("#a3a3a3"),
            borderWidth=0,
            borderPadding=6,
            backColor=colors.HexColor("#f7f7f7"),
            textColor=colors.HexColor("#525252"),
            spaceBefore=3,
            spaceAfter=8,
            wordWrap="CJK",
        ),
        "code": ParagraphStyle(
            "AstrBotCode",
            parent=sample["Code"],
            fontName=code_font,
            fontSize=8.5,
            leading=12,
            leftIndent=8,
            rightIndent=8,
            borderPadding=5,
            backColor=colors.HexColor("#f4f4f5"),
            textColor=colors.HexColor("#27272a"),
            spaceAfter=0,
            wordWrap="CJK",
        ),
        "footer": ParagraphStyle(
            "AstrBotFooter",
            parent=sample["BodyText"],
            fontName=body_font,
            fontSize=8,
            leading=10,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#737373"),
        ),
    }
    heading_sizes = {1: 24, 2: 19, 3: 16, 4: 14, 5: 12, 6: 11}
    for level, size in heading_sizes.items():
        styles[f"h{level}"] = ParagraphStyle(
            f"AstrBotHeading{level}",
            parent=sample["Heading1"],
            fontName=body_font,
            fontSize=size,
            leading=size * 1.3,
            textColor=colors.HexColor("#171717"),
            spaceBefore=12 if level > 1 else 4,
            spaceAfter=7,
            keepWithNext=True,
            wordWrap="CJK",
        )
    return styles


def _code_markup(line: str) -> str:
    """Preserve code indentation in ReportLab paragraph markup.

    Args:
        line: One source code line.

    Returns:
        Escaped markup with non-breaking spaces.
    """
    if not line:
        return "&#160;"
    escaped = html.escape(line)
    leading = len(line) - len(line.lstrip(" "))
    return "&#160;" * leading + escaped[leading:]


def _build_story(
    blocks: list[MarkdownBlock],
    styles: dict[str, ParagraphStyle],
    code_font: str,
) -> list:
    """Convert parsed blocks into ReportLab flowables.

    Args:
        blocks: Parsed Markdown blocks.
        styles: Document styles.
        code_font: Registered code font name.

    Returns:
        A ReportLab story list.
    """
    story: list = []
    index = 0
    while index < len(blocks):
        block = blocks[index]
        if block.kind == "heading":
            story.append(
                Paragraph(
                    render_inline_markdown(block.text, code_font),
                    styles[f"h{block.level}"],
                )
            )
        elif block.kind == "paragraph":
            story.append(
                Paragraph(render_inline_markdown(block.text, code_font), styles["body"])
            )
        elif block.kind == "quote":
            story.append(
                Paragraph(
                    render_inline_markdown(block.text, code_font), styles["quote"]
                )
            )
        elif block.kind == "code":
            for line in block.text.split("\n") or [""]:
                story.append(Paragraph(_code_markup(line), styles["code"]))
            story.append(Spacer(1, 7))
        elif block.kind == "rule":
            story.append(Spacer(1, 4))
            story.append(
                HRFlowable(
                    width="100%",
                    thickness=0.6,
                    color=colors.HexColor("#d4d4d4"),
                    spaceBefore=3,
                    spaceAfter=8,
                )
            )
        elif block.kind == "pagebreak":
            story.append(PageBreak())
        elif block.kind in {"ordered-list", "unordered-list"}:
            list_kind = block.kind
            items: list[ListItem] = []
            start = block.start
            while index < len(blocks) and blocks[index].kind == list_kind:
                item = blocks[index]
                items.append(
                    ListItem(
                        Paragraph(
                            render_inline_markdown(item.text, code_font),
                            styles["body"],
                        ),
                        leftIndent=12,
                    )
                )
                index += 1
            story.append(
                ListFlowable(
                    items,
                    bulletType="1" if list_kind == "ordered-list" else "bullet",
                    start=start if list_kind == "ordered-list" else "bulletchar",
                    leftIndent=20,
                    bulletFontName="Helvetica",
                    bulletFontSize=styles["body"].fontSize,
                    spaceAfter=6,
                )
            )
            continue
        index += 1
    return story


def convert_markdown_to_pdf(
    input_path: Path,
    output_path: Path,
    *,
    title: str | None,
    page_size: str,
    font_path: Path | None,
) -> None:
    """Convert Markdown into a validated PDF.

    Args:
        input_path: UTF-8 Markdown source.
        output_path: Destination PDF.
        title: Optional PDF title override.
        page_size: Either ``a4`` or ``letter``.
        font_path: Optional TrueType font for broader Unicode support.

    Raises:
        ValueError: If the input is empty or output validation fails.
    """
    source = input_path.read_text(encoding="utf-8")
    if not source.strip():
        raise ValueError("Markdown input is empty.")
    blocks = parse_markdown(source)
    if not blocks:
        raise ValueError("Markdown input contains no renderable content.")
    document_title = title or next(
        (
            _plain_inline_text(block.text)
            for block in blocks
            if block.kind == "heading" and block.level == 1
        ),
        input_path.stem,
    )
    body_font, code_font = _register_fonts(font_path, source)
    styles = _build_styles(body_font, code_font)
    story = _build_story(blocks, styles, code_font)
    page_dimensions = A4 if page_size == "a4" else LETTER

    generated = BytesIO()

    def draw_footer(canvas, document) -> None:
        canvas.saveState()
        canvas.setFont(body_font, 8)
        canvas.setFillColor(colors.HexColor("#737373"))
        canvas.drawCentredString(
            page_dimensions[0] / 2,
            13 * mm,
            str(document.page),
        )
        canvas.restoreState()

    document = SimpleDocTemplate(
        generated,
        pagesize=page_dimensions,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=22 * mm,
        title=document_title,
        author="AstrBot",
        creator="AstrBot PDF Skill",
    )
    document.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)

    generated.seek(0)
    reader = PdfReader(generated)
    if not reader.pages:
        raise ValueError("Generated PDF contains no pages.")
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    writer.add_metadata(
        {
            "/Title": document_title,
            "/Author": "AstrBot",
            "/Creator": "AstrBot PDF Skill",
        }
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as output_file:
        writer.write(output_file)

    verified = PdfReader(output_path)
    if not verified.pages:
        raise ValueError("Final PDF validation failed: no pages found.")


def main() -> int:
    """Run the command-line converter.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(
        description="Convert a limited Markdown subset into a validated PDF."
    )
    parser.add_argument("input", type=Path, help="UTF-8 Markdown input file")
    parser.add_argument("output", type=Path, help="Destination PDF file")
    parser.add_argument("--title", help="Optional PDF title override")
    parser.add_argument(
        "--page-size",
        choices=("a4", "letter"),
        default="a4",
        help="Output page size (default: a4)",
    )
    parser.add_argument(
        "--font",
        type=Path,
        help="Optional TrueType or TrueType Collection font for document text",
    )
    args = parser.parse_args()

    input_path = args.input.expanduser().resolve(strict=False)
    output_path = args.output.expanduser().resolve(strict=False)
    if not input_path.is_file():
        parser.error(f"Input file not found: {input_path}")
    if input_path == output_path:
        parser.error("Input and output paths must be different.")
    if output_path.suffix.lower() != ".pdf":
        parser.error("Output path must end with .pdf")

    try:
        convert_markdown_to_pdf(
            input_path,
            output_path,
            title=args.title,
            page_size=args.page_size,
            font_path=args.font,
        )
    except Exception as exc:
        parser.error(str(exc))
    print(f"created: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
