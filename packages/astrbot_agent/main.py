import os
import astrbot.api.star as star
from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.provider import ProviderRequest
from astrbot.api import AstrBotConfig
from .tools.fs import CreateFileTool, ReadFileTool
from .tools.shell import ExecuteShellTool
from .tools.python import PythonTool
from .commands.file import FileCommand


class Main(star.Star):
    """AstrBot Agent"""

    def __init__(self, context: star.Context, config: AstrBotConfig) -> None:
        self.context = context
        self.config = config
        self.endpoint = config.get("endpoint", "http://localhost:8000")
        self.access_token = config.get("access_token", "")
        os.environ["SHIPYARD_ENDPOINT"] = self.endpoint
        os.environ["SHIPYARD_ACCESS_TOKEN"] = self.access_token

        context.add_llm_tool(
            CreateFileTool(), ExecuteShellTool(), PythonTool(), ReadFileTool()
        )

        self.file_c = FileCommand(context)

    async def initialize(self):
        pass

    @filter.command("fileupload")
    async def fileupload(self, event: AstrMessageEvent):
        """处理文件上传"""
        await self.file_c.file(event)

    @filter.on_llm_request()
    async def on_llm_request(self, event: AstrMessageEvent, req: ProviderRequest):
        """处理 LLM 请求"""
        sender_id = event.get_sender_id()
        uploads = self.file_c.user_file_uploaded_files.pop(sender_id, None)
        if uploads:
            logger.info(f"Attaching uploaded files for user {sender_id}: {uploads}")

        req.system_prompt = f"{req.system_prompt}\n\n\n# User Uploaded Files: {uploads}"
