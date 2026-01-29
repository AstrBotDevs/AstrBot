import os
import traceback

from quart import request

from astrbot.core import DEMO_MODE, logger
from astrbot.core.computer.computer_client import get_booter
from astrbot.core.skills.skill_manager import SkillManager
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from .route import Response, Route, RouteContext


class SkillsRoute(Route):
    def __init__(self, context: RouteContext, core_lifecycle) -> None:
        super().__init__(context)
        self.core_lifecycle = core_lifecycle
        self.routes = {
            "/skills": ("GET", self.get_skills),
            "/skills/upload": ("POST", self.upload_skill),
            "/skills/update": ("POST", self.update_skill),
            "/skills/delete": ("POST", self.delete_skill),
        }
        self.register_routes()

    async def get_skills(self):
        try:
            cfg = self.core_lifecycle.astrbot_config.get("provider_settings", {}).get(
                "skills", {}
            )
            runtime = cfg.get("runtime", "local")
            skills = SkillManager().list_skills(
                active_only=False, runtime=runtime, show_sandbox_path=False
            )
            return Response().ok([skill.__dict__ for skill in skills]).__dict__
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

            cfg = self.core_lifecycle.astrbot_config.get("provider_settings", {}).get(
                "skills", {}
            )
            runtime = cfg.get("runtime", "local")
            if runtime == "sandbox":
                sandbox_enabled = (
                    self.core_lifecycle.astrbot_config.get("provider_settings", {})
                    .get("sandbox", {})
                    .get("enable", False)
                )
                if not sandbox_enabled:
                    return (
                        Response()
                        .error(
                            "Sandbox is not enabled. Please enable sandbox before using sandbox runtime."
                        )
                        .__dict__
                    )
            skill_mgr = SkillManager()
            skill_name = skill_mgr.install_skill_from_zip(temp_path, overwrite=True)

            if runtime == "sandbox":
                sb = await get_booter(self.core_lifecycle.star_context, "skills-upload")
                remote_root = "/home/shared/skills"
                remote_zip = f"{remote_root}/{skill_name}.zip"
                await sb.shell.exec(f"mkdir -p {remote_root}")
                upload_result = await sb.upload_file(temp_path, remote_zip)
                if not upload_result.get("success", False):
                    return (
                        Response().error("Failed to upload skill to sandbox").__dict__
                    )
                await sb.shell.exec(
                    f"unzip -o {remote_zip} -d {remote_root} && rm -f {remote_zip}"
                )

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
