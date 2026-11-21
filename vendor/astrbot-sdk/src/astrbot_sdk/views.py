"""Plugin views: static page assets served to the Host over the pipeline.

The dashboard discovers and reads view files (views/ or pages/ directory
inside the plugin) through the Runner instead of touching the plugin
directory directly, so the serving path works identically for local and
future remote runners. manifest lists pages and files; read streams one
file's content with traversal protection.
"""

from __future__ import annotations

import mimetypes
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import InvalidRequest, NotFound

# Directory names holding plugin views, in preference order (mirrors the
# dashboard's PluginPageService).
VIEW_ROOT_DIR_NAMES = ("views", "pages")
ENTRY_FILE_NAME = "index.html"


@dataclass(frozen=True, slots=True)
class ViewFileEntry:
    """One file inside one view page directory."""

    path: str
    size: int


@dataclass(frozen=True, slots=True)
class ViewPageEntry:
    """One page discovered inside the views root."""

    name: str
    files: tuple[ViewFileEntry, ...]


def _views_root(plugin_root: Path) -> Path | None:
    for dir_name in VIEW_ROOT_DIR_NAMES:
        candidate = plugin_root / dir_name
        if candidate.is_dir():
            return candidate
    return None


_I18N_DIR = Path(".astrbot-plugin") / "i18n"
_I18N_MAX_BYTES = 1024 * 1024


def load_i18n(plugin_root: Path) -> dict[str, str]:
    """Read .astrbot-plugin/i18n/*.json contents keyed by locale."""
    i18n_dir = plugin_root / _I18N_DIR
    translations: dict[str, str] = {}
    if not i18n_dir.is_dir():
        return translations
    for file in sorted(i18n_dir.iterdir()):
        if file.suffix.lower() != ".json" or not file.is_file():
            continue
        locale = file.stem
        if not locale or len(locale) > 32 or file.stat().st_size > _I18N_MAX_BYTES:
            continue
        translations[locale] = file.read_text(encoding="utf-8-sig")
    return translations


def scan_views(plugin_root: Path) -> list[ViewPageEntry]:
    """List all pages and their files below the plugin's views root."""
    root = _views_root(plugin_root)
    if root is None:
        return []
    pages: list[ViewPageEntry] = []
    for page_dir in sorted(
        (item for item in root.iterdir() if item.is_dir()),
        key=lambda item: item.name.lower(),
    ):
        if not (page_dir / ENTRY_FILE_NAME).is_file():
            continue
        files = tuple(
            ViewFileEntry(
                path=str(file.relative_to(page_dir)),
                size=file.stat().st_size,
            )
            for file in sorted(page_dir.rglob("*"))
            if file.is_file()
        )
        pages.append(ViewPageEntry(name=page_dir.name, files=files))
    return pages


def _resolve_view_file(plugin_root: Path, page: str, path: str) -> Path:
    """Resolve one file inside a view page, rejecting traversal."""
    if not page or page.startswith(".") or "/" in page or "\\" in page:
        raise InvalidRequest(f"invalid view page name: {page!r}")
    root = _views_root(plugin_root)
    if root is None:
        raise NotFound("plugin has no views root")
    page_dir = (root / page).resolve(strict=False)
    try:
        page_dir.relative_to(root.resolve(strict=False))
    except ValueError as exc:
        raise InvalidRequest(f"invalid view page name: {page!r}") from exc
    target = (page_dir / path).resolve(strict=False)
    try:
        target.relative_to(page_dir)
    except ValueError as exc:
        raise InvalidRequest(f"view path escapes the page directory: {path!r}") from exc
    if not target.is_file():
        raise NotFound(f"view file not found: {page}/{path}")
    return target


async def read_view_file(
    plugin_root: Path,
    page: str,
    path: str,
) -> tuple[dict[str, Any], AsyncIterator[bytes]]:
    """Read one view file as (info, chunk stream)."""
    import asyncio

    target = _resolve_view_file(plugin_root, page, path)
    info = {
        "content_type": mimetypes.guess_type(target.name)[0]
        or "application/octet-stream",
        "size": target.stat().st_size,
    }

    async def chunks() -> AsyncIterator[bytes]:
        file = await asyncio.to_thread(target.open, "rb")
        try:
            while chunk := await asyncio.to_thread(file.read, 512 * 1024):
                yield chunk
        finally:
            await asyncio.to_thread(file.close)

    return info, chunks()
