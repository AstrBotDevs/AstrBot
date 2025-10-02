import mcp
from astrbot.api import FunctionTool
from astrbot.api.event import AstrMessageEvent
from dataclasses import dataclass, field
from ..sandbox_client import SandboxClient


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
                "slient": {
                    "type": "boolean",
                    "description": "Whether to suppress the output of the code execution.",
                    "default": False,
                },
            },
            "required": ["code"],
        }
    )

    async def run(self, event: AstrMessageEvent, code: str, silent: bool = False):
        sb = await SandboxClient().get_ship(event.unified_msg_origin)
        try:
            result = await sb.python.exec(code, silent=silent)
            output = result.get("output", {})
            images: list[dict] = output.get("images", [])
            text: str = output.get("text", "")

            resp = mcp.types.CallToolResult(content=[])

            if images:
                for img in images:
                    resp.content.append(
                        mcp.types.ImageContent(
                            type="image", data=img["image/png"], mimeType="image/png"
                        )
                    )
            if text:
                resp.content.append(mcp.types.TextContent(type="text", text=text))

            return resp

        except Exception as e:
            return f"Error executing code: {str(e)}"
