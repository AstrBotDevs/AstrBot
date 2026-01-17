from dataclasses import dataclass, field

import mcp

from astrbot.api import FunctionTool
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.sandbox.sandbox_client import get_booter


@dataclass
class PythonTool(FunctionTool):
    name: str = "astrbot_execute_ipython"
    description: str = "Execute a command in an IPython shell."
    parameters: dict = field(
        default_factory=lambda: {
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
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], code: str, silent: bool = False
    ) -> ToolExecResult:
        sb = await get_booter(
            context.context.context,
            context.context.event.unified_msg_origin,
        )
        try:
            result = await sb.python.exec(code, silent=silent)
            data = result.get("data", {})
            output = data.get("output", {})
            error = data.get("error", "")
            images: list[dict] = output.get("images", [])
            text: str = output.get("text", "")

            resp = mcp.types.CallToolResult(content=[])

            if error:
                resp.content.append(
                    mcp.types.TextContent(type="text", text=f"error: {error}")
                )

            if images:
                for img in images:
                    resp.content.append(
                        mcp.types.ImageContent(
                            type="image", data=img["image/png"], mimeType="image/png"
                        )
                    )
            if text:
                resp.content.append(mcp.types.TextContent(type="text", text=text))

            if not resp.content:
                resp.content.append(
                    mcp.types.TextContent(type="text", text="No output.")
                )

            return resp

        except Exception as e:
            return f"Error executing code: {str(e)}"
