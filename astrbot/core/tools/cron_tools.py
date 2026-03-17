from datetime import datetime
from typing import Any

from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext


def _extract_job_session(job: Any) -> str | None:
    payload = getattr(job, "payload", None)
    if not isinstance(payload, dict):
        return None
    session = payload.get("session")
    return str(session) if session is not None else None


@dataclass
class CreateActiveCronTool(FunctionTool[AstrAgentContext]):
    name: str = "create_future_task"
    description: str = (
        "Create a future task for your future. Supports recurring cron expressions or one-time run_at datetime. "
        "Use this when you or the user want scheduled follow-up or proactive actions."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "cron_expression": {
                    "type": "string",
                    "description": "Cron expression defining recurring schedule (e.g., '0 8 * * *' or '0 23 * * mon-fri'). Prefer named weekdays like 'mon-fri' or 'sat,sun' instead of numeric day-of-week ranges such as '1-5' to avoid ambiguity across cron implementations.",
                },
                "run_at": {
                    "type": "string",
                    "description": "ISO datetime for one-time execution, e.g., 2026-02-02T08:00:00+08:00. Use with run_once=true.",
                },
                "note": {
                    "type": "string",
                    "description": "Detailed instructions for your future agent to execute when it wakes.",
                },
                "name": {
                    "type": "string",
                    "description": "Optional label to recognize this future task.",
                },
                "run_once": {
                    "type": "boolean",
                    "description": "If true, the task will run only once and then be deleted. Use run_at to specify the time.",
                },
            },
            "required": ["note"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        cron_mgr = context.context.context.cron_manager
        if cron_mgr is None:
            return "error: cron manager is not available."

        cron_expression = kwargs.get("cron_expression")
        run_at = kwargs.get("run_at")
        run_once = bool(kwargs.get("run_once", False))
        note = str(kwargs.get("note", "")).strip()
        name = str(kwargs.get("name") or "").strip() or "active_agent_task"

        if not note:
            return "error: note is required."
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


@dataclass
class DeleteCronJobTool(FunctionTool[AstrAgentContext]):
    name: str = "delete_future_task"
    description: str = "Delete a future task (cron job) by its job_id."
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "The job_id returned when the job was created.",
                }
            },
            "required": ["job_id"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        cron_mgr = context.context.context.cron_manager
        if cron_mgr is None:
            return "error: cron manager is not available."
        current_umo = context.context.event.unified_msg_origin
        job_id = kwargs.get("job_id")
        if not job_id:
            return "error: job_id is required."
        job = await cron_mgr.db.get_cron_job(str(job_id))
        if not job:
            return f"error: cron job {job_id} not found."
        if _extract_job_session(job) != current_umo:
            return "error: you can only delete future tasks in the current umo."
        await cron_mgr.delete_job(str(job_id))
        return f"Deleted cron job {job_id}."


@dataclass
class ListCronJobsTool(FunctionTool[AstrAgentContext]):
    name: str = "list_future_tasks"
    description: str = "List existing future tasks (cron jobs) for inspection."
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "job_type": {
                    "type": "string",
                    "description": "Optional filter: basic or active_agent.",
                }
            },
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        cron_mgr = context.context.context.cron_manager
        if cron_mgr is None:
            return "error: cron manager is not available."
        current_umo = context.context.event.unified_msg_origin
        job_type = kwargs.get("job_type")
        jobs = [
            job
            for job in await cron_mgr.list_jobs(job_type)
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


@dataclass
class UpdateCronTool(FunctionTool[AstrAgentContext]):
    name: str = "update_future_task"
    description: str = (
        "Update an existing future task (cron job). "
        "You can modify the schedule, note, name, enabled state, etc."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "The job_id of the task to update.",
                },
                "name": {
                    "type": "string",
                    "description": "New name/label for the task.",
                },
                "cron_expression": {
                    "type": "string",
                    "description": "New cron expression for recurring tasks (e.g. '0 8 * * *').",
                },
                "run_at": {
                    "type": "string",
                    "description": "New ISO datetime for one-time tasks, e.g. 2026-03-20T10:00:00+08:00.",
                },
                "note": {
                    "type": "string",
                    "description": "New task instructions/description.",
                },
                "enabled": {
                    "type": "boolean",
                    "description": "Enable or disable the task.",
                },
                "timezone": {
                    "type": "string",
                    "description": "Timezone, e.g. Asia/Shanghai.",
                },
                "run_once": {
                    "type": "boolean",
                    "description": "Switch between one-time (true) and recurring (false) task types.",
                },
            },
            "required": ["job_id"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        cron_mgr = context.context.context.cron_manager
        if cron_mgr is None:
            return "error: cron manager is not available."
        current_umo = context.context.event.unified_msg_origin
        job_id = kwargs.get("job_id")
        if not job_id:
            return "error: job_id is required."
        job = await cron_mgr.db.get_cron_job(str(job_id))
        if not job:
            return f"error: cron job {job_id} not found."
        if _extract_job_session(job) != current_umo:
            return "error: you can only update future tasks in the current session."

        updates: dict[str, Any] = {}
        if "name" in kwargs:
            updates["name"] = str(kwargs["name"])
        if "cron_expression" in kwargs:
            updates["cron_expression"] = str(kwargs["cron_expression"])
        if "enabled" in kwargs:
            updates["enabled"] = bool(kwargs["enabled"])
        if "timezone" in kwargs:
            updates["timezone"] = str(kwargs["timezone"])
        if "run_once" in kwargs:
            updates["run_once"] = bool(kwargs["run_once"])

        # Update payload fields (note, run_at)
        if "note" in kwargs or "run_at" in kwargs:
            payload = dict(job.payload) if job.payload else {}
            if "note" in kwargs:
                note = kwargs.get("note")
                payload["note"] = str(note) if note is not None else ""
                updates["description"] = payload["note"]
            if "run_at" in kwargs:
                run_at = kwargs.get("run_at")
                if run_at:
                    try:
                        datetime.fromisoformat(str(run_at))
                    except Exception:
                        return "error: run_at must be ISO datetime."
                    payload["run_at"] = str(run_at)
                else:
                    payload.pop("run_at", None)
            updates["payload"] = payload

        if not updates:
            return "error: no fields to update."

        updated = await cron_mgr.update_job(str(job_id), **updates)
        if not updated:
            return f"error: failed to update cron job {job_id}."
        return f"Updated future task {job_id} ({updated.name}) successfully."


@dataclass
class GetCronDetailTool(FunctionTool[AstrAgentContext]):
    name: str = "get_future_task_detail"
    description: str = (
        "Get detailed information about a specific future task (cron job), "
        "including its full note/instructions, schedule, payload, and execution history."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "The job_id of the task to inspect.",
                }
            },
            "required": ["job_id"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        cron_mgr = context.context.context.cron_manager
        if cron_mgr is None:
            return "error: cron manager is not available."
        current_umo = context.context.event.unified_msg_origin
        job_id = kwargs.get("job_id")
        if not job_id:
            return "error: job_id is required."
        job = await cron_mgr.db.get_cron_job(str(job_id))
        if not job:
            return f"error: cron job {job_id} not found."
        if _extract_job_session(job) != current_umo:
            return "error: you can only view future tasks in the current session."

        payload = job.payload or {}
        lines = [
            f"job_id: {job.job_id}",
            f"name: {job.name}",
            f"type: {job.job_type}",
            f"description: {job.description or 'N/A'}",
            f"note: {payload.get('note', 'N/A')}",
            f"cron_expression: {job.cron_expression or 'N/A'}",
            f"timezone: {job.timezone or 'system default'}",
            f"run_once: {getattr(job, 'run_once', False)}",
            f"run_at: {payload.get('run_at', 'N/A')}",
            f"enabled: {job.enabled}",
            f"status: {job.status}",
            f"next_run_time: {job.next_run_time or 'N/A'}",
            f"last_run_at: {job.last_run_at or 'N/A'}",
            f"last_error: {job.last_error or 'none'}",
            f"created_at: {getattr(job, 'created_at', 'N/A')}",
            f"session: {payload.get('session', 'N/A')}",
        ]
        return "\n".join(lines)


CREATE_CRON_JOB_TOOL = CreateActiveCronTool()
DELETE_CRON_JOB_TOOL = DeleteCronJobTool()
LIST_CRON_JOBS_TOOL = ListCronJobsTool()
UPDATE_CRON_JOB_TOOL = UpdateCronTool()
GET_CRON_DETAIL_TOOL = GetCronDetailTool()

__all__ = [
    "CREATE_CRON_JOB_TOOL",
    "DELETE_CRON_JOB_TOOL",
    "LIST_CRON_JOBS_TOOL",
    "UPDATE_CRON_JOB_TOOL",
    "GET_CRON_DETAIL_TOOL",
    "CreateActiveCronTool",
    "DeleteCronJobTool",
    "ListCronJobsTool",
    "UpdateCronTool",
    "GetCronDetailTool",
]
