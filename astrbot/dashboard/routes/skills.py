import os
import traceback
from typing import Any

from quart import request

from astrbot.core import DEMO_MODE, logger
from astrbot.core.computer.computer_client import sync_skills_to_active_sandboxes
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


class SkillsRoute(Route):
    def __init__(self, context: RouteContext, core_lifecycle) -> None:
        super().__init__(context)
        self.core_lifecycle = core_lifecycle
        self.routes = {
            "/skills": ("GET", self.get_skills),
            "/skills/upload": ("POST", self.upload_skill),
            "/skills/update": ("POST", self.update_skill),
            "/skills/delete": ("POST", self.delete_skill),
            "/skills/neo/candidates": ("GET", self.get_neo_candidates),
            "/skills/neo/releases": ("GET", self.get_neo_releases),
            "/skills/neo/payload": ("GET", self.get_neo_payload),
            "/skills/neo/evaluate": ("POST", self.evaluate_neo_candidate),
            "/skills/neo/promote": ("POST", self.promote_neo_candidate),
            "/skills/neo/rollback": ("POST", self.rollback_neo_release),
            "/skills/neo/sync": ("POST", self.sync_neo_release),
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
        if not endpoint or not access_token:
            raise ValueError(
                "Shipyard Neo configuration is incomplete. "
                "Please set provider_settings.sandbox.shipyard_neo_endpoint "
                "and shipyard_neo_access_token."
            )
        return endpoint, access_token

    async def get_skills(self):
        try:
            provider_settings = self.core_lifecycle.astrbot_config.get(
                "provider_settings", {}
            )
            runtime = provider_settings.get("computer_use_runtime", "local")
            skills = SkillManager().list_skills(
                active_only=False, runtime=runtime, show_sandbox_path=False
            )
            return (
                Response()
                .ok(
                    {
                        "skills": [skill.__dict__ for skill in skills],
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
            return Response().ok({"name": name}).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def get_neo_candidates(self):
        try:
            endpoint, access_token = self._get_neo_client_config()
            status = request.args.get("status")
            skill_key = request.args.get("skill_key")
            limit = int(request.args.get("limit", 100))
            offset = int(request.args.get("offset", 0))

            from shipyard_neo import BayClient

            async with BayClient(
                endpoint_url=endpoint,
                access_token=access_token,
            ) as client:
                candidates = await client.skills.list_candidates(
                    status=status,
                    skill_key=skill_key,
                    limit=limit,
                    offset=offset,
                )
                return Response().ok(_to_jsonable(candidates)).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def get_neo_releases(self):
        try:
            endpoint, access_token = self._get_neo_client_config()
            skill_key = request.args.get("skill_key")
            stage = request.args.get("stage")
            active_only = _to_bool(request.args.get("active_only"), False)
            limit = int(request.args.get("limit", 100))
            offset = int(request.args.get("offset", 0))

            from shipyard_neo import BayClient

            async with BayClient(
                endpoint_url=endpoint,
                access_token=access_token,
            ) as client:
                releases = await client.skills.list_releases(
                    skill_key=skill_key,
                    active_only=active_only,
                    stage=stage,
                    limit=limit,
                    offset=offset,
                )
                return Response().ok(_to_jsonable(releases)).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def get_neo_payload(self):
        try:
            endpoint, access_token = self._get_neo_client_config()
            payload_ref = request.args.get("payload_ref", "")
            if not payload_ref:
                return Response().error("Missing payload_ref").__dict__

            from shipyard_neo import BayClient

            async with BayClient(
                endpoint_url=endpoint,
                access_token=access_token,
            ) as client:
                payload = await client.skills.get_payload(payload_ref)
                return Response().ok(_to_jsonable(payload)).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def evaluate_neo_candidate(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )
        try:
            endpoint, access_token = self._get_neo_client_config()
            data = await request.get_json()
            candidate_id = data.get("candidate_id")
            passed_value = data.get("passed")
            if not candidate_id or passed_value is None:
                return Response().error("Missing candidate_id or passed").__dict__
            passed = _to_bool(passed_value, False)

            from shipyard_neo import BayClient

            async with BayClient(
                endpoint_url=endpoint,
                access_token=access_token,
            ) as client:
                result = await client.skills.evaluate_candidate(
                    candidate_id,
                    passed=passed,
                    score=data.get("score"),
                    benchmark_id=data.get("benchmark_id"),
                    report=data.get("report"),
                )
                return Response().ok(_to_jsonable(result)).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def promote_neo_candidate(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )
        try:
            endpoint, access_token = self._get_neo_client_config()
            data = await request.get_json()
            candidate_id = data.get("candidate_id")
            stage = data.get("stage", "canary")
            sync_to_local = _to_bool(data.get("sync_to_local"), True)
            if not candidate_id:
                return Response().error("Missing candidate_id").__dict__
            if stage not in {"canary", "stable"}:
                return Response().error("Invalid stage, must be canary/stable").__dict__

            from shipyard_neo import BayClient

            async with BayClient(
                endpoint_url=endpoint,
                access_token=access_token,
            ) as client:
                release = await client.skills.promote_candidate(
                    candidate_id, stage=stage
                )
                release_json = _to_jsonable(release)

                sync_json = None
                if stage == "stable" and sync_to_local:
                    sync_mgr = NeoSkillSyncManager()
                    try:
                        sync_result = await sync_mgr.sync_release(
                            client,
                            release_id=str(release_json.get("id", "")),
                            require_stable=True,
                        )
                        sync_json = {
                            "skill_key": sync_result.skill_key,
                            "local_skill_name": sync_result.local_skill_name,
                            "release_id": sync_result.release_id,
                            "candidate_id": sync_result.candidate_id,
                            "payload_ref": sync_result.payload_ref,
                            "map_path": sync_result.map_path,
                            "synced_at": sync_result.synced_at,
                        }
                    except Exception as sync_err:
                        rollback_result = await client.skills.rollback_release(
                            str(release_json.get("id", ""))
                        )
                        resp = Response().error(
                            "Stable promote synced failed and has been rolled back. "
                            f"sync_error={sync_err}"
                        )
                        resp.data = {
                            "release": release_json,
                            "rollback": _to_jsonable(rollback_result),
                        }
                        return resp.__dict__

                # Try to push latest local skills to all active sandboxes.
                try:
                    await sync_skills_to_active_sandboxes()
                except Exception:
                    logger.warning("Failed to sync skills to active sandboxes.")

                return (
                    Response().ok({"release": release_json, "sync": sync_json}).__dict__
                )
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def rollback_neo_release(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )
        try:
            endpoint, access_token = self._get_neo_client_config()
            data = await request.get_json()
            release_id = data.get("release_id")
            if not release_id:
                return Response().error("Missing release_id").__dict__

            from shipyard_neo import BayClient

            async with BayClient(
                endpoint_url=endpoint,
                access_token=access_token,
            ) as client:
                result = await client.skills.rollback_release(release_id)
                return Response().ok(_to_jsonable(result)).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def sync_neo_release(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )
        try:
            endpoint, access_token = self._get_neo_client_config()
            data = await request.get_json()
            release_id = data.get("release_id")
            skill_key = data.get("skill_key")
            require_stable = _to_bool(data.get("require_stable"), True)
            if not release_id and not skill_key:
                return Response().error("Missing release_id or skill_key").__dict__

            from shipyard_neo import BayClient

            async with BayClient(
                endpoint_url=endpoint,
                access_token=access_token,
            ) as client:
                sync_mgr = NeoSkillSyncManager()
                result = await sync_mgr.sync_release(
                    client,
                    release_id=release_id,
                    skill_key=skill_key,
                    require_stable=require_stable,
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
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__
