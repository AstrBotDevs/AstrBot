#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import quote

IMAGE_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".avif",
    ".bmp",
    ".ico",
    ".tif",
    ".tiff",
}

MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
HTML_IMG_RE = re.compile(r"<img\b[^>]*\bsrc\s*=\s*([\"'])([^\"']+)\1[^>]*>", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload all locally referenced images from Markdown docs to Cloudflare R2 using rclone."
    )
    parser.add_argument("--remote", required=True, help="rclone remote name, e.g. r2")
    parser.add_argument("--bucket", default="", help="bucket name in remote path")
    parser.add_argument(
        "--prefix",
        default="docs-images",
        help="destination prefix inside bucket/remote (default: docs-images)",
    )
    parser.add_argument(
        "--docs-root",
        default=".",
        help="docs root to scan for .md files (default: current directory)",
    )
    parser.add_argument("--dry-run", action="store_true", help="preview uploads without sending files")
    parser.add_argument("--list-only", action="store_true", help="only print matched image files")
    parser.add_argument(
        "--rewrite-markdown",
        action="store_true",
        help="rewrite local image links in markdown/html to public URL after upload",
    )
    parser.add_argument(
        "--public-base-url",
        default="",
        help="public URL base used for replacement, e.g. https://cdn.example.com/docs",
    )
    parser.add_argument(
        "--backup-ext",
        default=".bak",
        help="backup extension used when rewriting markdown (default: .bak)",
    )
    return parser.parse_args()


def is_local_ref(ref: str) -> bool:
    lower = ref.lower()
    return not (
        lower.startswith("http://")
        or lower.startswith("https://")
        or lower.startswith("//")
        or lower.startswith("data:")
        or lower.startswith("mailto:")
    )


def parse_md_ref(raw: str) -> str:
    ref = raw.strip()
    if ref.startswith("<") and ">" in ref:
        ref = ref[1 : ref.find(">")]
    else:
        ref = re.split(r"\s+", ref, maxsplit=1)[0]
    ref = ref.split("#", 1)[0].split("?", 1)[0]
    return ref.strip()


def clean_ref(raw: str) -> str:
    ref = raw.strip().strip("<>")
    ref = ref.split("#", 1)[0].split("?", 1)[0]
    return ref.strip()


def resolve_local_ref(md_file: Path, ref: str, root: Path) -> Optional[Path]:
    if not ref:
        return None
    if ref.startswith("/"):
        candidate = root / ref.lstrip("/")
    else:
        candidate = (md_file.parent / ref).resolve()

    try:
        resolved = candidate.resolve()
    except FileNotFoundError:
        return None

    if not resolved.is_file():
        return None

    try:
        resolved.relative_to(root)
    except ValueError:
        return None

    if resolved.suffix.lower() not in IMAGE_EXTS:
        return None

    return resolved


def find_markdown_files(root: Path) -> List[Path]:
    files: List[Path] = []
    for path in root.rglob("*.md"):
        if "node_modules" in path.parts:
            continue
        files.append(path)
    return sorted(files)


def collect_images(root: Path, md_files: Sequence[Path]) -> Tuple[Set[Path], List[Tuple[Path, str]]]:
    images: Set[Path] = set()
    missing: List[Tuple[Path, str]] = []

    for md_file in md_files:
        text = md_file.read_text(encoding="utf-8")

        for m in MD_IMAGE_RE.finditer(text):
            ref = parse_md_ref(m.group(1))
            if not ref or not is_local_ref(ref):
                continue
            resolved = resolve_local_ref(md_file, ref, root)
            if resolved:
                images.add(resolved)
            else:
                missing.append((md_file, ref))

        for m in HTML_IMG_RE.finditer(text):
            ref = clean_ref(m.group(2))
            if not ref or not is_local_ref(ref):
                continue
            resolved = resolve_local_ref(md_file, ref, root)
            if resolved:
                images.add(resolved)
            else:
                missing.append((md_file, ref))

    return images, missing


def build_target(remote: str, bucket: str, prefix: str) -> str:
    target = f"{remote}:"
    if bucket:
        target = f"{remote}:{bucket}"

    p = prefix.strip("/")
    if p:
        target = f"{target}/{p}"

    return target


def rel_object_path(root: Path, image_path: Path, prefix: str) -> str:
    rel = image_path.relative_to(root).as_posix()
    p = prefix.strip("/")
    return f"{p}/{rel}" if p else rel


def build_public_url(base: str, object_path: str) -> str:
    base = base.rstrip("/")
    encoded_path = quote(object_path, safe="/-._~")
    return f"{base}/{encoded_path}"


def run_rclone_upload(root: Path, target: str, rel_files: Iterable[str], dry_run: bool) -> None:
    if shutil.which("rclone") is None:
        raise RuntimeError("rclone not found in PATH")

    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        for rel in rel_files:
            tmp.write(f"{rel}\n")

    try:
        cmd = [
            "rclone",
            "copy",
            str(root),
            target,
            "--files-from",
            str(tmp_path),
            "--create-empty-src-dirs",
        ]
        if dry_run:
            cmd.append("--dry-run")

        print()
        if dry_run:
            print("Dry-run:", " ".join(cmd))
        else:
            print(f"Uploading to: {target}")

        subprocess.run(cmd, check=True)
    finally:
        tmp_path.unlink(missing_ok=True)


def rewrite_markdown_files(
    root: Path,
    md_files: Sequence[Path],
    image_set: Set[Path],
    prefix: str,
    public_base_url: str,
    backup_ext: str,
) -> int:
    changed_count = 0

    def to_url(md_file: Path, raw_ref: str, is_markdown: bool) -> Optional[str]:
        ref = parse_md_ref(raw_ref) if is_markdown else clean_ref(raw_ref)
        if not ref or not is_local_ref(ref):
            return None
        resolved = resolve_local_ref(md_file, ref, root)
        if not resolved or resolved not in image_set:
            return None
        obj = rel_object_path(root, resolved, prefix)
        return build_public_url(public_base_url, obj)

    for md_file in md_files:
        text = md_file.read_text(encoding="utf-8")

        def md_repl(match: re.Match[str]) -> str:
            raw = match.group(1)
            url = to_url(md_file, raw, is_markdown=True)
            if not url:
                return match.group(0)
            return match.group(0).replace(raw, url, 1)

        def html_repl(match: re.Match[str]) -> str:
            quote_ch = match.group(1)
            raw = match.group(2)
            url = to_url(md_file, raw, is_markdown=False)
            if not url:
                return match.group(0)
            return match.group(0).replace(f"src={quote_ch}{raw}{quote_ch}", f"src={quote_ch}{url}{quote_ch}", 1)

        updated = MD_IMAGE_RE.sub(md_repl, text)
        updated = HTML_IMG_RE.sub(html_repl, updated)

        if updated != text:
            if backup_ext:
                backup_path = md_file.with_suffix(md_file.suffix + backup_ext)
                backup_path.write_text(text, encoding="utf-8")
            md_file.write_text(updated, encoding="utf-8")
            changed_count += 1

    return changed_count


def main() -> int:
    args = parse_args()

    if args.rewrite_markdown and not args.public_base_url:
        print("Error: --public-base-url is required when using --rewrite-markdown", file=sys.stderr)
        return 1

    root = Path(args.docs_root).resolve()
    if not root.is_dir():
        print(f"Error: docs root not found: {args.docs_root}", file=sys.stderr)
        return 1

    if shutil.which("rg") is None:
        print("Error: rg (ripgrep) not found in PATH", file=sys.stderr)
        return 1

    md_files = find_markdown_files(root)
    images, missing = collect_images(root, md_files)

    if not images:
        print("No local image references found in Markdown docs.")
        return 0

    rel_files = sorted(p.relative_to(root).as_posix() for p in images)

    print(f"Found {len(rel_files)} image files:")
    for rel in rel_files:
        print(rel)

    if missing:
        print(file=sys.stderr)
        print(f"Warning: {len(missing)} referenced files were not found (showing up to 20):", file=sys.stderr)
        for md, ref in missing[:20]:
            print(f"{md}\t{ref}", file=sys.stderr)

    if args.list_only:
        return 0

    target = build_target(args.remote, args.bucket, args.prefix)
    run_rclone_upload(root, target, rel_files, dry_run=args.dry_run)

    if args.rewrite_markdown and not args.dry_run:
        changed = rewrite_markdown_files(
            root=root,
            md_files=md_files,
            image_set=images,
            prefix=args.prefix,
            public_base_url=args.public_base_url,
            backup_ext=args.backup_ext,
        )
        print(f"Rewrote {changed} markdown files.")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
