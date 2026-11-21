"""Synchronize and verify the pure-Python `astrbot-sdk` snapshot in `vendor/`.

AstrBot Core ships a vendored copy of the pure-Python `astrbot-sdk` runtime so
hosts and CI do not need a Rust toolchain or network access at startup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_VENDOR_ROOT = _REPO_ROOT / "vendor" / "astrbot-sdk"
_DEFAULT_SOURCE = _REPO_ROOT / ".worktrees" / "astrbot-sdk"
_UPSTREAM_FILE = "UPSTREAM.json"
_UPSTREAM_REPO_URL = "https://github.com/AstrBotDevs/astrbot-sdk"

_GIT_ENV_STRIP = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CEILING_DIRECTORIES",
)


def _clean_git_env() -> dict[str, str]:
    env = dict(os.environ)
    for var in _GIT_ENV_STRIP:
        env.pop(var, None)
    return env


def _is_cache_artifact(path: Path) -> bool:
    name = path.name
    if name == "__pycache__" or name.startswith(".pytest"):
        return True
    return name.endswith((".pyc", ".pyo"))


def _is_forbidden_native_artifact(path: Path) -> bool:
    return path.name.endswith((".so", ".pyd", ".dylib", ".dll"))


def _collect_source_files(source_root: Path) -> list[tuple[str, Path]]:
    src_pkg = source_root / "src" / "astrbot_sdk"
    if not src_pkg.is_dir():
        raise FileNotFoundError(f"missing astrbot_sdk package under {source_root}")

    entries: list[tuple[str, Path]] = []
    for top_name in ("README.md", "pyproject.toml"):
        top_file = source_root / top_name
        if top_file.is_file():
            entries.append((top_name, top_file))

    for file_path in sorted(src_pkg.rglob("*")):
        if not file_path.is_file():
            continue
        if any(
            _is_cache_artifact(p) or _is_forbidden_native_artifact(p)
            for p in file_path.parents
        ):
            continue
        if _is_cache_artifact(file_path) or _is_forbidden_native_artifact(file_path):
            continue
        rel = file_path.relative_to(source_root).as_posix()
        entries.append((rel, file_path))

    entries.sort(key=lambda item: item[0])
    return entries


def compute_tree_sha256(root: Path) -> str:
    """Compute a deterministic SHA-256 digest over vendor snapshot files.

    Args:
        root: Directory containing `vendor/astrbot-sdk`.

    Returns:
        Hexadecimal SHA-256 digest string.
    """
    hasher = hashlib.sha256()
    files = sorted(
        (
            file_path.relative_to(root).as_posix(),
            file_path,
        )
        for file_path in root.rglob("*")
        if file_path.is_file()
        and file_path.relative_to(root).as_posix() != _UPSTREAM_FILE
    )
    for rel, file_path in files:
        if any(_is_cache_artifact(p) for p in file_path.parents) or _is_cache_artifact(
            file_path
        ):
            continue
        if any(
            _is_forbidden_native_artifact(p) for p in file_path.parents
        ) or _is_forbidden_native_artifact(file_path):
            raise ValueError(f"forbidden build artifact in vendor snapshot: {rel}")
        data = file_path.read_bytes()
        hasher.update(rel.encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update(str(len(data)).encode("ascii"))
        hasher.update(b":")
        hasher.update(data)
        hasher.update(b"\n")
    return hasher.hexdigest()


def _source_commit_sha(source_root: Path) -> str:
    if not (source_root / ".git").exists():
        return "unknown"
    proc = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        env=_clean_git_env(),
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def sync_from_source(
    source_root: Path, vendor_root: Path = _VENDOR_ROOT
) -> dict[str, str]:
    """Copy the pure-Python `astrbot-sdk` tree into `vendor/astrbot-sdk/`.

    Args:
        source_root: Checkout of `astrbot-sdk`.
        vendor_root: Target vendor directory in `AstrBot`.

    Returns:
        Upstream metadata dictionary written to `UPSTREAM.json`.
    """
    entries = _collect_source_files(source_root)
    if vendor_root.exists():
        shutil.rmtree(vendor_root)
    vendor_root.mkdir(parents=True, exist_ok=True)

    for rel, src_path in entries:
        dest_path = vendor_root / rel
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dest_path)

    metadata = {
        "repository": _UPSTREAM_REPO_URL,
        "commit": _source_commit_sha(source_root),
        "tree_sha256": compute_tree_sha256(vendor_root),
    }
    (vendor_root / _UPSTREAM_FILE).write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return metadata


def check_vendor_snapshot(
    vendor_root: Path = _VENDOR_ROOT,
    source_root: Path | None = None,
) -> dict[str, str]:
    """Verify `vendor/astrbot-sdk/` integrity against `UPSTREAM.json`.

    Args:
        vendor_root: Vendor snapshot directory.
        source_root: Optional upstream checkout to verify parity against.

    Returns:
        Loaded upstream metadata dictionary.

    Raises:
        ValueError: Snapshot metadata is missing or contents drifted.
    """
    upstream_path = vendor_root / _UPSTREAM_FILE
    if not upstream_path.is_file():
        raise ValueError(f"missing vendor manifest: {upstream_path}")
    data = json.loads(upstream_path.read_text(encoding="utf-8"))
    expected = data.get("tree_sha256")
    actual = compute_tree_sha256(vendor_root)
    if expected != actual:
        raise ValueError(
            f"vendor/astrbot-sdk digest mismatch: expected {expected}, got {actual}"
        )

    if source_root is not None:
        hasher = hashlib.sha256()
        for rel, src_path in _collect_source_files(source_root):
            raw = src_path.read_bytes()
            hasher.update(rel.encode("utf-8"))
            hasher.update(b"\x00")
            hasher.update(str(len(raw)).encode("ascii"))
            hasher.update(b":")
            hasher.update(raw)
            hasher.update(b"\n")
        source_digest = hasher.hexdigest()
        if source_digest != expected:
            raise ValueError(
                f"vendor/astrbot-sdk ({expected}) differs from source ({source_digest})"
            )
    return dict(data)


def main() -> None:
    """CLI entrypoint for vendor snapshot synchronization and verification."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="Local astrbot-sdk checkout (defaults to .worktrees/astrbot-sdk when syncing)",
    )
    parser.add_argument(
        "--from-git",
        default=None,
        help="Optional Git URL to shallow-clone and sync from",
    )
    parser.add_argument(
        "--ref",
        default="main",
        help="Git branch or tag when using --from-git",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify vendor/astrbot-sdk integrity without writing files",
    )
    args = parser.parse_args()

    if args.check and args.from_git is None:
        meta = check_vendor_snapshot(_VENDOR_ROOT, source_root=args.source)
        print(
            f"vendor/astrbot-sdk ok (commit={meta.get('commit')}, sha256={meta.get('tree_sha256')})"
        )
        return

    if args.from_git:
        with tempfile.TemporaryDirectory(prefix="astrbot_sdk_sync_") as tmp_dir:
            clone_dir = Path(tmp_dir) / "repo"
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    "--branch",
                    args.ref,
                    args.from_git,
                    str(clone_dir),
                ],
                env=_clean_git_env(),
                check=True,
            )
            if args.check:
                meta = check_vendor_snapshot(_VENDOR_ROOT, source_root=clone_dir)
                print(f"vendor/astrbot-sdk ok ({meta['tree_sha256']})")
            else:
                meta = sync_from_source(clone_dir, _VENDOR_ROOT)
                print(
                    f"synced vendor/astrbot-sdk ({meta['commit']} -> {meta['tree_sha256']})"
                )
        return

    source = (args.source or _DEFAULT_SOURCE).resolve()
    meta = sync_from_source(source, _VENDOR_ROOT)
    print(f"synced vendor/astrbot-sdk ({meta['commit']} -> {meta['tree_sha256']})")


if __name__ == "__main__":
    main()
