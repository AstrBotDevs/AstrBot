import os

import astrbot.api.star as star
from astrbot.api import AstrBotConfig

from .tools.fs import CreateFileTool, FileUploadTool, ReadFileTool
from .tools.python import PythonTool
from .tools.shell import ExecuteShellTool


class Main(star.Star):
    """AstrBot Agent"""

    def __init__(self, context: star.Context, config: AstrBotConfig) -> None:
        self.context = context
        self.config = config
        self.endpoint = config.get("endpoint", "http://localhost:8000")
        self.access_token = config.get("access_token", "")
        os.environ["ASTRBOT_SANDBOX_TYPE"] = config.get("booter", "shipyard-bay")
        os.environ["SHIPYARD_ENDPOINT"] = self.endpoint
        os.environ["SHIPYARD_ACCESS_TOKEN"] = self.access_token

        context.add_llm_tools(
            CreateFileTool(),
            ExecuteShellTool(),
            PythonTool(),
            ReadFileTool(),
            FileUploadTool(),
        )
