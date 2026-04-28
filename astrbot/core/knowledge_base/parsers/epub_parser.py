"""EPUB document parser."""

import html
import re

from astrbot.core.knowledge_base.parsers.base import BaseParser, ParseResult

_KEYS = (
    "Title|Author|Creator|Language|Publisher|Date|Modified|Identifier|ISBN|Description|"
    "Subject|Rights|Source|Series|标题|书名|作者|语言|出版社|日期|出版日期|标识符|简介|描述|"
    "主题|版权|来源|系列|タイトル|書名|著者|言語|出版社|日付|識別子|説明|件名|権利|ソース|シリーズ"
)
_META_RE = re.compile(rf"^\s*(?:[-*]\s*)?\*\*(?:{_KEYS})\s*[:：]\*\*\s+\S")
_TOC_HEAD_RE = re.compile(
    r"^\s{0,3}(?:#{1,6}\s*)?(?:table of contents|contents|toc|目录|目次|もくじ)\s*$",
    re.I,
)
_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)")
_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_EMPTY_IMG_LINK_RE = re.compile(
    r"\[\s*\]\([^)]+\.(?:png|jpe?g|gif|webp|svg)(?:#[^)]+)?\)", re.I
)
_FOOTNOTE_LABEL_RE = re.compile(
    r"^(?:\d{1,3}|[ivxlcdm]{1,8}|[*†‡§¶]|↩|↑|back|return|返回|回到正文)$", re.I
)
_FOOTNOTE_HREF_RE = re.compile(
    r"(?:^#|[#/_-](?:fn|footnote|note|noteref|backlink|return|filepos)\b)", re.I
)
_DOTTED_TOC_RE = re.compile(r"^\s*.+?\.{2,}\s*(?:\d+|[ivxlcdm]+)\s*$", re.I)
_SEP_RE = re.compile(r"^\s*(?:[-=*_]){3,}\s*$")
_NOISE_RE = re.compile(
    r"^\s*(?:\[\s*)?(?:\d{1,3}|[ivxlcdm]{1,8}|[*†‡§¶]|↩|↑)(?:\s*\])?\s*$", re.I
)
_GENERIC_ALT_RE = re.compile(
    r"^(?:image|img|picture|photo|illustration|figure|fig|cover|插图|图片|图像|封面)\s*[\d._-]*$",
    re.I,
)
_FILENAME_ALT_RE = re.compile(r"^[\w.\- ]+\.(?:png|jpe?g|gif|webp|svg)$", re.I)


def _n(s: str) -> str:
    return (
        html.unescape(s)
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\ufeff", "")
        .replace("\u00a0", " ")
        .replace("\u200b", "")
    )


def _is_internal(href: str) -> bool:
    href = html.unescape(href).strip().lower()
    return (
        href.startswith("#")
        or href.endswith(".html")
        or href.endswith(".xhtml")
        or ".html#" in href
        or ".xhtml#" in href
    )


def _is_toc_line(s: str) -> bool:
    s = s.strip()
    if not s:
        return False
    s = re.sub(r"^\s*(?:[-*+]|\d+\.)\s+", "", s)
    m = re.fullmatch(r"\[([^\]]+)\]\(([^)]+)\)", s)
    return bool((m and _is_internal(m.group(2))) or _DOTTED_TOC_RE.match(s))


def _strip_head(text: str) -> str:
    lines = _n(text).split("\n")
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    start = i
    while i < len(lines) and _META_RE.match(lines[i].strip()):
        i += 1
    if i - start >= 2:
        while i < len(lines) and not lines[i].strip():
            i += 1
    else:
        i = start
    toc0, had_head = i, False
    if i < len(lines) and _TOC_HEAD_RE.match(lines[i].strip()):
        had_head = True
        i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
    toc = 0
    while i < len(lines) and i - toc0 < 120:
        s = lines[i].strip()
        if not s:
            if toc and i + 1 < len(lines) and _is_toc_line(lines[i + 1]):
                i += 1
                continue
            break
        if not _is_toc_line(s):
            break
        toc += 1
        i += 1
    if toc >= 2 and (had_head or toc >= 3):
        while i < len(lines) and not lines[i].strip():
            i += 1
        return "\n".join(lines[i:]).strip()
    return "\n".join(lines[toc0:]).strip()


def _strip_links(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        label = html.unescape(m.group(1)).strip()
        href = html.unescape(m.group(2)).strip().lower()
        if not _is_internal(href):
            return m.group(0)
        if _FOOTNOTE_HREF_RE.search(href) or (
            href.startswith("#") and _FOOTNOTE_LABEL_RE.fullmatch(label)
        ):
            return ""
        return label

    return _LINK_RE.sub(repl, _n(text))


def _img_alt(m: re.Match[str]) -> str:
    alt = re.sub(r"\s+", " ", html.unescape(m.group(1)).strip())
    if not alt or _GENERIC_ALT_RE.fullmatch(alt) or _FILENAME_ALT_RE.fullmatch(alt):
        return ""
    return alt


def _sanitize(text: str) -> str:
    out, prev_blank, prev = [], True, ""
    for raw in _n(text).split("\n"):
        line = _IMG_RE.sub(_img_alt, raw)
        line = _EMPTY_IMG_LINK_RE.sub("", line).rstrip()
        s = line.strip()
        if not s:
            if not prev_blank:
                out.append("")
                prev_blank = True
            continue
        if _SEP_RE.match(s) or _NOISE_RE.match(s):
            continue
        norm = re.sub(r"^\s{0,3}#{1,6}\s*", "", s).strip("*_ ").casefold()
        if norm and norm == prev and len(norm) <= 120:
            continue
        out.append(line)
        prev_blank = False
        prev = norm
    return "\n".join(out).strip()


class EpubParser(BaseParser):
    """Parse EPUB files via MarkItDown."""

    async def parse(self, file_content: bytes, file_name: str) -> ParseResult:
        from .markitdown_parser import MarkitdownParser

        result = await MarkitdownParser().parse(file_content, file_name)
        text = _sanitize(_strip_links(_strip_head(result.text)))
        return ParseResult(text=text, media=result.media)
