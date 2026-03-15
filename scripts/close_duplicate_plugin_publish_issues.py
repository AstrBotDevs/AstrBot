from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    created_at: datetime
    url: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Close duplicate open plugin-publish issues while keeping the latest one."
        )
    )
    parser.add_argument(
        "--repo",
        default="AstrBotDevs/AstrBot",
        help="GitHub repository in owner/name format.",
    )
    parser.add_argument(
        "--label",
        default="plugin-publish",
        help="Issue label to target.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Maximum number of open issues to inspect.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually close duplicate issues. Defaults to dry-run.",
    )
    return parser.parse_args()


def run_gh_command(args: list[str]) -> str:
    try:
        completed = subprocess.run(
            args,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("GitHub CLI `gh` is not installed or not in PATH.") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip()
        stdout = exc.stdout.strip()
        details = stderr or stdout or str(exc)
        raise RuntimeError(f"`{' '.join(args)}` failed: {details}") from exc
    return completed.stdout


def load_open_issues(repo: str, label: str, limit: int) -> list[Issue]:
    output = run_gh_command(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repo,
            "--label",
            label,
            "--state",
            "open",
            "--limit",
            str(limit),
            "--json",
            "number,title,createdAt,url",
        ]
    )
    items = json.loads(output)
    return [
        Issue(
            number=item["number"],
            title=item["title"],
            created_at=datetime.fromisoformat(item["createdAt"].replace("Z", "+00:00")),
            url=item["url"],
        )
        for item in items
    ]


def normalize_title(title: str) -> str:
    return " ".join(title.split()).strip()


def find_duplicates(
    issues: list[Issue],
) -> list[tuple[Issue, list[Issue]]]:
    grouped: dict[str, list[Issue]] = defaultdict(list)
    for issue in issues:
        grouped[normalize_title(issue.title)].append(issue)

    duplicate_groups: list[tuple[Issue, list[Issue]]] = []
    for group in grouped.values():
        if len(group) < 2:
            continue
        ordered = sorted(
            group,
            key=lambda issue: (issue.created_at, issue.number),
            reverse=True,
        )
        keep = ordered[0]
        close_candidates = ordered[1:]
        duplicate_groups.append((keep, close_candidates))

    duplicate_groups.sort(
        key=lambda item: (item[0].created_at, item[0].number),
        reverse=True,
    )
    return duplicate_groups


def print_plan(duplicate_groups: list[tuple[Issue, list[Issue]]], apply: bool) -> None:
    action = "Will close" if apply else "Would close"
    if not duplicate_groups:
        print("No duplicate open issues found.")
        return

    total_to_close = sum(len(close_list) for _, close_list in duplicate_groups)
    print(f"Found {len(duplicate_groups)} duplicate title groups.")
    print(
        f"{action} {total_to_close} issues and keep {len(duplicate_groups)} latest issues."
    )

    for keep, close_list in duplicate_groups:
        print()
        print(f'Keep  #{keep.number} [{keep.created_at.isoformat()}] "{keep.title}"')
        print(f"      {keep.url}")
        for issue in close_list:
            print(
                f'Close #{issue.number} [{issue.created_at.isoformat()}] "{issue.title}"'
            )
            print(f"      {issue.url}")


def close_duplicates(
    repo: str, duplicate_groups: list[tuple[Issue, list[Issue]]]
) -> None:
    for keep, close_list in duplicate_groups:
        reason = (
            f"Closing as duplicate of #{keep.number}. "
            "Keeping the latest open issue with this title."
        )
        for issue in close_list:
            print(f"Closing #{issue.number} as duplicate of #{keep.number}...")
            run_gh_command(
                [
                    "gh",
                    "issue",
                    "close",
                    str(issue.number),
                    "--repo",
                    repo,
                    "--comment",
                    reason,
                ]
            )


def main() -> int:
    args = parse_args()
    try:
        issues = load_open_issues(args.repo, args.label, args.limit)
        duplicate_groups = find_duplicates(issues)
        print_plan(duplicate_groups, apply=args.apply)
        if args.apply and duplicate_groups:
            print()
            close_duplicates(args.repo, duplicate_groups)
            print("Done.")
        elif not args.apply:
            print()
            print("Dry-run only. Re-run with `--apply` to close the duplicates.")
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
