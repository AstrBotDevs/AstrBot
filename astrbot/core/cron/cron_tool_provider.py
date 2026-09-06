"""CronToolProvider — provides cron job management tools.

Follows the same ``ToolProvider`` protocol as ``ComputerToolProvider``.
"""

from __future__ import annotations

from astrbot.core.agent.tool import FunctionTool
from astrbot.core.tool_provider import ToolProvider, ToolProviderContext
from astrbot.core.tools.cron_tools import (
    CREATE_CRON_JOB_TOOL,
    DELETE_CRON_JOB_TOOL,
    LIST_CRON_JOBS_TOOL,
)


class CronToolProvider(ToolProvider):
    """Provides cron-job management tools when enabled."""

    def get_tools(self, ctx: ToolProviderContext) -> list[FunctionTool]:
        return [CREATE_CRON_JOB_TOOL, DELETE_CRON_JOB_TOOL, LIST_CRON_JOBS_TOOL]

    def get_system_prompt_addon(self, ctx: ToolProviderContext) -> str:
        return ""
