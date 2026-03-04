#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
from collections import defaultdict
from pathlib import Path

from astrbot.core.release_constants import NIGHTLY_TAG


def _run_git(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        stdout = (e.stdout or "").strip()
        detail = stderr or stdout or "no output"
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}") from e
    return result.stdout.strip()


def _is_valid_ref(ref: str) -> bool:
    if not ref:
        return False
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", ref],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _classify(subject: str) -> str:
    lowered = subject.lower().strip()
    if lowered.startswith("feat") or "新增" in subject:
        return "新增"
    if lowered.startswith("fix") or "修复" in subject:
        return "修复"
    if (
        lowered.startswith("perf")
        or lowered.startswith("refactor")
        or "优化" in subject
    ):
        return "优化"
    return "其他"


def _write_fallback(output_path: Path) -> None:
    short_sha = _run_git("rev-parse", "--short=8", "HEAD")
    output_path.write_text(
        f"## What's Changed\n\n- {NIGHTLY_TAG.capitalize()} build from `{short_sha}`\n",
        encoding="utf-8",
    )


def generate_notes(base_tag: str, repo: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not _is_valid_ref(base_tag):
        _write_fallback(output_path)
        return

    log_output = _run_git(
        "log",
        "--no-merges",
        "--pretty=format:%h%x1f%s",
        f"{base_tag}..HEAD",
    )
    sections: dict[str, list[str]] = defaultdict(list)
    for line in log_output.splitlines():
        if not line.strip() or "\x1f" not in line:
            continue
        short_sha, subject = line.split("\x1f", 1)
        commit_link = f"https://github.com/{repo}/commit/{short_sha}"
        sections[_classify(subject)].append(
            f"- {subject} ([`{short_sha}`]({commit_link}))"
        )

    nightly_commit = _run_git("rev-parse", "--short=8", "HEAD")
    with output_path.open("w", encoding="utf-8") as file:
        file.write("## What's Changed\n\n")
        file.write(f"- Baseline tag: `{base_tag}`\n")
        file.write(f"- {NIGHTLY_TAG.capitalize()} commit: `{nightly_commit}`\n")

        if not any(sections.values()):
            file.write(f"- No changes since `{base_tag}`\n\n")
            return

        file.write("\n")
        for title in ("新增", "修复", "优化", "其他"):
            items = sections.get(title, [])
            if not items:
                continue
            file.write(f"### {title}\n")
            file.write("\n".join(items))
            file.write("\n\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate release notes for nightly release.",
    )
    parser.add_argument("--base-tag", default="", help="Baseline stable tag.")
    parser.add_argument("--repo", required=True, help="GitHub repository slug.")
    parser.add_argument("--output", required=True, help="Output markdown path.")
    args = parser.parse_args()

    try:
        generate_notes(args.base_tag.strip(), args.repo.strip(), Path(args.output))
    except Exception as e:
        raise SystemExit(f"Failed to generate nightly release notes: {e}") from e


if __name__ == "__main__":
    main()
