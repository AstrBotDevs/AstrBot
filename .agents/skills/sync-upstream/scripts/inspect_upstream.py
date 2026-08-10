#!/usr/bin/env python3
"""Inspect the pending upstream interval without changing the repository."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from upstream_decisions import LedgerError, latest_by_commit, load_events

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def run_git(repo: Path, *arguments: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *arguments],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or "git command failed"
        raise LedgerError(detail) from exc


def read_sync_config(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    marker = re.search(r"(?m)^\s+commit:\s*([0-9a-f]{40})\s*$", text)
    branch = re.search(r"(?m)^\s+branch:\s*([^\s#]+)\s*$", text)
    if not marker or not SHA_RE.fullmatch(marker.group(1)):
        raise LedgerError(f"could not find a full sync marker in {path}")
    if not branch:
        raise LedgerError(f"could not find upstream branch in {path}")
    return marker.group(1), branch.group(1)


def pending_commits(repo: Path, marker: str, ref: str) -> list[dict[str, Any]]:
    raw = run_git(
        repo,
        "log",
        "--reverse",
        "--topo-order",
        "--format=%H%x1f%ad%x1f%s",
        "--date=short",
        f"{marker}..{ref}",
    )
    result: list[dict[str, Any]] = []
    for line in raw.splitlines():
        commit, date, subject = line.split("\x1f", 2)
        paths = run_git(
            repo, "diff-tree", "--no-commit-id", "--name-only", "-r", commit
        )
        result.append(
            {
                "commit": commit,
                "date": date,
                "subject": subject,
                "paths": paths.splitlines() if paths else [],
            }
        )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--sync-file", type=Path, default=Path("upstream-sync.yaml"))
    parser.add_argument(
        "--decisions-file", type=Path, default=Path("upstream-decisions.jsonl")
    )
    parser.add_argument("--remote", default="upstream")
    parser.add_argument("--branch", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        marker, configured_branch = read_sync_config(args.repo / args.sync_file)
        branch = args.branch or configured_branch
        ref = f"{args.remote}/{branch}"
        head = run_git(args.repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
        run_git(args.repo, "cat-file", "-e", f"{marker}^{{commit}}")
        ancestor = subprocess.run(
            ["git", "-C", str(args.repo), "merge-base", "--is-ancestor", marker, ref],
            capture_output=True,
        )
        if ancestor.returncode:
            raise LedgerError(f"sync marker {marker} is not an ancestor of {ref}")
        events = load_events(args.repo / args.decisions_file)
        decisions = latest_by_commit(events)
        commits = pending_commits(args.repo, marker, ref)
        for item in commits:
            decision = decisions.get(item["commit"])
            item["decision"] = decision
        report = {
            "marker": marker,
            "upstream_ref": ref,
            "upstream_head": head,
            "pending_count": len(commits),
            "commits": commits,
        }
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"marker: {marker}")
            print(f"upstream: {ref} ({head})")
            print(f"pending: {len(commits)}")
            for item in commits:
                disposition = (item["decision"] or {}).get("disposition", "NEW")
                print(
                    f"{disposition:12} {item['commit']} {item['date']} {item['subject']}"
                )
                for path in item["paths"]:
                    print(f"              {path}")
    except (LedgerError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
