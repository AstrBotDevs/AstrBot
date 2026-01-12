import json
from dataclasses import dataclass, field

from astrbot.api import FunctionTool
from astrbot.api.event import AstrMessageEvent

from ..sandbox_client import SandboxClient


@dataclass
class CreateFileTool(FunctionTool):
    name: str = "astrbot_create_file"
    description: str = "Create a new file in the sandbox."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "path": {
                    "path": "string",
                    "description": "The path where the file should be created, relative to the sandbox root. Must not use absolute paths or traverse outside the sandbox.",
                },
                "content": {
                    "type": "string",
                    "description": "The content to write into the file.",
                },
            },
            "required": ["path", "content"],
        }
    )

    async def run(self, event: AstrMessageEvent, path: str, content: str):
        sb = await SandboxClient().get_ship(event.unified_msg_origin)
        try:
            result = await sb.fs.create_file(path, content)
            return json.dumps(result)
        except Exception as e:
            return f"Error creating file: {str(e)}"

@dataclass
class ReadFileTool(FunctionTool):
    name: str = "astrbot_read_file"
    description: str = "Read the content of a file in the sandbox."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The path of the file to read, relative to the sandbox root. Must not use absolute paths or traverse outside the sandbox.",
                },
            },
            "required": ["path"],
        }
    )

    async def run(self, event: AstrMessageEvent, path: str):
        sb = await SandboxClient().get_ship(event.unified_msg_origin)
        try:
            result = await sb.fs.read_file(path)
            return result
        except Exception as e:
            return f"Error reading file: {str(e)}"
