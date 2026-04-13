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

    def _serialize_job(self, job) -> dict:
        data = job.model_dump() if hasattr(job, "model_dump") else job.__dict__
        for k in ["created_at", "updated_at", "last_run_at", "next_run_time"]:
            if isinstance(data.get(k), datetime):
                data[k] = data[k].isoformat()
        # expose note explicitly for UI (prefer payload.note then description)
        payload = data.get("payload") or {}
        data["note"] = payload.get("note") or data.get("description") or ""
        data["run_at"] = payload.get("run_at")
        data["run_once"] = data.get("run_once", False)
        # status is internal; hide to avoid implying one-time completion for recurring jobs
        data.pop("status", None)
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

            name = payload.get("name") or "active_agent_task"
            cron_expression = payload.get("cron_expression")
            note = payload.get("note") or payload.get("description") or name
            session = payload.get("session")
            persona_id = payload.get("persona_id")
            provider_id = payload.get("provider_id")
            timezone = payload.get("timezone")
            enabled = bool(payload.get("enabled", True))
            run_once = bool(payload.get("run_once", False))
            run_at = payload.get("run_at")

            if not session:
                return jsonify(Response().error("session is required").__dict__)
            if run_once and not run_at:
                return jsonify(
                    Response().error("run_at is required when run_once=true").__dict__
                )
            if (not run_once) and not cron_expression:
                return jsonify(
                    Response()
                    .error("cron_expression is required when run_once=false")
                    .__dict__
                )
            if run_once and cron_expression:
                cron_expression = None  # ignore cron when run_once specified
            run_at_dt = None
            if run_at:
                try:
                    run_at_dt = datetime.fromisoformat(str(run_at))
                except Exception:
                    return jsonify(
                        Response().error("run_at must be ISO datetime").__dict__
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

            job = await cron_mgr.db.get_cron_job(job_id)
            if not job:
                return jsonify(Response().error("Job not found").__dict__)

            updates = {}
            if "name" in payload:
                name = str(payload.get("name") or "").strip()
                if not name:
                    return jsonify(Response().error("name cannot be empty").__dict__)
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
                merged_payload = (
                    dict(job.payload) if isinstance(job.payload, dict) else {}
                )
                if "payload" in payload and isinstance(payload.get("payload"), dict):
                    merged_payload.update(payload["payload"])

                if "session" in payload:
                    session = str(payload.get("session") or "").strip()
                    if not session:
                        return jsonify(
                            Response().error("session cannot be empty").__dict__
                        )
                    merged_payload["session"] = session

                note_updated = False
                if "note" in payload:
                    note = str(payload.get("note") or "").strip()
                    if not note:
                        return jsonify(
                            Response().error("note cannot be empty").__dict__
                        )
                    merged_payload["note"] = note
                    updates["description"] = note
                    note_updated = True
                elif "description" in payload:
                    description = str(payload.get("description") or "").strip()
                    if not description:
                        return jsonify(
                            Response().error("description cannot be empty").__dict__
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
                            Response().error("run_at must be ISO datetime").__dict__
                        )

                if next_run_once:
                    if not run_at_iso:
                        return jsonify(
                            Response()
                            .error("run_at is required when run_once=true")
                            .__dict__
                        )
                    next_cron_expression = None
                    merged_payload["run_at"] = run_at_iso
                else:
                    if not next_cron_expression:
                        return jsonify(
                            Response()
                            .error("cron_expression is required when run_once=false")
                            .__dict__
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
                            Response().error("cron_expression cannot be empty").__dict__
                        )
                    updates["cron_expression"] = cron_expression

                if "description" in payload:
                    description = str(payload.get("description") or "").strip()
                    updates["description"] = description or None

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
