from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from astrbot.core.db import BaseDatabase
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.utils.astrbot_path import get_astrbot_workspaces_path

WORKSPACE_TYPE_SESSION = "session"
WORKSPACE_TYPE_PROJECT = "project"
WORKSPACE_TYPE_CUSTOM = "custom"
WORKSPACE_TYPES = {
    WORKSPACE_TYPE_SESSION,
    WORKSPACE_TYPE_PROJECT,
    WORKSPACE_TYPE_CUSTOM,
}


def normalize_umo_for_workspace(umo: str) -> str:
    """Normalize a unified message origin into a filesystem-safe name.

    Args:
        umo: Unified message origin.

    Returns:
        Filesystem-safe workspace directory name.
    """
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", umo.strip())
    return normalized or "unknown"


def normalize_project_workspace_type(value: Any) -> str:
    """Normalize stored or incoming project workspace type.

    Args:
        value: Raw workspace type value.

    Returns:
        A known workspace type.
    """
    workspace_type = str(value or WORKSPACE_TYPE_SESSION).strip().lower()
    return (
        workspace_type if workspace_type in WORKSPACE_TYPES else WORKSPACE_TYPE_SESSION
    )


def normalize_workspace_path(path: Any) -> str | None:
    """Normalize a custom workspace path value for storage.

    Args:
        path: Raw path value from API or database.

    Returns:
        Normalized path string, or None when empty.
    """
    if not isinstance(path, str):
        return None
    value = path.strip()
    return value or None


def default_workspace_root(umo: str) -> Path:
    """Return the legacy per-session workspace root.

    Args:
        umo: Unified message origin.

    Returns:
        The legacy workspace directory path.
    """
    return (
        Path(get_astrbot_workspaces_path()) / normalize_umo_for_workspace(umo)
    ).resolve(strict=False)


def project_workspace_root(project_id: str) -> Path:
    """Return the default shared workspace root for a ChatUI project.

    Args:
        project_id: ChatUI project ID.

    Returns:
        The project workspace directory path.
    """
    safe_project_id = re.sub(r"[^A-Za-z0-9._-]+", "_", project_id.strip())
    return (Path(get_astrbot_workspaces_path()) / f"project_{safe_project_id}").resolve(
        strict=False
    )


def workspace_path_to_root(path: str) -> Path:
    """Resolve a custom workspace path.

    Args:
        path: Stored workspace path. Relative values are rooted under AstrBot
            workspaces. Absolute values must also point inside AstrBot workspaces.

    Returns:
        Absolute resolved path.

    Raises:
        ValueError: If the path escapes or targets the AstrBot workspaces
            root.
    """
    workspaces_root = Path(get_astrbot_workspaces_path()).resolve(strict=False)
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        resolved = candidate.resolve(strict=False)
    else:
        resolved = (workspaces_root / candidate).resolve(strict=False)
    if resolved == workspaces_root or not resolved.is_relative_to(workspaces_root):
        raise ValueError(
            "Custom workspace path must stay within a subdirectory of AstrBot workspaces"
        )
    return resolved


def resolve_project_workspace_root(project: Any, *, fallback_umo: str) -> Path:
    """Resolve the workspace root from a project record.

    Args:
        project: Project-like object with workspace fields.
        fallback_umo: UMO used when the project keeps legacy session workspaces.

    Returns:
        Workspace root used as cwd.
    """
    fallback = default_workspace_root(fallback_umo)
    workspace_type = normalize_project_workspace_type(
        getattr(project, "workspace_type", WORKSPACE_TYPE_SESSION)
    )
    if workspace_type == WORKSPACE_TYPE_SESSION:
        return fallback
    if workspace_type == WORKSPACE_TYPE_PROJECT:
        return project_workspace_root(str(project.project_id))
    if workspace_type == WORKSPACE_TYPE_CUSTOM:
        workspace_path = normalize_workspace_path(
            getattr(project, "workspace_path", None)
        )
        if workspace_path:
            return workspace_path_to_root(workspace_path)
    return fallback


def parse_webchat_umo(umo: str) -> tuple[str, str] | None:
    """Extract creator and session ID from a webchat UMO.

    Args:
        umo: Unified message origin.

    Returns:
        Tuple of creator and ChatUI session ID, or None for non-webchat UMO.
    """
    try:
        message_session = MessageSession.from_str(umo)
    except Exception:
        return None

    if message_session.platform_name != "webchat":
        return None

    parts = message_session.session_id.split("!", 2)
    if len(parts) != 3 or parts[0] != "webchat":
        return None
    return parts[1], parts[2]


async def resolve_workspace_root_for_umo(
    umo: str,
    db: BaseDatabase | None = None,
) -> Path:
    """Resolve the workspace root for a UMO.

    Args:
        umo: Unified message origin.
        db: Optional database instance. Falls back to the global database helper.

    Returns:
        Workspace root used as cwd.
    """
    parsed = parse_webchat_umo(umo)
    if not parsed:
        return default_workspace_root(umo)

    creator, session_id = parsed
    if db is None:
        from astrbot.core import db_helper

        db = db_helper

    project = await db.get_project_by_session(session_id=session_id, creator=creator)
    if not project:
        return default_workspace_root(umo)
    return resolve_project_workspace_root(project, fallback_umo=umo)
