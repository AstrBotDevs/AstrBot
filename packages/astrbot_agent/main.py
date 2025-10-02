import os
import astrbot.api.star as star
from astrbot.api import AstrBotConfig
from .tools.fs import CreateFileTool
from .tools.shell import ExecuteShellTool
from .tools.python import PythonTool


class Main(star.Star):
    """AstrBot Agent"""

    def __init__(self, context: star.Context, config: AstrBotConfig) -> None:
        self.context = context
        self.config = config
        self.endpoint = config.get("endpoint", "http://localhost:8000")
        self.access_token = config.get("access_token", "")
        os.environ["SHIPYARD_ENDPOINT"] = self.endpoint
        os.environ["SHIPYARD_ACCESS_TOKEN"] = self.access_token

        context.add_llm_tool(CreateFileTool(), ExecuteShellTool(), PythonTool())

    async def initialize(self):
        pass
