from __future__ import annotations

import traceback

from astrbot.core import logger
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle


class SubAgentServiceError(Exception):
    pass


class SubAgentService:
    def __init__(self, core_lifecycle: AstrBotCoreLifecycle) -> None:
        self.core_lifecycle = core_lifecycle

    def get_config(self) -> dict:
        try:
            config_data = self.core_lifecycle.astrbot_config.get(
                "subagent_orchestrator"
            )
            return self._normalize_config(config_data)
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise SubAgentServiceError(f"获取 subagent 配置失败: {exc!s}") from exc

    async def update_config(self, data: object) -> None:
        try:
            if not isinstance(data, dict):
                raise SubAgentServiceError("配置必须为 JSON 对象")

            config = self.core_lifecycle.astrbot_config
            config["subagent_orchestrator"] = data
            config.save_config()

            orchestrator = getattr(self.core_lifecycle, "subagent_orchestrator", None)
            if orchestrator is not None:
                await orchestrator.reload_from_config(data)
        except SubAgentServiceError:
            raise
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise SubAgentServiceError(f"保存 subagent 配置失败: {exc!s}") from exc

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
    def _normalize_config(data: object) -> dict:
        if not isinstance(data, dict):
            data = {
                "main_enable": False,
                "remove_main_duplicate_tools": False,
                "agents": [],
            }

        if "main_enable" not in data and "enable" in data:
            data["main_enable"] = bool(data.get("enable", False))

        data.setdefault("main_enable", False)
        data.setdefault("remove_main_duplicate_tools", False)
        data.setdefault("agents", [])

        agents = data.get("agents")
        if isinstance(agents, list):
            for agent in agents:
                if isinstance(agent, dict):
                    agent.setdefault("provider_id", None)
                    agent.setdefault("persona_id", None)

        return data

    @staticmethod
    def _is_subagent_internal_tool(tool) -> bool:
        return (
            isinstance(tool, HandoffTool)
            or tool.handler_module_path == "core.subagent_orchestrator"
        )
