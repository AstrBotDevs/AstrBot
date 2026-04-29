import asyncio
from asyncio import Queue
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from astrbot import logger
from astrbot.core.cron.events import CronMessageEvent
from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import CronJob
from astrbot.core.platform.message_session import MessageSession

if TYPE_CHECKING:
    from astrbot.core.star.context import Context


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

    async def start(self, ctx: "Context") -> None:
        self.ctx: Context = ctx  # star context
        async with self._lock:
            # 从 Context 获取事件队列，用于将定时任务消息放入管道
            self._event_queue: Queue = ctx.get_event_queue()
            if self._started:
                return
            self.scheduler.start()
            self._started = True
            await self.sync_from_db()

    async def shutdown(self) -> None:
        async with self._lock:
            if not self._started:
                return
            self.scheduler.shutdown(wait=False)
            self._started = False

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

    def _remove_scheduled(self, job_id: str) -> None:
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

    def _schedule_job(self, job: CronJob) -> None:
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
        except (ValueError, TypeError) as e:
            logger.exception("Failed to schedule cron job %s", job.job_id)
            raise CronJobSchedulingError(str(e)) from e

    def _get_next_run_time(self, job_id: str):
        aps_job = self.scheduler.get_job(job_id)
        if not aps_job or aps_job.next_run_time is None:
            return None
        return aps_job.next_run_time.astimezone(timezone.utc)

    async def _run_job(self, job_id: str) -> None:
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
                await self._run_active_agent_job(job, start_time=start_time)
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
            if job.run_once:
                # one-shot: remove after execution regardless of success
                await self.delete_job(job_id)

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
        session_str = payload.get("session")
        if not session_str:
            raise ValueError("ActiveAgentCronJob missing session.")
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
            },
            "cron_payload": payload,
        }

        # 将定时任务消息放入事件队列，使其经过完整的 PipelineScheduler 流程
        # 这样插件的 on_llm_response 等处理器可以正常拦截和处理消息
        await self._dispatch_to_pipeline(
            message=note,
            session_str=session_str,
            extras=extras,
        )

    async def _dispatch_to_pipeline(
        self,
        *,
        message: str,
        session_str: str,
        extras: dict,
    ) -> None:
        # 将定时任务消息放入事件队列，由 PipelineScheduler 统一处理。

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

        # judge user's role
        umo = cron_event.unified_msg_origin
        cfg = self.ctx.get_config(umo=umo)
        cron_payload = extras.get("cron_payload", {}) if extras else {}
        sender_id = cron_payload.get("sender_id")
        admin_ids = cfg.get("admins_id", [])
        if admin_ids:
            cron_event.role = "admin" if sender_id in admin_ids else "member"
        if cron_payload.get("origin", "tool") == "api":
            cron_event.role = "admin"

        # 将事件放入事件队列，由 PipelineScheduler 处理
        # 不再直接调用 build_main_agent，避免双重消息
        await self._event_queue.put(cron_event)
        logger.debug(
            f"Cron job {extras.get('cron_job', {}).get('id')} dispatched to pipeline (hooks triggered)."
        )
        # 原始的_woke_main_agent 手动调用 persist_agent_history()
        # PipelineScheduler 的 internal.py 自动调用 _save_to_history()
        # 功能完整保留，且更简洁


__all__ = ["CronJobManager"]
