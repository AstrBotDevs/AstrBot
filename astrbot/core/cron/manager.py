import asyncio
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from astrbot import logger
from astrbot.core.cron.events import CronMessageEvent
from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import CronJob
from astrbot.core.platform.message_session import MessageSession


class CronJobManager:
    """Central scheduler for BasicCronJob and ActiveAgentCronJob."""

    def __init__(self, ctx, db: BaseDatabase):
        self.ctx = ctx
        self.db = db
        self.scheduler = AsyncIOScheduler()
        self._basic_handlers: dict[str, Callable[..., Any]] = {}
        self._lock = asyncio.Lock()
        self._started = False

    async def start(self):
        async with self._lock:
            if self._started:
                return
            self.scheduler.start()
            self._started = True
            await self.sync_from_db()

    async def shutdown(self):
        async with self._lock:
            if not self._started:
                return
            self.scheduler.shutdown(wait=False)
            self._started = False

    async def sync_from_db(self):
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
            self._schedule_job(job)

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
        cron_expression: str,
        payload: dict,
        description: str | None = None,
        timezone: str | None = None,
        enabled: bool = True,
        persistent: bool = True,
    ) -> CronJob:
        job = await self.db.create_cron_job(
            name=name,
            job_type="active_agent",
            cron_expression=cron_expression,
            timezone=timezone,
            payload=payload,
            description=description,
            enabled=enabled,
            persistent=persistent,
        )
        if enabled:
            self._schedule_job(job)
        return job

    async def update_job(self, job_id: str, **kwargs) -> CronJob | None:
        job = await self.db.update_cron_job(job_id, **kwargs)
        if not job:
            return None
        self._remove_scheduled(job_id)
        if job.enabled:
            self._schedule_job(job)
        return job

    async def delete_job(self, job_id: str) -> None:
        self._remove_scheduled(job_id)
        self._basic_handlers.pop(job_id, None)
        await self.db.delete_cron_job(job_id)

    async def list_jobs(self, job_type: str | None = None) -> list[CronJob]:
        return await self.db.list_cron_jobs(job_type)

    def _remove_scheduled(self, job_id: str):
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

    def _schedule_job(self, job: CronJob):
        if not self._started:
            self.scheduler.start()
            self._started = True
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
            trigger = CronTrigger.from_crontab(job.cron_expression, timezone=tzinfo)
            self.scheduler.add_job(
                self._run_job,
                id=job.job_id,
                trigger=trigger,
                args=[job.job_id],
                replace_existing=True,
                misfire_grace_time=30,
            )
            asyncio.create_task(
                self.db.update_cron_job(
                    job.job_id, next_run_time=self._get_next_run_time(job.job_id)
                )
            )
        except Exception as e:
            logger.error(f"Failed to schedule cron job {job.job_id}: {e!s}")

    def _get_next_run_time(self, job_id: str):
        aps_job = self.scheduler.get_job(job_id)
        return aps_job.next_run_time if aps_job else None

    async def _run_job(self, job_id: str):
        job = await self.db.get_cron_job(job_id)
        if not job or not job.enabled:
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
                await self._run_active_agent_job(job)
            else:
                raise ValueError(f"Unknown cron job type: {job.job_type}")
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

    async def _run_basic_job(self, job: CronJob):
        handler = self._basic_handlers.get(job.job_id)
        if not handler:
            raise RuntimeError(f"Basic cron job handler not found for {job.job_id}")
        payload = job.payload or {}
        result = handler(**payload) if payload else handler()
        if asyncio.iscoroutine(result):
            await result

    async def _run_active_agent_job(self, job: CronJob):
        payload = job.payload or {}
        session_str = payload.get("session")
        if not session_str:
            raise ValueError("ActiveAgentCronJob missing session.")
        note = payload.get("note") or job.description or job.name

        extras = {
            "cron_job": {
                "id": job.job_id,
                "name": job.name,
                "type": job.job_type,
                "description": job.description,
                "note": note,
            },
            "cron_payload": payload,
        }

        await self._dispatch_agent_event(
            message=note,
            session_str=session_str,
            extras=extras,
        )

    async def _dispatch_agent_event(
        self,
        *,
        message: str,
        session_str: str,
        extras: dict | None = None,
    ):
        try:
            session = (
                session_str
                if isinstance(session_str, MessageSession)
                else MessageSession.from_str(session_str)
            )
        except Exception as e:  # noqa: BLE001
            logger.error(f"Invalid session for cron job: {e}")
            return

        cron_event = CronMessageEvent(
            context=self.ctx,
            session=session,
            message=message,
            extras=extras or {},
            message_type=session.message_type,
        )

        await self.ctx.get_event_queue().put(cron_event)


__all__ = ["CronJobManager"]
