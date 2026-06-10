import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import mcp

from astrbot.api import FunctionTool
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.computer import computer_client
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from ..registry import builtin_tool
from .util import check_admin_permission

_SANDBOX_RUNTIME_TOOL_CONFIG = {
    "provider_settings.computer_use_runtime": "sandbox",
}


def _dump(data) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _remote_basename(path: str) -> str:
    return path.replace("\\", "/").rstrip("/").split("/")[-1]


def _format_agent_time(value: int | float | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return str(value)
    if not isinstance(value, (int, float)):
        return str(value)
    return (
        datetime.fromtimestamp(float(value))
        .astimezone()
        .strftime("%Y-%m-%d %H:%M:%S %Z")
    )


def _format_sandbox_for_agent(value):
    if isinstance(value, list):
        return [_format_sandbox_for_agent(item) for item in value]
    if not isinstance(value, dict):
        return value
    formatted = {}
    for key, item in value.items():
        if key.endswith("_at"):
            formatted[key] = _format_agent_time(item)
        else:
            formatted[key] = _format_sandbox_for_agent(item)
    return formatted


def _sandbox_manager():
    return computer_client.sandbox_manager


def _current_provider_id(context: ContextWrapper[AstrAgentContext]) -> str:
    plugin_context = context.context.context
    session_id = context.context.event.unified_msg_origin
    config = plugin_context.get_config(umo=session_id)
    sandbox_cfg = config.get("provider_settings", {}).get("sandbox", {})
    return str(sandbox_cfg.get("booter", "")).strip()


def _is_admin(context: ContextWrapper[AstrAgentContext]) -> bool:
    return context.context.event.role == "admin"


def _sandbox_config(context: ContextWrapper[AstrAgentContext]) -> dict:
    config = context.context.context.get_config(
        umo=context.context.event.unified_msg_origin
    )
    sandbox_cfg = config.get("provider_settings", {}).get("sandbox", {})
    return sandbox_cfg if isinstance(sandbox_cfg, dict) else {}


def _member_sandbox_permission_enabled(
    context: ContextWrapper[AstrAgentContext], permission: str
) -> bool:
    permissions = _sandbox_config(context).get("member_permissions", {})
    if not isinstance(permissions, dict):
        return False
    return bool(permissions.get(permission, False))


def _check_basic_sandbox_permission(
    context: ContextWrapper[AstrAgentContext], operation_name: str
) -> str | None:
    return check_admin_permission(context, operation_name)


def _check_member_sandbox_permission(
    context: ContextWrapper[AstrAgentContext], operation_name: str, permission: str
) -> str | None:
    if permission_error := check_admin_permission(context, operation_name):
        return permission_error
    if _is_admin(context) or _member_sandbox_permission_enabled(context, permission):
        return None
    return (
        f"error: Permission denied. {operation_name} is disabled for non-admin users "
        "by sandbox member permission settings."
    )


def _visible_to_session(record: dict, session_id: str) -> bool:
    return record.get("controller_session_id") == session_id or _is_idle_sandbox(record)


def _is_idle_sandbox(record: dict) -> bool:
    controller_session_id = record.get("controller_session_id")
    if not controller_session_id:
        return True
    lease_expires_at = record.get("lease_expires_at")
    return bool(lease_expires_at and lease_expires_at <= time.time())


def _sandbox_status_for_session(record: dict, session_id: str) -> str:
    controller_session_id = record.get("controller_session_id")
    if controller_session_id == session_id:
        return "current"
    if controller_session_id and not _is_idle_sandbox(record):
        return "occupied"
    return "idle"


def _redact_sandbox_for_session(record: dict, session_id: str, *, admin: bool) -> dict:
    visible = dict(record)
    visible["access"] = {
        "status": _sandbox_status_for_session(record, session_id),
        "can_switch": _visible_to_session(record, session_id),
        "occupied": not _is_idle_sandbox(record),
    }
    if admin:
        return visible
    visible.pop("connect_info", None)
    visible["owner_session_id"] = None
    visible["owner_user_id"] = None
    visible["created_by_session_id"] = None
    visible["created_by_user_id"] = None
    if record.get("controller_session_id") != session_id:
        visible["controller_session_id"] = None
        visible["controller_user_id"] = None
    return visible


def _sandbox_access_denied(
    context: ContextWrapper[AstrAgentContext], record: dict | None
) -> str | None:
    if record is None or _is_admin(context):
        return None
    session_id = context.context.event.unified_msg_origin
    if _visible_to_session(record, session_id):
        return None
    return "error: Permission denied. This sandbox belongs to another session."


async def _query_list_sandboxes(
    context: ContextWrapper[AstrAgentContext],
) -> ToolExecResult:
    if permission_error := _check_basic_sandbox_permission(
        context, "Listing sandboxes"
    ):
        return permission_error
    session_id = context.context.event.unified_msg_origin
    manager = _sandbox_manager()
    list_checked = getattr(manager, "list_sandboxes_checked", None)
    if callable(list_checked):
        sandboxes = await list_checked()
    else:
        sandboxes = manager.list_sandboxes()
    sandboxes = [
        _redact_sandbox_for_session(record, session_id, admin=_is_admin(context))
        for record in sandboxes
    ]
    return _dump({"sandboxes": _format_sandbox_for_agent(sandboxes)})


async def _query_list_providers(
    context: ContextWrapper[AstrAgentContext],
) -> ToolExecResult:
    if permission_error := _check_basic_sandbox_permission(
        context, "Listing sandbox providers"
    ):
        return permission_error
    return _dump({"providers": computer_client.list_sandbox_providers()})


async def _query_get_current(
    context: ContextWrapper[AstrAgentContext],
) -> ToolExecResult:
    if permission_error := _check_basic_sandbox_permission(
        context, "Getting current sandbox"
    ):
        return permission_error
    session_id = context.context.event.unified_msg_origin
    return _dump(
        _format_sandbox_for_agent(_sandbox_manager().get_current_sandbox(session_id))
    )


async def _lifecycle_create(
    context: ContextWrapper[AstrAgentContext],
    sandbox_name: str = "",
    provider_id: str = "",
) -> ToolExecResult:
    if permission_error := _check_member_sandbox_permission(
        context, "Creating sandbox", "create"
    ):
        return permission_error

    plugin_context = context.context.context
    session_id = context.context.event.unified_msg_origin
    requested_provider_id = str(provider_id).strip().lower()
    if requested_provider_id:
        provider_id = requested_provider_id
    else:
        provider_id = _current_provider_id(context)
    if not provider_id:
        return "Error creating sandbox: sandbox booter is not configured."
    manager = _sandbox_manager()
    if provider_id not in manager.providers:
        providers = computer_client.list_sandbox_providers()
        available = ", ".join(p["provider_id"] for p in providers) or "none"
        return (
            f"Error creating sandbox: sandbox provider '{provider_id}' is not "
            f"available. Available providers: {available}."
        )

    try:
        sandbox = await manager.create_sandbox(
            plugin_context,
            session_id,
            provider_id,
            sandbox_name=sandbox_name.strip() or None,
        )
    except Exception as e:
        detail = str(e) or type(e).__name__
        return f"Error creating sandbox: {detail}"

    return _dump({"sandbox": _format_sandbox_for_agent(sandbox)})


async def _lifecycle_switch(
    context: ContextWrapper[AstrAgentContext], sandbox_id: str = ""
) -> ToolExecResult:
    if permission_error := _check_basic_sandbox_permission(
        context, "Switching sandbox"
    ):
        return permission_error
    if not sandbox_id:
        return "Error switching sandbox: sandbox_id is required."
    session_id = context.context.event.unified_msg_origin
    manager = _sandbox_manager()
    record = manager.registry.get_sandbox(sandbox_id)
    if permission_error := _sandbox_access_denied(context, record):
        return permission_error
    try:
        sandbox = await manager.switch_current_sandbox_checked(
            session_id, sandbox_id, context=context.context.context
        )
    except Exception as e:
        detail = str(e) or type(e).__name__
        return f"Error switching sandbox: {detail}"
    return _dump({"sandbox": _format_sandbox_for_agent(sandbox)})


async def _lifecycle_release(
    context: ContextWrapper[AstrAgentContext], sandbox_id: str = ""
) -> ToolExecResult:
    if permission_error := _check_basic_sandbox_permission(
        context, "Releasing sandbox"
    ):
        return permission_error
    session_id = context.context.event.unified_msg_origin
    try:
        sandbox = _sandbox_manager().release_current_sandbox(
            session_id, sandbox_id.strip() or None
        )
    except Exception as e:
        detail = str(e) or type(e).__name__
        return f"Error releasing sandbox: {detail}"
    return _dump({"sandbox": _format_sandbox_for_agent(sandbox)})


async def _lifecycle_set_retention(
    context: ContextWrapper[AstrAgentContext],
    retention_policy: str = "",
    sandbox_id: str = "",
    sandbox_name: str = "",
) -> ToolExecResult:
    if permission_error := _check_member_sandbox_permission(
        context, "Changing sandbox retention policy", "set_retention_policy"
    ):
        return permission_error
    if not retention_policy:
        return "Error changing sandbox retention policy: retention_policy is required."
    manager = _sandbox_manager()
    session_id = context.context.event.unified_msg_origin
    target_sandbox_id = sandbox_id.strip()
    if not target_sandbox_id:
        current = manager.get_current_sandbox(session_id)
        target_sandbox_id = current.get("current_sandbox_id") or ""
    if not target_sandbox_id:
        return "Error changing sandbox retention policy: No current sandbox"
    record = manager.registry.get_sandbox(target_sandbox_id)
    if permission_error := _sandbox_access_denied(context, record):
        return permission_error
    try:
        sandbox = manager.set_sandbox_retention_policy(
            context.context.context,
            session_id,
            target_sandbox_id,
            retention_policy.strip().lower(),
            sandbox_name=sandbox_name.strip() or None,
        )
    except Exception as e:
        detail = str(e) or type(e).__name__
        return f"Error changing sandbox retention policy: {detail}"
    return _dump({"sandbox": _format_sandbox_for_agent(sandbox)})


async def _lifecycle_renew_lease(
    context: ContextWrapper[AstrAgentContext],
    ttl_seconds: int | float | None = None,
) -> ToolExecResult:
    if permission_error := _check_basic_sandbox_permission(
        context, "Renewing sandbox lease"
    ):
        return permission_error
    session_id = context.context.event.unified_msg_origin
    try:
        sandbox = await _sandbox_manager().renew_current_sandbox_lease(
            session_id, ttl_seconds=ttl_seconds, context=context.context.context
        )
    except Exception as e:
        detail = str(e) or type(e).__name__
        return f"Error renewing sandbox lease: {detail}"
    return _dump({"sandbox": _format_sandbox_for_agent(sandbox)})


async def _lifecycle_takeover(
    context: ContextWrapper[AstrAgentContext], sandbox_id: str = ""
) -> ToolExecResult:
    if permission_error := _check_member_sandbox_permission(
        context, "Taking over sandbox", "takeover"
    ):
        return permission_error
    if not sandbox_id:
        return "Error taking over sandbox: sandbox_id is required."
    session_id = context.context.event.unified_msg_origin
    try:
        sandbox = await _sandbox_manager().takeover_sandbox(
            session_id, sandbox_id, context=context.context.context
        )
    except Exception as e:
        detail = str(e) or type(e).__name__
        return f"Error taking over sandbox: {detail}"
    return _dump({"sandbox": _format_sandbox_for_agent(sandbox)})


async def _lifecycle_destroy(
    context: ContextWrapper[AstrAgentContext], sandbox_id: str = ""
) -> ToolExecResult:
    if permission_error := _check_member_sandbox_permission(
        context, "Destroying sandbox", "destroy"
    ):
        return permission_error
    if not sandbox_id:
        return "Error destroying sandbox: sandbox_id is required."
    session_id = context.context.event.unified_msg_origin
    try:
        sandbox = await _sandbox_manager().destroy_sandbox(session_id, sandbox_id)
    except Exception as e:
        detail = str(e) or type(e).__name__
        return f"Error destroying sandbox: {detail}"
    return _dump({"sandbox": _format_sandbox_for_agent(sandbox)})


def _current_sandbox_id_for_operation(
    context: ContextWrapper[AstrAgentContext], sandbox_id: str = ""
) -> str:
    target_sandbox_id = sandbox_id.strip()
    if target_sandbox_id:
        return target_sandbox_id
    current = _sandbox_manager().get_current_sandbox(
        context.context.event.unified_msg_origin
    )
    return str(current.get("current_sandbox_id") or "").strip()


async def _operation_capture_screenshot(
    context: ContextWrapper[AstrAgentContext],
    sandbox_id: str = "",
    send_to_user: bool = False,
    return_image_to_llm: bool = False,
) -> ToolExecResult:
    if permission_error := _check_basic_sandbox_permission(
        context, "Sandbox screenshot capture"
    ):
        return permission_error
    target_sandbox_id = _current_sandbox_id_for_operation(context, sandbox_id)
    if not target_sandbox_id:
        return "Error taking sandbox screenshot: No current sandbox"
    try:
        booter = await _sandbox_manager().get_observer_booter_by_id(
            target_sandbox_id,
            context.context.event.unified_msg_origin,
            context=context.context.context,
        )
        gui = getattr(booter, "gui", None)
        if gui is None:
            return f"Error taking sandbox screenshot: sandbox {target_sandbox_id} does not support screenshots."
        screenshot_dir = Path(get_astrbot_temp_path()) / "sandbox_screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        path = str(screenshot_dir / f"{uuid.uuid4().hex}.png")
        result = await gui.screenshot(path)
        payload = {"sandbox_id": target_sandbox_id, "path": path, **result}
        if send_to_user:
            await context.context.event.send(MessageChain().file_image(path))
            payload["sent_to_user"] = True
        image_data = payload.pop("base64", "")
        if return_image_to_llm:
            content: list[mcp.types.TextContent | mcp.types.ImageContent] = [
                mcp.types.TextContent(type="text", text=_dump(payload))
            ]
            if image_data:
                content.append(
                    mcp.types.ImageContent(
                        type="image",
                        data=str(image_data),
                        mimeType=str(payload.get("mime_type", "image/png")),
                    )
                )
            return mcp.types.CallToolResult(content=content)
        if image_data:
            payload["base64"] = image_data
        return _dump(payload)
    except Exception as e:
        detail = str(e) or type(e).__name__
        return f"Error taking sandbox screenshot: {detail}"


async def _operation_copy_file(
    context: ContextWrapper[AstrAgentContext],
    source_sandbox_id: str = "",
    source_path: str = "",
    target_sandbox_id: str = "",
    target_path: str = "",
) -> ToolExecResult:
    if permission_error := _check_basic_sandbox_permission(
        context, "Copying files between sandboxes"
    ):
        return permission_error
    if not all([source_sandbox_id, source_path, target_sandbox_id, target_path]):
        return "Error copying file between sandboxes: source_sandbox_id, source_path, target_sandbox_id, and target_path are required."
    try:
        manager = _sandbox_manager()
        session_id = context.context.event.unified_msg_origin
        source = await manager.get_observer_booter_by_id(
            source_sandbox_id, session_id, context=context.context.context
        )
        target = await manager.get_observer_booter_by_id(
            target_sandbox_id, session_id, context=context.context.context
        )
        temp_dir = Path(get_astrbot_temp_path()) / "sandbox_copy"
        temp_dir.mkdir(parents=True, exist_ok=True)
        local_path = temp_dir / f"{uuid.uuid4().hex}-{_remote_basename(target_path)}"
        try:
            await source.download_file(source_path, str(local_path))
            upload_result = await target.upload_file(str(local_path), target_path)
        finally:
            try:
                local_path.unlink(missing_ok=True)
            except OSError:
                pass
        return _dump(
            {
                "source_sandbox_id": source_sandbox_id,
                "source_path": source_path,
                "target_sandbox_id": target_sandbox_id,
                "target_path": target_path,
                "upload_result": upload_result,
            }
        )
    except Exception as e:
        detail = str(e) or type(e).__name__
        return f"Error copying file between sandboxes: {detail}"


@builtin_tool(config=_SANDBOX_RUNTIME_TOOL_CONFIG)
@dataclass
class SandboxQueryTool(FunctionTool):
    name: str = "astrbot_sandbox_query"
    description: str = (
        "Query managed sandboxes, the current sandbox, or loaded sandbox providers. "
        "Actions: list_sandboxes has no extra parameters; get_current has no extra parameters; "
        "list_providers has no extra parameters. Use list_sandboxes before creating a new sandbox "
        "when you need to find a reusable one."
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list_sandboxes", "get_current", "list_providers"],
                    "description": "Query action to perform.",
                }
            },
            "required": ["action"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], action: str
    ) -> ToolExecResult:
        match action:
            case "list_sandboxes":
                return await _query_list_sandboxes(context)
            case "get_current":
                return await _query_get_current(context)
            case "list_providers":
                return await _query_list_providers(context)
        return f"Error querying sandbox: unsupported action '{action}'."


@builtin_tool(config=_SANDBOX_RUNTIME_TOOL_CONFIG)
@dataclass
class SandboxLifecycleTool(FunctionTool):
    name: str = "astrbot_sandbox_lifecycle"
    description: str = (
        "Manage sandbox lifecycle and session occupancy: create, switch, release, "
        "renew lease, set retention, takeover, or destroy a sandbox. "
        "Actions: create accepts sandbox_name and provider_id; switch requires sandbox_id; "
        "release accepts optional sandbox_id; renew_lease accepts ttl_seconds; "
        "set_retention requires retention_policy and accepts sandbox_id/sandbox_name; "
        "takeover requires sandbox_id; destroy requires sandbox_id."
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "create",
                        "switch",
                        "release",
                        "renew_lease",
                        "set_retention",
                        "takeover",
                        "destroy",
                    ],
                    "description": "Lifecycle action to perform.",
                },
                "sandbox_id": {
                    "type": "string",
                    "description": "Target sandbox ID for switch, release, retention, takeover, or destroy.",
                },
                "sandbox_name": {
                    "type": "string",
                    "description": "Optional sandbox name for create or set_retention.",
                },
                "provider_id": {
                    "type": "string",
                    "description": "Optional provider ID for create. Defaults to configured sandbox booter.",
                },
                "retention_policy": {
                    "type": "string",
                    "enum": ["persistent", "temporary"],
                    "description": "Target retention policy for set_retention.",
                },
                "ttl_seconds": {
                    "type": "number",
                    "description": "Optional lease duration for renew_lease.",
                },
            },
            "required": ["action"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        action: str,
        sandbox_id: str = "",
        sandbox_name: str = "",
        provider_id: str = "",
        retention_policy: str = "",
        ttl_seconds: int | float | None = None,
    ) -> ToolExecResult:
        match action:
            case "create":
                return await _lifecycle_create(context, sandbox_name, provider_id)
            case "switch":
                return await _lifecycle_switch(context, sandbox_id)
            case "release":
                return await _lifecycle_release(context, sandbox_id)
            case "renew_lease":
                return await _lifecycle_renew_lease(context, ttl_seconds)
            case "set_retention":
                return await _lifecycle_set_retention(
                    context, retention_policy, sandbox_id, sandbox_name
                )
            case "takeover":
                return await _lifecycle_takeover(context, sandbox_id)
            case "destroy":
                return await _lifecycle_destroy(context, sandbox_id)
        return f"Error managing sandbox lifecycle: unsupported action '{action}'."


@builtin_tool(config=_SANDBOX_RUNTIME_TOOL_CONFIG)
@dataclass
class SandboxOperationTool(FunctionTool):
    name: str = "astrbot_sandbox_operation"
    description: str = (
        "Run standard sandbox operations. Actions: capture_screenshot accepts sandbox_id, "
        "send_to_user, and return_image_to_llm; copy_file requires source_sandbox_id, "
        "source_path, target_sandbox_id, and target_path."
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["capture_screenshot", "copy_file"],
                    "description": "Sandbox operation to perform.",
                },
                "sandbox_id": {
                    "type": "string",
                    "description": "Target sandbox ID for capture_screenshot. Defaults to current sandbox.",
                },
                "send_to_user": {
                    "type": "boolean",
                    "description": "Whether capture_screenshot should send the image to the current conversation.",
                    "default": False,
                },
                "return_image_to_llm": {
                    "type": "boolean",
                    "description": "Whether capture_screenshot should include image content in the tool result for model inspection.",
                    "default": False,
                },
                "source_sandbox_id": {
                    "type": "string",
                    "description": "Source sandbox ID for copy_file.",
                },
                "source_path": {
                    "type": "string",
                    "description": "Source path for copy_file.",
                },
                "target_sandbox_id": {
                    "type": "string",
                    "description": "Target sandbox ID for copy_file.",
                },
                "target_path": {
                    "type": "string",
                    "description": "Target path for copy_file.",
                },
            },
            "required": ["action"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        action: str,
        sandbox_id: str = "",
        send_to_user: bool = False,
        return_image_to_llm: bool = False,
        source_sandbox_id: str = "",
        source_path: str = "",
        target_sandbox_id: str = "",
        target_path: str = "",
    ) -> ToolExecResult:
        match action:
            case "capture_screenshot":
                return await _operation_capture_screenshot(
                    context, sandbox_id, send_to_user, return_image_to_llm
                )
            case "copy_file":
                return await _operation_copy_file(
                    context,
                    source_sandbox_id,
                    source_path,
                    target_sandbox_id,
                    target_path,
                )
        return f"Error running sandbox operation: unsupported action '{action}'."
