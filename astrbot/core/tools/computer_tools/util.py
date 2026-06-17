import re
from pathlib import Path

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.astr_agent_context import AstrAgentContext
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
