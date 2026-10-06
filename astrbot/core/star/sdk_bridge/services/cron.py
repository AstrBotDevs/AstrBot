from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from astrbot_sdk.errors import InvalidRequest, NotFound

if TYPE_CHECKING:
    from astrbot.core.star.sdk_bridge.bridge import SDKPluginBridge

# Job kwargs forwarded to APScheduler; anything else a plugin passes is
# dropped instead of leaking Host internals.
_ALLOWED_JOB_KWARGS = {
    "id",
    "name",
    "replace_existing",
    "misfire_grace_time",
    "coalesce",
    "max_instances",
}

_DATETIME_TRIGGER_KEYS = {"run_date", "start_date", "end_date"}


def _serialize_cron_job(job: Any) -> dict[str, Any]:
    """Serialize one core CronJob row to a JSON-safe dict."""
    return {
        "job_id": job.job_id,
        "name": job.name,
        "description": job.description,
        "job_type": job.job_type,
        "cron_expression": job.cron_expression,
        "timezone": job.timezone,
        "payload": job.payload or {},
        "enabled": job.enabled,
        "persistent": job.persistent,
        "run_once": job.run_once,
        "status": job.status,
        "last_run_at": job.last_run_at.isoformat() if job.last_run_at else None,
        "next_run_time": (job.next_run_time.isoformat() if job.next_run_time else None),
        "last_error": job.last_error,
    }


def _build_trigger(spec: dict[str, Any]) -> Any:
    """Rebuild an APScheduler trigger from its serialized spec."""
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.date import DateTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    kind = spec.get("type")
    params = dict(spec.get("params") or {})
    for key in _DATETIME_TRIGGER_KEYS & params.keys():
        if isinstance(params[key], str):
            params[key] = datetime.fromisoformat(params[key])
    if kind == "date":
        return DateTrigger(**params)
    if kind == "cron":
        return CronTrigger(**params)
    if kind == "interval":
        return IntervalTrigger(**params)
    raise InvalidRequest(f"unknown cron trigger type: {kind}")


class CronScheduleService:
    """Run legacy plugin cron jobs on the Host scheduler.

    Basic jobs and raw APScheduler jobs are registered on the Host
    CronJobManager with a proxy handler; each firing is forwarded back to
    the plugin Runner through invoke_cron. Only granted to legacy plugins;
    new SDK plugins cannot declare it.
    """

    capability_id = "cron.schedule"

    def __init__(self, bridge: SDKPluginBridge) -> None:
        """Initialize the service.

        Args:
            bridge: Owning bridge used to reach the calling Runner.
        """
        self._bridge = bridge

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Serve one cron.schedule operation."""
        if operation == "add_basic_job":
            return await self._add_basic_job(payload)
        if operation == "delete_job":
            return await self._delete_job(payload)
        if operation == "list_jobs":
            return await self._list_jobs(payload)
        if operation == "add_scheduler_job":
            return self._add_scheduler_job(payload)
        if operation == "remove_job":
            return self._remove_scheduler_job(payload)
        raise NotFound(f"unknown cron.schedule operation: {operation}")

    def _make_proxy(self, handler_id: str) -> Any:
        """Build the Host-side job handler invoking back into the Runner."""
        bridge = self._bridge

        async def proxy(*args: Any, **kwargs: Any) -> None:
            await bridge._require_client().invoke_cron(
                handler_id,
                {"args": list(args), "kwargs": kwargs},
            )

        return proxy

    async def _add_basic_job(self, payload: dict[str, Any]) -> Any:
        handler_id = str(payload.get("handler_id") or "")
        name = str(payload.get("name") or "")
        cron_expression = str(payload.get("cron_expression") or "")
        if not handler_id or not name or not cron_expression:
            raise InvalidRequest(
                "add_basic_job requires handler_id, name and cron_expression",
            )
        job_payload = payload.get("payload")
        if job_payload is not None and not isinstance(job_payload, dict):
            raise InvalidRequest("add_basic_job payload must be an object")
        job = await self._bridge.context.cron_manager.add_basic_job(
            name=name,
            cron_expression=cron_expression,
            handler=self._make_proxy(handler_id),
            description=payload.get("description"),
            timezone=payload.get("timezone"),
            payload=job_payload,
            enabled=bool(payload.get("enabled", True)),
            persistent=bool(payload.get("persistent", False)),
        )
        return {"job": _serialize_cron_job(job)}

    async def _delete_job(self, payload: dict[str, Any]) -> Any:
        job_id = str(payload.get("job_id") or "")
        if not job_id:
            raise InvalidRequest("delete_job requires job_id")
        await self._bridge.context.cron_manager.delete_job(job_id)
        return {}

    async def _list_jobs(self, payload: dict[str, Any]) -> Any:
        job_type = payload.get("job_type")
        jobs = await self._bridge.context.cron_manager.list_jobs(
            str(job_type) if job_type else None,
        )
        return {"jobs": [_serialize_cron_job(job) for job in jobs]}

    def _add_scheduler_job(self, payload: dict[str, Any]) -> Any:
        handler_id = str(payload.get("handler_id") or "")
        spec = payload.get("trigger")
        if not handler_id or not isinstance(spec, dict):
            raise InvalidRequest("add_scheduler_job requires handler_id and trigger")
        options = payload.get("options") or {}
        if not isinstance(options, dict):
            raise InvalidRequest("add_scheduler_job options must be an object")
        job_options = {
            key: value for key, value in options.items() if key in _ALLOWED_JOB_KWARGS
        }
        args = payload.get("args") or []
        func_kwargs = payload.get("kwargs") or {}
        if not isinstance(func_kwargs, dict):
            raise InvalidRequest("add_scheduler_job kwargs must be an object")
        job = self._bridge.context.cron_manager.scheduler.add_job(
            self._make_proxy(handler_id),
            _build_trigger(spec),
            args=list(args),
            kwargs=func_kwargs,
            **job_options,
        )
        return {"job_id": job.id}

    def _remove_scheduler_job(self, payload: dict[str, Any]) -> Any:
        job_id = str(payload.get("job_id") or "")
        if not job_id:
            raise InvalidRequest("remove_job requires job_id")
        self._bridge.context.cron_manager.scheduler.remove_job(job_id)
        return {}
