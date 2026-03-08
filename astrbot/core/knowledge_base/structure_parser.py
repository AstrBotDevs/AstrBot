from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class SectionNode:
    title: str
    level: int
    path: str
    body: str
    children: list[SectionNode] = field(default_factory=list)


class StructureParser:
    HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

    async def parse_structure(self, text: str, file_type: str) -> list[SectionNode]:
        ft = file_type.lower().strip(".")
        if ft in {"md", "markdown", "txt"}:
            return self._parse_markdown(text)
        return []

    def flatten(self, nodes: list[SectionNode]) -> list[SectionNode]:
        result: list[SectionNode] = []
        for node in nodes:
            result.append(node)
            result.extend(self.flatten(node.children))
        return result

    def _parse_markdown(self, text: str) -> list[SectionNode]:
        heading_matches = list(self.HEADING_RE.finditer(text))
        if not heading_matches:
            return []

        headings: list[tuple[int, str, int, int]] = []
        for idx, match in enumerate(heading_matches):
            level = len(match.group(1))
            title = match.group(2).strip()
            content_start = match.end()
            content_end = (
                heading_matches[idx + 1].start()
                if idx + 1 < len(heading_matches)
                else len(text)
            )
            headings.append((level, title, content_start, content_end))

        roots: list[SectionNode] = []
        stack: list[SectionNode] = []
        for level, title, start, end in headings:
            body = text[start:end].strip()
            while stack and stack[-1].level >= level:
                stack.pop()

            parent_path = stack[-1].path if stack else ""
            path = f"{parent_path} > {title}" if parent_path else title
            node = SectionNode(
                title=title,
                level=level,
                path=path,
                body=body,
            )
            if stack:
                stack[-1].children.append(node)
            else:
                roots.append(node)
            stack.append(node)

        return roots
