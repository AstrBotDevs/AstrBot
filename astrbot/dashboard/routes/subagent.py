import traceback

from quart import jsonify, request

from astrbot.core import logger
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.subagent.codec import decode_subagent_config, encode_subagent_config

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
            ("/subagent/tasks", ("GET", self.get_tasks)),
            ("/subagent/tasks/<task_id>/retry", ("POST", self.retry_task)),
            ("/subagent/tasks/<task_id>/cancel", ("POST", self.cancel_task)),
        ]
        self.register_routes()

    @staticmethod
    def _split_compat_warnings(
        diagnostics: list[str] | None,
    ) -> tuple[list[str], list[str]]:
        if not diagnostics:
            return [], []
        compat_warnings: list[str] = []
        normal_diagnostics: list[str] = []
        for item in diagnostics:
            if "legacy field" in item:
                compat_warnings.append(item)
            else:
                normal_diagnostics.append(item)
        return normal_diagnostics, compat_warnings

    async def get_config(self):
        try:
            cfg = self.core_lifecycle.astrbot_config
            raw = cfg.get("subagent_orchestrator")
            if not isinstance(raw, dict):
                raw = {}
            canonical, diagnostics = decode_subagent_config(raw)
            normal_diagnostics, compat_warnings = self._split_compat_warnings(
                diagnostics
            )
            data = encode_subagent_config(
                canonical,
                diagnostics=normal_diagnostics,
                compat_warnings=compat_warnings,
            )
            return jsonify(Response().ok(data=data).__dict__)
        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify(Response().error(f"获取 subagent 配置失败: {e!s}").__dict__)

    async def update_config(self):
        try:
            data = await request.json
            if not isinstance(data, dict):
                return jsonify(Response().error("配置必须为 JSON 对象").__dict__)
            # Canonical field is `instructions`; `system_prompt` is accepted for
            # backward compatibility and serialized as a deprecated mirror field.
            canonical, diagnostics = decode_subagent_config(data)
            normalized = encode_subagent_config(canonical)

            cfg = self.core_lifecycle.astrbot_config
            cfg["subagent_orchestrator"] = normalized

            # Persist to cmd_config.json
            # AstrBotConfigManager does not expose a `save()` method; persist via AstrBotConfig.
            cfg.save_config()

            # Reload dynamic handoff tools if orchestrator exists
            orch = getattr(self.core_lifecycle, "subagent_orchestrator", None)
            reload_diagnostics: list[str] = []
            if orch is not None:
                res = await orch.reload_from_config(normalized)
                if isinstance(res, list):
                    reload_diagnostics = res
            merged_diagnostics = diagnostics + reload_diagnostics
            normal_diagnostics, compat_warnings = self._split_compat_warnings(
                merged_diagnostics
            )

            return jsonify(
                Response()
                .ok(
                    message="保存成功",
                    data={
                        "diagnostics": normal_diagnostics,
                        "compat_warnings": compat_warnings,
                    },
                )
                .__dict__
            )
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

    async def get_tasks(self):
        try:
            status = request.args.get("status", default=None, type=str)
            limit = request.args.get("limit", default=100, type=int)
            if limit < 1:
                limit = 1
            if limit > 1000:
                limit = 1000
            orch = getattr(self.core_lifecycle, "subagent_orchestrator", None)
            if orch is None:
                return jsonify(Response().ok(data=[]).__dict__)
            tasks = await orch.list_tasks(status=status, limit=limit)
            return jsonify(Response().ok(data=tasks).__dict__)
        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify(Response().error(f"获取任务列表失败: {e!s}").__dict__)

    async def retry_task(self, task_id: str):
        try:
            orch = getattr(self.core_lifecycle, "subagent_orchestrator", None)
            if orch is None:
                return jsonify(
                    Response().error("subagent orchestrator 不存在").__dict__
                )
            ok = await orch.retry_task(task_id)
            if not ok:
                return jsonify(Response().error("任务不存在或无法重试").__dict__)
            return jsonify(Response().ok(message="重试已提交").__dict__)
        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify(Response().error(f"重试任务失败: {e!s}").__dict__)

    async def cancel_task(self, task_id: str):
        try:
            orch = getattr(self.core_lifecycle, "subagent_orchestrator", None)
            if orch is None:
                return jsonify(
                    Response().error("subagent orchestrator 不存在").__dict__
                )
            ok = await orch.cancel_task(task_id)
            if not ok:
                return jsonify(Response().error("任务不存在或无法取消").__dict__)
            return jsonify(Response().ok(message="任务已取消").__dict__)
        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify(Response().error(f"取消任务失败: {e!s}").__dict__)
