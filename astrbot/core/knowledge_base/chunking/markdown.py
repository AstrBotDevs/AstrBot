"""Markdown 感知分块器

根据 Markdown 标题层级结构进行分块，保持每个章节的语义完整性。
对于超过 chunk_size 的章节，内部使用递归字符分割。
"""

import re
from dataclasses import dataclass

from .base import BaseChunker
from .recursive import RecursiveCharacterChunker


@dataclass
class _Section:
    """解析后的 Markdown 章节"""

    heading_path: list[str]
    title_path: list[str]
    section_index: int | None
    text: str
    has_body: bool


@dataclass
class MarkdownChunk:
    """A Markdown chunk with source structure metadata."""

    text: str
    title_path: list[str] | None = None
    section_index: int | None = None


@dataclass
class _ChunkDraft:
    text: str
    has_body: bool
    title_path: list[str] | None
    section_index: int | None


@dataclass
class _MarkdownBlock:
    kind: str
    text: str


class MarkdownChunker(BaseChunker):
    """Markdown 感知分块器

    按照 Markdown 标题层级切分文档，每个章节作为独立的 chunk。
    如果某个章节内容超过 chunk_size，则在该章节内部进行递归分割。
    子章节可选继承父级标题作为上下文前缀。
    """

    def __init__(
        self,
        chunk_size: int = 1024,
        chunk_overlap: int = 50,
        include_heading_context: bool = True,
        max_heading_depth: int = 4,
        min_chunk_size: int = 0,
        continuation_prefix: str = "...",
    ) -> None:
        """初始化 Markdown 分块器

        Args:
            chunk_size: 每个 chunk 的最大字符数
            chunk_overlap: 递归分割时的重叠字符数
            include_heading_context: 是否在子章节 chunk 前附加父级标题路径
            max_heading_depth: 最大识别的标题深度 (1-6)
            min_chunk_size: 最小 chunk 大小，低于此值的相邻同级 chunk 会被合并
            continuation_prefix: 续接 chunk 的前缀标记（默认 "..."）

        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.include_heading_context = include_heading_context
        # 限制 max_heading_depth 在 1-6 之间，防止无效值导致正则错误
        self.max_heading_depth = max(1, min(int(max_heading_depth), 6))
        self.min_chunk_size = min_chunk_size
        self.continuation_prefix = continuation_prefix
        self._fallback_chunker = RecursiveCharacterChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    async def chunk(self, text: str, **kwargs) -> list[str]:
        """按 Markdown 标题层级分块

        Args:
            text: Markdown 格式的输入文本
            chunk_size: 覆盖默认的 chunk 大小
            chunk_overlap: 覆盖默认的重叠大小

        Returns:
            list[str]: 分块后的文本列表

        """
        chunks = await self.chunk_with_metadata(text, **kwargs)
        return [chunk.text for chunk in chunks]

    async def chunk_with_metadata(self, text: str, **kwargs) -> list[MarkdownChunk]:
        """Split Markdown text and keep per-chunk structure metadata."""
        text = self._strip_front_matter(text)
        if not text or not text.strip():
            return []

        chunk_size = kwargs.get("chunk_size", self.chunk_size)
        chunk_overlap = kwargs.get("chunk_overlap", self.chunk_overlap)

        sections = self._parse_sections(text)

        if not sections:
            chunks = await self._split_section_preserving_blocks(
                text, chunk_size=chunk_size, chunk_overlap=chunk_overlap
            )
            return [MarkdownChunk(text=chunk) for chunk in chunks]

        raw_chunks = await self._sections_to_chunks(sections, chunk_size, chunk_overlap)
        merged = self._merge_heading_only_chunks(raw_chunks, chunk_size)
        return self._merge_short_chunks(merged, chunk_size)

    def _estimate_prefix_length(self, heading_path: list[str]) -> int:
        """估算标题上下文前缀的最大长度（用于扣除子块可用空间）"""
        if not self.include_heading_context or not heading_path:
            return 0
        title = " > ".join(heading_path)
        # 续接前缀格式: "{continuation_prefix} {title}\n\n"
        continuation = f"{self.continuation_prefix} {title}\n\n"
        return len(continuation)

    async def _sections_to_chunks(
        self, sections: list[_Section], chunk_size: int, chunk_overlap: int
    ) -> list[_ChunkDraft]:
        """将解析后的 sections 转换为 (chunk_text, has_body) 列表"""
        raw_chunks: list[_ChunkDraft] = []

        for section in sections:
            section_text = section.text
            heading_path = section.heading_path
            title_path = self._normalize_title_path(section.title_path)
            section_index = section.section_index
            has_body = section.has_body

            # 构建带上下文的文本
            context_prefix = self._build_context_prefix(heading_path)
            full_text = context_prefix + section_text

            if len(full_text) <= chunk_size:
                raw_chunks.append(
                    _ChunkDraft(
                        text=full_text.strip(),
                        has_body=has_body,
                        title_path=title_path,
                        section_index=section_index,
                    )
                )
            else:
                sub_chunks = await self._split_section_preserving_blocks(
                    section_text,
                    heading_path=heading_path,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )
                for i, sub_chunk in enumerate(sub_chunks):
                    raw_chunks.append(
                        _ChunkDraft(
                            text=sub_chunk,
                            has_body=True,
                            title_path=title_path,
                            section_index=section_index,
                        )
                    )

        return raw_chunks

    def _build_context_prefix(self, heading_path: list[str]) -> str:
        """构建标题路径前缀"""
        if self.include_heading_context and heading_path:
            return " > ".join(heading_path) + "\n\n"
        return ""

    def _apply_heading_context(
        self, heading_path: list[str], content: str, is_continuation: bool
    ) -> str:
        """为 chunk 内容添加标题上下文"""
        if not self.include_heading_context or not heading_path:
            return content.strip()

        title = " > ".join(heading_path)
        if is_continuation:
            return f"{self.continuation_prefix} {title}\n\n{content}".strip()
        return f"{title}\n\n{content}".strip()

    async def _split_section_preserving_blocks(
        self,
        text: str,
        *,
        chunk_size: int,
        chunk_overlap: int,
        heading_path: list[str] | None = None,
    ) -> list[str]:
        heading_path = heading_path or []
        prefix_len = self._estimate_prefix_length(heading_path)
        effective_chunk_size = max(chunk_size // 4, chunk_size - prefix_len)
        blocks = self._parse_markdown_blocks(text)
        if not blocks:
            chunks = await self._fallback_chunker.chunk(
                text,
                chunk_size=effective_chunk_size,
                chunk_overlap=chunk_overlap,
            )
            return [
                self._apply_heading_context(heading_path, chunk, i > 0)
                for i, chunk in enumerate(chunks)
                if chunk.strip()
            ]

        chunks: list[str] = []
        current = ""
        piece_index = 0

        for block in blocks:
            pieces = await self._split_block(block, effective_chunk_size, chunk_overlap)
            for piece in pieces:
                piece = piece.strip()
                if not piece:
                    continue
                if not current:
                    current = piece
                    continue
                combined = current + "\n\n" + piece
                if len(combined) <= effective_chunk_size:
                    current = combined
                    continue

                chunks.append(
                    self._apply_heading_context(
                        heading_path,
                        current,
                        piece_index > 0,
                    )
                )
                piece_index += 1
                current = piece

        if current:
            chunks.append(
                self._apply_heading_context(
                    heading_path,
                    current,
                    piece_index > 0,
                )
            )

        return chunks

    async def _split_block(
        self, block: _MarkdownBlock, chunk_size: int, chunk_overlap: int
    ) -> list[str]:
        text = block.text.strip()
        if not text:
            return []
        if len(text) <= chunk_size:
            return [text]

        if block.kind == "table":
            return self._split_table_block(text, chunk_size)
        if block.kind == "code":
            return self._split_fenced_code_block(text, chunk_size)
        if block.kind == "math":
            return self._split_wrapped_line_block(text, chunk_size)
        if block.kind in {"blockquote", "list", "html"}:
            return self._split_line_block(text, chunk_size)
        if block.kind in {"paragraph", "text"}:
            return self._split_text_preserving_inline_spans(text, chunk_size)

        return await self._fallback_chunker.chunk(
            text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def _parse_markdown_blocks(self, text: str) -> list[_MarkdownBlock]:
        lines = text.splitlines(keepends=True)
        blocks: list[_MarkdownBlock] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if not line.strip():
                i += 1
                continue

            if self._is_fence_start(line):
                block_lines, i = self._collect_fenced_code_block(lines, i)
                blocks.append(_MarkdownBlock("code", "".join(block_lines).strip()))
                continue

            if self._is_math_block_start(line):
                block_lines, i = self._collect_math_block(lines, i)
                blocks.append(_MarkdownBlock("math", "".join(block_lines).strip()))
                continue

            if self._is_markdown_table_start(lines, i):
                block_lines, i = self._collect_markdown_table(lines, i)
                blocks.append(_MarkdownBlock("table", "".join(block_lines).strip()))
                continue

            if self._is_html_block_start(line):
                block_lines, i = self._collect_html_block(lines, i)
                blocks.append(_MarkdownBlock("html", "".join(block_lines).strip()))
                continue

            if line.lstrip().startswith(">"):
                block_lines, i = self._collect_prefixed_block(
                    lines,
                    i,
                    lambda candidate: candidate.lstrip().startswith(">"),
                )
                blocks.append(
                    _MarkdownBlock("blockquote", "".join(block_lines).strip())
                )
                continue

            if self._is_list_item(line):
                block_lines, i = self._collect_list_block(lines, i)
                blocks.append(_MarkdownBlock("list", "".join(block_lines).strip()))
                continue

            if self._is_link_reference(line):
                block_lines, i = self._collect_prefixed_block(
                    lines,
                    i,
                    self._is_link_reference,
                )
                blocks.append(
                    _MarkdownBlock("link_reference", "".join(block_lines).strip())
                )
                continue

            block_lines, i = self._collect_paragraph(lines, i)
            blocks.append(_MarkdownBlock("paragraph", "".join(block_lines).strip()))

        return [block for block in blocks if block.text.strip()]

    @staticmethod
    def _strip_front_matter(text: str) -> str:
        if not text.startswith(("---\n", "+++\n")):
            return text

        marker = text[:3]
        lines = text.splitlines(keepends=True)
        for idx in range(1, min(len(lines), 200)):
            if lines[idx].strip() == marker:
                return "".join(lines[idx + 1 :]).lstrip("\n")
        return text

    @staticmethod
    def _is_fence_start(line: str) -> bool:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        return indent <= 3 and (
            stripped.startswith("```") or stripped.startswith("~~~")
        )

    @staticmethod
    def _fence_marker(line: str) -> tuple[str, int] | None:
        stripped = line.lstrip()
        if stripped.startswith("```"):
            return "`", len(stripped) - len(stripped.lstrip("`"))
        if stripped.startswith("~~~"):
            return "~", len(stripped) - len(stripped.lstrip("~"))
        return None

    def _collect_fenced_code_block(
        self, lines: list[str], start: int
    ) -> tuple[list[str], int]:
        marker = self._fence_marker(lines[start])
        if marker is None:
            return [lines[start]], start + 1
        fence_char, fence_len = marker
        block_lines = [lines[start]]
        i = start + 1
        while i < len(lines):
            block_lines.append(lines[i])
            candidate = lines[i].lstrip()
            indent = len(lines[i]) - len(candidate)
            if (
                indent <= 3
                and candidate.startswith(fence_char * fence_len)
                and set(candidate.strip()) <= {fence_char}
            ):
                i += 1
                break
            i += 1
        return block_lines, i

    @staticmethod
    def _is_table_separator(line: str) -> bool:
        stripped = line.strip()
        if "|" not in stripped:
            return False
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells:
            return False
        return all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells)

    @staticmethod
    def _is_table_row(line: str) -> bool:
        stripped = line.strip()
        return bool(stripped) and "|" in stripped

    def _is_markdown_table_start(self, lines: list[str], index: int) -> bool:
        return (
            index + 1 < len(lines)
            and self._is_table_row(lines[index])
            and self._is_table_separator(lines[index + 1])
        )

    def _collect_markdown_table(
        self, lines: list[str], start: int
    ) -> tuple[list[str], int]:
        block_lines = [lines[start], lines[start + 1]]
        i = start + 2
        while i < len(lines) and self._is_table_row(lines[i]):
            block_lines.append(lines[i])
            i += 1
        return block_lines, i

    @staticmethod
    def _is_html_block_start(line: str) -> bool:
        stripped = line.lstrip().lower()
        return stripped.startswith(
            (
                "<table",
                "<pre",
                "<code",
                "<blockquote",
                "<details",
                "<div",
            )
        )

    @staticmethod
    def _html_closing_tag(line: str) -> str | None:
        stripped = line.lstrip().lower()
        for tag in ("table", "pre", "code", "blockquote", "details", "div"):
            if stripped.startswith(f"<{tag}"):
                return f"</{tag}>"
        return None

    def _collect_html_block(
        self, lines: list[str], start: int
    ) -> tuple[list[str], int]:
        closing_tag = self._html_closing_tag(lines[start])
        block_lines = [lines[start]]
        i = start + 1
        if closing_tag is None or closing_tag in lines[start].lower():
            return block_lines, i

        while i < len(lines):
            block_lines.append(lines[i])
            if closing_tag in lines[i].lower():
                i += 1
                break
            i += 1
        return block_lines, i

    @staticmethod
    def _is_list_item(line: str) -> bool:
        return bool(re.match(r"^\s{0,3}(?:[-*+]|\d+[.)])\s+", line))

    @staticmethod
    def _is_link_reference(line: str) -> bool:
        return bool(re.match(r"^\s{0,3}\[[^\]]+\]:\s+\S+", line))

    def _collect_prefixed_block(
        self,
        lines: list[str],
        start: int,
        predicate,
    ) -> tuple[list[str], int]:
        block_lines = []
        i = start
        while i < len(lines) and (predicate(lines[i]) or not lines[i].strip()):
            if (
                not lines[i].strip()
                and i + 1 < len(lines)
                and not predicate(lines[i + 1])
            ):
                break
            block_lines.append(lines[i])
            i += 1
        return block_lines, i

    def _collect_list_block(
        self, lines: list[str], start: int
    ) -> tuple[list[str], int]:
        block_lines = [lines[start]]
        i = start + 1
        while i < len(lines):
            line = lines[i]
            if self._is_fence_start(line) or self._is_markdown_table_start(lines, i):
                break
            if self._is_list_item(line) or line.startswith((" ", "\t")):
                block_lines.append(line)
                i += 1
                continue
            if not line.strip() and i + 1 < len(lines):
                next_line = lines[i + 1]
                if self._is_list_item(next_line) or next_line.startswith((" ", "\t")):
                    block_lines.append(line)
                    i += 1
                    continue
            break
        return block_lines, i

    def _collect_paragraph(self, lines: list[str], start: int) -> tuple[list[str], int]:
        block_lines = []
        i = start
        while i < len(lines):
            line = lines[i]
            if not line.strip():
                break
            if i != start and (
                self._is_fence_start(line)
                or self._is_math_block_start(line)
                or self._is_markdown_table_start(lines, i)
                or self._is_html_block_start(line)
                or self._is_list_item(line)
                or line.lstrip().startswith(">")
                or self._is_link_reference(line)
            ):
                break
            block_lines.append(line)
            i += 1
        return block_lines, i

    def _split_table_block(self, text: str, chunk_size: int) -> list[str]:
        lines = text.splitlines()
        if len(lines) <= 2:
            return [text]

        header = lines[:2]
        rows = lines[2:]
        chunks = []
        current_rows: list[str] = []

        for row in rows:
            candidate_lines = header + current_rows + [row]
            candidate = "\n".join(candidate_lines)
            if current_rows and len(candidate) > chunk_size:
                chunks.append("\n".join(header + current_rows))
                current_rows = [row]
            else:
                current_rows.append(row)

        if current_rows:
            chunks.append("\n".join(header + current_rows))

        return chunks or [text]

    @staticmethod
    def _is_math_block_start(line: str) -> bool:
        stripped = line.strip()
        return (
            stripped.startswith("$$")
            or stripped.startswith(r"\[")
            or bool(
                re.match(
                    r"^\\begin\{(?:equation|align|gather|multline|cases)\*?\}", stripped
                )
            )
        )

    @staticmethod
    def _math_block_closer(line: str) -> str:
        stripped = line.strip()
        if stripped.startswith("$$"):
            return "$$"
        if stripped.startswith(r"\["):
            return r"\]"

        env_match = re.match(r"^\\begin\{([^}]+)\}", stripped)
        if env_match:
            return rf"\end{{{env_match.group(1)}}}"
        return ""

    def _collect_math_block(
        self, lines: list[str], start: int
    ) -> tuple[list[str], int]:
        opener_line = lines[start]
        closer = self._math_block_closer(opener_line)
        block_lines = [opener_line]
        if not closer:
            return block_lines, start + 1

        opener_stripped = opener_line.strip()
        if (
            closer in opener_stripped[len(closer) :]
            if closer in {"$$", r"\]"}
            else closer in opener_stripped
        ):
            return block_lines, start + 1

        i = start + 1
        while i < len(lines):
            block_lines.append(lines[i])
            if closer in lines[i].strip():
                i += 1
                break
            i += 1
        return block_lines, i

    @staticmethod
    def _split_wrapped_line_block(text: str, chunk_size: int) -> list[str]:
        lines = text.splitlines()
        if len(lines) <= 2:
            return [text]

        opener = lines[0]
        closer = lines[-1]
        body = lines[1:-1]
        chunks = []
        current: list[str] = []

        for line in body:
            candidate = "\n".join([opener, *current, line, closer])
            if current and len(candidate) > chunk_size:
                chunks.append("\n".join([opener, *current, closer]))
                current = [line]
            else:
                current.append(line)

        if current:
            chunks.append("\n".join([opener, *current, closer]))

        return chunks or [text]

    @staticmethod
    def _split_fenced_code_block(text: str, chunk_size: int) -> list[str]:
        lines = text.splitlines()
        if len(lines) <= 2:
            return [text]

        opener = lines[0]
        closer = lines[-1] if lines[-1].lstrip().startswith(("```", "~~~")) else ""
        body = lines[1:-1] if closer else lines[1:]
        chunks = []
        current: list[str] = []

        for line in body:
            candidate_lines = [opener, *current, line]
            if closer:
                candidate_lines.append(closer)
            candidate = "\n".join(candidate_lines)
            if current and len(candidate) > chunk_size:
                chunk_lines = [opener, *current]
                if closer:
                    chunk_lines.append(closer)
                chunks.append("\n".join(chunk_lines))
                current = [line]
            else:
                current.append(line)

        if current:
            chunk_lines = [opener, *current]
            if closer:
                chunk_lines.append(closer)
            chunks.append("\n".join(chunk_lines))

        return chunks or [text]

    @staticmethod
    def _split_line_block(text: str, chunk_size: int) -> list[str]:
        lines = text.splitlines()
        chunks = []
        current: list[str] = []
        for line in lines:
            candidate = "\n".join([*current, line])
            if current and len(candidate) > chunk_size:
                chunks.append("\n".join(current))
                current = [line]
            else:
                current.append(line)
        if current:
            chunks.append("\n".join(current))
        return chunks or [text]

    def _split_text_preserving_inline_spans(
        self, text: str, chunk_size: int
    ) -> list[str]:
        tokens = self._tokenize_protected_inline_spans(text)
        chunks = []
        current = ""
        for token in tokens:
            if not token:
                continue
            candidate = current + token if current else token.lstrip()
            if current and len(candidate) > chunk_size:
                chunks.append(current.strip())
                current = token.lstrip()
            else:
                current = candidate

            if len(current) > chunk_size and not self._is_inline_protected_token(
                current
            ):
                split_chunks = self._split_long_plain_token(current, chunk_size)
                chunks.extend(split_chunks[:-1])
                current = split_chunks[-1] if split_chunks else ""

        if current.strip():
            chunks.append(current.strip())
        return [chunk for chunk in chunks if chunk]

    def _tokenize_protected_inline_spans(self, text: str) -> list[str]:
        spans = self._find_protected_inline_spans(text)
        tokens: list[str] = []
        cursor = 0
        for start, end in spans:
            if start > cursor:
                tokens.extend(re.findall(r"\S+\s*|\s+", text[cursor:start]))
            tokens.append(text[start:end])
            cursor = end
        if cursor < len(text):
            tokens.extend(re.findall(r"\S+\s*|\s+", text[cursor:]))
        return tokens

    def _find_protected_inline_spans(self, text: str) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
        i = 0
        while i < len(text):
            end = self._match_markdown_link(text, i)
            if end is None:
                end = self._match_autolink(text, i)
            if end is None:
                end = self._match_inline_math(text, i)
            if end is not None:
                if not spans or i >= spans[-1][1]:
                    spans.append((i, end))
                i = end
                continue
            i += 1
        return spans

    @staticmethod
    def _match_markdown_link(text: str, start: int) -> int | None:
        marker_start = start
        if text.startswith("![", start):
            start += 1
        elif text[start] != "[":
            return None

        label_end = text.find("]", start + 1)
        if label_end == -1 or label_end + 1 >= len(text):
            return None

        next_char = text[label_end + 1]
        if next_char == "(":
            link_end = text.find(")", label_end + 2)
            return link_end + 1 if link_end != -1 else None
        if next_char == "[":
            ref_end = text.find("]", label_end + 2)
            return ref_end + 1 if ref_end != -1 else None

        return None if marker_start == start else None

    @staticmethod
    def _match_autolink(text: str, start: int) -> int | None:
        if text.startswith(("<http://", "<https://"), start):
            end = text.find(">", start + 1)
            return end + 1 if end != -1 else None

        if not (
            text.startswith("http://", start) or text.startswith("https://", start)
        ):
            return None

        end = start
        while end < len(text) and not text[end].isspace():
            end += 1
        while end > start and text[end - 1] in ".,;:!?)>]":
            end -= 1
        return end

    @staticmethod
    def _match_inline_math(text: str, start: int) -> int | None:
        if text.startswith(r"\(", start):
            end = text.find(r"\)", start + 2)
            return end + 2 if end != -1 else None

        if text[start] != "$":
            return None
        if text.startswith("$$", start):
            return None
        if start > 0 and text[start - 1] == "\\":
            return None
        if start + 1 >= len(text) or text[start + 1].isspace():
            return None

        i = start + 1
        while i < len(text):
            if text[i] == "$" and text[i - 1] != "\\":
                if i > start + 1 and not text[i - 1].isspace():
                    return i + 1
                return None
            i += 1
        return None

    @staticmethod
    def _is_inline_protected_token(token: str) -> bool:
        stripped = token.strip()
        return (
            stripped.startswith("[")
            or stripped.startswith("![")
            or stripped.startswith("<http")
            or stripped.startswith("http")
            or stripped.startswith("$")
            or stripped.startswith(r"\(")
        )

    @staticmethod
    def _split_long_plain_token(text: str, chunk_size: int) -> list[str]:
        if chunk_size <= 0:
            return [text]
        return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

    def _merge_heading_only_chunks(
        self, raw_chunks: list[_ChunkDraft], chunk_size: int
    ) -> list[MarkdownChunk]:
        """合并没有实质正文的 chunk 到下一个有正文的 chunk"""
        merged: list[MarkdownChunk] = []
        pending_text = ""
        pending_title_path: list[str] | None = None
        pending_section_index: int | None = None

        for chunk in raw_chunks:
            chunk_text = chunk.text
            if not chunk_text:
                continue
            if not chunk.has_body:
                # 纯标题节，暂存；但如果 pending 已经够长，先 flush
                if (
                    pending_text
                    and len(pending_text) + len(chunk_text) + 2 > chunk_size
                ):
                    merged.append(
                        MarkdownChunk(
                            text=pending_text.strip(),
                            title_path=pending_title_path,
                            section_index=pending_section_index,
                        )
                    )
                    pending_text = ""
                    pending_title_path = None
                    pending_section_index = None
                pending_text += chunk_text + "\n\n"
                pending_title_path = chunk.title_path or pending_title_path
                pending_section_index = chunk.section_index
            else:
                if pending_text:
                    combined = pending_text + chunk_text
                    if len(combined) <= chunk_size:
                        merged.append(
                            MarkdownChunk(
                                text=combined.strip(),
                                title_path=chunk.title_path or pending_title_path,
                                section_index=chunk.section_index,
                            )
                        )
                    else:
                        merged.append(
                            MarkdownChunk(
                                text=pending_text.strip(),
                                title_path=pending_title_path,
                                section_index=pending_section_index,
                            )
                        )
                        merged.append(
                            MarkdownChunk(
                                text=chunk_text.strip(),
                                title_path=chunk.title_path,
                                section_index=chunk.section_index,
                            )
                        )
                    pending_text = ""
                    pending_title_path = None
                    pending_section_index = None
                else:
                    merged.append(
                        MarkdownChunk(
                            text=chunk_text.strip(),
                            title_path=chunk.title_path,
                            section_index=chunk.section_index,
                        )
                    )

        # 处理尾部残留的 pending
        if pending_text:
            trailing_text = pending_text.strip()
            if merged and len(merged[-1].text + "\n\n" + trailing_text) <= chunk_size:
                merged[-1] = MarkdownChunk(
                    text=merged[-1].text + "\n\n" + trailing_text,
                    title_path=self._merge_title_paths(
                        [merged[-1].title_path, pending_title_path]
                    ),
                    section_index=self._merge_section_indexes(
                        [merged[-1].section_index, pending_section_index]
                    ),
                )
            else:
                merged.append(
                    MarkdownChunk(
                        text=trailing_text,
                        title_path=pending_title_path,
                        section_index=pending_section_index,
                    )
                )

        return [chunk for chunk in merged if chunk.text.strip()]

    def _merge_short_chunks(
        self, chunks: list[MarkdownChunk], chunk_size: int
    ) -> list[MarkdownChunk]:
        """合并过短的相邻 chunk（低于 min_chunk_size）"""
        if self.min_chunk_size <= 0 or len(chunks) <= 1:
            return chunks

        final: list[MarkdownChunk] = []
        buf: MarkdownChunk | None = None

        for chunk in chunks:
            if buf:
                combined = buf.text + "\n\n" + chunk.text
                if len(combined) <= chunk_size:
                    buf = MarkdownChunk(
                        text=combined,
                        title_path=self._merge_title_paths(
                            [buf.title_path, chunk.title_path]
                        ),
                        section_index=self._merge_section_indexes(
                            [buf.section_index, chunk.section_index]
                        ),
                    )
                else:
                    final.append(buf)
                    if len(chunk.text) < self.min_chunk_size:
                        buf = chunk
                    else:
                        buf = None
                        final.append(chunk)
            elif len(chunk.text) < self.min_chunk_size:
                buf = chunk
            else:
                final.append(chunk)

        if buf:
            if final and len(final[-1].text + "\n\n" + buf.text) <= chunk_size:
                final[-1] = MarkdownChunk(
                    text=final[-1].text + "\n\n" + buf.text,
                    title_path=self._merge_title_paths(
                        [final[-1].title_path, buf.title_path]
                    ),
                    section_index=self._merge_section_indexes(
                        [final[-1].section_index, buf.section_index]
                    ),
                )
            else:
                final.append(buf)

        return final

    @staticmethod
    def _normalize_title_path(title_path: list[str]) -> list[str] | None:
        path = [title.strip() for title in title_path if title and title.strip()]
        return path or None

    @staticmethod
    def _merge_title_paths(paths: list[list[str] | None]) -> list[str] | None:
        non_empty_paths = [path for path in paths if path]
        if not non_empty_paths:
            return None

        common = list(non_empty_paths[0])
        for path in non_empty_paths[1:]:
            prefix: list[str] = []
            for left, right in zip(common, path, strict=False):
                if left != right:
                    break
                prefix.append(left)
            common = prefix
            if not common:
                return None
        return common

    @staticmethod
    def _merge_section_indexes(indexes: list[int | None]) -> int | None:
        non_empty_indexes = [index for index in indexes if index is not None]
        if not non_empty_indexes:
            return None
        first_index = non_empty_indexes[0]
        if all(index == first_index for index in non_empty_indexes):
            return first_index
        return None

    def _parse_sections(self, text: str) -> list[_Section]:
        """解析 Markdown 文本为章节列表

        会跳过围栏代码块（``` 或 ~~~）内的内容，避免误匹配代码中的 # 字符。

        Returns:
            list[_Section]: 章节列表

        """
        # 先标记围栏代码块的范围，解析时跳过
        fenced_ranges = self._find_fenced_code_ranges(text)

        # 匹配 Markdown 标题行（支持 # 后有或无空格）
        heading_pattern = re.compile(
            r"^(#{1," + str(self.max_heading_depth) + r"})\s*(.+)$", re.MULTILINE
        )

        # 找到所有标题及其位置（排除代码块内的）
        headings = []
        for match in heading_pattern.finditer(text):
            if self._is_in_fenced_block(match.start(), fenced_ranges):
                continue
            level = len(match.group(1))
            title = match.group(2).strip()
            start = match.start()
            end = match.end()
            headings.append(
                {"level": level, "title": title, "start": start, "end": end}
            )

        if not headings:
            return []

        sections: list[_Section] = []
        section_index = 0

        # 处理第一个标题之前的内容（如果有）
        preamble = text[: headings[0]["start"]].strip()
        if preamble:
            sections.append(
                _Section(
                    heading_path=[],
                    title_path=[],
                    section_index=section_index,
                    text=preamble,
                    has_body=True,
                )
            )
            section_index += 1

        # 维护标题栈来追踪层级路径
        heading_stack: list[dict] = []

        for i, heading in enumerate(headings):
            # 更新标题栈
            while heading_stack and heading_stack[-1]["level"] >= heading["level"]:
                heading_stack.pop()
            heading_stack.append({"level": heading["level"], "title": heading["title"]})

            # 获取当前章节的内容范围
            content_start = heading["end"]
            if i + 1 < len(headings):
                content_end = headings[i + 1]["start"]
            else:
                content_end = len(text)

            # 提取内容（标题行 + 正文）
            heading_line = text[heading["start"] : heading["end"]]
            body = text[content_start:content_end].strip()

            # 组合章节文本
            section_text = heading_line
            if body:
                section_text += "\n" + body

            # 构建标题路径
            heading_path = [h["title"] for h in heading_stack[:-1]]
            title_path = [h["title"] for h in heading_stack]

            sections.append(
                _Section(
                    heading_path=heading_path,
                    title_path=title_path,
                    section_index=section_index,
                    text=section_text,
                    has_body=bool(body),
                )
            )
            section_index += 1

        return sections

    @staticmethod
    def _find_fenced_code_ranges(text: str) -> list[tuple[int, int]]:
        """找到所有围栏代码块的 (start, end) 范围"""
        ranges: list[tuple[int, int]] = []
        fence_pattern = re.compile(r"^(`{3,}|~{3,})", re.MULTILINE)
        matches = list(fence_pattern.finditer(text))

        i = 0
        while i < len(matches):
            open_match = matches[i]
            open_fence = open_match.group(1)
            fence_char = open_fence[0]
            fence_len = len(open_fence)

            # 找到对应的关闭围栏
            for j in range(i + 1, len(matches)):
                close_match = matches[j]
                close_fence = close_match.group(1)
                if close_fence[0] == fence_char and len(close_fence) >= fence_len:
                    ranges.append((open_match.start(), close_match.end()))
                    i = j + 1
                    break
            else:
                # 没有找到关闭围栏，剩余部分都视为代码块
                ranges.append((open_match.start(), len(text)))
                break
            continue

        return ranges

    @staticmethod
    def _is_in_fenced_block(pos: int, ranges: list[tuple[int, int]]) -> bool:
        """判断给定位置是否在围栏代码块内"""
        for start, end in ranges:
            if start <= pos < end:
                return True
        return False
