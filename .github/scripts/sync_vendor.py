#!/usr/bin/env python3

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from textwrap import dedent
from typing import NoReturn


VENDOR_README = dedent(
    """\
    # AstrBot SDK Vendor Snapshot

    This directory is the minimized subtree payload consumed by the AstrBot main
    repository.

    - `src/astrbot_sdk/` is synchronized from the source repository unchanged
    - `pyproject.toml` is copied with its original src-layout package discovery
    - `VENDORED.md` describes the vendoring contract
    - tests, docs, CI files, and other source-repo-only content stay outside this directory
    """
)

VENDORED_NOTICE = dedent(
    """\
    # Vendored Snapshot Notes

    This directory is a minimized snapshot for the AstrBot main repository to import
    via `git subtree`.

    - The source of truth is this `astrbot-sdk` repository.
    - `vendor/src/astrbot_sdk/` is synchronized from `src/astrbot_sdk/`.
    - `vendor/pyproject.toml` is copied from the root so the vendored branch keeps
      the same src-layout packaging metadata.
    - Do not edit vendored files directly inside the AstrBot main repository.
    - Tests and documentation remain only in the SDK source repository and are not
      copied into the vendored snapshot.
    - If the vendored copy needs changes, update the SDK source repository first and
      regenerate the `vendor/` snapshot.
    """
)

EXPECTED_TOP_LEVEL = {
    "LICENSE",
    "README.md",
    "VENDORED.md",
    "pyproject.toml",
    "src",
}
FORBIDDEN_PARTS = {"tests", "docs", ".github"}
SRC_LAYOUT_MARKER = "# Package Discovery (src layout)"
SRC_DISCOVERY_LINE = 'where = ["src"]'


def fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def repo_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
    )
    return Path(result.stdout.strip()).resolve()


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def build_vendor_pyproject(root_pyproject_text: str) -> str:
    if SRC_LAYOUT_MARKER not in root_pyproject_text:
        fail("root pyproject.toml is missing the expected src layout marker")
    if SRC_DISCOVERY_LINE not in root_pyproject_text:
        fail(
            "root pyproject.toml is missing the expected setuptools src discovery line"
        )

    return root_pyproject_text


def ensure_clean_vendor_package(vendor_pkg_dir: Path) -> None:
    for path in vendor_pkg_dir.rglob("*"):
        if path.is_dir() and path.name == "__pycache__":
            shutil.rmtree(path)
        elif path.is_file() and path.suffix in {".pyc", ".pyo"}:
            path.unlink()


def validate_vendor_layout(vendor_dir: Path, root_license: Path) -> None:
    actual_top_level = {path.name for path in vendor_dir.iterdir()}
    if actual_top_level != EXPECTED_TOP_LEVEL:
        fail(
            "vendor/ top-level contents are invalid; "
            f"expected {sorted(EXPECTED_TOP_LEVEL)}, got {sorted(actual_top_level)}"
        )

    for path in vendor_dir.rglob("*"):
        if any(part in FORBIDDEN_PARTS for part in path.parts):
            fail(f"vendor/ contains forbidden path: {path}")

    if root_license.read_bytes() != (vendor_dir / "LICENSE").read_bytes():
        fail("vendor/LICENSE is out of sync with root LICENSE")

    vendored_pyproject = (vendor_dir / "pyproject.toml").read_text(encoding="utf-8")
    if SRC_DISCOVERY_LINE not in vendored_pyproject:
        fail("vendor/pyproject.toml must retain src-based package discovery")
    if not (vendor_dir / "src" / "astrbot_sdk").is_dir():
        fail("vendor/src/astrbot_sdk is missing")


def build_vendor_snapshot(root: Path) -> None:
    src_dir = root / "src" / "astrbot_sdk"
    vendor_dir = root / "vendor"
    vendor_pkg_dir = vendor_dir / "src" / "astrbot_sdk"
    root_license = root / "LICENSE"
    root_pyproject = root / "pyproject.toml"

    if not src_dir.is_dir():
        fail(f"expected source package at {src_dir}")
    if not root_license.is_file():
        fail(f"expected root LICENSE at {root_license}")
    if not root_pyproject.is_file():
        fail(f"expected root pyproject.toml at {root_pyproject}")

    if vendor_dir.exists():
        shutil.rmtree(vendor_dir)

    shutil.copytree(
        src_dir,
        vendor_pkg_dir,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    ensure_clean_vendor_package(vendor_pkg_dir)

    write_text(vendor_dir / "README.md", VENDOR_README)
    shutil.copy2(root_license, vendor_dir / "LICENSE")
    write_text(
        vendor_dir / "pyproject.toml",
        build_vendor_pyproject(root_pyproject.read_text(encoding="utf-8")),
    )
    write_text(vendor_dir / "VENDORED.md", VENDORED_NOTICE)

    validate_vendor_layout(vendor_dir, root_license)
    print(f"vendor snapshot refreshed from {src_dir}")


def main() -> None:
    build_vendor_snapshot(repo_root())


if __name__ == "__main__":
    main()
