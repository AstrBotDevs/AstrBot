"""Markdown 感知分块器

根据 Markdown 标题层级结构进行分块，保持每个章节的语义完整性。
对于超过 chunk_size 的章节，内部使用递归字符分割。
"""

import re

from .base import BaseChunker
from .recursive import RecursiveCharacterChunker


class MarkdownChunker(BaseChunker):
    """Markdown 感知分块器

    按照 Markdown 标题层级切分文档，每个章节作为独立的 chunk。
    如果某个章节内容超过 chunk_size，则在该章节内部进行递归分割。
    子章节会继承父级标题作为上下文前缀。
    """

    def __init__(
        self,
        chunk_size: int = 1024,
        chunk_overlap: int = 50,
        include_heading_context: bool = True,
        max_heading_depth: int = 4,
        min_chunk_size: int = 0,
    ) -> None:
        """初始化 Markdown 分块器

        Args:
            chunk_size: 每个 chunk 的最大字符数
            chunk_overlap: 递归分割时的重叠字符数
            include_heading_context: 是否在子章节 chunk 前附加父级标题路径
            max_heading_depth: 最大识别的标题深度 (1-6)
            min_chunk_size: 最小 chunk 大小，低于此值的相邻同级 chunk 会被合并

        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.include_heading_context = include_heading_context
        self.max_heading_depth = min(max_heading_depth, 6)
        self.min_chunk_size = min_chunk_size
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
        if not text or not text.strip():
            return []

        chunk_size = kwargs.get("chunk_size", self.chunk_size)
        chunk_overlap = kwargs.get("chunk_overlap", self.chunk_overlap)

        # 解析 Markdown 结构
        sections = self._parse_sections(text)

        if not sections:
            # 没有识别到标题结构，回退到递归分割
            return await self._fallback_chunker.chunk(
                text, chunk_size=chunk_size, chunk_overlap=chunk_overlap
            )

        # 将 sections 转换为 chunks，同时记录哪些 section 有实质正文
        raw_chunks = []  # list of (chunk_text, has_body)
        for section in sections:
            section_text = section["text"]
            heading_path = section["heading_path"]
            has_body = section["has_body"]

            # 构建带上下文的文本
            if self.include_heading_context and heading_path:
                context_prefix = " > ".join(heading_path) + "\n\n"
            else:
                context_prefix = ""

            full_text = context_prefix + section_text

            if len(full_text) <= chunk_size:
                raw_chunks.append((full_text.strip(), has_body))
            else:
                # 章节过长，内部递归分割，但保留标题上下文
                sub_chunks = await self._fallback_chunker.chunk(
                    section_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap
                )
                for i, sub_chunk in enumerate(sub_chunks):
                    if self.include_heading_context and heading_path:
                        if i == 0:
                            chunk_text = context_prefix + sub_chunk
                        else:
                            chunk_text = (
                                f"[续] {' > '.join(heading_path)}\n\n" + sub_chunk
                            )
                    else:
                        chunk_text = sub_chunk
                    raw_chunks.append((chunk_text.strip(), True))

        # 合并没有实质正文的 chunk 到下一个有正文的 chunk
        merged = []
        pending = ""
        for chunk_text, has_body in raw_chunks:
            if not chunk_text:
                continue
            if not has_body:
                # 纯标题节，暂存，等待合并到下一个有内容的 chunk
                pending += chunk_text + "\n\n"
            else:
                if pending:
                    combined = pending + chunk_text
                    # 如果合并后不超过 chunk_size，合并
                    if len(combined) <= chunk_size:
                        merged.append(combined.strip())
                    else:
                        # 超长了，分开保留
                        merged.append(pending.strip())
                        merged.append(chunk_text.strip())
                    pending = ""
                else:
                    merged.append(chunk_text.strip())
        # 处理尾部残留的 pending
        if pending:
            if merged:
                combined = merged[-1] + "\n\n" + pending.strip()
                if len(combined) <= chunk_size:
                    merged[-1] = combined
                else:
                    merged.append(pending.strip())
            else:
                merged.append(pending.strip())

        merged = [c for c in merged if c.strip()]

        # 合并过短的相邻 chunk（低于 min_chunk_size）
        if self.min_chunk_size > 0 and len(merged) > 1:
            final = []
            buf = ""
            for c in merged:
                if buf:
                    combined = buf + "\n\n" + c
                    if len(combined) <= chunk_size:
                        buf = combined
                    else:
                        final.append(buf)
                        buf = c if len(c) < self.min_chunk_size else ""
                        if len(c) >= self.min_chunk_size:
                            final.append(c)
                elif len(c) < self.min_chunk_size:
                    buf = c
                else:
                    final.append(c)
            if buf:
                if final and len(final[-1] + "\n\n" + buf) <= chunk_size:
                    final[-1] = final[-1] + "\n\n" + buf
                else:
                    final.append(buf)
            merged = final

        return merged

    def _parse_sections(self, text: str) -> list[dict]:
        """解析 Markdown 文本为章节列表

        每个章节包含:
        - heading_path: 从顶层到当前标题的路径列表
        - text: 该章节的正文内容
        - has_body: 是否有标题行之外的实质正文

        Returns:
            list[dict]: 章节列表

        """
        # 匹配 Markdown 标题行
        heading_pattern = re.compile(
            r"^(#{1," + str(self.max_heading_depth) + r"})\s*(.+)$", re.MULTILINE
        )

        # 找到所有标题及其位置
        headings = []
        for match in heading_pattern.finditer(text):
            level = len(match.group(1))
            title = match.group(2).strip()
            start = match.start()
            end = match.end()
            headings.append(
                {"level": level, "title": title, "start": start, "end": end}
            )

        if not headings:
            return []

        sections = []

        # 处理第一个标题之前的内容（如果有）
        preamble = text[: headings[0]["start"]].strip()
        if preamble:
            sections.append({"heading_path": [], "text": preamble, "has_body": True})

        # 维护标题栈来追踪层级路径
        heading_stack: list[dict] = []

        for i, heading in enumerate(headings):
            # 更新标题栈
            while heading_stack and heading_stack[-1]["level"] >= heading["level"]:
                heading_stack.pop()
            heading_stack.append(
                {"level": heading["level"], "title": heading["title"]}
            )

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

            sections.append({
                "heading_path": heading_path,
                "text": section_text,
                "has_body": bool(body),
            })

        return sections
