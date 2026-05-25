from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.astr_agent_context import AstrAgentContext


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
