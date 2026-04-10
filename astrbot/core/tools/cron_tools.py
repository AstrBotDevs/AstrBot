from datetime import datetime
from typing import Any

from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.tools.registry import builtin_tool


def _extract_job_session(job: Any) -> str | None:
    payload = getattr(job, "payload", None)
    if not isinstance(payload, dict):
        return None
    session = payload.get("session")
    return str(session) if session is not None else None


@builtin_tool
@dataclass
class FutureTaskTool(FunctionTool[AstrAgentContext]):
    name: str = "future_task"
    description: str = (
        "Manage your future tasks. "
        "Use action='create' to schedule a recurring cron task or one-time run_at task. "
        "Use action='list' to inspect existing tasks. "
        "Use action='delete' to remove a task by job_id."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "delete", "list"],
                    "description": "Action to perform. 'list' takes no parameters. 'delete' requires only 'job_id'.",
                },
                "name": {
                    "type": "string",
                    "description": "Optional label to recognize this future task.",
                },
                "cron_expression": {
                    "type": "string",
                    "description": "Cron expression defining recurring schedule, e.g., '0 8 * * *' or '0 23 * * mon-fri'. Prefer named weekdays like 'mon-fri' or 'sat,sun' instead of numeric day-of-week ranges such as '1-5' to avoid ambiguity across cron implementations.",
                },
                "note": {
                    "type": "string",
                    "description": "Detailed instructions for your future agent to execute when it wakes.",
                },
                "run_once": {
                    "type": "boolean",
                    "description": "Run only once and delete after execution. Use with run_at.",
                },
                "run_at": {
                    "type": "string",
                    "description": "ISO datetime for one-time execution, e.g., 2026-02-02T08:00:00+08:00. Use with run_once=true.",
                },
                "job_id": {
                    "type": "string",
                    "description": "For action='delete': the job_id returned when the future task was created.",
                },
            },
            "required": ["action"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        cron_mgr = context.context.context.cron_manager
        if cron_mgr is None:
            return "error: cron manager is not available."

        action = str(kwargs.get("action") or "").strip().lower()
        if action == "create":
            cron_expression = kwargs.get("cron_expression")
            run_at = kwargs.get("run_at")
            run_once = bool(kwargs.get("run_once", False))
            note = str(kwargs.get("note", "")).strip()
            name = str(kwargs.get("name") or "").strip() or "active_agent_task"

            if not note:
                return "error: note is required when action=create."
            if run_once and not run_at:
                return "error: run_at is required when run_once=true."
            if (not run_once) and not cron_expression:
                return "error: cron_expression is required when run_once=false."
            if run_once and cron_expression:
                cron_expression = None
            run_at_dt = None
            if run_at:
                try:
                    run_at_dt = datetime.fromisoformat(str(run_at))
                except Exception:
                    return "error: run_at must be ISO datetime, e.g., 2026-02-02T08:00:00+08:00"

            payload = {
                "session": context.context.event.unified_msg_origin,
                "sender_id": context.context.event.get_sender_id(),
                "note": note,
                "origin": "tool",
            }

            job = await cron_mgr.add_active_job(
                name=name,
                cron_expression=str(cron_expression) if cron_expression else None,
                payload=payload,
                description=note,
                run_once=run_once,
                run_at=run_at_dt,
            )
            next_run = job.next_run_time or run_at_dt
            suffix = (
                f"one-time at {next_run}"
                if run_once
                else f"expression '{cron_expression}' (next {next_run})"
            )
            return f"Scheduled future task {job.job_id} ({job.name}) {suffix}."

        current_umo = context.context.event.unified_msg_origin
        if action == "delete":
            job_id = kwargs.get("job_id")
            if not job_id:
                return "error: job_id is required when action=delete."
            job = await cron_mgr.db.get_cron_job(str(job_id))
            if not job:
                return f"error: cron job {job_id} not found."
            if _extract_job_session(job) != current_umo:
                return "error: you can only delete future tasks in the current umo."
            await cron_mgr.delete_job(str(job_id))
            return f"Deleted cron job {job_id}."

        if action == "list":
            jobs = [
                job
                for job in await cron_mgr.list_jobs()
                if _extract_job_session(job) == current_umo
            ]
            if not jobs:
                return "No cron jobs found."
            lines = []
            for j in jobs:
                lines.append(
                    f"{j.job_id} | {j.name} | {j.job_type} | run_once={getattr(j, 'run_once', False)} | enabled={j.enabled} | next={j.next_run_time}"
                )
            return "\n".join(lines)

        return "error: action must be one of create, delete, or list."


__all__ = [
    "FutureTaskTool",
]
