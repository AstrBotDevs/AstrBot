import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from astrbot import logger
from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import CronJob

if TYPE_CHECKING:
    from astrbot.core.star.context import Context


_CRONTAB_WEEKDAY_NAMES = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")
_CRONTAB_WEEKDAY_PATTERN = re.compile(r"^(?:(\*)|(\d+)(?:-(\d+))?)(?:/(\d+))?$")


PROACTIVE_AGENT_CRON_WOKE_USER_PROMPT = (
    "<system_reminder>\n"
    "# CRON JOB CONTEXT\n"
    "The following object describes the scheduled task that triggered you:\n"
    "{cron_job}\n\n"
    "You are now responding to a scheduled task. "
    "Do not greet the user or ask questions unless strictly necessary. "
    "Use the existing conversation and available tools to complete the task. "
    "If contacting the user, explain why and refer to the task naturally. "
    "Proceed according to your system instructions. "
    "Output using same language as previous conversation. "
    "After completing your task, summarize and output your actions and results."
    "\n</system_reminder>"
)


def _normalize_crontab_day_of_week(day_of_week: str) -> str:
    """Normalize standard crontab weekdays for APScheduler.

    APScheduler treats numeric weekdays as Monday=0, while standard crontab and
    AstrBot's WebUI use Sunday=0/7. Numeric weekday fields are expanded to
    weekday names so the scheduled day remains unambiguous.

    Args:
        day_of_week: The day-of-week field from a five-part crontab expression.

    Returns:
        A day-of-week field compatible with APScheduler.

    Raises:
        ValueError: If a numeric weekday value or step is outside the supported
            crontab range.
    """
    normalized_parts: list[str] = []
    for raw_part in day_of_week.split(","):
        part = raw_part.strip().lower()
        match = _CRONTAB_WEEKDAY_PATTERN.fullmatch(part)
        if not match:
            normalized_parts.append(part)
            continue

        wildcard, start_text, end_text, step_text = match.groups()
        step = int(step_text or "1")
        if step < 1:
            raise ValueError("day_of_week step must be greater than 0")

        if wildcard:
            if step == 1:
                normalized_parts.append("*")
                continue
            values = range(0, 7, step)
        else:
            start = int(start_text)
            end = int(end_text) if end_text is not None else None
            if start < 0 or start > 7 or (end is not None and (end < 0 or end > 7)):
                raise ValueError("day_of_week values must be between 0 and 7")
            if end is not None and start > end:
                raise ValueError("day_of_week range start must not exceed end")
            if end is None:
                end = 7 if step_text else start
            values = range(start, end + 1, step)

        weekdays: list[int] = []
        for value in values:
            weekday = 0 if value == 7 else value
            if weekday not in weekdays:
                weekdays.append(weekday)

        if len(weekdays) == 7:
            normalized_parts.append("*")
        else:
            normalized_parts.extend(_CRONTAB_WEEKDAY_NAMES[value] for value in weekdays)

    return ",".join(normalized_parts)


class CronJobSchedulingError(Exception):
    """Raised when a cron job fails to be scheduled."""

    pass


class CronJobManager:
    """Central scheduler for BasicCronJob and ActiveAgentCronJob."""

    def __init__(self, db: BaseDatabase) -> None:
        self.db = db
        self.scheduler = AsyncIOScheduler()
        self._basic_handlers: dict[str, Callable[..., Any]] = {}
        self._lock = asyncio.Lock()
        self._started = False
        # The scheduler may start early via _schedule_job; track DB sync separately.
        self._db_synced = False
        self._running_tasks: dict[str, set[asyncio.Task]] = {}
        # Ref-counted deletion markers. A run must not register after deletion
        # has started, and nested/concurrent deletes must not clear the marker
        # before the last deletion finishes.
        self._deleting_jobs: dict[str, int] = {}

    async def start(self, ctx: "Context") -> None:
        self.ctx: Context = ctx  # star context
        async with self._lock:
            if self._db_synced:
                return
            if not self._started:
                self.scheduler.start()
                self._started = True
            await self.sync_from_db()
            self._db_synced = True

    async def shutdown(self) -> None:
        async with self._lock:
            if not self._started:
                return
            self.scheduler.shutdown(wait=False)
            await asyncio.sleep(0)
            self._started = False
            self._db_synced = False

    async def sync_from_db(self) -> None:
        jobs = await self.db.list_cron_jobs()
        for job in jobs:
            if not job.enabled or not job.persistent:
                continue
            if job.job_type == "basic" and job.job_id not in self._basic_handlers:
                logger.warning(
                    "Skip scheduling basic cron job %s due to missing handler.",
                    job.job_id,
                )
                continue
            try:
                self._schedule_job(job)
            except CronJobSchedulingError:
                continue  # Error already logged in _schedule_job

    async def add_basic_job(
        self,
        *,
        name: str,
        cron_expression: str,
        handler: Callable[..., Any | Awaitable[Any]],
        description: str | None = None,
        timezone: str | None = None,
        payload: dict | None = None,
        enabled: bool = True,
        persistent: bool = False,
    ) -> CronJob:
        job = await self.db.create_cron_job(
            name=name,
            job_type="basic",
            cron_expression=cron_expression,
            timezone=timezone,
            payload=payload or {},
            description=description,
            enabled=enabled,
            persistent=persistent,
        )
        self._basic_handlers[job.job_id] = handler
        if enabled:
            self._schedule_job(job)
        return job

    async def add_active_job(
        self,
        *,
        name: str,
        cron_expression: str | None,
        payload: dict,
        description: str | None = None,
        timezone: str | None = None,
        enabled: bool = True,
        persistent: bool = True,
        run_once: bool = False,
        run_at: datetime | None = None,
    ) -> CronJob:
        # If run_once with run_at, store run_at in payload for later reference.
        if run_once and run_at:
            payload = {**payload, "run_at": run_at.isoformat()}
        job = await self.db.create_cron_job(
            name=name,
            job_type="active_agent",
            cron_expression=cron_expression,
            timezone=timezone,
            payload=payload,
            description=description,
            enabled=enabled,
            persistent=persistent,
            run_once=run_once,
        )
        if enabled:
            self._schedule_job(job)
        return job

    async def update_job(self, job_id: str, **kwargs) -> CronJob | None:
        current_job = await self.db.get_cron_job(job_id)
        if not current_job:
            return None
        candidate = current_job.model_copy(update=kwargs)
        if candidate.enabled:
            # Invalid edits must not overwrite the durable job or remove its
            # working schedule. Disabled legacy jobs can still be corrected.
            self._build_trigger(candidate)
        job = await self.db.update_cron_job(job_id, **kwargs)
        if not job:
            return None
        self._remove_scheduled(job_id)
        if job.enabled:
            self._schedule_job(job)
        return job

    async def delete_job(self, job_id: str) -> None:
        """Remove a schedule and drain its active runs before deleting its row.

        Runs that have already started are cancelled and drained. Runs that
        start after deletion begins return without executing.

        Args:
            job_id: Job to delete, including any currently executing run.
        """
        self._deleting_jobs[job_id] = self._deleting_jobs.get(job_id, 0) + 1
        try:
            self._remove_scheduled(job_id)
            self._basic_handlers.pop(job_id, None)
            tasks = [
                task
                for task in self._running_tasks.get(job_id, set())
                if task is not asyncio.current_task() and not task.done()
            ]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await self.db.delete_cron_job(job_id)
        finally:
            remaining = self._deleting_jobs.get(job_id, 0) - 1
            if remaining > 0:
                self._deleting_jobs[job_id] = remaining
            else:
                self._deleting_jobs.pop(job_id, None)

    async def list_jobs(self, job_type: str | None = None) -> list[CronJob]:
        return await self.db.list_cron_jobs(job_type)

    def _remove_scheduled(self, job_id: str) -> None:
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

    def _build_trigger(self, job: CronJob) -> CronTrigger | DateTrigger:
        """Validate a job's timing without modifying stored or scheduled jobs.

        Args:
            job: Candidate job definition, including one-shot payload fields.

        Returns:
            A trigger using the same timezone and weekday rules as scheduling.

        Raises:
            CronJobSchedulingError: If the schedule cannot be parsed.
        """
        try:
            tzinfo = None
            if job.timezone:
                try:
                    tzinfo = ZoneInfo(job.timezone)
                except Exception:
                    logger.warning(
                        "Invalid timezone %s for cron job %s, fallback to system.",
                        job.timezone,
                        job.job_id,
                    )
            if job.run_once:
                run_at_str = None
                if isinstance(job.payload, dict):
                    run_at_str = job.payload.get("run_at")
                run_at_str = run_at_str or job.cron_expression
                if not run_at_str:
                    raise ValueError("run_once job missing run_at timestamp")
                run_at = datetime.fromisoformat(run_at_str)
                if run_at.tzinfo is None and tzinfo is not None:
                    run_at = run_at.replace(tzinfo=tzinfo)
                trigger = DateTrigger(run_date=run_at, timezone=tzinfo)
            else:
                if not job.cron_expression:
                    raise ValueError("recurring job missing cron_expression")
                minute, hour, day, month, day_of_week = job.cron_expression.split()
                normalized_cron_expression = " ".join(
                    [
                        minute,
                        hour,
                        day,
                        month,
                        _normalize_crontab_day_of_week(day_of_week),
                    ]
                )
                trigger = CronTrigger.from_crontab(
                    normalized_cron_expression, timezone=tzinfo
                )
            return trigger
        except (ValueError, TypeError) as e:
            logger.exception("Failed to build trigger for cron job %s", job.job_id)
            raise CronJobSchedulingError(str(e)) from e

    def _schedule_job(self, job: CronJob) -> None:
        if not self._started:
            self.scheduler.start()
            self._started = True
        try:
            trigger = self._build_trigger(job)
            self.scheduler.add_job(
                self._run_job,
                id=job.job_id,
                trigger=trigger,
                args=[job.job_id],
                replace_existing=True,
                misfire_grace_time=300,
            )
            asyncio.create_task(
                self.db.update_cron_job(
                    job.job_id, next_run_time=self._get_next_run_time(job.job_id)
                )
            )
        except (ValueError, TypeError) as e:
            logger.exception("Failed to schedule cron job %s", job.job_id)
            raise CronJobSchedulingError(str(e)) from e

    def _get_next_run_time(self, job_id: str):
        aps_job = self.scheduler.get_job(job_id)
        if not aps_job or aps_job.next_run_time is None:
            return None
        return aps_job.next_run_time.astimezone(timezone.utc)

    def get_next_run_time(self, job_id: str) -> datetime | None:
        """Read the live next-run time straight from the scheduler.

        The DB copy of ``next_run_time`` is written via a fire-and-forget
        task in ``_schedule_job``, so it can still be stale/None right after
        ``add_active_job``/``update_job`` return. The scheduler itself is
        updated synchronously, so callers that need an immediate answer
        should use this instead of the job row's ``next_run_time`` field.

        Args:
            job_id: The scheduled job's ID.

        Returns:
            The job's next scheduled run time in UTC, or None if the job
            is not currently scheduled.
        """
        return self._get_next_run_time(job_id)

    async def run_job_now(self, job_id: str) -> None:
        await self._run_job(job_id, ignore_enabled=True, delete_run_once=False)

    async def _run_job(
        self,
        job_id: str,
        *,
        ignore_enabled: bool = False,
        delete_run_once: bool = True,
    ) -> None:
        task = asyncio.current_task()
        if task is None or job_id in self._deleting_jobs:
            return
        # Register before the first await so delete_job always snapshots a run
        # that has passed the deletion-marker check.
        self._running_tasks.setdefault(job_id, set()).add(task)
        try:
            job = await self.db.get_cron_job(job_id)
            if not job or (not job.enabled and not ignore_enabled):
                return
            start_time = datetime.now(timezone.utc)
            await self.db.update_cron_job(
                job_id, status="running", last_run_at=start_time, last_error=None
            )
            status = "completed"
            last_error = None
            try:
                if job.job_type == "basic":
                    await self._run_basic_job(job)
                elif job.job_type == "active_agent":
                    await self._run_active_agent_job(job, start_time=start_time)
                    status = "dispatched"
                else:
                    raise ValueError(f"Unknown cron job type: {job.job_type}")
            except asyncio.CancelledError:
                status = "cancelled"
                raise
            except Exception as e:  # noqa: BLE001
                status = "failed"
                last_error = str(e)
                logger.error(f"Cron job {job_id} failed: {e!s}", exc_info=True)
            finally:
                next_run = self._get_next_run_time(job_id)
                await self.db.update_cron_job(
                    job_id,
                    status=status,
                    last_run_at=start_time,
                    last_error=last_error,
                    next_run_time=next_run,
                )
                if job.run_once and delete_run_once and status != "cancelled":
                    # One-shot runs remove themselves, excluding their own task.
                    await self.delete_job(job_id)
        finally:
            running = self._running_tasks.get(job_id)
            if running is not None:
                running.discard(task)
                if not running:
                    del self._running_tasks[job_id]

    async def _run_basic_job(self, job: CronJob) -> None:
        handler = self._basic_handlers.get(job.job_id)
        if not handler:
            raise RuntimeError(f"Basic cron job handler not found for {job.job_id}")
        payload = job.payload or {}
        result = handler(**payload) if payload else handler()
        if asyncio.iscoroutine(result):
            await result

    async def _run_active_agent_job(self, job: CronJob, start_time: datetime) -> None:
        payload = job.payload or {}
        umo = str(payload.get("session") or "").strip()
        if not umo:
            raise ValueError(f"Cron job {job.job_id!r} has no target UMO.")
        note = payload.get("note") or job.description or job.name

        extras = {
            "cron_job": {
                "id": job.job_id,
                "name": job.name,
                "type": job.job_type,
                "run_once": job.run_once,
                "description": job.description,
                "note": note,
                "run_started_at": start_time.isoformat(),
                "run_at": (
                    job.payload.get("run_at") if isinstance(job.payload, dict) else None
                ),
                "session": umo,
            },
            "cron_payload": payload,
        }

        from astrbot.core.agent_wakeup import wake_main_agent

        cfg = self.ctx.get_config(umo=umo)
        role = (
            "admin"
            if (
                payload.get("origin", "tool") == "api"
                or payload.get("sender_id") in (cfg.get("admins_id") or [])
            )
            else "member"
        )
        await wake_main_agent(
            self.ctx,
            umo=umo,
            source="cron",
            source_id=job.job_id,
            user_prompt=PROACTIVE_AGENT_CRON_WOKE_USER_PROMPT.format(
                cron_job=json.dumps(extras["cron_job"], ensure_ascii=False)
            ),
            role=role,
        )


__all__ = ["CronJobManager"]
