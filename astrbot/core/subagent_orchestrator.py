from __future__ import annotations

import json
from typing import Any

from astrbot import logger
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.cron.events import CronMessageEvent
from astrbot.core.persona_mgr import PersonaManager
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.provider.func_tool_manager import FunctionToolManager
from astrbot.core.subagent.codec import decode_subagent_config
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
        mount_plan = await self._planner.build_mount_plan(canonical)
        mount_plan.diagnostics = diagnostics + mount_plan.diagnostics
        self._mount_plan = mount_plan
        self.handoffs = mount_plan.handoffs
        return mount_plan.diagnostics

    def get_mount_plan(self) -> SubagentMountPlan:
        return self._mount_plan

    def get_config(self) -> SubagentConfig:
        return self._config

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
        handoff = self.find_handoff(task.handoff_tool_name)
        if handoff is None:
            raise ValueError(f"Handoff tool `{task.handoff_tool_name}` not found.")

        payload = json.loads(task.payload_json)
        if not isinstance(payload, dict):
            raise ValueError("Invalid task payload.")
        tool_args = payload.get("tool_args", {})
        if not isinstance(tool_args, dict):
            raise ValueError("Invalid task tool_args payload.")
        meta = payload.get("_meta", {})
        if not isinstance(meta, dict):
            meta = {}

        session = MessageSession.from_str(task.umo)
        cron_event = CronMessageEvent(
            context=self._context,
            session=session,
            message=str(
                tool_args.get("input") or f"[SubagentTask] {task.subagent_name}"
            ),
            extras={
                "background_note": meta.get("background_note")
                or f"Background task for subagent '{task.subagent_name}' finished."
            },
            message_type=session.message_type,
        )
        if role := meta.get("role"):
            cron_event.role = role

        from astrbot.core.astr_agent_context import (
            AgentContextWrapper,
            AstrAgentContext,
        )

        agent_ctx = AstrAgentContext(context=self._context, event=cron_event)
        wrapper = AgentContextWrapper(
            context=agent_ctx,
            tool_call_timeout=int(meta.get("tool_call_timeout", 3600)),
        )

        import mcp

        from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor

        tool_args = dict(tool_args)
        tool_args[
            "image_urls"
        ] = await FunctionToolExecutor._collect_handoff_image_urls(
            wrapper,
            tool_args.get("image_urls"),
        )
        result_text = ""
        async for r in FunctionToolExecutor._execute_handoff(
            handoff,
            wrapper,
            image_urls_prepared=True,
            **tool_args,
        ):
            if isinstance(r, mcp.types.CallToolResult):
                for content in r.content:
                    if isinstance(content, mcp.types.TextContent):
                        result_text += content.text + "\n"

        await FunctionToolExecutor._wake_main_agent_for_background_result(
            run_context=wrapper,
            task_id=task.task_id,
            tool_name=handoff.name,
            result_text=result_text,
            tool_args=tool_args,
            note=meta.get("background_note")
            or f"Background task for subagent '{task.subagent_name}' finished.",
            summary_name=f"Dedicated to subagent `{task.subagent_name}`",
            extra_result_fields={"subagent_name": task.subagent_name},
        )
        return result_text or "ok"
