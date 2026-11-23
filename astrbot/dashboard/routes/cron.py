import asyncio
import traceback
from datetime import datetime

from quart import jsonify, request

from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.dashboard.services.cron_service import CronService

from .route import Response, Route, RouteContext


class CronRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.core_lifecycle = core_lifecycle
        self._background_tasks: set[asyncio.Task] = set()
        self.routes = [
            ("/cron/jobs", ("GET", self.list_jobs)),
            ("/cron/jobs", ("POST", self.create_job)),
            ("/cron/jobs/<job_id>", ("PATCH", self.update_job)),
            ("/cron/jobs/<job_id>", ("DELETE", self.delete_job)),
            ("/cron/jobs/<job_id>/run", ("POST", self.run_job_now)),
        ]
        self.register_routes()

    def _serialize_job(self, job) -> dict:
        return CronService.serialize_job(job)

    async def list_jobs(self):
        try:
            cron_mgr = self.core_lifecycle.cron_manager
            if cron_mgr is None:
                return jsonify(
                    Response().error("Cron manager not initialized").to_json(),
                )
            job_type = request.args.get("type")
            jobs = await cron_mgr.list_jobs(job_type)
            data = [self._serialize_job(j) for j in jobs]
            return jsonify(Response().ok(data=data).to_json())
        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify(Response().error(f"Failed to list jobs: {e!s}").to_json())

    async def _read_job_request(self):
        cron_mgr = self.core_lifecycle.cron_manager
        if cron_mgr is None:
            return (
                None,
                None,
                jsonify(Response().error("Cron manager not initialized").to_json()),
            )
        payload = await request.json
        if not isinstance(payload, dict):
            return (
                cron_mgr,
                None,
                jsonify(Response().error("Invalid payload").to_json()),
            )
        return cron_mgr, payload, None

    async def create_job(self):
        try:
            cron_mgr, payload, error = await self._read_job_request()
            if cron_mgr is None or payload is None:
                return error

            name = payload.get("name") or "active_agent_task"
            cron_expression = payload.get("cron_expression")
            note = payload.get("note") or payload.get("description") or name
            session = str(payload.get("session") or "").strip()
            persona_id = payload.get("persona_id")
            provider_id = payload.get("provider_id")
            timezone = payload.get("timezone")
            enabled = bool(payload.get("enabled", True))
            run_once = bool(payload.get("run_once", False))
            run_at = payload.get("run_at")

            if run_once and not run_at:
                return jsonify(
                    Response().error("run_at is required when run_once=true").to_json(),
                )
            if (not run_once) and not cron_expression:
                return jsonify(
                    Response()
                    .error("cron_expression is required when run_once=false")
                    .to_json(),
                )
            if run_once and cron_expression:
                cron_expression = None  # ignore cron when run_once specified
            run_at_dt = None
            if run_at:
                try:
                    run_at_dt = datetime.fromisoformat(str(run_at))
                except Exception:
                    return jsonify(
                        Response().error("run_at must be ISO datetime").to_json(),
                    )

            job_payload = {
                "session": session,
                "note": note,
                "persona_id": persona_id,
                "provider_id": provider_id,
                "run_at": run_at,
                "origin": "api",
            }

            job = await cron_mgr.add_active_job(
                name=name,
                cron_expression=cron_expression,
                payload=job_payload,
                description=note,
                timezone=timezone,
                enabled=enabled,
                run_once=run_once,
                run_at=run_at_dt,
            )

            return jsonify(Response().ok(data=self._serialize_job(job)).to_json())
        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify(Response().error(f"Failed to create job: {e!s}").to_json())

    async def update_job(self, job_id: str):
        try:
            cron_mgr, payload, error = await self._read_job_request()
            if cron_mgr is None or payload is None:
                return error

            job = await cron_mgr.db.get_cron_job(job_id)
            if not job:
                return jsonify(Response().error("Job not found").to_json())

            updates = {}
            if "name" in payload:
                name = str(payload.get("name") or "").strip()
                if not name:
                    return jsonify(Response().error("name cannot be empty").to_json())
                updates["name"] = name

            if "enabled" in payload:
                updates["enabled"] = bool(payload.get("enabled"))

            if "timezone" in payload:
                timezone = payload.get("timezone")
                updates["timezone"] = str(timezone).strip() or None

            next_run_once = (
                bool(payload.get("run_once"))
                if "run_once" in payload
                else bool(job.run_once)
            )

            if job.job_type == "active_agent":
                merged_payload = CronService.merge_active_agent_payload(job, payload)

                note_updated = False
                if "note" in payload:
                    note = str(payload.get("note") or "").strip()
                    if not note:
                        return jsonify(
                            Response().error("note cannot be empty").to_json()
                        )
                    merged_payload["note"] = note
                    updates["description"] = note
                    note_updated = True
                elif "description" in payload:
                    description = str(payload.get("description") or "").strip()
                    if not description:
                        return jsonify(
                            Response().error("description cannot be empty").to_json()
                        )
                    updates["description"] = description
                    merged_payload["note"] = description
                    note_updated = True

                if not note_updated and updates.get("description") is None:
                    existing_note = str(
                        merged_payload.get("note") or job.description or ""
                    ).strip()
                    if existing_note:
                        merged_payload["note"] = existing_note

                next_cron_expression = (
                    payload.get("cron_expression")
                    if "cron_expression" in payload
                    else job.cron_expression
                )
                if next_cron_expression is not None:
                    next_cron_expression = str(next_cron_expression).strip() or None

                run_at_raw = (
                    payload.get("run_at")
                    if "run_at" in payload
                    else merged_payload.get("run_at")
                )
                run_at_iso = None
                if run_at_raw:
                    try:
                        run_at_iso = datetime.fromisoformat(str(run_at_raw)).isoformat()
                    except Exception:
                        return jsonify(
                            Response().error("run_at must be ISO datetime").to_json()
                        )

                if next_run_once:
                    if not run_at_iso:
                        return jsonify(
                            Response()
                            .error("run_at is required when run_once=true")
                            .to_json()
                        )
                    next_cron_expression = None
                    merged_payload["run_at"] = run_at_iso
                else:
                    if not next_cron_expression:
                        return jsonify(
                            Response()
                            .error("cron_expression is required when run_once=false")
                            .to_json()
                        )
                    merged_payload.pop("run_at", None)

                updates["run_once"] = next_run_once
                updates["cron_expression"] = next_cron_expression
                updates["payload"] = merged_payload
            else:
                if "cron_expression" in payload:
                    cron_expression = str(payload.get("cron_expression") or "").strip()
                    if not cron_expression:
                        return jsonify(
                            Response()
                            .error("cron_expression cannot be empty")
                            .to_json()
                        )
                    updates["cron_expression"] = cron_expression

                if "description" in payload:
                    description = str(payload.get("description") or "").strip()
                    updates["description"] = description or None

            job = await cron_mgr.update_job(job_id, **updates)
            if not job:
                return jsonify(Response().error("Job not found").to_json())
            return jsonify(Response().ok(data=self._serialize_job(job)).to_json())
        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify(Response().error(f"Failed to update job: {e!s}").to_json())

    async def delete_job(self, job_id: str):
        try:
            cron_mgr = self.core_lifecycle.cron_manager
            if cron_mgr is None:
                return jsonify(
                    Response().error("Cron manager not initialized").to_json(),
                )
            await cron_mgr.delete_job(job_id)
            return jsonify(Response().ok(message="deleted").to_json())
        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify(Response().error(f"Failed to delete job: {e!s}").to_json())

    async def run_job_now(self, job_id: str):
        try:
            cron_mgr = self.core_lifecycle.cron_manager
            if cron_mgr is None:
                return jsonify(
                    Response().error("Cron manager not initialized").to_json()
                )
            job = await cron_mgr.db.get_cron_job(job_id)
            if not job:
                return jsonify(Response().error("Job not found").to_json())
            task = asyncio.create_task(cron_mgr.run_job_now(job_id))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            return jsonify(Response().ok(message="started").to_json())
        except Exception as e:  # noqa: BLE001
            logger.error(traceback.format_exc())
            return jsonify(Response().error(f"Failed to run job: {e!s}").to_json())
