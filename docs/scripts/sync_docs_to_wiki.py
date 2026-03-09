from __future__ import annotations

import argparse
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
FENCED_BLOCK_RE = re.compile(
    r"(^```.*?$.*?^```$|^~~~.*?$.*?^~~~$)",
    re.MULTILINE | re.DOTALL,
)
INLINE_CODE_RE = re.compile(r"(`[^`]*`)")
MANIFEST_NAME = ".astrbot-wiki-sync-manifest"
SOURCE_ALIASES = {
    "zh/config/providers/start.md": "zh/providers/start.md",
    "en/config/providers/start.md": "en/providers/start.md",
}
LANG_CONFIG = {
    "zh": {
        "index_title": "# AstrBot 中文文档",
        "index_intro": "该页面由 `AstrBot-docs` 自动同步到 GitHub Wiki。",
        "index_links": [
            ("关于 AstrBot", "zh-what-is-astrbot"),
            ("社区", "zh-community"),
            ("常见问题", "zh-faq"),
        ],
        "home_intro": "该 Wiki 由 `AstrBot-docs` 自动同步生成。",
        "home_links": [
            ("中文文档入口", "zh-index"),
            ("English Docs", "Home-en"),
        ],
        "sidebar_language_label": "Chinese",
        "sidebar_home_label": "首页",
        "sidebar_home_target": "Home",
        "sidebar_docs_entry_label": "文档入口",
    },
    "en": {
        "index_title": "# AstrBot English Documentation",
        "index_intro": "This page is synchronized automatically from `AstrBot-docs` to the GitHub wiki.",
        "index_links": [
            ("What is AstrBot", "en-what-is-astrbot"),
            ("Community", "en-community"),
            ("FAQ", "en-faq"),
        ],
        "home_intro": "This wiki is synchronized automatically from `AstrBot-docs`.",
        "home_links": [
            ("English docs entry", "en-index"),
            ("中文文档入口", "Home"),
        ],
        "sidebar_language_label": "English",
        "sidebar_home_label": "Home",
        "sidebar_home_target": "Home-en",
        "sidebar_docs_entry_label": "Docs Entry",
    },
}


@dataclass
class PageInfo:
    source_path: str
    page_name: str
    title: str
    content: str
    language: str
    group: str
    is_index: bool


@dataclass
class ResolutionResult:
    resolved_path: str | None
    ambiguous_matches: tuple[str, ...] = ()


@dataclass
class MarkdownLink:
    start: int
    end: int
    prefix: str
    target: str
    suffix: str


@dataclass
class Segment:
    kind: str
    text: str


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def discover_source_pages(source_root: str) -> tuple[str, ...]:
    root = Path(source_root)
    pages = []
    for language in ("zh", "en"):
        language_root = root / language
        if not language_root.exists():
            continue
        for path in language_root.rglob("*.md"):
            pages.append(path.relative_to(root).as_posix())
    return tuple(sorted(pages))


def find_label_end(content: str, label_start: int) -> int:
    index = label_start + 1
    while index < len(content):
        close = content.find("]", index)
        if close == -1:
            return -1
        if close > label_start and content[close - 1] == "\\":
            index = close + 1
            continue
        lookahead = close + 1
        while lookahead < len(content) and content[lookahead].isspace():
            lookahead += 1
        if lookahead < len(content) and content[lookahead] == "(":
            return close
        index = close + 1
    return -1


def find_target_end(content: str, target_start: int) -> int:
    depth = 0
    index = target_start
    while index < len(content):
        character = content[index]
        if character == "\\":
            index += 2
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            if depth == 0:
                return index
            depth -= 1
        index += 1
    return -1


def iter_markdown_links(content: str):
    """Yield inline Markdown links only.

    This scanner intentionally handles inline `[]()` links used in the docs tree.
    It does not parse reference-style links or arbitrary HTML.
    """

    index = 0
    while index < len(content):
        label_start = content.find("[", index)
        if label_start == -1:
            break

        link_start = (
            label_start - 1
            if label_start > 0 and content[label_start - 1] == "!"
            else label_start
        )
        label_end = find_label_end(content, label_start)
        if label_end == -1:
            index = label_start + 1
            continue

        target_start = label_end + 1
        while target_start < len(content) and content[target_start].isspace():
            target_start += 1
        if target_start >= len(content) or content[target_start] != "(":
            index = label_end + 1
            continue
        target_start += 1
        target_end = find_target_end(content, target_start)
        if target_end == -1:
            index = label_end + 1
            continue

        yield MarkdownLink(
            start=link_start,
            end=target_end + 1,
            prefix=content[link_start:target_start],
            target=content[target_start:target_end],
            suffix=")",
        )
        index = target_end + 1


def split_anchor(target: str) -> tuple[str, str]:
    if "#" not in target:
        return target, ""
    base, anchor = target.split("#", 1)
    return base, f"#{anchor}"


def prepare_candidate_path(path: PurePosixPath) -> PurePosixPath:
    if not path.suffix:
        path = path.with_suffix(".md")

    normalized = PurePosixPath(posixpath.normpath(path.as_posix()))
    normalized_text = normalized.as_posix()
    aliased = SOURCE_ALIASES.get(normalized_text, normalized_text)
    return PurePosixPath(aliased)


def language_for_source(source_path: str) -> str:
    return PurePosixPath(source_path).parts[0]


def parse_doc_target(target: str) -> tuple[str, str] | None:
    if target.startswith(("http://", "https://", "mailto:", "#")):
        return None

    base_target, anchor = split_anchor(target)
    if not base_target:
        return None

    suffix = PurePosixPath(base_target).suffix.lower()
    if suffix and suffix != ".md":
        return None

    return base_target, anchor


def find_existing_source_path(
    candidate: PurePosixPath,
    source_root: Path,
    source_pages: tuple[str, ...],
) -> ResolutionResult:
    candidate_text = candidate.as_posix()
    if (source_root / candidate_text).exists():
        return ResolutionResult(resolved_path=candidate_text)

    language = candidate.parts[0] if candidate.parts else ""
    suffix = (
        PurePosixPath(*candidate.parts[1:]).as_posix()
        if len(candidate.parts) > 1
        else ""
    )
    if not suffix:
        return ResolutionResult(resolved_path=None)

    prefix = f"{language}/"
    full_suffix = f"{language}/{suffix}"
    matches = [
        page
        for page in source_pages
        if page.startswith(prefix)
        and (page == full_suffix or page.endswith(f"/{suffix}"))
    ]
    if len(matches) == 1:
        return ResolutionResult(resolved_path=matches[0])
    if len(matches) > 1:
        return ResolutionResult(
            resolved_path=None,
            ambiguous_matches=tuple(sorted(matches)),
        )
    return ResolutionResult(resolved_path=None)


def resolve_link_path(
    base_target: str,
    source_path: str,
    source_root: Path,
    source_pages: tuple[str, ...],
) -> ResolutionResult:
    source_language = language_for_source(source_path)

    if base_target.startswith("/"):
        target = base_target.lstrip("/")
        if not target:
            candidate = PurePosixPath(source_language) / "index.md"
        elif target in {"en", "en/"}:
            candidate = PurePosixPath("en") / "index.md"
        elif target in {"zh", "zh/"}:
            candidate = PurePosixPath("zh") / "index.md"
        elif target.startswith(("en/", "zh/")):
            candidate = PurePosixPath(target)
        else:
            language_root = source_language if source_language == "en" else "zh"
            candidate = PurePosixPath(language_root) / target
    else:
        candidate = PurePosixPath(source_path).parent / base_target

    candidate = prepare_candidate_path(candidate)
    return find_existing_source_path(candidate, source_root, source_pages)


class LinkResolver:
    def __init__(self, source_root: Path):
        self.source_root = Path(source_root)
        self.source_pages = discover_source_pages(str(self.source_root))

    def resolve_base_target(
        self, base_target: str, source_path: str
    ) -> ResolutionResult:
        return resolve_link_path(
            base_target=base_target,
            source_path=source_path,
            source_root=self.source_root,
            source_pages=self.source_pages,
        )

    def resolve_markdown_target(
        self, target: str, source_path: str
    ) -> tuple[str | None, str]:
        parsed_target = parse_doc_target(target)
        if parsed_target is None:
            return None, ""

        base_target, anchor = parsed_target
        result = self.resolve_base_target(base_target, source_path)
        return result.resolved_path, anchor


def rewrite_link_target(target: str, source_path: str, resolver: LinkResolver) -> str:
    resolved, anchor = resolver.resolve_markdown_target(target, source_path)
    if resolved is None:
        return target

    return f"{page_name_for_source(resolved)}{anchor}"


def rewrite_links_in_segment(
    segment: str,
    source_path: str,
    resolver: LinkResolver,
) -> str:
    links = list(iter_markdown_links(segment))
    if not links:
        return segment

    result: list[str] = []
    previous_end = 0
    for link in links:
        result.append(segment[previous_end : link.start])
        result.append(
            f"{link.prefix}{rewrite_link_target(link.target, source_path, resolver)}{link.suffix}",
        )
        previous_end = link.end
    result.append(segment[previous_end:])
    return "".join(result)


def iter_segments(content: str):
    last_end = 0
    for fenced in FENCED_BLOCK_RE.finditer(content):
        before = content[last_end : fenced.start()]
        if before:
            last_inline_end = 0
            for inline in INLINE_CODE_RE.finditer(before):
                if inline.start() > last_inline_end:
                    yield Segment("text", before[last_inline_end : inline.start()])
                yield Segment("inline_code", inline.group(0))
                last_inline_end = inline.end()
            if last_inline_end < len(before):
                yield Segment("text", before[last_inline_end:])

        yield Segment("code_block", fenced.group(0))
        last_end = fenced.end()

    tail = content[last_end:]
    if not tail:
        return

    last_inline_end = 0
    for inline in INLINE_CODE_RE.finditer(tail):
        if inline.start() > last_inline_end:
            yield Segment("text", tail[last_inline_end : inline.start()])
        yield Segment("inline_code", inline.group(0))
        last_inline_end = inline.end()
    if last_inline_end < len(tail):
        yield Segment("text", tail[last_inline_end:])


def rewrite_links(
    content: str,
    source_path: str,
    resolver: LinkResolver,
) -> str:
    output: list[str] = []
    for segment in iter_segments(content):
        if segment.kind == "text":
            output.append(
                rewrite_links_in_segment(
                    segment.text,
                    source_path=source_path,
                    resolver=resolver,
                )
            )
            continue

        output.append(segment.text)

    return "".join(output)


def find_unresolved_doc_links(source_root: Path) -> list[str]:
    unresolved: list[str] = []
    root = Path(source_root)
    resolver = LinkResolver(root)

    for source_path in resolver.source_pages:
        content = (root / source_path).read_text(encoding="utf-8")
        for link in iter_markdown_links(content):
            resolved_path, _ = resolver.resolve_markdown_target(
                link.target, source_path
            )
            if resolved_path is not None:
                continue
            parsed_target = parse_doc_target(link.target)
            if parsed_target is None:
                continue
            base_target, _ = parsed_target
            resolution = resolver.resolve_base_target(base_target, source_path)
            if resolution.ambiguous_matches:
                unresolved.append(
                    f"{source_path} -> {link.target} (ambiguous: {', '.join(resolution.ambiguous_matches)})",
                )
                continue
            unresolved.append(f"{source_path} -> {link.target}")

    return unresolved


def check_unresolved_doc_links(source_root: Path) -> None:
    unresolved = find_unresolved_doc_links(source_root)
    if not unresolved:
        return

    issues = "\n".join(f"- {item}" for item in unresolved)
    raise ValueError(f"Unresolved internal doc links found:\n{issues}")


def page_name_for_source(source_path: str) -> str:
    if not source_path.endswith(".md"):
        raise ValueError(f"Unsupported source path: {source_path}")
    return source_path[:-3].replace("/", "-")


def strip_frontmatter(content: str) -> str:
    if not content.startswith("---\n"):
        return content

    closing = content.find("\n---\n", 4)
    if closing == -1:
        return content

    return content[closing + 5 :].lstrip("\n")


def normalize_content(content: str) -> str:
    stripped = content.rstrip()
    if not stripped:
        return ""
    return f"{stripped}\n"


def default_title_for_source(source_path: str) -> str:
    stem = PurePosixPath(source_path).stem
    return stem.replace("-", " ")


def extract_title(content: str, source_path: str) -> str:
    match = TITLE_RE.search(content)
    if match:
        return match.group(1).strip()
    return default_title_for_source(source_path)


def build_language_index(language: str, page_names: set[str]) -> str:
    config = LANG_CONFIG[language]
    lines = [config["index_title"], "", config["index_intro"], ""]

    for label, page_name in config["index_links"]:
        if page_name in page_names:
            lines.append(f"- [{label}]({page_name})")

    return normalize_content("\n".join(lines))


def build_home_page(language: str) -> str:
    config = LANG_CONFIG[language]
    lines = ["# AstrBot Wiki", "", config["home_intro"], ""]
    for label, target in config["home_links"]:
        lines.append(f"- [{label}]({target})")
    return normalize_content("\n".join(lines))


def build_sidebar(page_infos: list[PageInfo]) -> str:
    lines: list[str] = []

    for language in ("zh", "en"):
        config = LANG_CONFIG[language]
        infos = [
            info
            for info in page_infos
            if info.language == language and not info.is_index
        ]
        infos.sort(key=lambda info: info.source_path)

        lines.append(f"### {config['sidebar_language_label']}")
        lines.append("")
        lines.append(
            f"- [{config['sidebar_home_label']}]({config['sidebar_home_target']})",
        )
        lines.append(
            f"- [{config['sidebar_docs_entry_label']}]({language}-index)",
        )

        grouped: dict[str, list[PageInfo]] = {}
        for info in infos:
            grouped.setdefault(info.group, []).append(info)

        for group_name in sorted(grouped):
            lines.append(f"- {group_name}")
            for info in grouped[group_name]:
                lines.append(f"  - [{info.title}]({info.page_name})")

        lines.append("")

    return normalize_content("\n".join(lines))


def build_page_info(
    source_root: Path, source_path: str, resolver: LinkResolver
) -> PageInfo:
    source_file = source_root / source_path
    content = source_file.read_text(encoding="utf-8")
    content = strip_frontmatter(content)
    content = rewrite_links(content, source_path=source_path, resolver=resolver)
    content = normalize_content(content)

    relative = PurePosixPath(source_path)
    parts = relative.parts
    group = "Top Level" if len(parts) <= 2 else parts[1].replace("-", " ")

    return PageInfo(
        source_path=source_path,
        page_name=page_name_for_source(source_path),
        title=extract_title(content, source_path),
        content=content,
        language=language_for_source(source_path),
        group=group,
        is_index=relative.name == "index.md",
    )


def read_manifest(wiki_root: Path) -> set[str]:
    manifest_path = wiki_root / MANIFEST_NAME
    if not manifest_path.exists():
        return set()
    return {
        line.strip()
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def write_manifest(wiki_root: Path, file_names: set[str]) -> None:
    manifest_path = wiki_root / MANIFEST_NAME
    content = "\n".join(sorted(file_names))
    if content:
        content = f"{content}\n"
    manifest_path.write_text(content, encoding="utf-8")


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def sync_docs_to_wiki(source_root: Path, wiki_root: Path) -> None:
    source_root = Path(source_root)
    wiki_root = Path(wiki_root)
    wiki_root.mkdir(parents=True, exist_ok=True)
    resolver = LinkResolver(source_root)

    page_infos = [
        build_page_info(source_root, source_path, resolver)
        for source_path in resolver.source_pages
    ]
    page_names = {info.page_name for info in page_infos}

    for info in page_infos:
        if info.is_index and not info.content.strip():
            generated = build_language_index(info.language, page_names)
            info.content = generated
            info.title = extract_title(generated, info.source_path)

    desired_files = {f"{info.page_name}.md": info.content for info in page_infos}
    desired_files["Home.md"] = build_home_page("zh")
    desired_files["Home-en.md"] = build_home_page("en")
    desired_files["_Sidebar.md"] = build_sidebar(page_infos)

    previously_managed = read_manifest(wiki_root)
    for existing_name in previously_managed - set(desired_files):
        existing_path = wiki_root / existing_name
        if existing_path.exists():
            existing_path.unlink()

    for file_name, content in desired_files.items():
        write_file(wiki_root / file_name, content)

    managed_files = set(desired_files)
    write_manifest(wiki_root, managed_files)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync AstrBot docs content to GitHub wiki pages."
    )
    parser.add_argument(
        "--source-root",
        default=str(repo_root()),
        help="Path to the AstrBot-docs repository root.",
    )
    parser.add_argument(
        "--wiki-root",
        help="Path to the checked out wiki repository.",
    )
    parser.add_argument(
        "--check-links-only",
        action="store_true",
        help="Validate internal doc links without writing wiki files.",
    )
    args = parser.parse_args()

    if not args.check_links_only and not args.wiki_root:
        parser.error("--wiki-root is required unless --check-links-only is set")

    check_unresolved_doc_links(Path(args.source_root))

    if args.check_links_only:
        return 0

    sync_docs_to_wiki(
        source_root=Path(args.source_root), wiki_root=Path(args.wiki_root)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
