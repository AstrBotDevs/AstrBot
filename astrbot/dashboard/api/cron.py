from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.schemas import CronJobRequest
from astrbot.dashboard.services.cron_service import CronService, CronServiceError

from .auth import AuthContext, require_dashboard_user, require_scope

router = APIRouter(tags=["Cron"])
legacy_router = APIRouter(
    prefix="/api/cron",
    tags=["Dashboard Cron"],
    include_in_schema=False,
)


async def require_system_scope(request: Request) -> AuthContext:
    return await require_scope(request, "system")


def get_service(request: Request) -> CronService:
    return request.app.state.services.cron


def _payload_dict(payload: CronJobRequest) -> dict:
    return payload.model_dump(exclude_none=True)


def _raise_cron_error(exc: CronServiceError) -> None:
    raise ApiError(str(exc)) from exc


async def _list_jobs(job_type: str | None, service: CronService):
    try:
        return ok(await service.list_jobs(job_type))
    except CronServiceError as exc:
        _raise_cron_error(exc)


async def _create_job(payload: CronJobRequest, service: CronService):
    try:
        return ok(await service.create_job(_payload_dict(payload)))
    except CronServiceError as exc:
        _raise_cron_error(exc)


async def _update_job(job_id: str, payload: CronJobRequest, service: CronService):
    try:
        return ok(await service.update_job(job_id, _payload_dict(payload)))
    except CronServiceError as exc:
        _raise_cron_error(exc)


async def _delete_job(job_id: str, service: CronService):
    try:
        await service.delete_job(job_id)
        return ok(message="deleted")
    except CronServiceError as exc:
        _raise_cron_error(exc)


async def _run_job(job_id: str, service: CronService):
    try:
        await service.run_job_now(job_id)
        return ok(message="started")
    except CronServiceError as exc:
        _raise_cron_error(exc)


@router.get("/cron/jobs")
async def list_cron_jobs(
    job_type: str | None = Query(default=None, alias="type"),
    _auth: AuthContext = Depends(require_system_scope),
    service: CronService = Depends(get_service),
):
    return await _list_jobs(job_type, service)


@router.post("/cron/jobs")
async def create_cron_job(
    payload: CronJobRequest,
    _auth: AuthContext = Depends(require_system_scope),
    service: CronService = Depends(get_service),
):
    return await _create_job(payload, service)


@router.patch("/cron/jobs/{job_id}")
async def update_cron_job(
    job_id: str,
    payload: CronJobRequest,
    _auth: AuthContext = Depends(require_system_scope),
    service: CronService = Depends(get_service),
):
    return await _update_job(job_id, payload, service)


@router.delete("/cron/jobs/{job_id}")
async def delete_cron_job(
    job_id: str,
    _auth: AuthContext = Depends(require_system_scope),
    service: CronService = Depends(get_service),
):
    return await _delete_job(job_id, service)


@router.post("/cron/jobs/{job_id}/run")
async def run_cron_job(
    job_id: str,
    _auth: AuthContext = Depends(require_system_scope),
    service: CronService = Depends(get_service),
):
    return await _run_job(job_id, service)


@legacy_router.get("/jobs")
async def list_dashboard_cron_jobs(
    job_type: str | None = Query(default=None, alias="type"),
    _username: str = Depends(require_dashboard_user),
    service: CronService = Depends(get_service),
):
    return await _list_jobs(job_type, service)


@legacy_router.post("/jobs")
async def create_dashboard_cron_job(
    payload: CronJobRequest,
    _username: str = Depends(require_dashboard_user),
    service: CronService = Depends(get_service),
):
    return await _create_job(payload, service)


@legacy_router.patch("/jobs/{job_id}")
async def update_dashboard_cron_job(
    job_id: str,
    payload: CronJobRequest,
    _username: str = Depends(require_dashboard_user),
    service: CronService = Depends(get_service),
):
    return await _update_job(job_id, payload, service)


@legacy_router.delete("/jobs/{job_id}")
async def delete_dashboard_cron_job(
    job_id: str,
    _username: str = Depends(require_dashboard_user),
    service: CronService = Depends(get_service),
):
    return await _delete_job(job_id, service)


@legacy_router.post("/jobs/{job_id}/run")
async def run_dashboard_cron_job(
    job_id: str,
    _username: str = Depends(require_dashboard_user),
    service: CronService = Depends(get_service),
):
    return await _run_job(job_id, service)
