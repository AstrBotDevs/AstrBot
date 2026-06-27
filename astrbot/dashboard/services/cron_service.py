from __future__ import annotations

import asyncio
import traceback
from datetime import datetime, timezone

from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle


class CronServiceError(Exception):
    pass


class CronService:
    def __init__(self, core_lifecycle: AstrBotCoreLifecycle) -> None:
        self.core_lifecycle = core_lifecycle
        self._background_tasks: set[asyncio.Task] = set()

    def _get_cron_manager(self):
        cron_mgr = self.core_lifecycle.cron_manager
        if cron_mgr is None:
            raise CronServiceError("Cron manager not initialized")
        return cron_mgr

    @staticmethod
    def serialize_job(job) -> dict:
        data = job.model_dump() if hasattr(job, "model_dump") else job.__dict__
        for key in ["created_at", "updated_at", "last_run_at", "next_run_time"]:
            value = data.get(key)
            if isinstance(value, datetime):
                if value.tzinfo is None:
                    value = value.replace(tzinfo=timezone.utc)
                data[key] = value.isoformat()

        payload = data.get("payload") or {}
        data["note"] = payload.get("note") or data.get("description") or ""
        data["run_at"] = payload.get("run_at")
        data["run_once"] = data.get("run_once", False)
        data.pop("status", None)
        return data

    async def list_jobs(self, job_type: str | None = None) -> list[dict]:
        try:
            cron_mgr = self._get_cron_manager()
            jobs = await cron_mgr.list_jobs(job_type)
            return [self.serialize_job(job) for job in jobs]
        except CronServiceError:
            raise
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise CronServiceError(f"Failed to list jobs: {exc!s}") from exc

    async def create_job(self, payload: object) -> dict:
        try:
            cron_mgr = self._get_cron_manager()
            if not isinstance(payload, dict):
                raise CronServiceError("Invalid payload")

            name = payload.get("name") or "active_agent_task"
            cron_expression = payload.get("cron_expression")
            note = payload.get("note") or payload.get("description") or name
            session = str(payload.get("session") or "").strip()
            persona_id = payload.get("persona_id")
            provider_id = payload.get("provider_id")
            timezone_name = payload.get("timezone")
            enabled = bool(payload.get("enabled", True))
            run_once = bool(payload.get("run_once", False))
            run_at = payload.get("run_at")

            if run_once and not run_at:
                raise CronServiceError("run_at is required when run_once=true")
            if (not run_once) and not cron_expression:
                raise CronServiceError(
                    "cron_expression is required when run_once=false"
                )
            if run_once and cron_expression:
                cron_expression = None

            run_at_dt = self._parse_optional_run_at(run_at)
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
                timezone=timezone_name,
                enabled=enabled,
                run_once=run_once,
                run_at=run_at_dt,
            )
            return self.serialize_job(job)
        except CronServiceError:
            raise
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise CronServiceError(f"Failed to create job: {exc!s}") from exc

    async def update_job(self, job_id: str, payload: object) -> dict:
        try:
            cron_mgr = self._get_cron_manager()
            if not isinstance(payload, dict):
                raise CronServiceError("Invalid payload")

            job = await cron_mgr.db.get_cron_job(job_id)
            if not job:
                raise CronServiceError("Job not found")

            updates = {}
            if "name" in payload:
                name = str(payload.get("name") or "").strip()
                if not name:
                    raise CronServiceError("name cannot be empty")
                updates["name"] = name

            if "enabled" in payload:
                updates["enabled"] = bool(payload.get("enabled"))

            if "timezone" in payload:
                timezone_name = payload.get("timezone")
                updates["timezone"] = str(timezone_name).strip() or None

            if job.job_type == "active_agent":
                self._merge_active_agent_updates(job, payload, updates)
            else:
                self._merge_generic_updates(payload, updates)

            updated_job = await cron_mgr.update_job(job_id, **updates)
            if not updated_job:
                raise CronServiceError("Job not found")
            return self.serialize_job(updated_job)
        except CronServiceError:
            raise
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise CronServiceError(f"Failed to update job: {exc!s}") from exc

    async def delete_job(self, job_id: str) -> None:
        try:
            cron_mgr = self._get_cron_manager()
            await cron_mgr.delete_job(job_id)
        except CronServiceError:
            raise
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise CronServiceError(f"Failed to delete job: {exc!s}") from exc

    async def run_job_now(self, job_id: str) -> None:
        try:
            cron_mgr = self._get_cron_manager()
            job = await cron_mgr.db.get_cron_job(job_id)
            if not job:
                raise CronServiceError("Job not found")
            task = asyncio.create_task(cron_mgr.run_job_now(job_id))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        except CronServiceError:
            raise
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise CronServiceError(f"Failed to run job: {exc!s}") from exc

    @staticmethod
    def _parse_optional_run_at(run_at: object) -> datetime | None:
        if not run_at:
            return None
        try:
            return datetime.fromisoformat(str(run_at))
        except Exception as exc:
            raise CronServiceError("run_at must be ISO datetime") from exc

    @staticmethod
    def _normalize_run_at_iso(run_at: object) -> str | None:
        if not run_at:
            return None
        try:
            return datetime.fromisoformat(str(run_at)).isoformat()
        except Exception as exc:
            raise CronServiceError("run_at must be ISO datetime") from exc

    def _merge_active_agent_updates(self, job, payload: dict, updates: dict) -> None:
        merged_payload = dict(job.payload) if isinstance(job.payload, dict) else {}
        if "payload" in payload and isinstance(payload.get("payload"), dict):
            merged_payload.update(payload["payload"])

        if "session" in payload:
            session = str(payload.get("session") or "").strip()
            if session:
                merged_payload["session"] = session
            else:
                merged_payload.pop("session", None)

        self._merge_note(payload, job, merged_payload, updates)

        next_run_once = (
            bool(payload.get("run_once"))
            if "run_once" in payload
            else bool(job.run_once)
        )
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
        run_at_iso = self._normalize_run_at_iso(run_at_raw)

        if next_run_once:
            if not run_at_iso:
                raise CronServiceError("run_at is required when run_once=true")
            next_cron_expression = None
            merged_payload["run_at"] = run_at_iso
        else:
            if not next_cron_expression:
                raise CronServiceError(
                    "cron_expression is required when run_once=false"
                )
            merged_payload.pop("run_at", None)

        updates["run_once"] = next_run_once
        updates["cron_expression"] = next_cron_expression
        updates["payload"] = merged_payload

    @staticmethod
    def _merge_note(
        payload: dict,
        job,
        merged_payload: dict,
        updates: dict,
    ) -> None:
        note_updated = False
        if "note" in payload:
            note = str(payload.get("note") or "").strip()
            if not note:
                raise CronServiceError("note cannot be empty")
            merged_payload["note"] = note
            updates["description"] = note
            note_updated = True
        elif "description" in payload:
            description = str(payload.get("description") or "").strip()
            if not description:
                raise CronServiceError("description cannot be empty")
            updates["description"] = description
            merged_payload["note"] = description
            note_updated = True

        if not note_updated and updates.get("description") is None:
            existing_note = str(
                merged_payload.get("note") or job.description or ""
            ).strip()
            if existing_note:
                merged_payload["note"] = existing_note

    @staticmethod
    def _merge_generic_updates(payload: dict, updates: dict) -> None:
        if "cron_expression" in payload:
            cron_expression = str(payload.get("cron_expression") or "").strip()
            if not cron_expression:
                raise CronServiceError("cron_expression cannot be empty")
            updates["cron_expression"] = cron_expression

        if "description" in payload:
            description = str(payload.get("description") or "").strip()
            updates["description"] = description or None
