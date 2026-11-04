from __future__ import annotations

import traceback

from astrbot.core import logger
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_runtime.tools.subagent import SUBAGENT_TOOL_NAMES
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle


class SubAgentServiceError(Exception):
    pass


class SubAgentService:
    def __init__(self, core_lifecycle: AstrBotCoreLifecycle) -> None:
        self.core_lifecycle = core_lifecycle

    def get_available_tools(self) -> list[dict]:
        try:
            tool_mgr = self.core_lifecycle.provider_manager.llm_tools
            tools = []
            for tool in tool_mgr.func_list:
                if self._is_subagent_internal_tool(tool):
                    continue
                tools.append(
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                        "active": tool.active,
                        "handler_module_path": tool.handler_module_path,
                    }
                )
            return tools
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise SubAgentServiceError(f"获取可用工具失败: {exc!s}") from exc

    @staticmethod
    def _is_subagent_internal_tool(tool: FunctionTool) -> bool:
        return isinstance(tool, HandoffTool) or tool.name in SUBAGENT_TOOL_NAMES
