import traceback

from quart import jsonify, request

from astrbot.core import logger
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle

from .route import Response, Route, RouteContext


class SubAgentRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.core_lifecycle = core_lifecycle
        # NOTE: dict cannot hold duplicate keys; use list form to register multiple
        # methods for the same path.
        self.routes = [
            ("/subagent/config", ("GET", self.get_config)),
            ("/subagent/config", ("POST", self.update_config)),
            ("/subagent/available-tools", ("GET", self.get_available_tools)),
        ]
        self.register_routes()

    async def get_config(self):
        try:
            cfg = self.core_lifecycle.astrbot_config
            data = cfg.get("subagent_orchestrator")

            # First-time access: return a sane default instead of erroring.
            if not isinstance(data, dict):
                data = {
                    "main_enable": False,
                    "remove_main_duplicate_tools": False,
                    "router_system_prompt": "",
                    "agents": [],
                    "dynamic_agents": {
                        "enabled": False,
                        "max_dynamic_subagent_count": 3,
                        "auto_cleanup_per_turn": True,
                        "tools_blacklist": [],
                        "tools_inherent": [],
                    },
                    "history_enabled": True,
                    "shared_context_enabled": False,
                    "shared_context_maxlen": 200,
                    "subagent_history_maxlen": 500,
                    "execution_timeout": 600,
                }

            # Ensure required keys exist.
            data.setdefault("main_enable", False)
            data.setdefault("remove_main_duplicate_tools", False)
            data.setdefault("router_system_prompt", "")
            data.setdefault("agents", [])
            data.setdefault("dynamic_agents", {})
            data.setdefault("history_enabled", True)
            data.setdefault("shared_context_enabled", False)
            data.setdefault("shared_context_maxlen", 200)
            data.setdefault("subagent_history_maxlen", 500)
            data.setdefault("execution_timeout", 600)

            # Ensure dynamic_agents sub-keys exist.
            dyn = data["dynamic_agents"]
            if isinstance(dyn, dict):
                dyn.setdefault("enabled", False)
                dyn.setdefault("max_dynamic_subagent_count", 3)
                dyn.setdefault("auto_cleanup_per_turn", True)
                dyn.setdefault("tools_blacklist", [])
                dyn.setdefault("tools_inherent", [])

            # Backward/forward compatibility: ensure each agent contains provider_id.
            # None means follow global/default provider settings.
            if isinstance(data.get("agents"), list):
                for a in data["agents"]:
                    if isinstance(a, dict):
                        a.setdefault("provider_id", None)
                        a.setdefault("persona_id", None)
            return jsonify(Response().ok(data=data).__dict__)
        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify(Response().error(f"获取 subagent 配置失败: {e!s}").__dict__)

    async def update_config(self):
        try:
            data = await request.json
            if not isinstance(data, dict):
                return jsonify(Response().error("配置必须为 JSON 对象").__dict__)

            cfg = self.core_lifecycle.astrbot_config
            cfg["subagent_orchestrator"] = data

            # Persist to cmd_config.json
            # AstrBotConfigManager does not expose a `save()` method; persist via AstrBotConfig.
            cfg.save_config()

            # Reload dynamic handoff tools if orchestrator exists
            orch = getattr(self.core_lifecycle, "subagent_orchestrator", None)
            if orch is not None:
                await orch.reload_from_config(data)

            return jsonify(Response().ok(message="保存成功").__dict__)
        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify(Response().error(f"保存 subagent 配置失败: {e!s}").__dict__)

    async def get_available_tools(self):
        """Return all registered tools (name/description/parameters/active/origin).

        UI can use this to build a multi-select list for subagent tool assignment.
        """
        try:
            tool_mgr = self.core_lifecycle.provider_manager.llm_tools
            tools_dict = []
            for tool in tool_mgr.func_list:
                # Prevent recursive routing: subagents should not be able to select
                # the handoff (transfer_to_*) tools as their own mounted tools.
                if isinstance(tool, HandoffTool):
                    continue
                if tool.handler_module_path == "core.subagent_orchestrator":
                    continue
                tools_dict.append(
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                        "active": tool.active,
                        "handler_module_path": tool.handler_module_path,
                    }
                )
            return jsonify(Response().ok(data=tools_dict).__dict__)
        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify(Response().error(f"获取可用工具失败: {e!s}").__dict__)
