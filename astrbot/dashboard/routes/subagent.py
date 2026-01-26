import traceback

from quart import request
from quart import jsonify

from astrbot.core import logger
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
            provider_settings = cfg.get("provider_settings", {})
            data = provider_settings.get("subagent_orchestrator")

            # First-time access: return a sane default instead of erroring.
            if not isinstance(data, dict):
                data = {
                    "main_enable": False,
                    "main_tools_policy": "handoff_only",
                    "agents": [],
                }

            # Backward compatibility: older config used `enable`.
            if isinstance(data, dict) and "main_enable" not in data and "enable" in data:
                data["main_enable"] = bool(data.get("enable", False))

            # Ensure required keys exist.
            data.setdefault("main_enable", False)
            data.setdefault("main_tools_policy", "handoff_only")
            data.setdefault("agents", [])

            # Backward/forward compatibility: ensure each agent contains provider_id.
            # None means follow global/default provider settings.
            if isinstance(data.get("agents"), list):
                for a in data["agents"]:
                    if isinstance(a, dict):
                        a.setdefault("provider_id", None)
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
            provider_settings = cfg.get("provider_settings", {})
            provider_settings["subagent_orchestrator"] = data
            cfg["provider_settings"] = provider_settings

            # Persist to cmd_config.json
            # AstrBotConfigManager does not expose a `save()` method; persist via AstrBotConfig.
            cfg.save_config()

            # Reload dynamic handoff tools if orchestrator exists
            orch = getattr(self.core_lifecycle, "subagent_orchestrator", None)
            if orch is not None:
                orch.reload_from_config(provider_settings)

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
