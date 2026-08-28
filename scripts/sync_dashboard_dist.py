from __future__ import annotations

import shutil
from pathlib import Path


def embed_docs_help(dist_dir: Path, *, repo_root: Path) -> Path | None:
    """Copy VitePress output into ``dist_dir/help`` when a docs build exists."""
    docs_src = repo_root / "docs" / ".vitepress" / "dist"
    if not docs_src.is_dir():
        return None
    help_dir = dist_dir / "help"
    if help_dir.exists():
        shutil.rmtree(help_dir)
    shutil.copytree(docs_src, help_dir)
    return help_dir


def sync_dashboard_dist(
    *,
    repo_root: Path | None = None,
    src: Path | None = None,
    dst: Path | None = None,
) -> tuple[Path, Path]:
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent
    if src is None:
        src = repo_root / "dashboard" / "dist"
    if dst is None:
        dst = repo_root / "data" / "dist"

    src = src.resolve()
    dst = dst.resolve()

    if not src.is_dir():
        raise FileNotFoundError(f"Dashboard dist not found: {src}")

    embed_docs_help(src, repo_root=repo_root)

    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)
    return src, dst


if __name__ == "__main__":
    copied_src, copied_dst = sync_dashboard_dist()
    print(f"Synced dashboard dist: {copied_src} -> {copied_dst}")
