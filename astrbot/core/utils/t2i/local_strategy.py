import asyncio
import html
import logging
import math
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import aiohttp
from PIL import Image, ImageDraw, ImageFont

from astrbot.core.config import VERSION
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.utils.http_ssl import build_tls_connector
from astrbot.core.utils.io import save_temp_img

from . import RenderStrategy

logger = logging.getLogger("astrbot")

PAPER = (251, 251, 250)
INK = (32, 34, 36)
MUTED = (102, 107, 112)
LINE = (212, 216, 219)
STRONG_LINE = (188, 194, 198)
SOFT_FILL = (242, 243, 243)
CODE_FILL = (244, 245, 245)
ACCENT = (47, 134, 189)
CONTENT_MARGIN = 32


class FontManager:
    """Load and cache cross-platform fonts with CJK coverage."""

    _font_cache: dict[
        tuple[int, bool, bool], ImageFont.FreeTypeFont | ImageFont.ImageFont
    ] = {}

    @classmethod
    def get_font(
        cls,
        size: int,
        *,
        bold: bool = False,
        monospace: bool = False,
    ) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        """Return a font suitable for local T2I rendering.

        Args:
            size: Font size in pixels.
            bold: Whether a bold face should be preferred.
            monospace: Whether a monospace face should be preferred.

        Returns:
            A loaded Pillow font. System CJK fonts are preferred over Latin-only
            fallbacks so Chinese text does not render as missing-glyph boxes.
        """
        cache_key = (size, bold, monospace)
        if cache_key in cls._font_cache:
            return cls._font_cache[cache_key]

        data_dir = Path(get_astrbot_data_path())
        if monospace:
            candidates: list[tuple[str | Path, int]] = [
                (data_dir / "font-mono.ttf", 0),
                ("/usr/share/fonts/opentype/noto/NotoSansMonoCJK-Regular.ttc", 0),
                ("C:/Windows/Fonts/msyh.ttc", 0),
                ("/System/Library/Fonts/Hiragino Sans GB.ttc", 0),
                ("/Library/Fonts/Arial Unicode.ttf", 0),
                ("/System/Library/Fonts/SFNSMono.ttf", 0),
                ("DejaVuSansMono.ttf", 0),
            ]
        elif bold:
            candidates = [
                (data_dir / "font-bold.ttf", 0),
                ("C:/Windows/Fonts/msyhbd.ttc", 0),
                ("/System/Library/Fonts/Hiragino Sans GB.ttc", 2),
                ("/System/Library/Fonts/PingFang.ttc", 1),
                ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 0),
                ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.otf", 0),
                ("NotoSansCJK-Bold.ttc", 0),
                (data_dir / "font.ttf", 0),
                ("/Library/Fonts/Arial Unicode.ttf", 0),
                ("DejaVuSans-Bold.ttf", 0),
            ]
        else:
            candidates = [
                (data_dir / "font.ttf", 0),
                ("C:/Windows/Fonts/msyh.ttc", 0),
                ("/System/Library/Fonts/Hiragino Sans GB.ttc", 0),
                ("/System/Library/Fonts/PingFang.ttc", 0),
                ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0),
                ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.otf", 0),
                ("NotoSansCJK-Regular.ttc", 0),
                ("/Library/Fonts/Arial Unicode.ttf", 0),
                ("DejaVuSans.ttf", 0),
            ]

        for font_path, index in candidates:
            try:
                font = ImageFont.truetype(str(font_path), size, index=index)
            except (OSError, TypeError):
                continue
            cls._font_cache[cache_key] = font
            return font

        font = ImageFont.load_default(size=size)
        cls._font_cache[cache_key] = font
        return font


class TextMeasurer:
    """Measure and wrap text using the actual selected font."""

    @staticmethod
    def get_text_size(
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    ) -> tuple[int, int]:
        """Measure the supplied text.

        Args:
            text: Text to measure.
            font: Pillow font used for measurement.

        Returns:
            Width and line height in pixels.
        """
        width = math.ceil(font.getlength(text)) if text else 0
        try:
            ascent, descent = font.getmetrics()
            height = math.ceil(ascent + descent)
        except AttributeError:
            left, top, right, bottom = font.getbbox(text or "Ag")
            height = math.ceil(bottom - top)
        return width, max(1, height)

    @staticmethod
    def split_text_to_fit_width(
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        max_width: int,
        *,
        preserve_whitespace: bool = False,
    ) -> list[str]:
        """Wrap text so every returned line fits the requested width.

        Args:
            text: A single logical line of text.
            font: Pillow font used for measurement.
            max_width: Maximum line width in pixels.
            preserve_whitespace: Preserve leading and trailing spaces for code.

        Returns:
            Wrapped lines. An empty input produces one empty line.
        """
        if not text:
            return [""]
        if max_width <= 0:
            return list(text)

        lines: list[str] = []
        remaining = text
        while remaining:
            if TextMeasurer.get_text_size(remaining, font)[0] <= max_width:
                lines.append(remaining if preserve_whitespace else remaining.rstrip())
                break

            low = 1
            high = len(remaining)
            while low <= high:
                middle = (low + high) // 2
                if TextMeasurer.get_text_size(remaining[:middle], font)[0] <= max_width:
                    low = middle + 1
                else:
                    high = middle - 1

            split_at = max(1, high)
            if not preserve_whitespace and split_at < len(remaining):
                prefix = remaining[:split_at]
                word_break = max(prefix.rfind(" "), prefix.rfind("\t"))
                if word_break >= max(1, split_at // 2):
                    split_at = word_break + 1

            line = remaining[:split_at]
            remaining = remaining[split_at:]
            if preserve_whitespace:
                lines.append(line)
            else:
                lines.append(line.rstrip())
                remaining = remaining.lstrip(" \t")

        return lines


@dataclass(frozen=True)
class InlineSpan:
    """A styled span inside a paragraph."""

    text: str
    bold: bool = False
    code: bool = False
    strike: bool = False
    link: bool = False


@dataclass
class InlineRun:
    """A measured inline span fragment placed on one visual line."""

    span: InlineSpan
    text: str
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont
    width: int


_INLINE_PATTERN = re.compile(
    r"(`[^`]+`|\*\*.+?\*\*|__.+?__|~~.+?~~|\[[^\]]+\]\([^)]+\)|(?<!\*)\*[^*]+\*(?!\*))"
)
_CJK_RANGE = "\u2e80-\u9fff\uf900-\ufaff"


def _parse_inline_spans(text: str) -> list[InlineSpan]:
    """Parse common inline Markdown without creating separate block rows.

    Args:
        text: Markdown paragraph text.

    Returns:
        Styled inline spans in source order.
    """
    spans: list[InlineSpan] = []
    position = 0
    for match in _INLINE_PATTERN.finditer(text):
        if match.start() > position:
            spans.append(InlineSpan(html.unescape(text[position : match.start()])))

        token = match.group(0)
        if token.startswith("`"):
            spans.append(InlineSpan(token[1:-1], code=True))
        elif token.startswith(("**", "__")):
            spans.append(InlineSpan(token[2:-2], bold=True))
        elif token.startswith("~~"):
            spans.append(InlineSpan(token[2:-2], strike=True))
        elif token.startswith("["):
            spans.append(InlineSpan(token[1 : token.index("]")], link=True))
        else:
            spans.append(InlineSpan(token[1:-1]))
        position = match.end()

    if position < len(text):
        spans.append(InlineSpan(html.unescape(text[position:])))
    return spans or [InlineSpan("")]


def _tokenize_inline_text(text: str) -> list[str]:
    """Split inline text into wrap-friendly Latin words and CJK characters.

    Args:
        text: Plain inline text.

    Returns:
        Tokens that may be placed independently during wrapping.
    """
    return re.findall(
        rf"\s+|[{_CJK_RANGE}]|[A-Za-z0-9_]+(?:['’-][A-Za-z0-9_]+)*|[^\s]",
        text,
    )


def _clean_inline_markdown(text: str) -> str:
    """Remove inline Markdown delimiters while preserving visible content.

    Args:
        text: Markdown text.

    Returns:
        Human-readable plain text.
    """
    cleaned = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = re.sub(
        r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), cleaned
    )
    cleaned = re.sub(r"~~(.+?)~~", r"\1", cleaned)
    cleaned = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", cleaned)
    cleaned = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", cleaned)
    cleaned = re.sub(r"(?<!\$)\$([^$]+)\$(?!\$)", r"\1", cleaned)
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    return html.unescape(cleaned)


class MarkdownBlock(ABC):
    """Base class for measured Markdown blocks."""

    height: int = 0

    @abstractmethod
    def measure(self, width: int, font_size: int) -> int:
        """Measure the block and cache its layout."""

    @abstractmethod
    def render(
        self,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        width: int,
        font_size: int,
    ) -> int:
        """Draw the cached layout and return the next y coordinate."""


class ParagraphBlock(MarkdownBlock):
    """A paragraph with mixed inline styles and automatic wrapping."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.lines: list[list[InlineRun]] = []
        self.line_height = 0

    def measure(self, width: int, font_size: int) -> int:
        """Lay out inline spans across visual lines.

        Args:
            width: Available content width.
            font_size: Base body font size.

        Returns:
            Measured block height.
        """
        regular_font = FontManager.get_font(font_size)
        _, font_height = TextMeasurer.get_text_size("Ag", regular_font)
        self.line_height = font_height + 8
        self.lines = []

        for source_line in self.content.split("\n"):
            current_line: list[InlineRun] = []
            current_width = 0
            for span in _parse_inline_spans(source_line):
                font = FontManager.get_font(
                    font_size if not span.code else max(16, font_size - 2),
                    bold=span.bold,
                    monospace=span.code,
                )
                for token in _tokenize_inline_text(span.text):
                    if token.isspace() and not current_line:
                        continue

                    token_width = TextMeasurer.get_text_size(token, font)[0]
                    if current_line and current_width + token_width > width:
                        self.lines.append(current_line)
                        current_line = []
                        current_width = 0
                        if token.isspace():
                            continue

                    if token_width > width:
                        fragments = TextMeasurer.split_text_to_fit_width(
                            token,
                            font,
                            width,
                        )
                    else:
                        fragments = [token]

                    for fragment_index, fragment in enumerate(fragments):
                        fragment_width = TextMeasurer.get_text_size(fragment, font)[0]
                        if current_line and current_width + fragment_width > width:
                            self.lines.append(current_line)
                            current_line = []
                            current_width = 0

                        if (
                            current_line
                            and current_line[-1].span == span
                            and fragment_index == 0
                        ):
                            previous = current_line[-1]
                            previous.text += fragment
                            previous.width = TextMeasurer.get_text_size(
                                previous.text,
                                previous.font,
                            )[0]
                            current_width = sum(run.width for run in current_line)
                        else:
                            current_line.append(
                                InlineRun(span, fragment, font, fragment_width)
                            )
                            current_width += fragment_width

                        if fragment_index < len(fragments) - 1:
                            self.lines.append(current_line)
                            current_line = []
                            current_width = 0

            self.lines.append(current_line)

        self.height = max(1, len(self.lines)) * self.line_height + 7
        return self.height

    def render(
        self,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        width: int,
        font_size: int,
    ) -> int:
        """Render the paragraph.

        Args:
            image: Destination image.
            draw: Pillow drawing context.
            x: Left content coordinate.
            y: Top block coordinate.
            width: Available content width.
            font_size: Base body font size.

        Returns:
            The next y coordinate.
        """
        del image, width, font_size
        text_y = y
        for line in self.lines:
            text_x = x
            for run in line:
                if run.span.code:
                    draw.rounded_rectangle(
                        (
                            text_x - 3,
                            text_y + 1,
                            text_x + run.width + 3,
                            text_y + self.line_height - 4,
                        ),
                        radius=3,
                        fill=CODE_FILL,
                        outline=LINE,
                        width=1,
                    )
                color = ACCENT if run.span.link else INK
                draw.text((text_x, text_y), run.text, font=run.font, fill=color)
                if run.span.strike:
                    strike_y = text_y + self.line_height // 2
                    draw.line(
                        (text_x, strike_y, text_x + run.width, strike_y),
                        fill=MUTED,
                        width=1,
                    )
                text_x += run.width
            text_y += self.line_height
        return y + self.height


class HeadingBlock(MarkdownBlock):
    """A Markdown heading with balanced spacing and wrapping."""

    def __init__(self, content: str, level: int, *, show_rule: bool = True) -> None:
        self.content = _clean_inline_markdown(content)
        self.level = max(1, min(level, 6))
        self.show_rule = show_rule
        self.lines: list[str] = []
        self.font: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = None
        self.line_height = 0
        self.top_gap = 0
        self.bottom_gap = 0

    def measure(self, width: int, font_size: int) -> int:
        """Measure the heading.

        Args:
            width: Available content width.
            font_size: Base body font size.

        Returns:
            Measured heading height.
        """
        factors = (1.84, 1.48, 1.28, 1.12, 1.0, 0.92)
        heading_size = max(18, round(font_size * factors[self.level - 1]))
        self.font = FontManager.get_font(heading_size, bold=True)
        _, measured_height = TextMeasurer.get_text_size("Ag", self.font)
        self.line_height = measured_height + 6
        self.lines = TextMeasurer.split_text_to_fit_width(
            self.content,
            self.font,
            width,
        )
        self.top_gap = (0, 28, 22, 18, 15, 13)[self.level - 1]
        self.bottom_gap = (14, 12, 10, 8, 7, 6)[self.level - 1]
        self.height = (
            self.top_gap + len(self.lines) * self.line_height + self.bottom_gap
        )
        return self.height

    def render(
        self,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        width: int,
        font_size: int,
    ) -> int:
        """Render the heading.

        Args:
            image: Destination image.
            draw: Pillow drawing context.
            x: Left content coordinate.
            y: Top block coordinate.
            width: Available content width.
            font_size: Base body font size.

        Returns:
            The next y coordinate.
        """
        del image, font_size
        text_y = y + self.top_gap
        if self.level == 2 and self.show_rule:
            draw.line(
                (
                    x,
                    y + max(8, self.top_gap - 10),
                    x + width,
                    y + max(8, self.top_gap - 10),
                ),
                fill=LINE,
                width=1,
            )
        for line in self.lines:
            draw.text((x, text_y), line, font=self.font, fill=INK)
            text_y += self.line_height
        return y + self.height


class RuleBlock(MarkdownBlock):
    """A horizontal Markdown rule."""

    def measure(self, width: int, font_size: int) -> int:
        """Measure the rule.

        Args:
            width: Available content width.
            font_size: Base body font size.

        Returns:
            Fixed rule height.
        """
        del width, font_size
        self.height = 30
        return self.height

    def render(
        self,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        width: int,
        font_size: int,
    ) -> int:
        """Render the horizontal rule.

        Args:
            image: Destination image.
            draw: Pillow drawing context.
            x: Left content coordinate.
            y: Top block coordinate.
            width: Available content width.
            font_size: Base body font size.

        Returns:
            The next y coordinate.
        """
        del image, font_size
        draw.line((x, y + 15, x + width, y + 15), fill=LINE, width=1)
        return y + self.height


class QuoteBlock(MarkdownBlock):
    """A grouped block quote."""

    def __init__(self, content: str) -> None:
        self.content = _clean_inline_markdown(content)
        self.lines: list[str] = []
        self.font: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = None
        self.line_height = 0

    def measure(self, width: int, font_size: int) -> int:
        """Measure quote text inside its inset panel.

        Args:
            width: Available content width.
            font_size: Base body font size.

        Returns:
            Measured quote height.
        """
        self.font = FontManager.get_font(max(16, font_size - 1))
        _, measured_height = TextMeasurer.get_text_size("Ag", self.font)
        self.line_height = measured_height + 7
        self.lines = []
        for source_line in self.content.split("\n"):
            self.lines.extend(
                TextMeasurer.split_text_to_fit_width(
                    source_line,
                    self.font,
                    width - 32,
                )
            )
        self.height = len(self.lines) * self.line_height + 28
        return self.height

    def render(
        self,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        width: int,
        font_size: int,
    ) -> int:
        """Render the quote panel.

        Args:
            image: Destination image.
            draw: Pillow drawing context.
            x: Left content coordinate.
            y: Top block coordinate.
            width: Available content width.
            font_size: Base body font size.

        Returns:
            The next y coordinate.
        """
        del image, font_size
        draw.rectangle((x, y + 4, x + width, y + self.height - 4), fill=SOFT_FILL)
        draw.line((x, y + 4, x + width, y + 4), fill=LINE, width=1)
        draw.line(
            (x, y + self.height - 4, x + width, y + self.height - 4),
            fill=LINE,
            width=1,
        )
        text_y = y + 13
        for line in self.lines:
            draw.text((x + 16, text_y), line, font=self.font, fill=MUTED)
            text_y += self.line_height
        return y + self.height


@dataclass
class ListEntry:
    """A parsed ordered, unordered, or task-list item."""

    marker: str
    content: str
    depth: int = 0
    checked: bool | None = None


class ListBlock(MarkdownBlock):
    """A consecutive Markdown list."""

    def __init__(self, entries: list[ListEntry]) -> None:
        self.entries = entries
        self.layouts: list[tuple[ListEntry, list[str]]] = []
        self.font: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = None
        self.line_height = 0

    def measure(self, width: int, font_size: int) -> int:
        """Measure all list items with hanging indentation.

        Args:
            width: Available content width.
            font_size: Base body font size.

        Returns:
            Measured list height.
        """
        self.font = FontManager.get_font(font_size)
        _, measured_height = TextMeasurer.get_text_size("Ag", self.font)
        self.line_height = measured_height + 7
        self.layouts = []
        total_height = 6
        for entry in self.entries:
            indent = min(entry.depth, 3) * 22
            lines = TextMeasurer.split_text_to_fit_width(
                _clean_inline_markdown(entry.content),
                self.font,
                max(40, width - 34 - indent),
            )
            self.layouts.append((entry, lines))
            total_height += len(lines) * self.line_height + 5
        self.height = total_height + 3
        return self.height

    def render(
        self,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        width: int,
        font_size: int,
    ) -> int:
        """Render list markers and wrapped item text.

        Args:
            image: Destination image.
            draw: Pillow drawing context.
            x: Left content coordinate.
            y: Top block coordinate.
            width: Available content width.
            font_size: Base body font size.

        Returns:
            The next y coordinate.
        """
        del image, width, font_size
        text_y = y + 6
        for entry, lines in self.layouts:
            indent = min(entry.depth, 3) * 22
            marker_x = x + indent
            text_x = marker_x + 30
            if entry.checked is None:
                draw.text(
                    (marker_x, text_y),
                    entry.marker,
                    font=self.font,
                    fill=ACCENT,
                )
            else:
                box_top = text_y + 6
                draw.rectangle(
                    (marker_x + 2, box_top, marker_x + 16, box_top + 14),
                    outline=ACCENT,
                    width=2,
                )
                if entry.checked:
                    draw.line(
                        (
                            marker_x + 5,
                            box_top + 7,
                            marker_x + 9,
                            box_top + 11,
                            marker_x + 15,
                            box_top + 3,
                        ),
                        fill=ACCENT,
                        width=2,
                        joint="curve",
                    )
            for line in lines:
                draw.text((text_x, text_y), line, font=self.font, fill=INK)
                text_y += self.line_height
            text_y += 5
        return y + self.height


class CodeBlock(MarkdownBlock):
    """A fenced code block with preserved indentation and wrapping."""

    def __init__(self, content: list[str], language: str = "") -> None:
        self.content = content or [""]
        self.language = language
        self.lines: list[str] = []
        self.font: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = None
        self.label_font: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = None
        self.line_height = 0
        self.label_height = 0

    def measure(self, width: int, font_size: int) -> int:
        """Measure wrapped code lines.

        Args:
            width: Available content width.
            font_size: Base body font size.

        Returns:
            Measured code-block height.
        """
        code_size = max(16, font_size - 5)
        self.font = FontManager.get_font(code_size, monospace=True)
        self.label_font = FontManager.get_font(max(13, code_size - 5), bold=True)
        _, measured_height = TextMeasurer.get_text_size("Ag", self.font)
        self.line_height = measured_height + 6
        self.label_height = 22 if self.language else 0
        self.lines = []
        for source_line in self.content:
            self.lines.extend(
                TextMeasurer.split_text_to_fit_width(
                    source_line,
                    self.font,
                    width - 30,
                    preserve_whitespace=True,
                )
            )
        self.height = 24 + self.label_height + len(self.lines) * self.line_height
        return self.height

    def render(
        self,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        width: int,
        font_size: int,
    ) -> int:
        """Render the code panel.

        Args:
            image: Destination image.
            draw: Pillow drawing context.
            x: Left content coordinate.
            y: Top block coordinate.
            width: Available content width.
            font_size: Base body font size.

        Returns:
            The next y coordinate.
        """
        del image, font_size
        draw.rounded_rectangle(
            (x, y + 4, x + width, y + self.height - 4),
            radius=4,
            fill=CODE_FILL,
            outline=LINE,
            width=1,
        )
        text_y = y + 13
        if self.language:
            label = self.language.upper()
            label_width = TextMeasurer.get_text_size(label, self.label_font)[0]
            draw.text(
                (x + width - label_width - 14, text_y),
                label,
                font=self.label_font,
                fill=MUTED,
            )
            text_y += self.label_height
        for line in self.lines:
            draw.text((x + 15, text_y), line, font=self.font, fill=INK)
            text_y += self.line_height
        return y + self.height


class MathBlock(MarkdownBlock):
    """A display-math fallback that keeps TeX source readable and wrapped."""

    def __init__(self, content: str) -> None:
        self.content = content.strip()
        self.lines: list[str] = []
        self.font: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = None
        self.line_height = 0

    def measure(self, width: int, font_size: int) -> int:
        """Measure display-math source.

        Args:
            width: Available content width.
            font_size: Base body font size.

        Returns:
            Measured block height.
        """
        self.font = FontManager.get_font(max(16, font_size - 2), monospace=True)
        _, measured_height = TextMeasurer.get_text_size("Ag", self.font)
        self.line_height = measured_height + 7
        self.lines = []
        for source_line in self.content.split("\n"):
            self.lines.extend(
                TextMeasurer.split_text_to_fit_width(
                    source_line.strip(),
                    self.font,
                    width - 28,
                )
            )
        self.height = len(self.lines) * self.line_height + 24
        return self.height

    def render(
        self,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        width: int,
        font_size: int,
    ) -> int:
        """Render display-math source as a centered local fallback.

        Args:
            image: Destination image.
            draw: Pillow drawing context.
            x: Left content coordinate.
            y: Top block coordinate.
            width: Available content width.
            font_size: Base body font size.

        Returns:
            The next y coordinate.
        """
        del image, font_size
        text_y = y + 10
        for line in self.lines:
            line_width = TextMeasurer.get_text_size(line, self.font)[0]
            draw.text(
                (x + max(0, (width - line_width) // 2), text_y),
                line,
                font=self.font,
                fill=INK,
            )
            text_y += self.line_height
        return y + self.height


class TableBlock(MarkdownBlock):
    """A compact GFM table with alignment and content-aware columns."""

    def __init__(
        self,
        headers: list[str],
        rows: list[list[str]],
        alignments: list[str],
    ) -> None:
        self.headers = headers
        self.rows = rows
        self.alignments = alignments
        self.column_widths: list[int] = []
        self.row_layouts: list[list[list[str]]] = []
        self.row_heights: list[int] = []
        self.body_font: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = None
        self.header_font: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = None
        self.line_height = 0

    def measure(self, width: int, font_size: int) -> int:
        """Measure cells and allocate content-aware column widths.

        Args:
            width: Available content width.
            font_size: Base body font size.

        Returns:
            Measured table height including outer spacing.
        """
        table_size = max(16, font_size - 4)
        self.body_font = FontManager.get_font(table_size)
        self.header_font = FontManager.get_font(table_size, bold=True)
        _, measured_height = TextMeasurer.get_text_size("Ag", self.body_font)
        self.line_height = measured_height + 6

        column_count = len(self.headers)
        all_rows = [self.headers, *self.rows]
        natural_widths: list[int] = []
        for column_index in range(column_count):
            measured = max(
                TextMeasurer.get_text_size(
                    _clean_inline_markdown(
                        row[column_index] if column_index < len(row) else ""
                    ),
                    self.header_font if row is self.headers else self.body_font,
                )[0]
                for row in all_rows
            )
            natural_widths.append(min(measured + 24, int(width * 0.55)))

        minimum_width = min(78, max(42, width // max(1, column_count * 2)))
        remaining_width = max(0, width - minimum_width * column_count)
        total_natural = max(1, sum(natural_widths))
        self.column_widths = [
            minimum_width + int(remaining_width * natural / total_natural)
            for natural in natural_widths
        ]
        self.column_widths[-1] += width - sum(self.column_widths)

        self.row_layouts = []
        self.row_heights = []
        for row_index, row in enumerate(all_rows):
            font = self.header_font if row_index == 0 else self.body_font
            cell_layouts: list[list[str]] = []
            for column_index, column_width in enumerate(self.column_widths):
                content = _clean_inline_markdown(
                    row[column_index] if column_index < len(row) else ""
                )
                cell_layouts.append(
                    TextMeasurer.split_text_to_fit_width(
                        content,
                        font,
                        max(20, column_width - 24),
                    )
                )
            self.row_layouts.append(cell_layouts)
            self.row_heights.append(
                max(len(lines) for lines in cell_layouts) * self.line_height + 20
            )

        self.height = sum(self.row_heights) + 16
        return self.height

    def render(
        self,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        width: int,
        font_size: int,
    ) -> int:
        """Render the table grid and cell contents.

        Args:
            image: Destination image.
            draw: Pillow drawing context.
            x: Left content coordinate.
            y: Top block coordinate.
            width: Available content width.
            font_size: Base body font size.

        Returns:
            The next y coordinate.
        """
        del image, font_size
        table_y = y + 8
        table_height = sum(self.row_heights)
        row_y = table_y
        for row_index, row_height in enumerate(self.row_heights):
            if row_index == 0:
                fill = (238, 241, 242)
            elif row_index % 2 == 0:
                fill = (247, 248, 248)
            else:
                fill = (253, 253, 252)
            draw.rectangle((x, row_y, x + width, row_y + row_height), fill=fill)

            column_x = x
            font = self.header_font if row_index == 0 else self.body_font
            for column_index, column_width in enumerate(self.column_widths):
                text_y = row_y + 10
                alignment = (
                    self.alignments[column_index]
                    if column_index < len(self.alignments)
                    else "left"
                )
                for line in self.row_layouts[row_index][column_index]:
                    line_width = TextMeasurer.get_text_size(line, font)[0]
                    if alignment == "center":
                        text_x = column_x + max(12, (column_width - line_width) // 2)
                    elif alignment == "right":
                        text_x = column_x + column_width - line_width - 12
                    else:
                        text_x = column_x + 12
                    draw.text((text_x, text_y), line, font=font, fill=INK)
                    text_y += self.line_height
                column_x += column_width
            row_y += row_height

        draw.rectangle(
            (x, table_y, x + width, table_y + table_height),
            outline=STRONG_LINE,
            width=1,
        )
        row_y = table_y
        for row_height in self.row_heights[:-1]:
            row_y += row_height
            draw.line((x, row_y, x + width, row_y), fill=LINE, width=1)
        column_x = x
        for column_width in self.column_widths[:-1]:
            column_x += column_width
            draw.line(
                (column_x, table_y, column_x, table_y + table_height),
                fill=LINE,
                width=1,
            )
        return y + self.height


class ImageBlock(MarkdownBlock):
    """A remotely loaded Markdown image with a readable failure fallback."""

    def __init__(self, alt_text: str, image_url: str) -> None:
        self.alt_text = alt_text
        self.image_url = image_url
        self.image: Image.Image | None = None
        self.display_image: Image.Image | None = None
        self.fallback_lines: list[str] = []
        self.font: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = None

    async def load(self) -> None:
        """Load the image over HTTP with a bounded timeout."""
        timeout = aiohttp.ClientTimeout(total=12)
        try:
            async with (
                aiohttp.ClientSession(
                    trust_env=True,
                    connector=build_tls_connector(),
                    timeout=timeout,
                ) as session,
                session.get(self.image_url) as response,
            ):
                if response.status != 200:
                    logger.warning(
                        "Failed to load local T2I image %s: HTTP %s",
                        self.image_url,
                        response.status,
                    )
                    return
                image_data = await response.read()
            with Image.open(BytesIO(image_data)) as loaded:
                self.image = loaded.convert("RGBA").copy()
        except Exception as err:
            logger.warning(
                "Failed to load local T2I image %s: %s",
                self.image_url,
                err,
            )

    def measure(self, width: int, font_size: int) -> int:
        """Measure the resized image or its failure message.

        Args:
            width: Available content width.
            font_size: Base body font size.

        Returns:
            Measured image-block height.
        """
        if self.image is None:
            self.font = FontManager.get_font(max(16, font_size - 2))
            self.fallback_lines = TextMeasurer.split_text_to_fit_width(
                f"[Image unavailable: {self.alt_text or self.image_url}]",
                self.font,
                width,
            )
            _, line_height = TextMeasurer.get_text_size("Ag", self.font)
            self.height = len(self.fallback_lines) * (line_height + 6) + 16
            return self.height

        display = self.image.copy()
        display.thumbnail((width, 900), Image.Resampling.LANCZOS)
        self.display_image = display
        self.height = display.height + 20
        return self.height

    def render(
        self,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        width: int,
        font_size: int,
    ) -> int:
        """Render the image or failure text.

        Args:
            image: Destination image.
            draw: Pillow drawing context.
            x: Left content coordinate.
            y: Top block coordinate.
            width: Available content width.
            font_size: Base body font size.

        Returns:
            The next y coordinate.
        """
        del font_size
        if self.display_image is None:
            text_y = y + 7
            _, line_height = TextMeasurer.get_text_size("Ag", self.font)
            for line in self.fallback_lines:
                draw.text((x, text_y), line, font=self.font, fill=MUTED)
                text_y += line_height + 6
            return y + self.height

        paste_x = x + (width - self.display_image.width) // 2
        paste_y = y + 10
        image.paste(self.display_image, (paste_x, paste_y), self.display_image)
        draw.rectangle(
            (
                paste_x,
                paste_y,
                paste_x + self.display_image.width,
                paste_y + self.display_image.height,
            ),
            outline=LINE,
            width=1,
        )
        return y + self.height


class MarkdownParser:
    """Parse a practical subset of Markdown into local-render blocks."""

    _heading_pattern = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*$")
    _list_pattern = re.compile(r"^(\s*)([-+*]|\d+[.)])\s+(.+)$")
    _rule_pattern = re.compile(r"^\s{0,3}((\*\s*){3,}|(-\s*){3,}|(_\s*){3,})$")
    _image_pattern = re.compile(
        r"^\s*!\[([^\]]*)\]\((\S+?)(?:\s+[\"'][^\"']*[\"'])?\)\s*$"
    )
    _table_separator_pattern = re.compile(
        r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$"
    )

    @classmethod
    def _is_table_start(cls, lines: list[str], index: int) -> bool:
        """Return whether the current and following lines start a GFM table.

        Args:
            lines: Source Markdown lines.
            index: Current source-line index.

        Returns:
            True when a header and separator row are present.
        """
        return (
            index + 1 < len(lines)
            and "|" in lines[index]
            and bool(cls._table_separator_pattern.match(lines[index + 1]))
        )

    @staticmethod
    def _split_table_row(line: str) -> list[str]:
        """Split a simple GFM table row.

        Args:
            line: Raw table row.

        Returns:
            Trimmed cell contents.
        """
        return [cell.strip() for cell in line.strip().strip("|").split("|")]

    @classmethod
    def _starts_block(cls, lines: list[str], index: int) -> bool:
        """Return whether a source line begins a non-paragraph block.

        Args:
            lines: Source Markdown lines.
            index: Current source-line index.

        Returns:
            True when parsing should end the active paragraph.
        """
        stripped = lines[index].strip()
        return bool(
            not stripped
            or stripped.startswith(("```", "$$", ">"))
            or cls._heading_pattern.match(lines[index])
            or cls._rule_pattern.match(lines[index])
            or cls._list_pattern.match(lines[index])
            or cls._image_pattern.match(lines[index])
            or cls._is_table_start(lines, index)
        )

    @classmethod
    async def parse(cls, text: str) -> list[MarkdownBlock]:
        """Parse Markdown and load referenced images.

        Args:
            text: Markdown source.

        Returns:
            Parsed and image-ready block objects.
        """
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").expandtabs(4)
        lines = normalized.split("\n")
        blocks: list[MarkdownBlock] = []
        image_blocks: list[ImageBlock] = []
        index = 0

        while index < len(lines):
            line = lines[index]
            stripped = line.strip()
            if not stripped:
                index += 1
                continue

            fence_match = re.match(r"^\s*```([^\s`]*)", line)
            if fence_match:
                language = fence_match.group(1)
                code_lines: list[str] = []
                index += 1
                while index < len(lines) and not re.match(r"^\s*```", lines[index]):
                    code_lines.append(lines[index])
                    index += 1
                if index < len(lines):
                    index += 1
                blocks.append(CodeBlock(code_lines, language))
                continue

            if stripped.startswith("$$"):
                if stripped.endswith("$$") and len(stripped) > 4:
                    math_content = stripped[2:-2].strip()
                    index += 1
                else:
                    math_lines: list[str] = []
                    opening_remainder = stripped[2:].strip()
                    if opening_remainder:
                        math_lines.append(opening_remainder)
                    index += 1
                    while index < len(lines) and not lines[index].strip().endswith(
                        "$$"
                    ):
                        math_lines.append(lines[index])
                        index += 1
                    if index < len(lines):
                        closing = lines[index].strip()
                        if closing != "$$":
                            math_lines.append(closing[:-2].rstrip())
                        index += 1
                    math_content = "\n".join(math_lines)
                blocks.append(MathBlock(math_content))
                continue

            image_match = cls._image_pattern.match(line)
            if image_match:
                image_block = ImageBlock(image_match.group(1), image_match.group(2))
                image_blocks.append(image_block)
                blocks.append(image_block)
                index += 1
                continue

            heading_match = cls._heading_pattern.match(line)
            if heading_match:
                level = len(heading_match.group(1))
                blocks.append(
                    HeadingBlock(
                        heading_match.group(2),
                        level,
                        show_rule=level != 2
                        or not blocks
                        or not isinstance(blocks[-1], RuleBlock),
                    )
                )
                index += 1
                continue

            if cls._rule_pattern.match(line):
                blocks.append(RuleBlock())
                index += 1
                continue

            if cls._is_table_start(lines, index):
                headers = cls._split_table_row(lines[index])
                separator = cls._split_table_row(lines[index + 1])
                alignments = []
                for cell in separator:
                    stripped_cell = cell.strip()
                    if stripped_cell.startswith(":") and stripped_cell.endswith(":"):
                        alignments.append("center")
                    elif stripped_cell.endswith(":"):
                        alignments.append("right")
                    else:
                        alignments.append("left")
                index += 2
                rows: list[list[str]] = []
                while (
                    index < len(lines) and "|" in lines[index] and lines[index].strip()
                ):
                    rows.append(cls._split_table_row(lines[index]))
                    index += 1
                blocks.append(TableBlock(headers, rows, alignments))
                continue

            if stripped.startswith(">"):
                quote_lines: list[str] = []
                while index < len(lines) and lines[index].strip().startswith(">"):
                    quote_lines.append(re.sub(r"^\s*>\s?", "", lines[index]))
                    index += 1
                blocks.append(QuoteBlock("\n".join(quote_lines)))
                continue

            list_match = cls._list_pattern.match(line)
            if list_match:
                entries: list[ListEntry] = []
                while index < len(lines):
                    item_match = cls._list_pattern.match(lines[index])
                    if item_match:
                        indent, marker, content = item_match.groups()
                        checked: bool | None = None
                        task_match = re.match(r"^\[([ xX])\]\s+(.*)$", content)
                        if task_match:
                            checked = task_match.group(1).lower() == "x"
                            content = task_match.group(2)
                        visible_marker = "•" if not marker[0].isdigit() else marker
                        entries.append(
                            ListEntry(
                                visible_marker,
                                content,
                                min(3, len(indent) // 2),
                                checked,
                            )
                        )
                        index += 1
                        continue
                    if (
                        entries
                        and index < len(lines)
                        and lines[index].startswith("  ")
                        and lines[index].strip()
                    ):
                        entries[-1].content += " " + lines[index].strip()
                        index += 1
                        continue
                    break
                blocks.append(ListBlock(entries))
                continue

            paragraph_lines = [line.strip()]
            index += 1
            while index < len(lines) and not cls._starts_block(lines, index):
                paragraph_lines.append(lines[index].strip())
                index += 1
            blocks.append(ParagraphBlock("\n".join(paragraph_lines)))

        if image_blocks:
            await asyncio.gather(*(block.load() for block in image_blocks))
        return blocks


class MarkdownRenderer:
    """Render parsed Markdown blocks into a compact branded image."""

    def __init__(
        self,
        font_size: int = 25,
        width: int = 800,
        bg_color: tuple[int, int, int] = PAPER,
    ) -> None:
        """Initialize the local renderer.

        Args:
            font_size: Base body font size.
            width: Output image width.
            bg_color: RGB background color.
        """
        self.font_size = font_size
        self.width = max(320, width)
        self.bg_color = bg_color

    def _draw_masthead(self, draw: ImageDraw.ImageDraw) -> None:
        """Draw the AstrBot mark, wordmark, and version.

        Args:
            draw: Pillow drawing context.
        """
        center_x = CONTENT_MARGIN + 14
        center_y = 43
        outer = 13
        inner = 4
        draw.polygon(
            [
                (center_x, center_y - outer),
                (center_x + inner, center_y - inner),
                (center_x + outer, center_y),
                (center_x + inner, center_y + inner),
                (center_x, center_y + outer),
                (center_x - inner, center_y + inner),
                (center_x - outer, center_y),
                (center_x - inner, center_y - inner),
            ],
            fill=ACCENT,
        )
        small_x = center_x + 16
        small_y = center_y - 14
        draw.polygon(
            [
                (small_x, small_y - 5),
                (small_x + 2, small_y - 2),
                (small_x + 5, small_y),
                (small_x + 2, small_y + 2),
                (small_x, small_y + 5),
                (small_x - 2, small_y + 2),
                (small_x - 5, small_y),
                (small_x - 2, small_y - 2),
            ],
            fill=ACCENT,
        )

        brand_font = FontManager.get_font(28, bold=True)
        version_font = FontManager.get_font(18)
        draw.text((CONTENT_MARGIN + 42, 27), "AstrBot", font=brand_font, fill=INK)
        version_text = f"v{VERSION}"
        version_width = TextMeasurer.get_text_size(version_text, version_font)[0]
        draw.text(
            (self.width - CONTENT_MARGIN - version_width, 31),
            version_text,
            font=version_font,
            fill=MUTED,
        )

    async def render(self, markdown_text: str) -> Image.Image:
        """Render Markdown into a Pillow image.

        Args:
            markdown_text: Markdown source.

        Returns:
            Rendered RGB image.
        """
        blocks = await MarkdownParser.parse(markdown_text)
        content_width = self.width - CONTENT_MARGIN * 2
        masthead_height = 91
        bottom_padding = 34
        total_height = masthead_height + bottom_padding
        for block in blocks:
            total_height += block.measure(content_width, self.font_size)

        image = Image.new(
            "RGB",
            (self.width, max(140, total_height)),
            self.bg_color,
        )
        draw = ImageDraw.Draw(image)
        self._draw_masthead(draw)

        y = masthead_height
        for block in blocks:
            y = block.render(
                image,
                draw,
                CONTENT_MARGIN,
                y,
                content_width,
                self.font_size,
            )
        return image


class LocalRenderStrategy(RenderStrategy):
    """Render Markdown locally with Pillow when remote T2I is unavailable."""

    async def render_custom_template(
        self,
        tmpl_str: str,
        tmpl_data: dict,
        return_url: bool = True,
    ) -> str:
        """Reject HTML templates because the local backend is Markdown-only.

        Args:
            tmpl_str: HTML template source.
            tmpl_data: Template variables.
            return_url: Whether the caller requested a URL.

        Raises:
            NotImplementedError: Always, because Pillow cannot render HTML templates.
        """
        del tmpl_str, tmpl_data, return_url
        raise NotImplementedError

    async def render(self, text: str, return_url: bool = False) -> str:
        """Render Markdown locally and save it as a temporary image.

        Args:
            text: Markdown source.
            return_url: Retained for strategy compatibility; local output is a path.

        Returns:
            Path to the saved temporary image.
        """
        del return_url
        renderer = MarkdownRenderer(font_size=25, width=800)
        image = await renderer.render(text)
        return save_temp_img(image)
