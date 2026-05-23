import asyncio
import json
import os
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from astrbot.api import logger
from astrbot.core.skills.skill_manager import SANDBOX_SKILLS_ROOT, SkillManager
from astrbot.core.star.context import Context
from astrbot.core.utils.astrbot_path import (
    get_astrbot_skills_path,
    get_astrbot_temp_path,
)

from .booters.base import ComputerBooter
from .booters.local import LocalBooter

session_booter: dict[str, ComputerBooter] = {}
local_booters: dict[tuple[str, bool], ComputerBooter] = {}


async def _sync_skills_to_sandbox(booter: ComputerBooter) -> None:
    """Sync local skills to sandbox and refresh cache.

    Backward-compatible orchestrator: keep historical behavior while internally
    splitting into `apply` and `scan` phases.
    """
    sync_skill_dirs = _collect_sync_skill_dirs()

    temp_dir = Path(get_astrbot_temp_path())
    temp_dir.mkdir(parents=True, exist_ok=True)
    zip_base = temp_dir / "skills_bundle"
    zip_path = zip_base.with_suffix(".zip")
    bundle_root = temp_dir / f"skills_bundle_{uuid.uuid4().hex}"

    try:
        if sync_skill_dirs:
            if zip_path.exists():
                zip_path.unlink()
            if bundle_root.exists():
                shutil.rmtree(bundle_root)
            bundle_root.mkdir(parents=True)
            for skill_name, skill_dir in sync_skill_dirs:
                shutil.copytree(skill_dir, bundle_root / skill_name)
            shutil.make_archive(str(zip_base), "zip", str(bundle_root))
            remote_zip = Path(SANDBOX_SKILLS_ROOT) / "skills.zip"
            logger.info("Uploading skills bundle to sandbox...")
            await booter.shell.exec(f"mkdir -p {SANDBOX_SKILLS_ROOT}")
            upload_result = await booter.upload_file(str(zip_path), str(remote_zip))
            if not upload_result.get("success", False):
                raise RuntimeError("Failed to upload skills bundle to sandbox.")
        else:
            logger.info(
                "No local skills found. Keeping sandbox built-ins and refreshing metadata."
            )
            await booter.shell.exec(f"rm -f {SANDBOX_SKILLS_ROOT}/skills.zip")

        # Keep backward-compatible behavior while splitting lifecycle into two
        # observable phases: apply (filesystem mutation) + scan (metadata read).
        await _apply_skills_to_sandbox(booter)
        payload = await _scan_sandbox_skills(booter)
        _update_sandbox_skills_cache(payload)
        managed = payload.get("managed_skills", []) if isinstance(payload, dict) else []
        logger.info(
            "[Computer] Sandbox skill sync complete: managed=%d",
            len(managed),
        )
    finally:
        if bundle_root.exists():
            try:
                shutil.rmtree(bundle_root)
            except Exception:
                logger.warning(f"Failed to remove temp skills bundle: {bundle_root}")
        if zip_path.exists():
            try:
                zip_path.unlink()
            except Exception:
                logger.warning(f"Failed to remove temp skills zip: {zip_path}")


async def get_booter(
    context: Context,
    session_id: str,
) -> ComputerBooter:
    config = context.get_config(umo=session_id)

    runtime = config.get("provider_settings", {}).get("computer_use_runtime", "local")
    if runtime == "local":
        return get_local_booter()
    elif runtime == "none":
        raise RuntimeError("Sandbox runtime is disabled by configuration.")

    sandbox_cfg = config.get("provider_settings", {}).get("sandbox", {})
    booter_type = sandbox_cfg.get("booter", "shipyard_neo")
    cua_idle_timeout = _get_cua_idle_timeout(config) if booter_type == "cua" else 0.0

    if session_id in session_booter:
        booter = session_booter[session_id]
        if not await booter.available():
            # Clean up old booter before rebuilding so sandbox resources
            # on Bay (containers, volumes, networks) are not leaked.
            # Only ShipyardNeoBooter supports delete_sandbox; other booters
            # (local, boxlite, cua, etc.) are not backed by a remote sandbox
            # manager and don't need it.
            try:
                if booter_type == "shipyard_neo":
                    await booter.shutdown(delete_sandbox=True)
                else:
                    await booter.shutdown()
            except Exception as shutdown_err:
                logger.warning(
                    "[Computer] Error shutting down stale booter for session %s: %s",
                    session_id,
                    shutdown_err,
                )
            _clear_cua_idle_state(session_id)
            session_booter.pop(session_id, None)
    if session_id not in session_booter:
        uuid_str = uuid.uuid5(uuid.NAMESPACE_DNS, session_id).hex
        logger.info(
            f"[Computer] Initializing booter: type={booter_type}, session={session_id}"
        )
        if booter_type == "shipyard":
            from .booters.shipyard import ShipyardBooter

            ep = sandbox_cfg.get("shipyard_endpoint", "")
            token = sandbox_cfg.get("shipyard_access_token", "")
            ttl = sandbox_cfg.get("shipyard_ttl", 3600)
            max_sessions = sandbox_cfg.get("shipyard_max_sessions", 10)

            client = ShipyardBooter(
                endpoint_url=ep, access_token=token, ttl=ttl, session_num=max_sessions
            )
        elif booter_type == "shipyard_neo":
            from .booters.shipyard_neo import ShipyardNeoBooter

            ep = sandbox_cfg.get("shipyard_neo_endpoint", "")
            token = sandbox_cfg.get("shipyard_neo_access_token", "")
            ttl = sandbox_cfg.get("shipyard_neo_ttl", 3600)
            profile = sandbox_cfg.get("shipyard_neo_profile", "python-default")

            # Auto-discover token from Bay's credentials.json if not configured
            if not token:
                token = _discover_bay_credentials(ep)

            logger.info(
                f"[Computer] Shipyard Neo config: endpoint={ep}, profile={profile}, ttl={ttl}"
            )
            client = ShipyardNeoBooter(
                endpoint_url=ep,
                access_token=token,
                profile=profile,
                ttl=ttl,
            )
        elif booter_type == "cua":
            from .booters.cua import CuaBooter, build_cua_booter_kwargs

            cua_kwargs = build_cua_booter_kwargs(sandbox_cfg)
            logger.info(
                f"[Computer] CUA config: image={cua_kwargs['image']}, "
                f"os_type={cua_kwargs['os_type']}, ttl={cua_kwargs['ttl']}"
            )
            client = CuaBooter(**cua_kwargs)
        elif booter_type == "boxlite":
            from .booters.boxlite import BoxliteBooter

            client = BoxliteBooter()
        else:
            raise ValueError(f"Unknown booter type: {booter_type}")

        try:
            await client.boot(uuid_str)
            logger.info(
                f"[Computer] Sandbox booted successfully: type={booter_type}, session={session_id}"
            )
            await _sync_skills_to_sandbox(client)
        except Exception as e:
            logger.error(f"Error booting sandbox for session {session_id}: {e}")
            try:
                if booter_type == "shipyard_neo":
                    await client.shutdown(delete_sandbox=True)
                else:
                    await client.shutdown()
            except Exception as shutdown_error:
                logger.warning(
                    "Failed to shutdown sandbox after boot error for session %s: %s",
                    session_id,
                    shutdown_error,
                )
            _clear_cua_idle_state(session_id)
            raise e

        session_booter[session_id] = client
    if booter_type == "cua":
        _schedule_cua_idle_cleanup(session_id, cua_idle_timeout)
    return session_booter[session_id]


def get_local_booter(session_id: str, sandboxed: bool = False) -> ComputerBooter:
    key = (session_id, sandboxed)
    if key not in local_booters:
        local_booters[key] = LocalBooter(session_id=session_id, sandboxed=sandboxed)
    return local_booters[key]
