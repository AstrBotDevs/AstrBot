from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot import logger
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.cron.manager import CronJobSchedulingError
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


def _extract_job_sender(job: Any) -> str | None:
    payload = getattr(job, "payload", None)
    if not isinstance(payload, dict):
        return None
    sender_id = payload.get("sender_id")
    return str(sender_id) if sender_id is not None else None


def _job_belongs_to_current_sender(
    job: Any, current_umo: str, current_sender_id: str
) -> bool:
    return (
        _extract_job_session(job) == current_umo
        and _extract_job_sender(job) == current_sender_id
    )


def _parse_run_at(run_at: Any) -> datetime | None:
    if run_at in (None, ""):
        return None
    return datetime.fromisoformat(str(run_at))


def _get_configured_timezone(context: ContextWrapper[AstrAgentContext]):
    """Return the configured display timezone, or ``None`` on invalid input."""
    event = context.context.event
    get_config = getattr(context.context.context, "get_config", None)
    if not callable(get_config):
        return None, None
    config = get_config(umo=event.unified_msg_origin)
    if not isinstance(config, dict):
        return None, None
    tz_name = str(config.get("timezone") or "").strip()
    if not tz_name:
        return None, None
    try:
        return tz_name, ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        logger.warning("Invalid timezone %r in config; using system timezone.", tz_name)
        return None, None


def _display_next_run_time(value: datetime | None, tzinfo) -> datetime | None:
    """Convert a scheduler/DB UTC value to the configured display timezone."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(tzinfo) if tzinfo else value.astimezone()


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

    async def _create_future_task(
        self,
        context: ContextWrapper[AstrAgentContext],
        cron_mgr,
        event,
        kwargs: dict[str, Any],
    ) -> ToolExecResult:
        cron_expression = kwargs.get("cron_expression")
        run_at = kwargs.get("run_at")
        run_once = bool(kwargs.get("run_once", False))
        note = str(kwargs.get("note", "")).strip()
        name = str(kwargs.get("name") or "").strip() or "active_agent_task"
        if not note:
            return "error: note is required when action=create."
        if run_once and not run_at:
            return "error: run_at is required when run_once=true."
        if not run_once and not cron_expression:
            return "error: cron_expression is required when run_once=false."
        if run_once and cron_expression:
            cron_expression = None
        try:
            run_at_dt = _parse_run_at(run_at)
        except Exception:
            return "error: run_at must be ISO datetime, e.g., 2026-02-02T08:00:00+08:00"
        timezone_name, timezone_info = _get_configured_timezone(context)
        payload = {
            "session": event.unified_msg_origin,
            "sender_id": event.get_sender_id(),
            "note": note,
            "origin": "tool",
        }
        try:
            job = await cron_mgr.add_active_job(
                name=name,
                cron_expression=str(cron_expression) if cron_expression else None,
                payload=payload,
                description=note,
                timezone=timezone_name,
                run_once=run_once,
                run_at=run_at_dt,
            )
        except CronJobSchedulingError:
            return "error: failed to schedule task due to invalid configuration."
        next_run = (
            cron_mgr.get_next_run_time(job.job_id)
            if hasattr(cron_mgr, "get_next_run_time")
            else None
        ) or job.next_run_time
        if next_run is not None:
            next_run = _display_next_run_time(next_run, timezone_info)
        elif run_at_dt is not None:
            if run_at_dt.tzinfo is None and timezone_info:
                next_run = run_at_dt.replace(tzinfo=timezone_info)
            elif run_at_dt.tzinfo is not None and timezone_info:
                next_run = run_at_dt.astimezone(timezone_info)
        suffix = (
            f"one-time at {next_run}"
            if run_once
            else f"expression '{cron_expression}' (next {next_run})"
        )
        return f"Scheduled future task {job.job_id} ({job.name}) {suffix}."

    async def _delete_future_task(
        self, cron_mgr, job_id: object, current_umo: str, current_sender_id: str
    ) -> ToolExecResult:
        if not job_id:
            return "error: job_id is required when action=delete."
        job = await cron_mgr.db.get_cron_job(str(job_id))
        if not job:
            return f"error: cron job {job_id} not found."
        if not _job_belongs_to_current_sender(job, current_umo, current_sender_id):
            return "error: you can only delete your own future tasks."
        await cron_mgr.delete_job(str(job_id))
        return f"Deleted cron job {job_id}."

    async def _list_future_tasks(
        self,
        context: ContextWrapper[AstrAgentContext],
        cron_mgr,
        current_umo: str,
        current_sender_id: str,
    ) -> ToolExecResult:
        jobs = [
            job
            for job in await cron_mgr.list_jobs()
            if _job_belongs_to_current_sender(job, current_umo, current_sender_id)
        ]
        if not jobs:
            return "No cron jobs found."
        _, timezone_info = _get_configured_timezone(context)
        return "\n".join(
            f"{job.job_id} | {job.name} | {job.job_type} | "
            f"run_once={getattr(job, 'run_once', False)} | enabled={job.enabled} | "
            f"next={_display_next_run_time(job.next_run_time, timezone_info)}"
            for job in jobs
        )

    async def _edit_future_task(
        self,
        cron_mgr,
        kwargs: dict[str, Any],
        current_umo: str,
        current_sender_id: str,
    ) -> ToolExecResult:
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
        if not _job_belongs_to_current_sender(job, current_umo, current_sender_id):
            return "error: you can only edit your own future tasks."

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
        ) or None
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
        updates.update(
            run_once=run_once,
            cron_expression=cron_expression,
            payload=payload,
        )
        try:
            job = await cron_mgr.update_job(str(job_id), **updates)
        except CronJobSchedulingError:
            return "error: failed to update task due to invalid configuration."
        if not job:
            return f"error: cron job {job_id} not found."
        return f"Updated future task {job.job_id} ({job.name})."

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        cron_mgr = context.context.context.cron_manager
        if cron_mgr is None:
            return "error: cron manager is not available."

        action = str(kwargs.get("action") or "").strip().lower()
        if action == "create":
            return await self._create_future_task(
                context, cron_mgr, context.context.event, kwargs
            )

        current_umo = context.context.event.unified_msg_origin
        current_sender_id = str(context.context.event.get_sender_id())
        if action == "edit":
            return await self._edit_future_task(
                cron_mgr, kwargs, current_umo, current_sender_id
            )

        if action == "delete":
            return await self._delete_future_task(
                cron_mgr,
                kwargs.get("job_id"),
                current_umo,
                current_sender_id,
            )

        if action == "list":
            return await self._list_future_tasks(
                context, cron_mgr, current_umo, current_sender_id
            )

        return "error: action must be one of create, edit, delete, or list."


__all__ = [
    "FutureTaskTool",
]
