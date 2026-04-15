from datetime import datetime
from typing import Any

from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.tools.registry import builtin_tool

_CRON_TOOL_CONFIG = {
    "provider_settings.proactive_capability.add_cron_tools": True,
}


def _extract_job_session(job: Any) -> str | None:
    payload = getattr(job, "payload", None)
    if not isinstance(payload, dict):
        return None
    session = payload.get("session")
    return str(session) if session is not None else None


def _parse_run_at(run_at: Any) -> datetime | None:
    if run_at in (None, ""):
        return None
    return datetime.fromisoformat(str(run_at))


@builtin_tool(config=_CRON_TOOL_CONFIG)
@dataclass
class FutureTaskTool(FunctionTool[AstrAgentContext]):
    name: str = "future_task"
    description: str = (
        "Manage your future tasks. "
        "Use action='create' to schedule a recurring cron task or one-time run_at task. "
        "Use action='edit' to update an existing task. "
        "Use action='list' to inspect existing tasks. "
        "Use action='delete' to remove a task by job_id."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "edit", "delete", "list"],
                    "description": "Action to perform. 'list' takes no parameters. 'delete' requires only 'job_id'. 'edit' requires 'job_id' plus the fields to change.",
                },
                "name": {
                    "type": "string",
                    "description": "Optional task label.",
                },
                "cron_expression": {
                    "type": "string",
                    "description": "Cron expression for a recurring schedule, e.g. '0 8 * * *' or '0 23 * * mon-fri'. Prefer named weekdays like 'mon-fri' or 'sat,sun' over numeric ranges like '1-5'.",
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
                    "description": "ISO datetime for one-time execution, e.g. 2026-02-02T08:00:00+08:00.",
                },
                "job_id": {
                    "type": "string",
                    "description": "Task ID. Required for 'delete' and 'edit'.",
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
            try:
                run_at_dt = _parse_run_at(run_at)
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
        if action == "edit":
            job_id = kwargs.get("job_id")
            if not job_id:
                return "error: job_id is required when action=edit."
            if not any(
                key in kwargs
                for key in ("name", "note", "run_once", "cron_expression", "run_at")
            ):
                return "error: no editable fields were provided."

            job = await cron_mgr.db.get_cron_job(str(job_id))
            if not job:
                return f"error: cron job {job_id} not found."
            if _extract_job_session(job) != current_umo:
                return "error: you can only edit future tasks in the current umo."

            payload = dict(job.payload) if isinstance(job.payload, dict) else {}

            updates: dict[str, Any] = {}
            if "name" in kwargs:
                name = str(kwargs.get("name") or "").strip()
                if not name:
                    return "error: name cannot be empty when action=edit."
                updates["name"] = name

            if "note" in kwargs:
                note = str(kwargs.get("note") or "").strip()
                if not note:
                    return "error: note cannot be empty when action=edit."
                payload["note"] = note
                updates["description"] = note

            current_run_at = payload.get("run_at")
            run_once = (
                bool(kwargs["run_once"]) if "run_once" in kwargs else bool(job.run_once)
            )
            cron_expression = (
                str(kwargs.get("cron_expression") or "").strip()
                if "cron_expression" in kwargs
                else job.cron_expression
            )
            cron_expression = cron_expression or None

            try:
                run_at_dt = (
                    _parse_run_at(kwargs.get("run_at"))
                    if "run_at" in kwargs
                    else _parse_run_at(current_run_at)
                )
            except Exception:
                return "error: run_at must be ISO datetime, e.g., 2026-02-02T08:00:00+08:00"

            if run_once:
                if run_at_dt is None:
                    return "error: run_at is required when run_once=true."
                cron_expression = None
                payload["run_at"] = run_at_dt.isoformat()
            else:
                if not cron_expression:
                    return "error: cron_expression is required when run_once=false."
                payload.pop("run_at", None)

            updates["run_once"] = run_once
            updates["cron_expression"] = cron_expression
            updates["payload"] = payload

            job = await cron_mgr.update_job(str(job_id), **updates)
            if not job:
                return f"error: cron job {job_id} not found."
            return f"Updated future task {job.job_id} ({job.name})."

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

        return "error: action must be one of create, edit, delete, or list."


__all__ = [
    "FutureTaskTool",
]
