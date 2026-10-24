from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.computer.process_sandbox import get_process_sandbox_status
from astrbot.core.config.default import get_local_permission_defaults
from astrbot.core.db import BaseDatabase
from astrbot.core.utils.astrbot_path import get_astrbot_workspaces_path
from astrbot.core.workspace import (
    normalize_umo_for_workspace,
    resolve_workspace_root_for_umo,
)

LOCAL_NETWORK_POLICY_NOTICE = (
    "Sandbox policy: Network access is disabled for local Shell/Python execution. "
    "Do not retry the same network operation with another command, Python, "
    "HTTP/HTTPS, or disabled certificate verification; these do not change the policy. "
    "Local offline operations are still allowed."
)


@dataclass(frozen=True)
class LocalPermissionPolicy:
    """Resolved Local computer permissions for one caller.

    Args:
        allow_execution: Whether Shell and Python execution is allowed.
        allow_network: Whether the execution environment may use the network.
        filesystem_scope: Host or workspace access, or none to disable Local tools.
        execution_disabled_reason: Isolation failure that disabled execution, if any.
    """

    allow_execution: bool
    allow_network: bool
    filesystem_scope: Literal["none", "workspace", "host"]
    execution_disabled_reason: str | None = None

    @property
    def requires_sandbox(self) -> bool:
        """Return whether execution needs operating-system isolation."""
        return self.allow_execution and (
            not self.allow_network or self.filesystem_scope != "host"
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


def format_exception_message(exc: BaseException) -> str:
    message = str(exc).strip()
    return message or exc.__class__.__name__


def is_local_runtime(context: ContextWrapper[AstrAgentContext]) -> bool:
    cfg = context.context.context.get_config(
        umo=context.context.event.unified_msg_origin
    )
    provider_settings = cfg.get("provider_settings", {})
    runtime = str(provider_settings.get("computer_use_runtime", "none"))
    return runtime == "local"


def get_local_permission_policy(
    context: ContextWrapper[AstrAgentContext],
    *,
    role: Literal["member", "admin"] | None = None,
) -> LocalPermissionPolicy:
    """Resolve the Local permission policy for the caller's role.

    Args:
        context: Tool call context.
        role: Role policy to inspect, or None to use the caller's role.

    Returns:
        Normalized policy. If required isolation is unavailable, execution is
        disabled without widening file access or changing the saved policy.
        Unknown roles use the member policy.
    """
    cfg = context.context.context.get_config(
        umo=context.context.event.unified_msg_origin
    )
    provider_settings = cfg.get("provider_settings", {})
    role = "admin" if (role or context.context.event.role) == "admin" else "member"
    defaults = get_local_permission_defaults()[role]

    permissions = provider_settings.get("computer_use_local_permissions")
    role_policy = permissions.get(role) if isinstance(permissions, dict) else None
    if not isinstance(role_policy, dict):
        role_policy = {}
        if role == "member" and not isinstance(permissions, dict):
            defaults["allow_execution"] = not provider_settings.get(
                "computer_use_require_admin",
                True,
            )

    filesystem_scope = role_policy.get("filesystem_scope", defaults["filesystem_scope"])
    if filesystem_scope not in {"none", "workspace", "host"}:
        filesystem_scope = defaults["filesystem_scope"]
    allow_execution = (
        filesystem_scope != "none"
        and role_policy.get("allow_execution", defaults["allow_execution"]) is True
    )
    allow_network = (
        allow_execution
        and role_policy.get("allow_network", defaults["allow_network"]) is True
    )
    policy = LocalPermissionPolicy(
        allow_execution=allow_execution,
        allow_network=allow_network,
        filesystem_scope=filesystem_scope,
    )
    if (
        provider_settings.get("computer_use_runtime") == "local"
        and policy.requires_sandbox
    ):
        sandbox = get_process_sandbox_status()
        if sandbox["status"] != "detected":
            backend = sandbox.get("backend") or "Local process isolation"
            reason = {
                "missing": f"{backend} is not installed",
                "unsupported": "Local process isolation is not supported on this platform",
                "unavailable": f"{backend} failed its startup probe",
            }.get(sandbox["status"], "Local process isolation is unavailable")
            if sandbox.get("error"):
                reason += f": {sandbox['error']}"
            if sandbox["status"] == "unsupported":
                recovery = "Run AstrBot in an environment that supports Local process isolation."
            elif sandbox["status"] == "missing" and backend == "bubblewrap":
                recovery = (
                    "Install bubblewrap on the AstrBot host, then restart AstrBot."
                )
            elif backend == "seatbelt":
                recovery = (
                    "Restore macOS Seatbelt (`sandbox-exec`) availability, "
                    "then restart AstrBot."
                )
            else:
                recovery = f"Fix the {backend} startup failure shown above, then restart AstrBot."
            permission_changes = []
            if policy.filesystem_scope != "host":
                permission_changes.append(
                    "set file access scope to `Entire environment`"
                )
            if not policy.allow_network:
                permission_changes.append(
                    "turn `Execute code` off and on again "
                    "(this also enables execution network access)"
                )
            return LocalPermissionPolicy(
                allow_execution=False,
                allow_network=False,
                filesystem_scope=policy.filesystem_scope,
                execution_disabled_reason=(
                    "The Agent Computer Use runtime is the local environment (`local`). "
                    f"The current user role is `{role}`; its configured Local permission "
                    "policy is: code execution enabled, execution network access "
                    f"{'enabled' if policy.allow_network else 'disabled'}, "
                    f"file access scope `{policy.filesystem_scope}`. "
                    "These restrictions require Local process isolation, "
                    f"but {reason}. Code execution is blocked. "
                    "Ask an AstrBot administrator to choose:\n"
                    f"1. Keep the configured restrictions: {recovery}\n"
                    "2. Allow execution without Local isolation: "
                    f"{' and '.join(permission_changes)} for this role in AstrBot "
                    "WebUI -> Config -> AI -> Capabilities -> Agent Computer Use -> "
                    "Local Permission Policies. (Warning: this permits code execution "
                    "with access to the entire environment and network, without isolation)."
                ),
            )
    return policy


def check_local_file_permission(
    context: ContextWrapper[AstrAgentContext],
) -> str | None:
    """Reject file tools when Local access is disabled for the caller's role.

    Args:
        context: Tool call context.

    Returns:
        A permission error, or None when the file tool may proceed.
    """
    if (
        is_local_runtime(context)
        and get_local_permission_policy(context).filesystem_scope == "none"
    ):
        return (
            "error: Permission denied. Local computer tools are disabled for this "
            "user role. Enable Local computer access for this role in AstrBot "
            "WebUI -> Config -> AI -> Capabilities -> Agent Computer Use -> "
            "Local Permission Policies."
        )
    return None


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
            "Tell user to add their user ID under `AstrBot WebUI -> Config -> "
            "Access Control -> Administrators -> Administrator IDs` in the "
            "profile used by this bot if they need this feature. "
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
        if policy.execution_disabled_reason:
            return policy, (
                f"error: Local isolation unavailable. {operation_name} was blocked. "
                f"{policy.execution_disabled_reason}"
            )
        if policy.filesystem_scope == "none":
            return policy, check_local_file_permission(context)
        role = "admin" if context.context.event.role == "admin" else "member"
        policy_location = (
            "AstrBot WebUI -> Config -> AI -> Capabilities -> "
            "Agent Computer Use -> Local Permission Policies"
        )
        instructions = (
            "Ask an AstrBot administrator to enable "
            f"`Execute code` for this role in {policy_location}."
        )
        if (
            role != "admin"
            and get_local_permission_policy(context, role="admin").allow_execution
        ):
            sender_id = context.context.event.get_sender_id()
            identity = (
                f" (the user id is: `{sender_id}`)"
                if sender_id
                else " (obtain the ID with /sid)"
            )
            instructions = (
                "Ask an AstrBot administrator to either:\n"
                f"1. Add this user's ID{identity} under AstrBot WebUI -> Config -> "
                "Access Control -> Administrators -> Administrator IDs.\n"
                f"2. Enable `Execute code` for members in {policy_location}."
            )
        return policy, (
            f"error: Permission denied. {operation_name} is disabled by the "
            f"Local permission policy for this user role ({role}). {instructions}"
        )
    return policy, None
