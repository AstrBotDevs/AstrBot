from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import mcp

from astrbot.api import FunctionTool
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.computer.computer_client import (
    copy_file_between_cua_sandboxes,
    create_cua_sandbox,
    destroy_cua_sandbox,
    get_cua_sandbox_observer_booter_by_id,
    get_current_cua_sandbox,
    list_cua_sandboxes,
    release_current_cua_sandbox,
    switch_current_cua_sandbox_checked,
    takeover_cua_sandbox,
)
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.tools.computer_tools.util import check_admin_permission
from astrbot.core.tools.registry import builtin_tool
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

_CUA_TOOL_CONFIG = {
    "provider_settings.computer_use_runtime": "sandbox",
    "provider_settings.sandbox.booter": "cua",
}


def _to_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _exception_detail(error: Exception) -> str:
    return str(error) or type(error).__name__


def _session_id(context: ContextWrapper[AstrAgentContext]) -> str:
    return context.context.event.unified_msg_origin


def _new_screenshot_path(umo: str) -> str:
    safe_prefix = uuid.uuid5(uuid.NAMESPACE_DNS, umo).hex[:12]
    screenshot_dir = Path(get_astrbot_temp_path()) / "cua_screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    return str(screenshot_dir / f"{safe_prefix}-{uuid.uuid4().hex}.png")


async def _screenshot_result(
    context: ContextWrapper[AstrAgentContext],
    gui: Any,
    *,
    send_to_user: bool,
    return_image_to_llm: bool,
) -> ToolExecResult:
    path = _new_screenshot_path(_session_id(context))
    result = await gui.screenshot(path)
    payload = {"success": True, **result, "path": path}
    if send_to_user:
        await context.context.event.send(MessageChain().file_image(path))
        payload["sent_to_user"] = True
    image_data = payload.pop("base64", "")
    content: list[mcp.types.TextContent | mcp.types.ImageContent] = [
        mcp.types.TextContent(type="text", text=_to_json(payload))
    ]
    if return_image_to_llm:
        content.append(
            mcp.types.ImageContent(
                type="image",
                data=str(image_data),
                mimeType=str(payload.get("mime_type", "image/png")),
            )
        )
    return mcp.types.CallToolResult(content=content)


@builtin_tool(config=_CUA_TOOL_CONFIG)
@dataclass
class CuaListSandboxesTool(FunctionTool):
    name: str = "astrbot_list_sandboxes"
    description: str = "List AstrBot-managed sandboxes with sandbox IDs, default marker, controller, lease, and provider fields. Use this before switching to another sandbox."
    parameters: dict = field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )

    async def call(self, context: ContextWrapper[AstrAgentContext]) -> ToolExecResult:
        return _to_json({"success": True, "sandboxes": list_cua_sandboxes()})


@builtin_tool(config=_CUA_TOOL_CONFIG)
@dataclass
class CuaGetCurrentSandboxTool(FunctionTool):
    name: str = "astrbot_get_current_sandbox"
    description: str = (
        "Return the current managed sandbox bound to this conversation/session."
    )
    parameters: dict = field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )

    async def call(self, context: ContextWrapper[AstrAgentContext]) -> ToolExecResult:
        return _to_json(
            {"success": True, **get_current_cua_sandbox(_session_id(context))}
        )


@builtin_tool(config=_CUA_TOOL_CONFIG)
@dataclass
class CuaCreateSandboxTool(FunctionTool):
    name: str = "astrbot_create_sandbox"
    description: str = (
        "Create a new AstrBot-managed CUA sandbox and switch this session to it."
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "sandbox_name": {
                    "type": "string",
                    "description": "Optional human-readable sandbox name.",
                },
            },
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        sandbox_name: str | None = None,
    ) -> ToolExecResult:
        if err := check_admin_permission(context, "Creating CUA sandboxes"):
            return err
        try:
            sandbox = await create_cua_sandbox(
                context.context.context,
                _session_id(context),
                sandbox_name=sandbox_name,
            )
            return _to_json({"success": True, "sandbox": sandbox})
        except Exception as e:
            return f"Error creating CUA sandbox: {_exception_detail(e)}"


@builtin_tool(config=_CUA_TOOL_CONFIG)
@dataclass
class CuaSwitchSandboxTool(FunctionTool):
    name: str = "astrbot_switch_sandbox"
    description: str = "Switch this conversation/session to an existing managed sandbox by sandbox_id and acquire its control lease if it is free. Use this when the user asks to switch to another sandbox."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "sandbox_id": {"type": "string", "description": "Target sandbox ID."},
            },
            "required": ["sandbox_id"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        sandbox_id: str,
    ) -> ToolExecResult:
        try:
            sandbox = await switch_current_cua_sandbox_checked(
                _session_id(context), sandbox_id
            )
            return _to_json({"success": True, "sandbox": sandbox})
        except Exception as e:
            return f"Error switching CUA sandbox: {_exception_detail(e)}"


@builtin_tool(config=_CUA_TOOL_CONFIG)
@dataclass
class CuaReleaseSandboxTool(FunctionTool):
    name: str = "astrbot_release_sandbox"
    description: str = (
        "Release this conversation/session's control lease for a managed sandbox."
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "sandbox_id": {
                    "type": "string",
                    "description": "Optional sandbox ID. Defaults to this session's current sandbox.",
                },
            },
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        sandbox_id: str | None = None,
    ) -> ToolExecResult:
        try:
            sandbox = release_current_cua_sandbox(_session_id(context), sandbox_id)
            return _to_json({"success": True, "sandbox": sandbox})
        except Exception as e:
            return f"Error releasing CUA sandbox: {_exception_detail(e)}"


@builtin_tool(config=_CUA_TOOL_CONFIG)
@dataclass
class CuaTakeoverSandboxTool(FunctionTool):
    name: str = "astrbot_takeover_sandbox"
    description: str = "Take over a managed sandbox by sandbox_id, binding it to this conversation/session even if another session currently controls it."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "sandbox_id": {"type": "string", "description": "Target sandbox ID."},
            },
            "required": ["sandbox_id"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        sandbox_id: str,
    ) -> ToolExecResult:
        if err := check_admin_permission(context, "Taking over CUA sandboxes"):
            return err
        try:
            sandbox = takeover_cua_sandbox(_session_id(context), sandbox_id)
            return _to_json({"success": True, "sandbox": sandbox})
        except Exception as e:
            return f"Error taking over CUA sandbox: {_exception_detail(e)}"


@builtin_tool(config=_CUA_TOOL_CONFIG)
@dataclass
class CuaDestroySandboxTool(FunctionTool):
    name: str = "astrbot_destroy_sandbox"
    description: str = "Destroy an AstrBot-managed CUA sandbox."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "sandbox_id": {"type": "string", "description": "Target sandbox ID."},
            },
            "required": ["sandbox_id"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        sandbox_id: str,
    ) -> ToolExecResult:
        if err := check_admin_permission(context, "Destroying CUA sandboxes"):
            return err
        try:
            sandbox = await destroy_cua_sandbox(_session_id(context), sandbox_id)
            return _to_json({"success": True, "sandbox": sandbox})
        except Exception as e:
            return f"Error destroying CUA sandbox: {_exception_detail(e)}"


@builtin_tool(config=_CUA_TOOL_CONFIG)
@dataclass
class CuaScreenshotSandboxTool(FunctionTool):
    name: str = "astrbot_screenshot_sandbox"
    description: str = "Capture a screenshot from a managed sandbox by sandbox_id without taking its control lease."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "sandbox_id": {"type": "string", "description": "Target sandbox ID."},
                "send_to_user": {
                    "type": "boolean",
                    "description": "Whether to send the screenshot image to the current conversation.",
                    "default": True,
                },
                "return_image_to_llm": {
                    "type": "boolean",
                    "description": "Whether to include the screenshot image content in the tool result.",
                    "default": True,
                },
            },
            "required": ["sandbox_id"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        sandbox_id: str,
        send_to_user: bool = True,
        return_image_to_llm: bool = True,
    ) -> ToolExecResult:
        if err := check_admin_permission(context, "Taking CUA sandbox screenshots"):
            return err
        try:
            booter = await get_cua_sandbox_observer_booter_by_id(sandbox_id)
            gui = getattr(booter, "gui", None)
            if gui is None:
                raise RuntimeError(
                    "Target sandbox does not support CUA GUI capability."
                )
            return await _screenshot_result(
                context,
                gui,
                send_to_user=send_to_user,
                return_image_to_llm=return_image_to_llm,
            )
        except Exception as e:
            return f"Error taking CUA sandbox screenshot: {_exception_detail(e)}"


@builtin_tool(config=_CUA_TOOL_CONFIG)
@dataclass
class CuaCopyFileBetweenSandboxesTool(FunctionTool):
    name: str = "astrbot_copy_file_between_sandboxes"
    description: str = "Copy a file between two managed CUA sandboxes through AstrBot temp relay storage."
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
                    "description": "Path to read from the source sandbox.",
                },
                "target_sandbox_id": {
                    "type": "string",
                    "description": "Target sandbox ID.",
                },
                "target_path": {
                    "type": "string",
                    "description": "Destination path in the target sandbox.",
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
        if err := check_admin_permission(
            context, "Copying files between CUA sandboxes"
        ):
            return err
        try:
            result = await copy_file_between_cua_sandboxes(
                session_id=_session_id(context),
                source_sandbox_id=source_sandbox_id,
                source_path=source_path,
                target_sandbox_id=target_sandbox_id,
                target_path=target_path,
                temp_dir=Path(get_astrbot_temp_path()),
            )
            return _to_json({"success": True, **result})
        except Exception as e:
            return f"Error copying file between CUA sandboxes: {_exception_detail(e)}"
