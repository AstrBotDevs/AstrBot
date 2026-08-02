import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.db import BaseDatabase
from astrbot.core.utils.astrbot_path import get_astrbot_workspaces_path
from astrbot.core.workspace import (
    normalize_umo_for_workspace,
    resolve_workspace_root_for_umo,
)


@dataclass(frozen=True)
class LocalPermissionPolicy:
    """Resolved Local computer permissions for one caller.

    Args:
        allow_execution: Whether Shell and Python execution is allowed.
        allow_network: Whether the execution environment may use the network.
        filesystem_scope: Whether Local tools may access the host or workspace only.
    """

    allow_execution: bool
    allow_network: bool
    filesystem_scope: Literal["workspace", "host"]

    @property
    def requires_sandbox(self) -> bool:
        """Return whether execution needs operating-system isolation."""
        return not self.allow_network or self.filesystem_scope != "host"


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


def get_local_permission_policy(
    context: ContextWrapper[AstrAgentContext],
) -> LocalPermissionPolicy:
    """Resolve the Local permission policy for the caller's role.

    Args:
        context: Tool call context.

    Returns:
        Normalized policy. Unknown roles use the member policy.
    """
    cfg = context.context.context.get_config(
        umo=context.context.event.unified_msg_origin
    )
    provider_settings = cfg.get("provider_settings", {})
    role = "admin" if context.context.event.role == "admin" else "member"
    default_execution = role == "admin"
    default_network = role == "admin"
    default_filesystem = "host" if role == "admin" else "workspace"

    permissions = provider_settings.get("computer_use_local_permissions")
    role_policy = permissions.get(role) if isinstance(permissions, dict) else None
    if not isinstance(role_policy, dict):
        role_policy = {}
        if role == "member" and not isinstance(permissions, dict):
            default_execution = not provider_settings.get(
                "computer_use_require_admin",
                True,
            )

    allow_execution = role_policy.get("allow_execution", default_execution) is True
    allow_network = (
        allow_execution and role_policy.get("allow_network", default_network) is True
    )
    filesystem_scope = role_policy.get("filesystem_scope", default_filesystem)
    if filesystem_scope not in {"workspace", "host"}:
        filesystem_scope = default_filesystem
    return LocalPermissionPolicy(
        allow_execution=allow_execution,
        allow_network=allow_network,
        filesystem_scope=filesystem_scope,
    )


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


def check_local_execution_permission(
    context: ContextWrapper[AstrAgentContext],
    operation_name: str,
) -> tuple[LocalPermissionPolicy | None, str | None]:
    """Resolve whether an execution tool needs an operating-system sandbox.

    Args:
        context: Tool call context.
        operation_name: User-facing name included in permission errors.

    Returns:
        Resolved Local policy and an optional error. Non-Local runtimes return
        no policy because their existing administrator gate is unchanged.
    """
    if not is_local_runtime(context):
        return None, check_admin_permission(context, operation_name)
    policy = get_local_permission_policy(context)
    if not policy.allow_execution:
        return policy, (
            f"error: Permission denied. {operation_name} is disabled by the "
            "Local permission policy for this user role."
        )
    if policy.requires_sandbox and not (
        sys.platform.startswith("linux") or sys.platform == "darwin"
    ):
        return policy, (
            "error: Permission denied. Restricted Local execution is only supported "
            "on Linux with bubblewrap or macOS with Seatbelt."
        )
    return policy, None
