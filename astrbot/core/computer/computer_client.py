from astrbot.core.lang import t
import os
import shutil
import uuid
from pathlib import Path

from astrbot.api import logger
from astrbot.core.skills.skill_manager import SANDBOX_SKILLS_ROOT
from astrbot.core.star.context import Context
from astrbot.core.utils.astrbot_path import (
    get_astrbot_skills_path,
    get_astrbot_temp_path,
)

from .booters.base import ComputerBooter
from .booters.local import LocalBooter

session_booter: dict[str, ComputerBooter] = {}
local_booter: ComputerBooter | None = None


async def _sync_skills_to_sandbox(booter: ComputerBooter) -> None:
    skills_root = get_astrbot_skills_path()
    if not os.path.isdir(skills_root):
        return
    if not any(Path(skills_root).iterdir()):
        return

    temp_dir = get_astrbot_temp_path()
    os.makedirs(temp_dir, exist_ok=True)
    zip_base = os.path.join(temp_dir, "skills_bundle")
    zip_path = f"{zip_base}.zip"

    try:
        if os.path.exists(zip_path):
            os.remove(zip_path)
        shutil.make_archive(zip_base, "zip", skills_root)
        remote_zip = Path(SANDBOX_SKILLS_ROOT) / "skills.zip"
        logger.info(t("msg-7cb974b8"))
        await booter.shell.exec(f"mkdir -p {SANDBOX_SKILLS_ROOT}")
        upload_result = await booter.upload_file(zip_path, str(remote_zip))
        if not upload_result.get("success", False):
            raise RuntimeError(t("msg-130cf3e3"))
        # Use -n flag to never overwrite existing files, fallback to Python if unzip unavailable
        await booter.shell.exec(
            f"unzip -n {remote_zip} -d {SANDBOX_SKILLS_ROOT} || "
            f"python3 -c \"import zipfile, os, pathlib; z=zipfile.ZipFile('{remote_zip}'); "
            f"[z.extract(m, '{SANDBOX_SKILLS_ROOT}') for m in z.namelist() "
            f"if not os.path.exists(os.path.join('{SANDBOX_SKILLS_ROOT}', m))]\" || "
            f"python -c \"import zipfile, os, pathlib; z=zipfile.ZipFile('{remote_zip}'); "
            f"[z.extract(m, '{SANDBOX_SKILLS_ROOT}') for m in z.namelist() "
            f"if not os.path.exists(os.path.join('{SANDBOX_SKILLS_ROOT}', m))]\"; "
            f"rm -f {remote_zip}"
        )
    finally:
        if os.path.exists(zip_path):
            try:
                os.remove(zip_path)
            except Exception:
                logger.warning(t("msg-99188d69", zip_path=zip_path))


async def get_booter(
    context: Context,
    session_id: str,
) -> ComputerBooter:
    config = context.get_config(umo=session_id)

    sandbox_cfg = config.get("provider_settings", {}).get("sandbox", {})
    booter_type = sandbox_cfg.get("booter", "shipyard")

    if session_id in session_booter:
        booter = session_booter[session_id]
        if not await booter.available():
            # rebuild
            session_booter.pop(session_id, None)
    if session_id not in session_booter:
        uuid_str = uuid.uuid5(uuid.NAMESPACE_DNS, session_id).hex
        if booter_type == "shipyard":
            from .booters.shipyard import ShipyardBooter

            ep = sandbox_cfg.get("shipyard_endpoint", "")
            token = sandbox_cfg.get("shipyard_access_token", "")
            ttl = sandbox_cfg.get("shipyard_ttl", 3600)
            max_sessions = sandbox_cfg.get("shipyard_max_sessions", 10)

            client = ShipyardBooter(
                endpoint_url=ep, access_token=token, ttl=ttl, session_num=max_sessions
            )
        elif booter_type == "boxlite":
            from .booters.boxlite import BoxliteBooter

            client = BoxliteBooter()
        else:
            raise ValueError(t("msg-3f3c81da", booter_type=booter_type))

        try:
            await client.boot(uuid_str)
            await _sync_skills_to_sandbox(client)
        except Exception as e:
            logger.error(t("msg-e20cc33a", session_id=session_id, e=e))
            raise e

        session_booter[session_id] = client
    return session_booter[session_id]


def get_local_booter() -> ComputerBooter:
    global local_booter
    if local_booter is None:
        local_booter = LocalBooter()
    return local_booter
