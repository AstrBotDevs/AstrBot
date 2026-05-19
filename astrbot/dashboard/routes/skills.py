import os
import re
import shutil
import traceback
from pathlib import Path

from quart import request, send_file

from astrbot.core import DEMO_MODE, logger
from astrbot.core.computer.computer_client import sync_skills_to_active_sandboxes
from astrbot.core.skills.skill_manager import SkillManager
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from .route import Response, Route, RouteContext

_SKILL_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_SKILL_FILE_MAX_BYTES = 512 * 1024
_EDITABLE_SKILL_FILE_SUFFIXES = {
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".ts",
    ".txt",
    ".yaml",
    ".yml",
}
_EDITABLE_SKILL_FILENAMES = {"Dockerfile", "Makefile"}


def _next_available_temp_path(temp_dir: str, filename: str) -> str:
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    candidate = filename
    index = 1
    while os.path.exists(os.path.join(temp_dir, candidate)):
        candidate = f"{stem}_{index}{suffix}"
        index += 1
    return os.path.join(temp_dir, candidate)


class SkillsRoute(Route):
    def __init__(self, context: RouteContext, core_lifecycle) -> None:
        super().__init__(context)
        self.core_lifecycle = core_lifecycle
        self.routes = {
            "/skills": ("GET", self.get_skills),
            "/skills/upload": ("POST", self.upload_skill),
            "/skills/batch-upload": ("POST", self.batch_upload_skills),
            "/skills/download": ("GET", self.download_skill),
            "/skills/files": ("GET", self.list_skill_files),
            "/skills/file": [
                ("GET", self.get_skill_file),
                ("POST", self.update_skill_file),
            ],
            "/skills/update": ("POST", self.update_skill),
            "/skills/delete": ("POST", self.delete_skill),
        }
        self.register_routes()

    def _resolve_local_skill_dir(self, name: str) -> Path:
        skill_name = str(name or "").strip()
        if not skill_name:
            raise ValueError("Missing skill name")
        if not _SKILL_NAME_RE.match(skill_name):
            raise ValueError("Invalid skill name")

        skill_mgr = SkillManager()
        if skill_mgr.is_sandbox_only_skill(skill_name):
            raise PermissionError(
                "Sandbox preset skill cannot be opened from local skill files."
            )

        plugin_skill_dir = skill_mgr._get_plugin_skill_dir(skill_name)
        if plugin_skill_dir is not None:
            return plugin_skill_dir.resolve(strict=True)

        skills_root = Path(skill_mgr.skills_root).resolve(strict=True)
        skill_dir = (skills_root / skill_name).resolve(strict=True)
        if not skill_dir.is_relative_to(skills_root):
            raise PermissionError("Invalid skill path")
        if not skill_dir.is_dir() or not (skill_dir / "SKILL.md").exists():
            raise FileNotFoundError("Local skill not found")
        return skill_dir

    def _resolve_skill_relative_path(
        self,
        skill_dir: Path,
        relative_path: str | None,
        *,
        expect_file: bool,
    ) -> Path:
        raw_path = str(relative_path or ".").strip() or "."
        normalized = Path(raw_path.replace("\\", "/"))
        if normalized.is_absolute() or ".." in normalized.parts:
            raise ValueError("Invalid relative path")

        target = (skill_dir / normalized).resolve(strict=True)
        if not target.is_relative_to(skill_dir):
            raise PermissionError("Path escapes skill directory")
        if expect_file and not target.is_file():
            raise FileNotFoundError("Skill file not found")
        if not expect_file and not target.is_dir():
            raise FileNotFoundError("Skill directory not found")
        return target

    @staticmethod
    def _skill_relative_path(skill_dir: Path, target: Path) -> str:
        rel = target.relative_to(skill_dir).as_posix()
        return "" if rel == "." else rel

    @staticmethod
    def _is_editable_skill_file(path: Path) -> bool:
        return (
            path.name in _EDITABLE_SKILL_FILENAMES
            or path.suffix.lower() in _EDITABLE_SKILL_FILE_SUFFIXES
        )

    def _serialize_skill_file_entry(
        self,
        skill_dir: Path,
        path: Path,
        *,
        readonly: bool = False,
    ) -> dict:
        stat = path.stat()
        is_dir = path.is_dir()
        return {
            "name": path.name,
            "path": self._skill_relative_path(skill_dir, path),
            "type": "directory" if is_dir else "file",
            "size": 0 if is_dir else stat.st_size,
            "editable": (
                not readonly
                and (not is_dir)
                and self._is_editable_skill_file(path)
                and stat.st_size <= _SKILL_FILE_MAX_BYTES
            ),
        }

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
            skill_mgr = SkillManager()
            temp_path = _next_available_temp_path(temp_dir, filename)
            await file.save(temp_path)

            try:
                try:
                    skill_name = skill_mgr.install_skill_from_zip(
                        temp_path, overwrite=False, skill_name_hint=Path(filename).stem
                    )
                except TypeError:
                    # Backward compatibility for callers that do not accept skill_name_hint
                    skill_name = skill_mgr.install_skill_from_zip(
                        temp_path, overwrite=False
                    )
            except Exception:
                # Keep behavior consistent with previous implementation
                # and bubble up install errors (including duplicates).
                raise

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

    async def batch_upload_skills(self):
        """批量上传多个 skill ZIP 文件"""
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        try:
            files = await request.files
            file_list = files.getlist("files")

            if not file_list:
                return Response().error("No files provided").__dict__

            succeeded = []
            failed = []
            skipped = []
            skill_mgr = SkillManager()
            temp_dir = get_astrbot_temp_path()
            os.makedirs(temp_dir, exist_ok=True)

            for file in file_list:
                filename = os.path.basename(file.filename or "unknown.zip")
                temp_path = None

                try:
                    if not filename.lower().endswith(".zip"):
                        failed.append(
                            {
                                "filename": filename,
                                "error": "Only .zip files are supported",
                            }
                        )
                        continue

                    temp_path = _next_available_temp_path(temp_dir, filename)
                    await file.save(temp_path)

                    try:
                        skill_name = skill_mgr.install_skill_from_zip(
                            temp_path,
                            overwrite=False,
                            skill_name_hint=Path(filename).stem,
                        )
                    except TypeError:
                        # Backward compatibility for monkeypatched implementations in tests
                        try:
                            skill_name = skill_mgr.install_skill_from_zip(
                                temp_path, overwrite=False
                            )
                        except FileExistsError:
                            skipped.append(
                                {
                                    "filename": filename,
                                    "name": Path(filename).stem,
                                    "error": "Skill already exists.",
                                }
                            )
                            skill_name = None
                    except FileExistsError:
                        skipped.append(
                            {
                                "filename": filename,
                                "name": Path(filename).stem,
                                "error": "Skill already exists.",
                            }
                        )
                        skill_name = None

                    if skill_name is None:
                        continue
                    succeeded.append({"filename": filename, "name": skill_name})

                except Exception as e:
                    failed.append({"filename": filename, "error": str(e)})
                finally:
                    if temp_path and os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except Exception:
                            pass

            if succeeded:
                try:
                    await sync_skills_to_active_sandboxes()
                except Exception:
                    logger.warning(
                        "Failed to sync uploaded skills to active sandboxes."
                    )

            total = len(file_list)
            success_count = len(succeeded)
            skipped_count = len(skipped)
            failed_count = len(failed)

            if failed_count == 0 and success_count == total:
                message = f"All {total} skill(s) uploaded successfully."
                return (
                    Response()
                    .ok(
                        {
                            "total": total,
                            "succeeded": succeeded,
                            "failed": failed,
                            "skipped": skipped,
                        },
                        message,
                    )
                    .__dict__
                )
            if failed_count == 0 and success_count == 0:
                message = f"All {total} file(s) were skipped."
                return (
                    Response()
                    .ok(
                        {
                            "total": total,
                            "succeeded": succeeded,
                            "failed": failed,
                            "skipped": skipped,
                        },
                        message,
                    )
                    .__dict__
                )
            if success_count == 0 and skipped_count == 0:
                message = f"Upload failed for all {total} file(s)."
                resp = Response().error(message)
                resp.data = {
                    "total": total,
                    "succeeded": succeeded,
                    "failed": failed,
                    "skipped": skipped,
                }
                return resp.__dict__

            message = f"Partial success: {success_count}/{total} skill(s) uploaded."
            return (
                Response()
                .ok(
                    {
                        "total": total,
                        "succeeded": succeeded,
                        "failed": failed,
                        "skipped": skipped,
                    },
                    message,
                )
                .__dict__
            )

        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

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
            if skill_mgr.is_plugin_skill(name):
                return (
                    Response()
                    .error(
                        "Plugin-provided skill cannot be downloaded from local skill files."
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

    async def list_skill_files(self):
        try:
            name = str(request.args.get("name") or "").strip()
            relative_path = request.args.get("path", "")
            readonly = SkillManager().is_plugin_skill(name)
            skill_dir = self._resolve_local_skill_dir(name)
            target_dir = self._resolve_skill_relative_path(
                skill_dir,
                relative_path,
                expect_file=False,
            )

            entries = []
            for entry in sorted(
                target_dir.iterdir(),
                key=lambda item: (not item.is_dir(), item.name.lower()),
            ):
                try:
                    resolved = entry.resolve(strict=True)
                except OSError:
                    continue
                if not resolved.is_relative_to(skill_dir):
                    continue
                if not resolved.is_dir() and not resolved.is_file():
                    continue
                entries.append(
                    self._serialize_skill_file_entry(
                        skill_dir,
                        resolved,
                        readonly=readonly,
                    )
                )

            return (
                Response()
                .ok(
                    {
                        "name": name,
                        "path": self._skill_relative_path(skill_dir, target_dir),
                        "entries": entries,
                    }
                )
                .__dict__
            )
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def get_skill_file(self):
        try:
            name = str(request.args.get("name") or "").strip()
            relative_path = request.args.get("path", "SKILL.md")
            skill_dir = self._resolve_local_skill_dir(name)
            target_file = self._resolve_skill_relative_path(
                skill_dir,
                relative_path,
                expect_file=True,
            )
            if not self._is_editable_skill_file(target_file):
                return Response().error("Unsupported file type").__dict__

            size = target_file.stat().st_size
            if size > _SKILL_FILE_MAX_BYTES:
                return Response().error("File is too large").__dict__

            try:
                content = target_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return Response().error("File is not valid UTF-8 text").__dict__

            return (
                Response()
                .ok(
                    {
                        "name": name,
                        "path": self._skill_relative_path(skill_dir, target_file),
                        "content": content,
                        "size": size,
                        "editable": not SkillManager().is_plugin_skill(name),
                    }
                )
                .__dict__
            )
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def update_skill_file(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        try:
            data = await request.get_json()
            name = str(data.get("name") or "").strip()
            relative_path = data.get("path", "SKILL.md")
            content = data.get("content")
            if not isinstance(content, str):
                return Response().error("Missing file content").__dict__

            encoded = content.encode("utf-8")
            if len(encoded) > _SKILL_FILE_MAX_BYTES:
                return Response().error("File content is too large").__dict__

            skill_dir = self._resolve_local_skill_dir(name)
            if SkillManager().is_plugin_skill(name):
                return Response().error("Plugin-provided skill is read-only.").__dict__
            target_file = self._resolve_skill_relative_path(
                skill_dir,
                relative_path,
                expect_file=True,
            )
            if not self._is_editable_skill_file(target_file):
                return Response().error("Unsupported file type").__dict__

            target_file.write_text(content, encoding="utf-8")

            try:
                await sync_skills_to_active_sandboxes()
            except Exception:
                logger.warning("Failed to sync edited skills to active sandboxes.")

            return (
                Response()
                .ok(
                    {
                        "name": name,
                        "path": self._skill_relative_path(skill_dir, target_file),
                        "size": len(encoded),
                    }
                )
                .__dict__
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
