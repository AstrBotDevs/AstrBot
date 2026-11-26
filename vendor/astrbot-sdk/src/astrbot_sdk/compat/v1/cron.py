"""Legacy cron_manager facade running plugin jobs on the Host scheduler.

In-process, plugins register jobs on the core CronJobManager (and its
APScheduler) and the handler fires inside the same loop. Isolated, job
handlers stay in the Runner: registration goes through the cron.schedule
capability, and each firing is delivered back through invoke_cron.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from types import SimpleNamespace
from typing import Any

from .errors import IsolationUnsupportedError

_LOGGER = logging.getLogger("astrbot.compat")


def _serialize_trigger(trigger: Any, trigger_args: dict[str, Any]) -> dict[str, Any]:
    """Serialize an APScheduler trigger (or alias) to a JSON-safe spec.

    Args:
        trigger: Trigger instance or alias string ("date"/"cron"/"interval").
        trigger_args: Constructor kwargs used with alias triggers.

    Returns:
        {"type": kind, "params": {...}} spec the Host rebuilds.

    Raises:
        IsolationUnsupportedError: The trigger type cannot cross the RPC.
    """
    if isinstance(trigger, str):
        return {"type": trigger, "params": dict(trigger_args)}
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.date import DateTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    if isinstance(trigger, DateTrigger):
        return {
            "type": "date",
            "params": {"run_date": trigger.run_date.isoformat()},
        }
    if isinstance(trigger, CronTrigger):
        params = {field.name: str(field) for field in trigger.fields}
        params["timezone"] = str(trigger.timezone)
        return {"type": "cron", "params": params}
    if isinstance(trigger, IntervalTrigger):
        seconds = trigger.interval.total_seconds()
        params: dict[str, Any] = {"seconds": seconds}
        if trigger.start_date is not None:
            params["start_date"] = trigger.start_date.isoformat()
        if trigger.end_date is not None:
            params["end_date"] = trigger.end_date.isoformat()
        return {"type": "interval", "params": params}
    raise IsolationUnsupportedError(
        f"cron trigger {type(trigger).__name__} is unavailable in isolated "
        "legacy mode; use date/cron/interval triggers."
    )


def _job_namespace(data: dict[str, Any]) -> SimpleNamespace:
    """Convert a serialized cron job dict into attribute access."""
    return SimpleNamespace(**data)


class SchedulerFacade:
    """Sync APScheduler-like facade; registrations are fire-and-forget RPCs.

    APScheduler's add_job/remove_job are sync, so the RPC cannot be awaited
    inline; delivery failures surface in the Runner log instead.
    """

    def __init__(self, facade_context: Any) -> None:
        """Initialize the facade.

        Args:
            facade_context: Legacy Context facade used to reach the Host.
        """
        self._facade_context = facade_context
        self._jobs: dict[str, SimpleNamespace] = {}

    @property
    def running(self) -> bool:
        """Always True; the Host scheduler lifecycle is not plugin-managed."""
        return True

    def start(self, *args: Any, **kwargs: Any) -> None:
        """No-op; the Host scheduler is already running."""

    def shutdown(self, *args: Any, **kwargs: Any) -> None:
        """No-op; the Host scheduler lifecycle is not plugin-managed."""

    def add_job(
        self,
        func: Any,
        trigger: Any = None,
        args: Any = None,
        kwargs: Any = None,
        id: str | None = None,
        name: str | None = None,
        **trigger_args: Any,
    ) -> SimpleNamespace:
        """Register one job on the Host scheduler (sync, fire-and-forget).

        Mirrors APScheduler: returns a job-like object immediately. Known
        job options (id/name/replace_existing/misfire_grace_time/coalesce/
        max_instances) are forwarded; remaining kwargs build alias triggers.

        Args:
            func: Plugin handler called on each firing.
            trigger: Trigger instance or alias string.
            args: Positional args for func.
            kwargs: Keyword args for func.
            id: Optional job ID; generated when omitted.
            name: Optional display name.
            **trigger_args: Trigger kwargs for alias triggers, plus job options.

        Returns:
            Job-like namespace with at least id and name.
        """
        job_id = id or uuid.uuid4().hex
        handler_id = f"cron:{uuid.uuid4().hex}"
        self._facade_context._ctx.cron_handlers[handler_id] = func
        options = {
            key: trigger_args.pop(key)
            for key in (
                "replace_existing",
                "misfire_grace_time",
                "coalesce",
                "max_instances",
            )
            if key in trigger_args
        }
        options["id"] = job_id
        if name is not None:
            options["name"] = name
        payload = {
            "handler_id": handler_id,
            "trigger": _serialize_trigger(trigger or "date", trigger_args),
            "args": list(args) if args else [],
            "kwargs": dict(kwargs) if kwargs else {},
            "options": options,
        }
        self._fire("add_scheduler_job", payload)
        job = SimpleNamespace(id=job_id, name=name or getattr(func, "__name__", ""))
        self._jobs[job_id] = job
        return job

    def remove_job(self, job_id: str, *args: Any, **kwargs: Any) -> None:
        """Remove one job from the Host scheduler (sync, fire-and-forget)."""
        self._jobs.pop(str(job_id), None)
        self._fire("remove_job", {"job_id": str(job_id)})

    def get_job(self, job_id: str, *args: Any, **kwargs: Any) -> Any:
        """Return the locally tracked job namespace, or None."""
        return self._jobs.get(str(job_id))

    def get_jobs(self, *args: Any, **kwargs: Any) -> list:
        """Return locally tracked job namespaces."""
        return list(self._jobs.values())

    def remove_all_jobs(self, *args: Any, **kwargs: Any) -> None:
        """Remove every locally tracked job (sync, fire-and-forget)."""
        for job_id in list(self._jobs):
            self.remove_job(job_id)

    def _fire(self, operation: str, payload: dict[str, Any]) -> None:
        """Send one cron.schedule RPC without blocking the caller."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            _LOGGER.error(
                "cron.schedule %s dropped: no running event loop",
                operation,
            )
            return
        task = loop.create_task(
            self._facade_context._ctx._invoke_capability(
                "cron.schedule",
                operation,
                payload,
            )
        )
        task.add_done_callback(self._log_failure)

    @staticmethod
    def _log_failure(task: asyncio.Task) -> None:
        """Surface fire-and-forget cron RPC failures to the log."""
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            _LOGGER.error("cron.schedule call failed: %s", exc)


class CronManagerFacade:
    """Legacy cron_manager facade over the cron.schedule capability."""

    def __init__(self, facade_context: Any) -> None:
        """Initialize the facade.

        Args:
            facade_context: Legacy Context facade used to reach the Host.
        """
        self._facade_context = facade_context
        self.scheduler = SchedulerFacade(facade_context)
        self._handler_by_job: dict[str, str] = {}

    async def add_basic_job(
        self,
        *,
        name: str,
        cron_expression: str,
        handler: Any,
        description: str | None = None,
        timezone: str | None = None,
        payload: dict | None = None,
        enabled: bool = True,
        persistent: bool = True,
    ) -> SimpleNamespace:
        """Register one cron job on the Host CronJobManager.

        Mirrors ``context.cron_manager.add_basic_job``; the handler fires in
        the Runner through invoke_cron.
        """
        handler_id = f"cron:{uuid.uuid4().hex}"
        self._facade_context._ctx.cron_handlers[handler_id] = handler
        result = await self._facade_context._ctx._invoke_capability(
            "cron.schedule",
            "add_basic_job",
            {
                "handler_id": handler_id,
                "name": name,
                "cron_expression": cron_expression,
                "description": description,
                "timezone": timezone,
                "payload": payload,
                "enabled": enabled,
                "persistent": persistent,
            },
        )
        job = _job_namespace(dict((result or {}).get("job") or {}))
        job_id = getattr(job, "job_id", None)
        if job_id:
            self._handler_by_job[str(job_id)] = handler_id
        return job

    async def delete_job(self, job_id: str) -> None:
        """Delete one cron job on the Host."""
        await self._facade_context._ctx._invoke_capability(
            "cron.schedule",
            "delete_job",
            {"job_id": str(job_id)},
        )
        handler_id = self._handler_by_job.pop(str(job_id), None)
        if handler_id:
            self._facade_context._ctx.cron_handlers.pop(handler_id, None)

    async def list_jobs(self, job_type: str | None = None) -> list:
        """List cron jobs registered on the Host."""
        result = await self._facade_context._ctx._invoke_capability(
            "cron.schedule",
            "list_jobs",
            {"job_type": job_type},
        )
        return [_job_namespace(dict(item)) for item in (result or {}).get("jobs") or []]

    async def run_job_now(self, job_id: str) -> None:
        """Immediate manual runs are unsupported in isolated mode."""
        raise IsolationUnsupportedError(
            "cron_manager.run_job_now is unavailable in isolated legacy mode."
        )
