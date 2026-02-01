import traceback
from datetime import datetime

from quart import jsonify, request

from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle

from .route import Response, Route, RouteContext


class CronRoute(Route):
    def __init__(
        self, context: RouteContext, core_lifecycle: AstrBotCoreLifecycle
    ) -> None:
        super().__init__(context)
        self.core_lifecycle = core_lifecycle
        self.routes = [
            ("/cron/jobs", ("GET", self.list_jobs)),
            ("/cron/jobs", ("POST", self.create_job)),
            ("/cron/jobs/<job_id>", ("PATCH", self.update_job)),
            ("/cron/jobs/<job_id>", ("DELETE", self.delete_job)),
        ]
        self.register_routes()

    def _serialize_job(self, job):
        data = job.model_dump() if hasattr(job, "model_dump") else job.__dict__
        for k in ["created_at", "updated_at", "last_run_at", "next_run_time"]:
            if isinstance(data.get(k), datetime):
                data[k] = data[k].isoformat()
        return data

    async def list_jobs(self):
        try:
            cron_mgr = self.core_lifecycle.cron_manager
            if cron_mgr is None:
                return jsonify(
                    Response().error("Cron manager not initialized").__dict__
                )
            job_type = request.args.get("type")
            jobs = await cron_mgr.list_jobs(job_type)
            data = [self._serialize_job(j) for j in jobs]
            return jsonify(Response().ok(data=data).__dict__)
        except Exception as e:  # noqa: BLE001
            logger.error(traceback.format_exc())
            return jsonify(Response().error(f"Failed to list jobs: {e!s}").__dict__)

    async def create_job(self):
        try:
            cron_mgr = self.core_lifecycle.cron_manager
            if cron_mgr is None:
                return jsonify(
                    Response().error("Cron manager not initialized").__dict__
                )

            payload = await request.json
            if not isinstance(payload, dict):
                return jsonify(Response().error("Invalid payload").__dict__)

            job_type = payload.get("job_type", "active_agent")
            name = payload.get("name") or "active_agent_task"
            cron_expression = payload.get("cron_expression")
            note = payload.get("note") or payload.get("description") or name
            session = payload.get("session")
            persona_id = payload.get("persona_id")
            provider_id = payload.get("provider_id")
            timezone = payload.get("timezone")
            enabled = bool(payload.get("enabled", True))

            if not cron_expression or not session:
                return jsonify(
                    Response()
                    .error("cron_expression and session are required")
                    .__dict__
                )

            job_payload = {
                "session": session,
                "note": note,
                "persona_id": persona_id,
                "provider_id": provider_id,
            }

            if job_type != "active_agent":
                return jsonify(
                    Response()
                    .error("Only active_agent jobs are supported now.")
                    .__dict__
                )

            job = await cron_mgr.add_active_job(
                name=name,
                cron_expression=cron_expression,
                payload=job_payload,
                description=note,
                timezone=timezone,
                enabled=enabled,
            )

            return jsonify(Response().ok(data=self._serialize_job(job)).__dict__)
        except Exception as e:  # noqa: BLE001
            logger.error(traceback.format_exc())
            return jsonify(Response().error(f"Failed to create job: {e!s}").__dict__)

    async def update_job(self, job_id: str):
        try:
            cron_mgr = self.core_lifecycle.cron_manager
            if cron_mgr is None:
                return jsonify(
                    Response().error("Cron manager not initialized").__dict__
                )

            payload = await request.json
            if not isinstance(payload, dict):
                return jsonify(Response().error("Invalid payload").__dict__)

            updates = {
                "name": payload.get("name"),
                "cron_expression": payload.get("cron_expression"),
                "description": payload.get("description"),
                "enabled": payload.get("enabled"),
                "timezone": payload.get("timezone"),
            }
            # remove None values to avoid unwanted resets
            updates = {k: v for k, v in updates.items() if v is not None}

            job = await cron_mgr.update_job(job_id, **updates)
            if not job:
                return jsonify(Response().error("Job not found").__dict__)
            return jsonify(Response().ok(data=self._serialize_job(job)).__dict__)
        except Exception as e:  # noqa: BLE001
            logger.error(traceback.format_exc())
            return jsonify(Response().error(f"Failed to update job: {e!s}").__dict__)

    async def delete_job(self, job_id: str):
        try:
            cron_mgr = self.core_lifecycle.cron_manager
            if cron_mgr is None:
                return jsonify(
                    Response().error("Cron manager not initialized").__dict__
                )
            await cron_mgr.delete_job(job_id)
            return jsonify(Response().ok(message="deleted").__dict__)
        except Exception as e:  # noqa: BLE001
            logger.error(traceback.format_exc())
            return jsonify(Response().error(f"Failed to delete job: {e!s}").__dict__)
