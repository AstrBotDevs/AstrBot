import os
import re
import shutil
import traceback
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from quart import request, send_file

from astrbot.core import DEMO_MODE, logger
from astrbot.core.computer.computer_client import (
    _discover_bay_credentials,
    sync_skills_to_active_sandboxes,
)
from astrbot.core.skills.neo_skill_sync import NeoSkillSyncManager
from astrbot.core.skills.skill_manager import SkillManager
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from .route import Response, Route, RouteContext


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    if hasattr(value, "model_dump"):
        return _to_jsonable(value.model_dump())
    return value


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


_SKILL_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class SkillsRoute(Route):
    def __init__(self, context: RouteContext, core_lifecycle) -> None:
        super().__init__(context)
        self.core_lifecycle = core_lifecycle
        self.routes = {
            "/skills": ("GET", self.get_skills),
            "/skills/upload": ("POST", self.upload_skill),
            "/skills/download": ("GET", self.download_skill),
            "/skills/update": ("POST", self.update_skill),
            "/skills/delete": ("POST", self.delete_skill),
            "/skills/neo/candidates": ("GET", self.get_neo_candidates),
            "/skills/neo/releases": ("GET", self.get_neo_releases),
            "/skills/neo/payload": ("GET", self.get_neo_payload),
            "/skills/neo/evaluate": ("POST", self.evaluate_neo_candidate),
            "/skills/neo/promote": ("POST", self.promote_neo_candidate),
            "/skills/neo/rollback": ("POST", self.rollback_neo_release),
            "/skills/neo/sync": ("POST", self.sync_neo_release),
            "/skills/neo/delete-candidate": ("POST", self.delete_neo_candidate),
            "/skills/neo/delete-release": ("POST", self.delete_neo_release),
        }
        self.register_routes()

    def _get_neo_client_config(self) -> tuple[str, str]:
        provider_settings = self.core_lifecycle.astrbot_config.get(
            "provider_settings",
            {},
        )
        sandbox = provider_settings.get("sandbox", {})
        endpoint = sandbox.get("shipyard_neo_endpoint", "")
        access_token = sandbox.get("shipyard_neo_access_token", "")

        # Auto-discover token from Bay's credentials.json if not configured
        if not access_token and endpoint:
            access_token = _discover_bay_credentials(endpoint)

        if not endpoint or not access_token:
            raise ValueError(
                "Shipyard Neo endpoint or access token not configured. "
                "Set them in Dashboard or ensure Bay's credentials.json is accessible."
            )
        return endpoint, access_token

    async def _delete_neo_release(
        self, client: Any, release_id: str, reason: str | None
    ):
        return await client.skills.delete_release(release_id, reason=reason)

    async def _delete_neo_candidate(
        self, client: Any, candidate_id: str, reason: str | None
    ):
        return await client.skills.delete_candidate(candidate_id, reason=reason)

    async def _with_neo_client(
        self,
        operation: Callable[[Any], Awaitable[dict]],
    ) -> dict:
        try:
            endpoint, access_token = self._get_neo_client_config()

            from shipyard_neo import BayClient

            async with BayClient(
                endpoint_url=endpoint,
                access_token=access_token,
            ) as client:
                return await operation(client)
        except ValueError as e:
            # Config not ready — expected when Neo isn't set up yet
            logger.debug("[Neo] %s", e)
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def get_skills(self):
        try:
            provider_settings = self.core_lifecycle.astrbot_config.get(
                "provider_settings", {}
            )
            runtime = provider_settings.get("computer_use_runtime", "local")
            skill_mgr = SkillManager()
            skills = skill_mgr.list_skills(
                active_only=False, runtime=runtime, show_sandbox_path=False
            )
            return (
                Response()
                .ok(
                    {
                        "skills": [skill.__dict__ for skill in skills],
                        "runtime": runtime,
                        "sandbox_cache": skill_mgr.get_sandbox_skills_cache_status(),
                    }
                )
                .__dict__
            )
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def upload_skill(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        temp_path = None
        try:
            files = await request.files
            file = files.get("file")
            if not file:
                return Response().error("Missing file").__dict__
            filename = os.path.basename(file.filename or "skill.zip")
            if not filename.lower().endswith(".zip"):
                return Response().error("Only .zip files are supported").__dict__

            temp_dir = get_astrbot_temp_path()
            os.makedirs(temp_dir, exist_ok=True)
            temp_path = os.path.join(temp_dir, filename)
            await file.save(temp_path)

            skill_mgr = SkillManager()
            skill_name = skill_mgr.install_skill_from_zip(temp_path, overwrite=True)

            try:
                await sync_skills_to_active_sandboxes()
            except Exception:
                logger.warning("Failed to sync uploaded skills to active sandboxes.")

            return (
                Response()
                .ok({"name": skill_name}, "Skill uploaded successfully.")
                .__dict__
            )
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    logger.warning(f"Failed to remove temp skill file: {temp_path}")

    async def download_skill(self):
        try:
            name = str(request.args.get("name") or "").strip()
            if not name:
                return Response().error("Missing skill name").__dict__
            if not _SKILL_NAME_RE.match(name):
                return Response().error("Invalid skill name").__dict__

            skill_mgr = SkillManager()
            if skill_mgr.is_sandbox_only_skill(name):
                return (
                    Response()
                    .error(
                        "Sandbox preset skill cannot be downloaded from local skill files."
                    )
                    .__dict__
                )

            skill_dir = Path(skill_mgr.skills_root) / name
            skill_md = skill_dir / "SKILL.md"
            if not skill_dir.is_dir() or not skill_md.exists():
                return Response().error("Local skill not found").__dict__

            export_dir = Path(get_astrbot_temp_path()) / "skill_exports"
            export_dir.mkdir(parents=True, exist_ok=True)
            zip_base = export_dir / name
            zip_path = zip_base.with_suffix(".zip")
            if zip_path.exists():
                zip_path.unlink()

            shutil.make_archive(
                str(zip_base),
                "zip",
                root_dir=str(skill_mgr.skills_root),
                base_dir=name,
            )

            return await send_file(
                str(zip_path),
                as_attachment=True,
                attachment_filename=f"{name}.zip",
                conditional=True,
            )
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def update_skill(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )
        try:
            data = await request.get_json()
            name = data.get("name")
            active = data.get("active", True)
            if not name:
                return Response().error("Missing skill name").__dict__
            SkillManager().set_skill_active(name, bool(active))
            return Response().ok({"name": name, "active": bool(active)}).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def delete_skill(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )
        try:
            data = await request.get_json()
            name = data.get("name")
            if not name:
                return Response().error("Missing skill name").__dict__
            SkillManager().delete_skill(name)
            try:
                await sync_skills_to_active_sandboxes()
            except Exception:
                logger.warning("Failed to sync deleted skills to active sandboxes.")
            return Response().ok({"name": name}).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def get_neo_candidates(self):
        logger.info("[Neo] GET /skills/neo/candidates requested.")
        status = request.args.get("status")
        skill_key = request.args.get("skill_key")
        limit = int(request.args.get("limit", 100))
        offset = int(request.args.get("offset", 0))

        async def _do(client):
            candidates = await client.skills.list_candidates(
                status=status,
                skill_key=skill_key,
                limit=limit,
                offset=offset,
            )
            result = _to_jsonable(candidates)
            total = result.get("total", "?") if isinstance(result, dict) else "?"
            logger.info(f"[Neo] Candidates fetched: total={total}")
            return Response().ok(result).__dict__

        return await self._with_neo_client(_do)

    async def get_neo_releases(self):
        logger.info("[Neo] GET /skills/neo/releases requested.")
        skill_key = request.args.get("skill_key")
        stage = request.args.get("stage")
        active_only = _to_bool(request.args.get("active_only"), False)
        limit = int(request.args.get("limit", 100))
        offset = int(request.args.get("offset", 0))

        async def _do(client):
            releases = await client.skills.list_releases(
                skill_key=skill_key,
                active_only=active_only,
                stage=stage,
                limit=limit,
                offset=offset,
            )
            result = _to_jsonable(releases)
            total = result.get("total", "?") if isinstance(result, dict) else "?"
            logger.info(f"[Neo] Releases fetched: total={total}")
            return Response().ok(result).__dict__

        return await self._with_neo_client(_do)

    async def get_neo_payload(self):
        logger.info("[Neo] GET /skills/neo/payload requested.")
        payload_ref = request.args.get("payload_ref", "")
        if not payload_ref:
            return Response().error("Missing payload_ref").__dict__

        async def _do(client):
            payload = await client.skills.get_payload(payload_ref)
            logger.info(f"[Neo] Payload fetched: ref={payload_ref}")
            return Response().ok(_to_jsonable(payload)).__dict__

        return await self._with_neo_client(_do)

    async def evaluate_neo_candidate(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )
        logger.info("[Neo] POST /skills/neo/evaluate requested.")
        data = await request.get_json()
        candidate_id = data.get("candidate_id")
        passed_value = data.get("passed")
        if not candidate_id or passed_value is None:
            return Response().error("Missing candidate_id or passed").__dict__
        passed = _to_bool(passed_value, False)

        async def _do(client):
            result = await client.skills.evaluate_candidate(
                candidate_id,
                passed=passed,
                score=data.get("score"),
                benchmark_id=data.get("benchmark_id"),
                report=data.get("report"),
            )
            logger.info(
                f"[Neo] Candidate evaluated: id={candidate_id}, passed={passed}"
            )
            return Response().ok(_to_jsonable(result)).__dict__

        return await self._with_neo_client(_do)

    async def promote_neo_candidate(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )
        logger.info("[Neo] POST /skills/neo/promote requested.")
        data = await request.get_json()
        candidate_id = data.get("candidate_id")
        stage = data.get("stage", "canary")
        sync_to_local = _to_bool(data.get("sync_to_local"), True)
        if not candidate_id:
            return Response().error("Missing candidate_id").__dict__
        if stage not in {"canary", "stable"}:
            return Response().error("Invalid stage, must be canary/stable").__dict__

        async def _do(client):
            sync_mgr = NeoSkillSyncManager()
            result = await sync_mgr.promote_with_optional_sync(
                client,
                candidate_id=candidate_id,
                stage=stage,
                sync_to_local=sync_to_local,
            )
            release_json = result.get("release")
            logger.info(f"[Neo] Candidate promoted: id={candidate_id}, stage={stage}")

            sync_json = result.get("sync")
            did_sync_to_local = bool(sync_json)
            if did_sync_to_local:
                logger.info(
                    f"[Neo] Stable release synced to local: skill={sync_json.get('local_skill_name', '')}"
                )

            if result.get("sync_error"):
                resp = Response().error(
                    "Stable promote synced failed and has been rolled back. "
                    f"sync_error={result['sync_error']}"
                )
                resp.data = {
                    "release": release_json,
                    "rollback": result.get("rollback"),
                }
                return resp.__dict__

            # Try to push latest local skills to all active sandboxes.
            if not did_sync_to_local:
                try:
                    await sync_skills_to_active_sandboxes()
                except Exception:
                    logger.warning("Failed to sync skills to active sandboxes.")

            return Response().ok({"release": release_json, "sync": sync_json}).__dict__

        return await self._with_neo_client(_do)

    async def rollback_neo_release(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )
        logger.info("[Neo] POST /skills/neo/rollback requested.")
        data = await request.get_json()
        release_id = data.get("release_id")
        if not release_id:
            return Response().error("Missing release_id").__dict__

        async def _do(client):
            result = await client.skills.rollback_release(release_id)
            logger.info(f"[Neo] Release rolled back: id={release_id}")
            return Response().ok(_to_jsonable(result)).__dict__

        return await self._with_neo_client(_do)

    async def sync_neo_release(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )
        logger.info("[Neo] POST /skills/neo/sync requested.")
        data = await request.get_json()
        release_id = data.get("release_id")
        skill_key = data.get("skill_key")
        require_stable = _to_bool(data.get("require_stable"), True)
        if not release_id and not skill_key:
            return Response().error("Missing release_id or skill_key").__dict__

        async def _do(client):
            sync_mgr = NeoSkillSyncManager()
            result = await sync_mgr.sync_release(
                client,
                release_id=release_id,
                skill_key=skill_key,
                require_stable=require_stable,
            )
            logger.info(
                f"[Neo] Release synced to local: skill={result.local_skill_name}, "
                f"release_id={result.release_id}"
            )
            return (
                Response()
                .ok(
                    {
                        "skill_key": result.skill_key,
                        "local_skill_name": result.local_skill_name,
                        "release_id": result.release_id,
                        "candidate_id": result.candidate_id,
                        "payload_ref": result.payload_ref,
                        "map_path": result.map_path,
                        "synced_at": result.synced_at,
                    }
                )
                .__dict__
            )

        return await self._with_neo_client(_do)

    async def delete_neo_candidate(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )
        logger.info("[Neo] POST /skills/neo/delete-candidate requested.")
        data = await request.get_json()
        candidate_id = data.get("candidate_id")
        reason = data.get("reason")
        if not candidate_id:
            return Response().error("Missing candidate_id").__dict__

        async def _do(client):
            result = await self._delete_neo_candidate(client, candidate_id, reason)
            logger.info(f"[Neo] Candidate deleted: id={candidate_id}")
            return Response().ok(_to_jsonable(result)).__dict__

        return await self._with_neo_client(_do)

    async def delete_neo_release(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )
        logger.info("[Neo] POST /skills/neo/delete-release requested.")
        data = await request.get_json()
        release_id = data.get("release_id")
        reason = data.get("reason")
        if not release_id:
            return Response().error("Missing release_id").__dict__

        async def _do(client):
            result = await self._delete_neo_release(client, release_id, reason)
            logger.info(f"[Neo] Release deleted: id={release_id}")
            return Response().ok(_to_jsonable(result)).__dict__

        return await self._with_neo_client(_do)
