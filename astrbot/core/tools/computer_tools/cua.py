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
from astrbot.core.computer.computer_client import get_booter
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


async def _get_gui_component(context: ContextWrapper[AstrAgentContext]) -> Any:
    booter = await get_booter(
        context.context.context,
        context.context.event.unified_msg_origin,
    )
    gui = getattr(booter, "gui", None)
    if gui is None:
        raise RuntimeError(
            "Current sandbox booter does not support CUA GUI capability. "
            "Please switch sandbox booter to cua."
        )
    return gui


@builtin_tool(config=_CUA_TOOL_CONFIG)
@dataclass
class CuaScreenshotTool(FunctionTool):
    name: str = "astrbot_cua_screenshot"
    description: str = (
        "Capture a screenshot from the CUA sandbox and optionally send it to the user."
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "send_to_user": {
                    "type": "boolean",
                    "description": "Whether to send the screenshot image to the current conversation.",
                    "default": True,
                },
                "return_image_to_llm": {
                    "type": "boolean",
                    "description": "Whether to include the screenshot image content in the tool result for model inspection.",
                    "default": True,
                },
            },
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        send_to_user: bool = True,
        return_image_to_llm: bool = True,
    ) -> ToolExecResult:
        if err := check_admin_permission(context, "Taking CUA screenshots"):
            return err
        try:
            gui = await _get_gui_component(context)
            path = _new_screenshot_path(context.context.event.unified_msg_origin)
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
        except Exception as e:
            return f"Error taking CUA screenshot: {_exception_detail(e)}"


@builtin_tool(config=_CUA_TOOL_CONFIG)
@dataclass
class CuaMouseClickTool(FunctionTool):
    name: str = "astrbot_cua_mouse_click"
    description: str = "Click a coordinate in the CUA sandbox desktop."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X coordinate."},
                "y": {"type": "integer", "description": "Y coordinate."},
                "button": {
                    "type": "string",
                    "description": "Mouse button, usually left, right, or middle.",
                    "default": "left",
                },
            },
            "required": ["x", "y"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        x: int,
        y: int,
        button: str = "left",
    ) -> ToolExecResult:
        if err := check_admin_permission(context, "Using CUA mouse"):
            return err
        try:
            gui = await _get_gui_component(context)
            return _to_json(await gui.click(x, y, button=button))
        except Exception as e:
            return f"Error clicking CUA desktop: {_exception_detail(e)}"


@builtin_tool(config=_CUA_TOOL_CONFIG)
@dataclass
class CuaKeyboardTypeTool(FunctionTool):
    name: str = "astrbot_cua_keyboard_type"
    description: str = "Type text into the CUA sandbox desktop."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to type."},
            },
            "required": ["text"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        text: str,
    ) -> ToolExecResult:
        if err := check_admin_permission(context, "Using CUA keyboard"):
            return err
        try:
            gui = await _get_gui_component(context)
            return _to_json(await gui.type_text(text))
        except Exception as e:
            return f"Error typing in CUA desktop: {_exception_detail(e)}"


def _new_screenshot_path(umo: str) -> str:
    safe_prefix = uuid.uuid5(uuid.NAMESPACE_DNS, umo).hex[:12]
    screenshot_dir = Path(get_astrbot_temp_path()) / "cua_screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    return str(screenshot_dir / f"{safe_prefix}-{uuid.uuid4().hex}.png")
