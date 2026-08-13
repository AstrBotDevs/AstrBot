import re
from pathlib import Path

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.auth.models import Resource
from astrbot.core.utils.astrbot_path import get_astrbot_workspaces_path


def normalize_umo_for_workspace(umo: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", umo.strip())
    return normalized or "unknown"


def workspace_root(umo: str) -> Path:
    """Root directory for relative paths in local runtime"""
    normalized_umo = normalize_umo_for_workspace(umo)
    return (Path(get_astrbot_workspaces_path()) / normalized_umo).resolve(strict=False)


def is_local_runtime(context: ContextWrapper[AstrAgentContext]) -> bool:
    cfg = context.context.context.get_config(
        umo=context.context.event.unified_msg_origin
    )
    provider_settings = cfg.get("provider_settings", {})
    runtime = str(provider_settings.get("computer_use_runtime", "local"))
    return runtime == "local"


async def check_admin_permission(
    context: ContextWrapper[AstrAgentContext], operation_name: str
) -> str | None:
    """Run the final action check immediately before a sensitive operation."""

    event = context.context.event
    action = {
        "Shell execution": "tool.local_exec",
        "Python execution": "tool.python_exec",
        "File upload/download": "tool.file_write",
        "Taking CUA screenshots": "tool.computer_use",
        "Using CUA mouse": "tool.computer_use",
        "Using CUA keyboard": "tool.computer_use",
        "Using browser tools": "tool.browser_control",
        "Using skill lifecycle tools": "extension.manage",
    }.get(operation_name, "tool.local_exec")
    authorization = getattr(context.context.context, "authorization", None)
    if (
        authorization is None
        or getattr(event, "subject", None) is None
        or getattr(event, "resource", None) is None
        or getattr(event, "auth_context", None) is None
    ):
        return "error: Permission denied. Authorization context is unavailable."
    decision = await authorization.authorize(
        event.subject,
        action,
        Resource.named("tool", operation_name, config_id=event.resource.config_id),
        event.auth_context,
    )
    if not decision.allowed:
        return (
            f"error: Permission denied. {operation_name} requires an authorized action. "
            f"User's ID is: {event.get_sender_id()}."
        )
    return None
