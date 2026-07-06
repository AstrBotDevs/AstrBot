from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request

from astrbot.core.utils.datetime_utils import to_utc_isoformat
from astrbot.core.workspace import resolve_workspace_root_for_umo
from astrbot.dashboard.responses import ApiError, ok

from .auth import AuthContext, require_scope

router = APIRouter(tags=["Workspaces"])


async def require_data_scope(request: Request) -> AuthContext:
    return await require_scope(request, "data")


def _format_mtime(path: Path) -> str | None:
    """Format a filesystem modified timestamp for API responses.

    Args:
        path: File or directory path.

    Returns:
        UTC ISO timestamp, or None when the timestamp cannot be read.
    """
    try:
        return to_utc_isoformat(
            datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        )
    except OSError:
        return None


@router.get("/workspaces/by-umo")
async def list_umo_workspace_files(
    request: Request,
    umo: str = Query(..., min_length=1),
    path: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_data_scope),
):
    """List files in the workspace resolved for one UMO.

    Args:
        request: FastAPI request with database state.
        umo: Unified message origin.
        path: Relative directory path under the workspace root.
        _auth: Auth context.

    Returns:
        Workspace metadata and one directory level of file entries.

    Raises:
        ApiError: If the requested path escapes the workspace root.
    """
    root = await resolve_workspace_root_for_umo(umo, request.app.state.db)
    root = root.expanduser().resolve(strict=False)
    raw_path = str(path or "").strip()
    requested = root if raw_path in {"", "."} else root / raw_path
    current = requested.resolve(strict=False)

    if current != root and not current.is_relative_to(root):
        raise ApiError("Path is outside the workspace", status_code=400)

    if not root.exists() or not root.is_dir():
        return ok(
            {
                "umo": umo,
                "absolute_path": str(root),
                "relative_path": "",
                "exists": False,
                "is_directory": False,
                "items": [],
            }
        )
    if not current.exists() or not current.is_dir():
        raise ApiError("Workspace folder not found", status_code=404)

    items = []
    try:
        children = sorted(
            current.iterdir(),
            key=lambda item: (
                not (item.is_dir() and not item.is_symlink()),
                item.name.lower(),
            ),
        )
    except OSError as exc:
        raise ApiError(f"Failed to list workspace files: {exc!s}") from exc

    for child in children:
        try:
            is_symlink = child.is_symlink()
            stat_result = child.lstat() if is_symlink else child.stat()
            if is_symlink:
                item_type = "symlink"
            elif child.is_dir():
                item_type = "directory"
            elif child.is_file():
                item_type = "file"
            else:
                item_type = "other"
            items.append(
                {
                    "name": child.name,
                    "type": item_type,
                    "relative_path": child.relative_to(root).as_posix(),
                    "size_bytes": 0
                    if item_type == "directory"
                    else stat_result.st_size,
                    "modified_at": _format_mtime(child),
                }
            )
        except OSError:
            continue

    return ok(
        {
            "umo": umo,
            "absolute_path": str(root),
            "relative_path": ""
            if current == root
            else current.relative_to(root).as_posix(),
            "exists": True,
            "is_directory": True,
            "items": items,
        }
    )
