from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.dashboard.fastapi_compat import jsonify, request
from astrbot.dashboard.services.cron_service import CronService, CronServiceError

from .route import Response, Route, RouteContext


class CronRoute(Route):
    def __init__(
        self, context: RouteContext, core_lifecycle: AstrBotCoreLifecycle
    ) -> None:
        super().__init__(context)
        self.service = CronService(core_lifecycle)
        self.routes = [
            ("/cron/jobs", ("GET", self.list_jobs)),
            ("/cron/jobs", ("POST", self.create_job)),
            ("/cron/jobs/<job_id>", ("PATCH", self.update_job)),
            ("/cron/jobs/<job_id>", ("DELETE", self.delete_job)),
            ("/cron/jobs/<job_id>/run", ("POST", self.run_job_now)),
        ]
        self.register_routes()

    @staticmethod
    def _ok(data=None, message: str | None = None):
        return jsonify(Response().ok(data=data, message=message).__dict__)

    @staticmethod
    def _error(message: str):
        return jsonify(Response().error(message).__dict__)

    @staticmethod
    async def _json_body() -> dict:
        data = await request.get_json()
        return data if isinstance(data, dict) else {}

    async def _run(self, operation, *, message: str | None = None):
        try:
            result = operation() if callable(operation) else operation
            while hasattr(result, "__await__"):
                result = await result
            return self._ok(result, message)
        except CronServiceError as exc:
            return self._error(str(exc))

    async def _run_json(self, operation, *, message: str | None = None):
        async def invoke():
            data = await self._json_body()
            return operation(data)

        return await self._run(invoke, message=message)

    async def list_jobs(self):
        return await self._run(
            self.service.list_jobs_from_legacy_query(request.args.get("type"))
        )

    async def create_job(self):
        return await self._run_json(self.service.create_job)

    async def update_job(self, job_id: str):
        return await self._run_json(
            lambda payload: self.service.update_job(job_id, payload)
        )

    async def delete_job(self, job_id: str):
        return await self._run(self.service.delete_job(job_id), message="deleted")

    async def run_job_now(self, job_id: str):
        return await self._run(self.service.run_job_now(job_id), message="started")
