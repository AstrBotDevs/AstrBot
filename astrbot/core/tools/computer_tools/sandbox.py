import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from astrbot.api import FunctionTool
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.computer.computer_client import sandbox_manager
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from ..registry import builtin_tool
from .util import check_admin_permission

_SANDBOX_RUNTIME_TOOL_CONFIG = {
    "provider_settings.computer_use_runtime": "sandbox",
}


def _dump(data) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _current_provider_id(context: ContextWrapper[AstrAgentContext]) -> str:
    plugin_context = context.context.context
    session_id = context.context.event.unified_msg_origin
    config = plugin_context.get_config(umo=session_id)
    sandbox_cfg = config.get("provider_settings", {}).get("sandbox", {})
    return str(sandbox_cfg.get("booter", "")).strip()


@builtin_tool(config=_SANDBOX_RUNTIME_TOOL_CONFIG)
@dataclass
class ListSandboxesTool(FunctionTool):
    name: str = "astrbot_list_sandboxes"
    description: str = "List all managed sandboxes."
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {}})

    async def call(self, context: ContextWrapper[AstrAgentContext]) -> ToolExecResult:
        del context
        return _dump({"sandboxes": sandbox_manager.list_sandboxes()})


@builtin_tool(config=_SANDBOX_RUNTIME_TOOL_CONFIG)
@dataclass
class GetCurrentSandboxTool(FunctionTool):
    name: str = "astrbot_get_current_sandbox"
    description: str = "Get the current sandbox bound to this session."
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {}})

    async def call(self, context: ContextWrapper[AstrAgentContext]) -> ToolExecResult:
        session_id = context.context.event.unified_msg_origin
        return _dump(sandbox_manager.get_current_sandbox(session_id))


@builtin_tool(config=_SANDBOX_RUNTIME_TOOL_CONFIG)
@dataclass
class CreateSandboxTool(FunctionTool):
    name: str = "astrbot_create_sandbox"
    description: str = (
        "Create a new managed sandbox for the current sandbox provider and switch the current session to it. "
        "Use this when the user explicitly wants a fresh sandbox or a separate environment."
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "sandbox_name": {
                    "type": "string",
                    "description": "Optional human-readable sandbox name.",
                }
            },
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        sandbox_name: str = "",
    ) -> ToolExecResult:
        if permission_error := check_admin_permission(context, "Creating sandbox"):
            return permission_error

        plugin_context = context.context.context
        session_id = context.context.event.unified_msg_origin
        provider_id = _current_provider_id(context)
        if not provider_id:
            return "Error creating sandbox: sandbox booter is not configured."

        try:
            sandbox = await sandbox_manager.create_sandbox(
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
    description: str = "Switch this session to an existing running sandbox by sandbox_id."
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
        try:
            sandbox = await sandbox_manager.switch_current_sandbox_checked(
                session_id, sandbox_id
            )
        except Exception as e:
            detail = str(e) or type(e).__name__
            return f"Error switching sandbox: {detail}"
        return _dump({"sandbox": sandbox})


@builtin_tool(config=_SANDBOX_RUNTIME_TOOL_CONFIG)
@dataclass
class ReleaseSandboxTool(FunctionTool):
    name: str = "astrbot_release_sandbox"
    description: str = "Release the control lease for the current sandbox or a specified sandbox."
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
            sandbox = sandbox_manager.release_current_sandbox(
                session_id, sandbox_id.strip() or None
            )
        except Exception as e:
            detail = str(e) or type(e).__name__
            return f"Error releasing sandbox: {detail}"
        return _dump({"sandbox": sandbox})


@builtin_tool(config=_SANDBOX_RUNTIME_TOOL_CONFIG)
@dataclass
class TakeoverSandboxTool(FunctionTool):
    name: str = "astrbot_takeover_sandbox"
    description: str = "Force takeover of a sandbox lease by sandbox_id. Admin only."
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
        if permission_error := check_admin_permission(context, "Taking over sandbox"):
            return permission_error
        session_id = context.context.event.unified_msg_origin
        try:
            sandbox = sandbox_manager.takeover_sandbox(session_id, sandbox_id)
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
        if permission_error := check_admin_permission(context, "Destroying sandbox"):
            return permission_error
        session_id = context.context.event.unified_msg_origin
        try:
            sandbox = await sandbox_manager.destroy_sandbox(session_id, sandbox_id)
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
        try:
            booter = await sandbox_manager.get_observer_booter_by_id(
                sandbox_id, context.context.event.unified_msg_origin
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
                "source_sandbox_id": {"type": "string", "description": "Source sandbox ID."},
                "source_path": {"type": "string", "description": "Path in source sandbox."},
                "target_sandbox_id": {"type": "string", "description": "Target sandbox ID."},
                "target_path": {"type": "string", "description": "Destination path in target sandbox."},
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
        try:
            session_id = context.context.event.unified_msg_origin
            source = await sandbox_manager.get_observer_booter_by_id(
                source_sandbox_id, session_id
            )
            target = await sandbox_manager.get_observer_booter_by_id(
                target_sandbox_id, session_id
            )
            temp_dir = Path(get_astrbot_temp_path()) / "sandbox_copy"
            temp_dir.mkdir(parents=True, exist_ok=True)
            local_path = temp_dir / f"{uuid.uuid4().hex}-{Path(target_path).name}"
            await source.download_file(source_path, str(local_path))
            upload_result = await target.upload_file(str(local_path), target_path)
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
