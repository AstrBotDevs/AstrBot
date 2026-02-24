import os
import uuid
from dataclasses import dataclass, field

from astrbot.api import FunctionTool, logger
from astrbot.api.event import MessageChain
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.message.components import File
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from ..computer_client import get_booter
from .permissions import check_admin_permission

# @dataclass
# class CreateFileTool(FunctionTool):
#     name: str = "astrbot_create_file"
#     description: str = "Create a new file in the sandbox."
#     parameters: dict = field(
#         default_factory=lambda: {
#             "type": "object",
#             "properties": {
#                 "path": {
#                     "path": "string",
#                     "description": "The path where the file should be created, relative to the sandbox root. Must not use absolute paths or traverse outside the sandbox.",
#                 },
#                 "content": {
#                     "type": "string",
#                     "description": "The content to write into the file.",
#                 },
#             },
#             "required": ["path", "content"],
#         }
#     )

#     async def call(
#         self, context: ContextWrapper[AstrAgentContext], path: str, content: str
#     ) -> ToolExecResult:
#         sb = await get_booter(
#             context.context.context,
#             context.context.event.unified_msg_origin,
#         )
#         try:
#             result = await sb.fs.create_file(path, content)
#             return json.dumps(result)
#         except Exception as e:
#             return f"Error creating file: {str(e)}"


# @dataclass
# class ReadFileTool(FunctionTool):
#     name: str = "astrbot_read_file"
#     description: str = "Read the content of a file in the sandbox."
#     parameters: dict = field(
#         default_factory=lambda: {
#             "type": "object",
#             "properties": {
#                 "path": {
#                     "type": "string",
#                     "description": "The path of the file to read, relative to the sandbox root. Must not use absolute paths or traverse outside the sandbox.",
#                 },
#             },
#             "required": ["path"],
#         }
#     )

#     async def call(self, context: ContextWrapper[AstrAgentContext], path: str):
#         sb = await get_booter(
#             context.context.context,
#             context.context.event.unified_msg_origin,
#         )
#         try:
#             result = await sb.fs.read_file(path)
#             return result
#         except Exception as e:
#             return f"Error reading file: {str(e)}"


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

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        local_path: str,
    ) -> str | None:
        if permission_error := check_admin_permission(context, "File upload/download"):
            return permission_error
        sb = await get_booter(
            context.context.context,
            context.context.event.unified_msg_origin,
        )
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


@dataclass
class FileDownloadTool(FunctionTool):
    name: str = "astrbot_download_file"
    description: str = "Download a file from the sandbox. Only call this when user explicitly need you to download a file."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "remote_path": {
                    "type": "string",
                    "description": "The path of the file in the sandbox to download.",
                },
                "also_send_to_user": {
                    "type": "boolean",
                    "description": "Whether to also send the downloaded file to the user via message. Defaults to true.",
                },
            },
            "required": ["remote_path"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        remote_path: str,
        also_send_to_user: bool = True,
    ) -> ToolExecResult:
        if permission_error := check_admin_permission(context, "File upload/download"):
            return permission_error
        sb = await get_booter(
            context.context.context,
            context.context.event.unified_msg_origin,
        )
        try:
            name = os.path.basename(remote_path)

            local_path = os.path.join(
                get_astrbot_temp_path(), f"sandbox_{uuid.uuid4().hex[:4]}_{name}"
            )

            # Download file from sandbox
            await sb.download_file(remote_path, local_path)
            logger.info(f"File {remote_path} downloaded from sandbox to {local_path}")

            if also_send_to_user:
                try:
                    name = os.path.basename(local_path)
                    await context.context.event.send(
                        MessageChain(chain=[File(name=name, file=local_path)])
                    )
                except Exception as e:
                    logger.error(f"Error sending file message: {e}")

                # remove
                # try:
                #     os.remove(local_path)
                # except Exception as e:
                #     logger.error(f"Error removing temp file {local_path}: {e}")

                return f"File downloaded successfully to {local_path} and sent to user."

            return f"File downloaded successfully to {local_path}"
        except Exception as e:
            logger.error(f"Error downloading file {remote_path}: {e}")
            return f"Error downloading file: {str(e)}"
