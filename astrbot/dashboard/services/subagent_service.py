from __future__ import annotations

import traceback
from copy import deepcopy
from typing import Any

from pydantic import TypeAdapter, ValidationError

from astrbot.core import logger
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_runtime.main_agent.subagent import ExpertDefinition
from astrbot.core.astr_agent_runtime.tools.subagent import SUBAGENT_TOOL_NAMES
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
            return self._normalize_config(deepcopy(config_data))
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise SubAgentServiceError(f"获取 subagent 配置失败: {exc!s}") from exc

    async def update_config(self, data: object) -> None:
        try:
            if not isinstance(data, dict):
                raise SubAgentServiceError("配置必须为 JSON 对象")

            config = self.core_lifecycle.astrbot_config
            data = self._normalize_config(deepcopy(data))
            definitions = TypeAdapter(list[ExpertDefinition]).validate_python(
                data["agents"]
            )
            if len({item.name for item in definitions}) != len(definitions):
                raise SubAgentServiceError("Expert names must be unique.")
            data["agents"] = [item.model_dump() for item in definitions]
            previous = deepcopy(config.get("subagent_orchestrator", {}))
            config["subagent_orchestrator"] = data
            try:
                config.save_config()
            except Exception:
                config["subagent_orchestrator"] = previous
                raise

        except SubAgentServiceError:
            raise
        except ValidationError as exc:
            raise SubAgentServiceError(str(exc)) from exc
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

    async def get_runtime(self, agent_id: str | None = None) -> list[dict]:
        """Return agent sessions and history supplied by their selected agent runtime.

        Args:
            agent_id: Worker whose private history should be included, if provided.

        Returns:
            Matching workers with conversation ownership and sender metadata.
        """
        service = self.core_lifecycle.subagents
        return await service.inspect(agent_id) if service is not None else []

    @staticmethod
    def _normalize_config(data: object) -> dict:
        normalized: dict[str, Any] = (
            data
            if isinstance(data, dict)
            else {
                "main_enable": False,
                "agents": [],
            }
        )

        if "main_enable" not in normalized and "enable" in normalized:
            normalized["main_enable"] = bool(normalized.get("enable", False))

        normalized.setdefault("main_enable", False)
        normalized.pop("remove_main_duplicate_tools", None)
        normalized.pop("router_system_prompt", None)
        normalized.setdefault("max_concurrent_agents", 3)
        normalized.setdefault("task_timeout", 600)
        normalized.setdefault("max_steps", 30)
        normalized.setdefault("agents", [])

        agents = normalized.get("agents")
        if isinstance(agents, list):
            for agent in agents:
                if isinstance(agent, dict):
                    agent.setdefault("provider_id", None)
                    agent.setdefault("persona_id", None)

        return normalized

    @staticmethod
    def _is_subagent_internal_tool(tool: FunctionTool) -> bool:
        return isinstance(tool, HandoffTool) or tool.name in SUBAGENT_TOOL_NAMES
