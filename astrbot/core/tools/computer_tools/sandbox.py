import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from astrbot.api import FunctionTool
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.computer import computer_client
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from ..registry import builtin_tool
from .util import check_admin_permission, check_strict_admin_permission

_SANDBOX_RUNTIME_TOOL_CONFIG = {
    "provider_settings.computer_use_runtime": "sandbox",
}


def _dump(data) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


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


def _visible_to_session(record: dict, session_id: str) -> bool:
    return record.get("controller_session_id") == session_id or _is_idle_sandbox(record)


def _is_idle_sandbox(record: dict) -> bool:
    return not bool(record.get("controller_session_id"))


def _sandbox_status_for_session(record: dict, session_id: str) -> str:
    controller_session_id = record.get("controller_session_id")
    if controller_session_id == session_id:
        return "current"
    if controller_session_id:
        return "occupied"
    return "idle"


def _redact_sandbox_for_session(record: dict, session_id: str, *, admin: bool) -> dict:
    if admin:
        return record
    visible = dict(record)
    visible["access"] = {
        "status": _sandbox_status_for_session(record, session_id),
        "can_switch": _visible_to_session(record, session_id),
        "occupied": bool(record.get("controller_session_id")),
    }
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


@builtin_tool(config=_SANDBOX_RUNTIME_TOOL_CONFIG)
@dataclass
class ListSandboxesTool(FunctionTool):
    name: str = "astrbot_list_sandboxes"
    description: str = "List all managed sandboxes. Use this before creating a new sandbox when you need to find a reusable or default sandbox."
    parameters: dict = field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )

    async def call(self, context: ContextWrapper[AstrAgentContext]) -> ToolExecResult:
        session_id = context.context.event.unified_msg_origin
        sandboxes = _sandbox_manager().list_sandboxes()
        sandboxes = [
            _redact_sandbox_for_session(record, session_id, admin=_is_admin(context))
            for record in sandboxes
        ]
        return _dump({"sandboxes": sandboxes})


@builtin_tool(config=_SANDBOX_RUNTIME_TOOL_CONFIG)
@dataclass
class ListSandboxProvidersTool(FunctionTool):
    name: str = "astrbot_list_sandbox_providers"
    description: str = (
        "List currently loaded sandbox providers and their capabilities. "
        "Use this before choosing a provider or creating a sandbox for a different runtime."
    )
    parameters: dict = field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )

    async def call(self, context: ContextWrapper[AstrAgentContext]) -> ToolExecResult:
        del context
        return _dump({"providers": computer_client.list_sandbox_providers()})


@builtin_tool(config=_SANDBOX_RUNTIME_TOOL_CONFIG)
@dataclass
class GetCurrentSandboxTool(FunctionTool):
    name: str = "astrbot_get_current_sandbox"
    description: str = "Get the current sandbox bound to this session. Use this before creating a new sandbox so you can reuse the current one when possible."
    parameters: dict = field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )

    async def call(self, context: ContextWrapper[AstrAgentContext]) -> ToolExecResult:
        session_id = context.context.event.unified_msg_origin
        return _dump(_sandbox_manager().get_current_sandbox(session_id))


@builtin_tool(config=_SANDBOX_RUNTIME_TOOL_CONFIG)
@dataclass
class CreateSandboxTool(FunctionTool):
    name: str = "astrbot_create_sandbox"
    description: str = (
        "Create a new managed sandbox for the current sandbox provider and switch the current session to it. "
        "This is a last resort: first check the current sandbox, then list sandboxes and prefer reusing the current sandbox, an idle default sandbox, or another reusable sandbox. "
        "Use this when the user explicitly wants a fresh sandbox or a separate environment, or when no existing sandbox can be reused safely. "
        "If you need a different runtime, list sandbox providers first and pass provider_id explicitly."
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "sandbox_name": {
                    "type": "string",
                    "description": "Optional human-readable sandbox name.",
                },
                "provider_id": {
                    "type": "string",
                    "description": (
                        "Optional sandbox provider ID. Defaults to the current active "
                        "provider if omitted."
                    ),
                },
            },
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        sandbox_name: str = "",
        provider_id: str = "",
    ) -> ToolExecResult:
        if permission_error := check_admin_permission(context, "Creating sandbox"):
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

        return _dump({"sandbox": sandbox})


@builtin_tool(config=_SANDBOX_RUNTIME_TOOL_CONFIG)
@dataclass
class SwitchSandboxTool(FunctionTool):
    name: str = "astrbot_switch_sandbox"
    description: str = "Switch this session to an existing running sandbox by sandbox_id. Use this after listing sandboxes when you want to reuse an existing sandbox instead of creating a new one."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "sandbox_id": {"type": "string", "description": "Target sandbox ID."}
            },
            "required": ["sandbox_id"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], sandbox_id: str
    ) -> ToolExecResult:
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
        return _dump({"sandbox": sandbox})


@builtin_tool(config=_SANDBOX_RUNTIME_TOOL_CONFIG)
@dataclass
class ReleaseSandboxTool(FunctionTool):
    name: str = "astrbot_release_sandbox"
    description: str = "End this session's control of the current sandbox or a specified sandbox so other sessions can reuse it. Use this when the task is done or the user asks to release the sandbox."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "sandbox_id": {
                    "type": "string",
                    "description": "Optional sandbox ID. Defaults to the current sandbox.",
                }
            },
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], sandbox_id: str = ""
    ) -> ToolExecResult:
        session_id = context.context.event.unified_msg_origin
        try:
            sandbox = _sandbox_manager().release_current_sandbox(
                session_id, sandbox_id.strip() or None
            )
        except Exception as e:
            detail = str(e) or type(e).__name__
            return f"Error releasing sandbox: {detail}"
        return _dump({"sandbox": sandbox})


@builtin_tool(config=_SANDBOX_RUNTIME_TOOL_CONFIG)
@dataclass
class KeepAliveSandboxTool(FunctionTool):
    name: str = "astrbot_keep_sandbox_alive"
    description: str = (
        "Extend this session's current sandbox occupancy. Use this before a long-running task so the sandbox is not released and reused by another session. "
        "Call astrbot_release_sandbox when the task is done."
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "ttl_seconds": {
                    "type": "number",
                    "description": "Optional lease duration in seconds. Defaults to the normal sandbox lease timeout.",
                }
            },
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        ttl_seconds: int | float | None = None,
    ) -> ToolExecResult:
        session_id = context.context.event.unified_msg_origin
        try:
            sandbox = await _sandbox_manager().renew_current_sandbox_lease(
                session_id, ttl_seconds=ttl_seconds
            )
        except Exception as e:
            detail = str(e) or type(e).__name__
            return f"Error keeping sandbox alive: {detail}"
        return _dump({"sandbox": sandbox})


@builtin_tool(config=_SANDBOX_RUNTIME_TOOL_CONFIG)
@dataclass
class TakeoverSandboxTool(FunctionTool):
    name: str = "astrbot_takeover_sandbox"
    description: str = "Force takeover of sandbox occupancy by sandbox_id. Admin only."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "sandbox_id": {"type": "string", "description": "Target sandbox ID."}
            },
            "required": ["sandbox_id"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], sandbox_id: str
    ) -> ToolExecResult:
        if permission_error := check_strict_admin_permission(
            context, "Taking over sandbox"
        ):
            return permission_error
        session_id = context.context.event.unified_msg_origin
        try:
            sandbox = await _sandbox_manager().takeover_sandbox(session_id, sandbox_id)
        except Exception as e:
            detail = str(e) or type(e).__name__
            return f"Error taking over sandbox: {detail}"
        return _dump({"sandbox": sandbox})


@builtin_tool(config=_SANDBOX_RUNTIME_TOOL_CONFIG)
@dataclass
class DestroySandboxTool(FunctionTool):
    name: str = "astrbot_destroy_sandbox"
    description: str = "Destroy a managed sandbox by sandbox_id. Admin only."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "sandbox_id": {"type": "string", "description": "Target sandbox ID."}
            },
            "required": ["sandbox_id"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], sandbox_id: str
    ) -> ToolExecResult:
        if permission_error := check_strict_admin_permission(
            context, "Destroying sandbox"
        ):
            return permission_error
        session_id = context.context.event.unified_msg_origin
        try:
            sandbox = await _sandbox_manager().destroy_sandbox(session_id, sandbox_id)
        except Exception as e:
            detail = str(e) or type(e).__name__
            return f"Error destroying sandbox: {detail}"
        return _dump({"sandbox": sandbox})


@builtin_tool(config=_SANDBOX_RUNTIME_TOOL_CONFIG)
@dataclass
class ScreenshotSandboxTool(FunctionTool):
    name: str = "astrbot_screenshot_sandbox"
    description: str = "Capture a screenshot from a specified sandbox and optionally send it to the user."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "sandbox_id": {"type": "string", "description": "Target sandbox ID."},
                "send_to_user": {
                    "type": "boolean",
                    "description": "Whether to send the screenshot image to the current conversation.",
                    "default": False,
                },
            },
            "required": ["sandbox_id"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        sandbox_id: str,
        send_to_user: bool = False,
    ) -> ToolExecResult:
        if permission_error := check_strict_admin_permission(
            context, "Sandbox screenshot capture"
        ):
            return permission_error
        try:
            booter = await _sandbox_manager().get_observer_booter_by_id(
                sandbox_id,
                context.context.event.unified_msg_origin,
                context=context.context.context,
            )
            gui = getattr(booter, "gui", None)
            if gui is None:
                return f"Error taking sandbox screenshot: sandbox {sandbox_id} does not support screenshots."
            screenshot_dir = Path(get_astrbot_temp_path()) / "sandbox_screenshots"
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            path = str(screenshot_dir / f"{uuid.uuid4().hex}.png")
            result = await gui.screenshot(path)
            payload = {"sandbox_id": sandbox_id, "path": path, **result}
            if send_to_user:
                await context.context.event.send(MessageChain().file_image(path))
                payload["sent_to_user"] = True
            return _dump(payload)
        except Exception as e:
            detail = str(e) or type(e).__name__
            return f"Error taking sandbox screenshot: {detail}"


@builtin_tool(config=_SANDBOX_RUNTIME_TOOL_CONFIG)
@dataclass
class CopyFileBetweenSandboxesTool(FunctionTool):
    name: str = "astrbot_copy_file_between_sandboxes"
    description: str = "Copy a file between two running sandboxes by downloading from the source and uploading to the target."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "source_sandbox_id": {
                    "type": "string",
                    "description": "Source sandbox ID.",
                },
                "source_path": {
                    "type": "string",
                    "description": "Path in source sandbox.",
                },
                "target_sandbox_id": {
                    "type": "string",
                    "description": "Target sandbox ID.",
                },
                "target_path": {
                    "type": "string",
                    "description": "Destination path in target sandbox.",
                },
            },
            "required": [
                "source_sandbox_id",
                "source_path",
                "target_sandbox_id",
                "target_path",
            ],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        source_sandbox_id: str,
        source_path: str,
        target_sandbox_id: str,
        target_path: str,
    ) -> ToolExecResult:
        if permission_error := check_strict_admin_permission(
            context, "Copying files between sandboxes"
        ):
            return permission_error
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
            local_path = temp_dir / f"{uuid.uuid4().hex}-{Path(target_path).name}"
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
