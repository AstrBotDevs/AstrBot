import json
import os
from dataclasses import dataclass, field

from astrbot.api import FunctionTool, logger
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
        sb = await SandboxClient.get_booter(event.unified_msg_origin)
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
        sb = await SandboxClient.get_booter(event.unified_msg_origin)
        try:
            result = await sb.fs.read_file(path)
            return result
        except Exception as e:
            return f"Error reading file: {str(e)}"


@dataclass
class FileUploadTool(FunctionTool):
    name: str = "astrbot_upload_file"
    description: str = "Upload a local file to the sandbox. The file must exist on the local filesystem."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "local_path": {
                    "type": "string",
                    "description": "The local file path to upload. This must be an absolute path to an existing file on the local filesystem.",
                },
                # "remote_path": {
                #     "type": "string",
                #     "description": "The filename to use in the sandbox. If not provided, file will be saved to the working directory with the same name as the local file.",
                # },
            },
            "required": ["local_path"],
        }
    )

    async def run(
        self,
        event: AstrMessageEvent,
        local_path: str,
    ):
        sb = await SandboxClient.get_booter(event.unified_msg_origin)
        try:
            # Check if file exists
            if not os.path.exists(local_path):
                return f"Error: File does not exist: {local_path}"

            if not os.path.isfile(local_path):
                return f"Error: Path is not a file: {local_path}"

            # Use basename if sandbox_filename is not provided
            remote_path = os.path.basename(local_path)

            # Upload file to sandbox
            result = await sb.upload_file(local_path, remote_path)
            logger.debug(f"Upload result: {result}")
            success = result.get("success", False)

            if not success:
                return f"Error uploading file: {result.get('message', 'Unknown error')}"

            file_path = result.get("file_path", "")
            logger.info(f"File {local_path} uploaded to sandbox at {file_path}")

            return f"File uploaded successfully to {file_path}"
        except Exception as e:
            logger.error(f"Error uploading file {local_path}: {e}")
            return f"Error uploading file: {str(e)}"
