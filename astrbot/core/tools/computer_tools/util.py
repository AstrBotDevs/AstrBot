from pathlib import Path

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.db import BaseDatabase
from astrbot.core.utils.astrbot_path import get_astrbot_workspaces_path
from astrbot.core.workspace import (
    normalize_umo_for_workspace,
    resolve_workspace_root_for_umo,
)


def workspace_root(umo: str) -> Path:
    """Return the legacy workspace root for compatibility.

    Args:
        umo: Unified message origin.

    Returns:
        Legacy per-session workspace root.
    """
    return (
        Path(get_astrbot_workspaces_path()) / normalize_umo_for_workspace(umo)
    ).resolve(strict=False)


async def workspace_root_for_context(
    context: ContextWrapper[AstrAgentContext],
) -> Path:
    """Resolve the workspace root for a tool call context.

    Args:
        context: Tool call context.

    Returns:
        Workspace root used as cwd.
    """
    umo = context.context.event.unified_msg_origin
    db = getattr(context.context.context, "_db", None)
    if not isinstance(db, BaseDatabase):
        return workspace_root(umo)
    try:
        return await resolve_workspace_root_for_umo(umo, db)
    except Exception:
        return workspace_root(umo)


def is_local_runtime(context: ContextWrapper[AstrAgentContext]) -> bool:
    cfg = context.context.context.get_config(
        umo=context.context.event.unified_msg_origin
    )
    provider_settings = cfg.get("provider_settings", {})
    runtime = str(provider_settings.get("computer_use_runtime", "local"))
    return runtime == "local"


def check_admin_permission(
    context: ContextWrapper[AstrAgentContext], operation_name: str
) -> str | None:
    cfg = context.context.context.get_config(
        umo=context.context.event.unified_msg_origin
    )
    provider_settings = cfg.get("provider_settings", {})
    require_admin = provider_settings.get("computer_use_require_admin", True)
    if require_admin and context.context.event.role != "admin":
        return (
            f"error: Permission denied. {operation_name} is only allowed for admin users. "
            "Tell user to set admins in `AstrBot WebUI -> Config -> General Config` by adding their user ID to the admins list if they need this feature. "
            f"User's ID is: {context.context.event.get_sender_id()}. User's ID can be found by using /sid command."
        )
    return None
