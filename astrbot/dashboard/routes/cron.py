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
        target_sessions = self._normalize_target_sessions(
            payload.get("target_sessions"), payload.get("session")
        )
        data["note"] = payload.get("note") or data.get("description") or ""
        data["run_at"] = payload.get("run_at")
        data["run_once"] = data.get("run_once", False)
        data["target_sessions"] = target_sessions
        data["session"] = target_sessions[0] if target_sessions else ""
        # status is internal; hide to avoid implying one-time completion for recurring jobs
        data.pop("status", None)
        return data

    @staticmethod
    def _normalize_target_sessions(
        target_sessions, fallback_session: str | None = None
    ) -> list[str]:
        sessions: list[str] = []

        if isinstance(target_sessions, list):
            raw_items = target_sessions
        elif isinstance(target_sessions, str):
            raw_items = target_sessions.splitlines()
        else:
            raw_items = []

        for item in raw_items:
            session = str(item).strip()
            if session and session not in sessions:
                sessions.append(session)

        if fallback_session:
            session = str(fallback_session).strip()
            if session and session not in sessions:
                sessions.insert(0, session)

        return sessions

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
            target_sessions = self._normalize_target_sessions(
                payload.get("target_sessions"), session
            )
            persona_id = payload.get("persona_id")
            provider_id = payload.get("provider_id")
            timezone = payload.get("timezone")
            enabled = bool(payload.get("enabled", True))
            run_once = bool(payload.get("run_once", False))
            run_at = payload.get("run_at")

            if not target_sessions:
                return jsonify(
                    Response().error("at least one session is required").__dict__
                )
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
                "session": target_sessions[0],
                "target_sessions": target_sessions,
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

            existing_job = await cron_mgr.db.get_cron_job(job_id)
            if not existing_job:
                return jsonify(Response().error("Job not found").__dict__)

            payload_data = dict(existing_job.payload or {})
            if "note" in payload:
                payload_data["note"] = payload.get("note")
            if "run_at" in payload:
                payload_data["run_at"] = payload.get("run_at")
            if "persona_id" in payload:
                payload_data["persona_id"] = payload.get("persona_id")
            if "provider_id" in payload:
                payload_data["provider_id"] = payload.get("provider_id")
            if "session" in payload or "target_sessions" in payload:
                target_sessions = self._normalize_target_sessions(
                    payload.get("target_sessions"),
                    payload.get("session"),
                )
                if not target_sessions:
                    return jsonify(
                        Response().error("at least one session is required").__dict__
                    )
                payload_data["session"] = target_sessions[0]
                payload_data["target_sessions"] = target_sessions
            if isinstance(payload.get("payload"), dict):
                payload_data.update(payload["payload"])

            updates = {
                "name": payload.get("name"),
                "cron_expression": payload.get("cron_expression"),
                "description": payload.get("note") or payload.get("description"),
                "enabled": payload.get("enabled"),
                "timezone": payload.get("timezone"),
                "run_once": payload.get("run_once"),
                "payload": payload_data,
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
