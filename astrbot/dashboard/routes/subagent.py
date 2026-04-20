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
                    "agents": [],
                }

            # Backward compatibility: older config used `enable`.
            if (
                isinstance(data, dict)
                and "main_enable" not in data
                and "enable" in data
            ):
                data["main_enable"] = bool(data.get("enable", False))

            # Ensure required keys exist.
            data.setdefault("main_enable", False)
            data.setdefault("remove_main_duplicate_tools", False)
            data.setdefault("agents", [])

            # Backward/forward compatibility: ensure each agent contains provider_id.
            # None means follow global/default provider settings.
            if isinstance(data.get("agents"), list):
                for a in data["agents"]:
                    if isinstance(a, dict):
                        a.setdefault("provider_id", None)
                        a.setdefault("persona_id", None)

            # 获取 enhanced_subagent 配置
            enhanced_data = cfg.get("enhanced_subagent", {})

            # 兼容旧格式：直接返回 subagent_orchestrator 的字段，同时附加 enhanced_subagent
            response_data = {
                "main_enable": data.get("main_enable", False),
                "remove_main_duplicate_tools": data.get("remove_main_duplicate_tools", False),
                "agents": data.get("agents", []),
                "enhanced_subagent": enhanced_data,
            }

            return jsonify(Response().ok(data=response_data).__dict__)
        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify(
                Response().error(f"获取 subagent 配置失败: {e!s}").__dict__
            )

    async def update_config(self):
        try:
            data = await request.json
            if not isinstance(data, dict):
                return jsonify(Response().error("配置必须为 JSON 对象").__dict__)

            cfg = self.core_lifecycle.astrbot_config

            # 兼容旧格式和新格式：
            # 1. 新格式: {"subagent_orchestrator": {...}, "enhanced_subagent": {...}}
            # 2. 旧格式: {"main_enable": ..., "agents": [...], ...}
            if "subagent_orchestrator" in data:
                # 新格式
                orch_data = data["subagent_orchestrator"]
                cfg["subagent_orchestrator"] = orch_data

                # Reload dynamic handoff tools if orchestrator exists
                orch = getattr(self.core_lifecycle, "subagent_orchestrator", None)
                if orch is not None:
                    await orch.reload_from_config(orch_data)
            else:
                # 旧格式：直接使用整个 data 作为 subagent_orchestrator
                cfg["subagent_orchestrator"] = data

                # Reload dynamic handoff tools if orchestrator exists
                orch = getattr(self.core_lifecycle, "subagent_orchestrator", None)
                if orch is not None:
                    await orch.reload_from_config(data)

            # 处理 enhanced_subagent（新格式专用）
            if "enhanced_subagent" in data:
                cfg["enhanced_subagent"] = data["enhanced_subagent"]

            # Persist to cmd_config.json
            cfg.save_config()

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
