#!/usr/bin/env python3
"""Prepare an AstrBot release branch and release metadata."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:[-+._a-zA-Z0-9]+)?$")


class ReleaseError(RuntimeError):
    """Error raised when a release preparation step cannot continue."""


def run_command(
    args: list[str],
    *,
    cwd: Path = REPO_ROOT,
    capture_output: bool = False,
) -> str:
    """Run a command and return captured stdout when requested.

    Args:
        args: Command and arguments to run.
        cwd: Working directory for the command.
        capture_output: Whether to capture and return stdout instead of streaming it.

    Returns:
        Captured stdout without surrounding whitespace when capture_output is true;
        otherwise an empty string.

    Raises:
        ReleaseError: The command is missing or exits with a non-zero status.
    """
    printable = " ".join(args)
    print(f"$ {printable}")
    try:
        if capture_output:
            result = subprocess.run(
                args,
                cwd=cwd,
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()

        subprocess.run(args, cwd=cwd, check=True)
        return ""
    except FileNotFoundError as exc:
        raise ReleaseError(f"Command not found: {args[0]}") from exc
    except subprocess.CalledProcessError as exc:
        if capture_output and exc.stderr:
            print(exc.stderr.strip(), file=sys.stderr)
        raise ReleaseError(f"Command failed ({exc.returncode}): {printable}") from exc


def git(args: list[str], *, capture_output: bool = False) -> str:
    """Run a git command in the repository root.

    Args:
        args: Arguments to pass after `git`.
        capture_output: Whether to capture and return stdout.

    Returns:
        Captured stdout when capture_output is true; otherwise an empty string.

    Raises:
        ReleaseError: Git exits with a non-zero status.
    """
    return run_command(["git", *args], capture_output=capture_output)


def ensure_clean_worktree() -> None:
    """Ensure the release starts from a clean worktree.

    Raises:
        ReleaseError: The repository contains tracked or untracked changes.
    """
    status = git(["status", "--porcelain"], capture_output=True)
    if status:
        raise ReleaseError(
            "Working tree must be clean before preparing a release.\n"
            "Commit, stash, or remove these changes first:\n"
            f"{status}"
        )


def validate_version(version: str) -> str:
    """Validate a release version string.

    Args:
        version: Version string without the leading tag prefix.

    Returns:
        The validated version string.

    Raises:
        ReleaseError: The version is empty, starts with `v`, or has an unsupported
            shape.
    """
    if version.startswith("v"):
        raise ReleaseError(
            "Pass the version without the tag prefix, for example 4.25.0"
        )
    if not VERSION_PATTERN.fullmatch(version):
        raise ReleaseError(
            "Unsupported version format. Expected a value like 4.25.0 or 4.26.0-beta.8"
        )
    return version


def latest_tag() -> str:
    """Return the most recent reachable tag, if one exists.

    Returns:
        The latest tag name, or an empty string when the repository has no tags.
    """
    try:
        return git(["describe", "--tags", "--abbrev=0"], capture_output=True)
    except ReleaseError:
        return ""


def release_commits(tag: str) -> list[str]:
    """Read commit subjects for the release range.

    Args:
        tag: Latest tag to use as the lower bound. When empty, all reachable
            commits are considered.

    Returns:
        Commit subjects formatted for changelog draft entries.

    Raises:
        ReleaseError: Git log fails.
    """
    log_range = f"{tag}..HEAD" if tag else "HEAD"
    output = git(
        ["log", "--reverse", "--pretty=format:%s (%h)", log_range],
        capture_output=True,
    )
    return [line for line in output.splitlines() if line.strip()]


def update_pyproject_version(version: str) -> Path:
    """Update `[project].version` in pyproject.toml.

    Args:
        version: Release version to write.

    Returns:
        Path to the modified pyproject.toml file.

    Raises:
        ReleaseError: The project version field cannot be found or parsed.
    """
    pyproject_path = REPO_ROOT / "pyproject.toml"
    lines = pyproject_path.read_text(encoding="utf-8").splitlines(keepends=True)
    in_project_section = False

    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_project_section = stripped == "[project]"
            continue
        if not in_project_section:
            continue

        key, separator, _raw_value = stripped.partition("=")
        if key.strip() != "version":
            continue
        if not separator:
            raise ReleaseError("Unsupported pyproject.toml project.version format")

        match = re.match(
            r"^(\s*version\s*=\s*)([\"'])(.*?)(\2)(\s*(?:#.*)?)(\n?)$",
            line,
        )
        if not match:
            raise ReleaseError("Unsupported pyproject.toml project.version format")

        prefix, quote, _current, _closing_quote, suffix, newline = match.groups()
        lines[index] = f"{prefix}{quote}{version}{quote}{suffix}{newline}"
        pyproject_path.write_text("".join(lines), encoding="utf-8")
        return pyproject_path

    raise ReleaseError("Missing [project].version in pyproject.toml")


def update_package_version(version: str) -> Path:
    """Update the package version in astrbot/__init__.py.

    Args:
        version: Release version to write.

    Returns:
        Path to the modified astrbot/__init__.py file.

    Raises:
        ReleaseError: The package version constant cannot be found or parsed.
    """
    package_init_path = REPO_ROOT / "astrbot" / "__init__.py"
    lines = package_init_path.read_text(encoding="utf-8").splitlines(keepends=True)

    for index, line in enumerate(lines):
        match = re.match(
            r"^(\s*__version__\s*=\s*)([\"'])(.*?)(\2)(\s*(?:#.*)?)(\n?)$",
            line,
        )
        if not match:
            continue

        prefix, quote, _current, _closing_quote, suffix, newline = match.groups()
        lines[index] = f"{prefix}{quote}{version}{quote}{suffix}{newline}"
        package_init_path.write_text("".join(lines), encoding="utf-8")
        return package_init_path

    raise ReleaseError("Missing __version__ in astrbot/__init__.py")


def write_changelog(version: str, commits: list[str]) -> Path:
    """Write a changelog draft for the release.

    Args:
        version: Release version without the leading `v`.
        commits: Commit subject lines to include as the first changelog draft.

    Returns:
        Path to the created changelog file.

    Raises:
        ReleaseError: The changelog file already exists.
    """
    changelog_path = REPO_ROOT / "changelogs" / f"v{version}.md"
    if changelog_path.exists():
        raise ReleaseError(f"Changelog already exists: {changelog_path}")

    changelog_path.parent.mkdir(parents=True, exist_ok=True)
    entries = [f"- {commit}" for commit in commits] or ["- "]
    changelog_path.write_text(
        "\n".join(
            [
                "## What's Changed",
                "",
                "<!-- Review, group, and polish these entries before publishing. -->",
                "",
                *entries,
                "",
            ]
        ),
        encoding="utf-8",
    )
    return changelog_path


def create_release_branch(version: str, base_branch: str, remote: str) -> str:
    """Create a release branch from the updated base branch.

    Args:
        version: Release version without the leading `v`.
        base_branch: Base branch to release from.
        remote: Remote name used for fetching and fast-forward pulls.

    Returns:
        Created release branch name.

    Raises:
        ReleaseError: The branch already exists or Git cannot create it.
    """
    branch = f"release/{version}"
    git(["checkout", base_branch])
    git(["pull", "--ff-only", remote, base_branch])
    git(["fetch", "--tags", remote])

    local_branch = git(["branch", "--list", branch], capture_output=True)
    if local_branch:
        raise ReleaseError(f"Local branch already exists: {branch}")

    remote_branch = git(["ls-remote", "--heads", remote, branch], capture_output=True)
    if remote_branch:
        raise ReleaseError(f"Remote branch already exists: {remote}/{branch}")

    git(["switch", "-c", branch])
    return branch


def run_validation(args: argparse.Namespace) -> None:
    """Run release validation commands selected by CLI flags.

    Args:
        args: Parsed CLI arguments.

    Raises:
        ReleaseError: A validation command fails.
    """
    if args.generate_api_client:
        run_command(["pnpm", "generate:api"], cwd=REPO_ROOT / "dashboard")

    if not args.skip_checks:
        run_command(["uv", "run", "ruff", "format", "--check", "."])
        run_command(["uv", "run", "ruff", "check", "."])

    if args.dashboard_build:
        run_command(["pnpm", "install"], cwd=REPO_ROOT / "dashboard")
        run_command(["pnpm", "build"], cwd=REPO_ROOT / "dashboard")


def commit_and_maybe_push(
    version: str,
    branch: str,
    changelog_path: Path,
    args: argparse.Namespace,
) -> None:
    """Commit release preparation changes and optionally push the branch.

    Args:
        version: Release version without the leading `v`.
        branch: Release branch name.
        changelog_path: Changelog file created for this release.
        args: Parsed CLI arguments.

    Raises:
        ReleaseError: Git add, commit, or push fails.
    """
    git(
        [
            "add",
            "pyproject.toml",
            "astrbot/__init__.py",
            str(changelog_path.relative_to(REPO_ROOT)),
        ]
    )
    if args.generate_api_client:
        git(["add", "dashboard/src/api/generated"])

    git(["commit", "-m", f"chore: bump version to {version}"])
    if args.push:
        git(["push", "-u", args.remote, branch])


def print_next_steps(
    version: str,
    branch: str,
    changelog_path: Path,
    args: argparse.Namespace,
) -> None:
    """Print the manual steps that remain after preparation.

    Args:
        version: Release version without the leading `v`.
        branch: Release branch name.
        changelog_path: Changelog file created for this release.
        args: Parsed CLI arguments.
    """
    changelog_rel = changelog_path.relative_to(REPO_ROOT)
    print("\nRelease preparation complete.")
    print(f"Branch: {branch}")
    print(f"Changelog: {changelog_rel}")

    if args.commit:
        if not args.push:
            print(f"Next: git push -u {args.remote} {branch}")
    else:
        print("Next:")
        print(f"1. Review and polish {changelog_rel}")
        print(f"2. git add pyproject.toml astrbot/__init__.py {changelog_rel}")
        print(f'3. git commit -m "chore: bump version to {version}"')
        print(f"4. git push -u {args.remote} {branch}")

    print(f"Open a PR from {branch} to {args.base_branch}.")
    print(
        "After the PR is merged, tag from the updated base branch with "
        f"`git tag v{version}` and `git push {args.remote} v{version}`."
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Raw command-line arguments excluding the executable name.

    Returns:
        Parsed CLI arguments.

    Raises:
        ReleaseError: Push is requested without commit.
    """
    parser = argparse.ArgumentParser(
        description="Prepare an AstrBot release branch, version bump, and changelog.",
    )
    parser.add_argument("version", help="Release version without the leading v")
    parser.add_argument("--base-branch", default="master", help="Release base branch")
    parser.add_argument("--remote", default="origin", help="Git remote name")
    parser.add_argument(
        "--generate-api-client",
        action="store_true",
        help="Run dashboard API client generation before validation",
    )
    parser.add_argument(
        "--dashboard-build",
        action="store_true",
        help="Run dashboard install and build validation",
    )
    parser.add_argument(
        "--skip-checks",
        action="store_true",
        help="Skip ruff format and ruff check",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Commit the generated release preparation changes",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push the release branch after committing; requires --commit",
    )
    args = parser.parse_args(argv)
    if args.push and not args.commit:
        raise ReleaseError("--push requires --commit")
    return args


def main(argv: list[str] | None = None) -> int:
    """Run the release preparation workflow.

    Args:
        argv: Optional command-line arguments for tests or programmatic calls.

    Returns:
        Process exit code.
    """
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
        version = validate_version(args.version)
        ensure_clean_worktree()

        branch = create_release_branch(version, args.base_branch, args.remote)
        tag = latest_tag()
        if tag:
            print(f"Latest tag: {tag}")
        else:
            print("No existing tags found; changelog will use all reachable commits.")

        commits = release_commits(tag)
        update_pyproject_version(version)
        update_package_version(version)
        changelog_path = write_changelog(version, commits)
        run_validation(args)

        if args.commit:
            commit_and_maybe_push(version, branch, changelog_path, args)

        print_next_steps(version, branch, changelog_path, args)
        return 0
    except ReleaseError as exc:
        print(f"prepare-release: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
