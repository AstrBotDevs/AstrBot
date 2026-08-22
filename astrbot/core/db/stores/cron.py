from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, delete, desc, select, update

from astrbot.core.db.po import CronJob

CRON_FIELD_NOT_SET = object()


class CronStoreMixin:
    async def create_cron_job(
        self,
        name: str,
        job_type: str,
        cron_expression: str | None,
        *,
        timezone: str | None = None,
        payload: dict | None = None,
        description: str | None = None,
        enabled: bool = True,
        persistent: bool = True,
        run_once: bool = False,
        status: str | None = None,
        job_id: str | None = None,
    ) -> CronJob:
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                job = CronJob(
                    name=name,
                    job_type=job_type,
                    cron_expression=cron_expression,
                    timezone=timezone,
                    payload=payload or {},
                    description=description,
                    enabled=enabled,
                    persistent=persistent,
                    run_once=run_once,
                    status=status or "scheduled",
                )
                if job_id:
                    job.job_id = job_id
                session.add(job)
                await session.flush()
                await session.refresh(job)
                return job

    async def update_cron_job(
        self,
        job_id: str,
        *,
        name: str | None | object = CRON_FIELD_NOT_SET,
        cron_expression: str | None | object = CRON_FIELD_NOT_SET,
        timezone: str | None | object = CRON_FIELD_NOT_SET,
        payload: dict | None | object = CRON_FIELD_NOT_SET,
        description: str | None | object = CRON_FIELD_NOT_SET,
        enabled: bool | None | object = CRON_FIELD_NOT_SET,
        persistent: bool | None | object = CRON_FIELD_NOT_SET,
        run_once: bool | None | object = CRON_FIELD_NOT_SET,
        status: str | None | object = CRON_FIELD_NOT_SET,
        next_run_time: datetime | None | object = CRON_FIELD_NOT_SET,
        last_run_at: datetime | None | object = CRON_FIELD_NOT_SET,
        last_error: str | None | object = CRON_FIELD_NOT_SET,
    ) -> CronJob | None:
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                updates: dict = {}
                for key, val in {
                    "name": name,
                    "cron_expression": cron_expression,
                    "timezone": timezone,
                    "payload": payload,
                    "description": description,
                    "enabled": enabled,
                    "persistent": persistent,
                    "run_once": run_once,
                    "status": status,
                    "next_run_time": next_run_time,
                    "last_run_at": last_run_at,
                    "last_error": last_error,
                }.items():
                    if val is CRON_FIELD_NOT_SET:
                        continue
                    updates[key] = val

                stmt = (
                    update(CronJob)
                    .where(col(CronJob.job_id) == job_id)
                    .values(**updates)
                    .execution_options(synchronize_session="fetch")
                )
                await session.execute(stmt)
                result = await session.execute(
                    select(CronJob).where(col(CronJob.job_id) == job_id)
                )
                return result.scalar_one_or_none()

    async def delete_cron_job(self, job_id: str) -> None:
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(CronJob).where(col(CronJob.job_id) == job_id)
                )

    async def get_cron_job(self, job_id: str) -> CronJob | None:
        async with self.get_db() as session:
            session: AsyncSession
            result = await session.execute(
                select(CronJob).where(col(CronJob.job_id) == job_id)
            )
            return result.scalar_one_or_none()

    async def list_cron_jobs(self, job_type: str | None = None) -> list[CronJob]:
        async with self.get_db() as session:
            session: AsyncSession
            query = select(CronJob)
            if job_type:
                query = query.where(col(CronJob.job_type) == job_type)
            query = query.order_by(desc(CronJob.created_at))
            result = await session.execute(query)
            return list(result.scalars().all())
