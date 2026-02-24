from dataclasses import dataclass, field

import mcp

from astrbot.api import FunctionTool
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext, AstrMessageEvent
from astrbot.core.computer.computer_client import get_booter, get_local_booter
from astrbot.core.computer.tools.permissions import check_admin_permission
from astrbot.core.message.message_event_result import MessageChain

param_schema = {
    "type": "object",
    "properties": {
        "code": {
            "type": "string",
            "description": "The Python code to execute.",
        },
        "silent": {
            "type": "boolean",
            "description": "Whether to suppress the output of the code execution.",
            "default": False,
        },
    },
    "required": ["code"],
}


async def handle_result(result: dict, event: AstrMessageEvent) -> ToolExecResult:
    data = result.get("data", {})
    output = data.get("output", {})
    error = data.get("error", "")
    images: list[dict] = output.get("images", [])
    text: str = output.get("text", "")

    resp = mcp.types.CallToolResult(content=[])

    if error:
        resp.content.append(mcp.types.TextContent(type="text", text=f"error: {error}"))

    if images:
        for img in images:
            resp.content.append(
                mcp.types.ImageContent(
                    type="image", data=img["image/png"], mimeType="image/png"
                )
            )

            if event.get_platform_name() == "webchat":
                await event.send(message=MessageChain().base64_image(img["image/png"]))
    if text:
        resp.content.append(mcp.types.TextContent(type="text", text=text))

    if not resp.content:
        resp.content.append(mcp.types.TextContent(type="text", text="No output."))

    return resp


@dataclass
class PythonTool(FunctionTool):
    name: str = "astrbot_execute_ipython"
    description: str = "Run codes in an IPython shell."
    parameters: dict = field(default_factory=lambda: param_schema)

    async def call(
        self, context: ContextWrapper[AstrAgentContext], code: str, silent: bool = False
    ) -> ToolExecResult:
        if permission_error := check_admin_permission(context, "Python execution"):
            return permission_error
        sb = await get_booter(
            context.context.context,
            context.context.event.unified_msg_origin,
        )
        try:
            result = await sb.python.exec(code, silent=silent)
            return await handle_result(result, context.context.event)
        except Exception as e:
            return f"Error executing code: {str(e)}"


@dataclass
class LocalPythonTool(FunctionTool):
    name: str = "astrbot_execute_python"
    description: str = "Execute codes in a Python environment."

    parameters: dict = field(default_factory=lambda: param_schema)

    async def call(
        self, context: ContextWrapper[AstrAgentContext], code: str, silent: bool = False
    ) -> ToolExecResult:
        if permission_error := check_admin_permission(context, "Python execution"):
            return permission_error
        sb = get_local_booter()
        try:
            result = await sb.python.exec(code, silent=silent)
            return await handle_result(result, context.context.event)
        except Exception as e:
            return f"Error executing code: {str(e)}"
