from __future__ import annotations

from typing import Any

from astrbot import logger
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.persona_mgr import PersonaManager
from astrbot.core.provider.func_tool_manager import FunctionToolManager
from astrbot.core.subagent.codec import decode_subagent_config
from astrbot.core.subagent.error_classifier import build_error_classifier_from_config
from astrbot.core.subagent.handoff_executor import HandoffExecutor
from astrbot.core.subagent.models import (
    SubagentConfig,
    SubagentMountPlan,
    SubagentTaskData,
)
from astrbot.core.subagent.planner import SubagentPlanner
from astrbot.core.subagent.runtime import SubagentRuntime
from astrbot.core.subagent.worker import SubagentWorker


class SubAgentOrchestrator:
    """Subagent orchestration facade.

    This class holds canonical config + mount plan, and delegates heavy lifting to:
    - planner: deterministic handoff plan generation
    - runtime/worker: background task queue and retries
    """

    def __init__(
        self, tool_mgr: FunctionToolManager, persona_mgr: PersonaManager
    ) -> None:
        self._tool_mgr = tool_mgr
        self._persona_mgr = persona_mgr
        self._planner = SubagentPlanner(tool_mgr, persona_mgr)
        self._config = SubagentConfig()
        self._mount_plan = SubagentMountPlan()
        self._context = None
        db = getattr(persona_mgr, "db", None)
        self._runtime = SubagentRuntime(db=db)
        self._runtime.set_task_executor(self._execute_background_task)
        self._worker = SubagentWorker(self._runtime)
        self.handoffs: list[HandoffTool] = []

    def bind_context(self, context) -> None:
        self._context = context

    def start_worker(self):
        return self._worker.start()

    async def stop_worker(self) -> None:
        await self._worker.stop()

    async def reload_from_config(self, cfg: dict[str, Any]) -> list[str]:
        try:
            canonical, diagnostics = decode_subagent_config(cfg)
        except Exception as exc:
            logger.error("Invalid subagent config: %s", exc)
            self._config = SubagentConfig()
            self._mount_plan = SubagentMountPlan(
                diagnostics=[f"ERROR: invalid config: {exc}"]
            )
            self.handoffs = []
            return self._mount_plan.diagnostics

        self._config = canonical
        self._runtime.set_max_concurrent(canonical.max_concurrent_subagent_runs)
        classifier, classifier_diagnostics = build_error_classifier_from_config(
            canonical.error_classifier
        )
        self._runtime.set_error_classifier(classifier)
        diagnostics.extend(classifier_diagnostics)
        mount_plan = await self._planner.build_mount_plan(canonical)
        mount_plan.diagnostics = diagnostics + mount_plan.diagnostics
        self._mount_plan = mount_plan
        self.handoffs = mount_plan.handoffs
        return mount_plan.diagnostics

    def get_mount_plan(self) -> SubagentMountPlan:
        return self._mount_plan

    def get_config(self) -> SubagentConfig:
        return self._config

    def get_max_nested_depth(self) -> int:
        return int(self._config.max_nested_depth)

    async def submit_handoff(
        self,
        *,
        handoff: HandoffTool,
        run_context,
        payload: dict[str, Any],
        background: bool,
        tool_call_id: str | None = None,
    ) -> str | None:
        if not background:
            return None

        event = run_context.context.event
        event_get_extra = getattr(event, "get_extra", None)
        background_note = (
            event_get_extra("background_note") if callable(event_get_extra) else None
        )
        umo = getattr(event, "unified_msg_origin", None)
        if not isinstance(umo, str) or not umo:
            raise ValueError(
                "Cannot submit subagent handoff without unified_msg_origin"
            )
        task_payload = {
            "tool_args": payload,
            "_meta": {
                "role": getattr(event, "role", None),
                "background_note": background_note,
                "tool_call_timeout": int(
                    getattr(run_context, "tool_call_timeout", 3600)
                ),
            },
        }
        return await self._runtime.enqueue(
            umo=umo,
            subagent_name=getattr(handoff, "agent_display_name", handoff.agent.name),
            handoff_tool_name=handoff.name,
            payload=task_payload,
            tool_call_id=tool_call_id,
        )

    async def list_tasks(
        self, status: str | None = None, limit: int = 100
    ) -> list[dict]:
        return await self._runtime.list_tasks(status=status, limit=limit)

    async def retry_task(self, task_id: str) -> bool:
        return await self._runtime.retry_task(task_id)

    async def cancel_task(self, task_id: str) -> bool:
        return await self._runtime.cancel_task(task_id)

    def find_handoff(self, handoff_tool_name: str) -> HandoffTool | None:
        return self._mount_plan.handoff_by_tool_name.get(handoff_tool_name)

    async def _execute_background_task(self, task: SubagentTaskData) -> str:
        if not self._context:
            raise RuntimeError("Subagent orchestrator context is not bound.")
        return await HandoffExecutor.execute_queued_task(
            task=task,
            plugin_context=self._context,
            handoff=self.find_handoff(task.handoff_tool_name),
        )
