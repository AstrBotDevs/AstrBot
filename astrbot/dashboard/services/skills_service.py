from __future__ import annotations

import os
import re
import shutil
import traceback
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from astrbot.core import DEMO_MODE, logger
from astrbot.core.computer.computer_client import (
    _discover_bay_credentials,
    sync_skills_to_active_sandboxes,
)
from astrbot.core.skills.neo_skill_sync import NeoSkillSyncManager
from astrbot.core.skills.skill_manager import SkillManager
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

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


class SkillsServiceError(Exception):
    pass


@dataclass
class SkillsOperationResult:
    ok: bool = True
    data: dict | list | None = None
    message: str | None = None


@dataclass
class SkillArchive:
    path: Path
    filename: str


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
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


def _next_available_temp_path(temp_dir: str, filename: str) -> str:
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    candidate = filename
    index = 1
    while os.path.exists(os.path.join(temp_dir, candidate)):
        candidate = f"{stem}_{index}{suffix}"
        index += 1
    return os.path.join(temp_dir, candidate)


class SkillsService:
    def __init__(self, core_lifecycle) -> None:
        self.core_lifecycle = core_lifecycle

    @staticmethod
    def _payload(data: object) -> dict[str, Any]:
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _ensure_mutation_allowed() -> None:
        if DEMO_MODE:
            raise SkillsServiceError(
                "You are not permitted to do this operation in demo mode"
            )

    @staticmethod
    async def _save_upload(file: Any, target_path: str) -> None:
        if hasattr(file, "save"):
            maybe_awaitable = file.save(target_path)
            if hasattr(maybe_awaitable, "__await__"):
                await maybe_awaitable
            return

        if hasattr(file, "read"):
            data = file.read()
            if hasattr(data, "__await__"):
                data = await data
            Path(target_path).write_bytes(data)
            return

        raise SkillsServiceError("Invalid upload file")

    def resolve_local_skill_dir(self, name: str) -> Path:
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

    @staticmethod
    def resolve_skill_relative_path(
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
    def skill_relative_path(skill_dir: Path, target: Path) -> str:
        rel = target.relative_to(skill_dir).as_posix()
        return "" if rel == "." else rel

    @staticmethod
    def is_editable_skill_file(path: Path) -> bool:
        return (
            path.name in _EDITABLE_SKILL_FILENAMES
            or path.suffix.lower() in _EDITABLE_SKILL_FILE_SUFFIXES
        )

    def serialize_skill_file_entry(
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
            "path": self.skill_relative_path(skill_dir, path),
            "type": "directory" if is_dir else "file",
            "size": 0 if is_dir else stat.st_size,
            "editable": (
                not readonly
                and (not is_dir)
                and self.is_editable_skill_file(path)
                and stat.st_size <= _SKILL_FILE_MAX_BYTES
            ),
        }

    def get_neo_client_config(self) -> tuple[str, str]:
        provider_settings = self.core_lifecycle.astrbot_config.get(
            "provider_settings",
            {},
        )
        sandbox = provider_settings.get("sandbox", {})
        endpoint = sandbox.get("shipyard_neo_endpoint", "")
        access_token = sandbox.get("shipyard_neo_access_token", "")

        if not access_token and endpoint:
            access_token = _discover_bay_credentials(endpoint)

        if not endpoint or not access_token:
            raise ValueError(
                "Shipyard Neo endpoint or access token not configured. "
                "Set them in Dashboard or ensure Bay's credentials.json is accessible."
            )
        return endpoint, access_token

    async def with_neo_client(
        self,
        operation: Callable[[Any], Awaitable[Any]],
    ) -> SkillsOperationResult:
        try:
            endpoint, access_token = self.get_neo_client_config()

            from shipyard_neo import BayClient

            async with BayClient(
                endpoint_url=endpoint,
                access_token=access_token,
            ) as client:
                result = await operation(client)
                if isinstance(result, SkillsOperationResult):
                    return result
                return SkillsOperationResult(data=_to_jsonable(result))
        except ValueError as exc:
            logger.debug("[Neo] %s", exc)
            return SkillsOperationResult(ok=False, message=str(exc))
        except Exception as exc:
            logger.error(traceback.format_exc())
            return SkillsOperationResult(ok=False, message=str(exc))

    def get_skills(self) -> dict:
        provider_settings = self.core_lifecycle.astrbot_config.get(
            "provider_settings", {}
        )
        runtime = provider_settings.get("computer_use_runtime", "local")
        skill_mgr = SkillManager()
        skills = skill_mgr.list_skills(
            active_only=False,
            runtime=runtime,
            show_sandbox_path=False,
        )
        return {
            "skills": [skill.__dict__ for skill in skills],
            "runtime": runtime,
            "sandbox_cache": skill_mgr.get_sandbox_skills_cache_status(),
        }

    async def upload_skill(self, file: Any | None) -> SkillsOperationResult:
        self._ensure_mutation_allowed()
        temp_path = None
        if not file:
            raise SkillsServiceError("Missing file")

        filename = os.path.basename(file.filename or "skill.zip")
        if not filename.lower().endswith(".zip"):
            raise SkillsServiceError("Only .zip files are supported")

        temp_dir = get_astrbot_temp_path()
        os.makedirs(temp_dir, exist_ok=True)
        skill_mgr = SkillManager()
        temp_path = _next_available_temp_path(temp_dir, filename)

        try:
            await self._save_upload(file, temp_path)
            try:
                skill_name = skill_mgr.install_skill_from_zip(
                    temp_path,
                    overwrite=False,
                    skill_name_hint=Path(filename).stem,
                )
            except TypeError:
                skill_name = skill_mgr.install_skill_from_zip(
                    temp_path,
                    overwrite=False,
                )

            try:
                await sync_skills_to_active_sandboxes()
            except Exception:
                logger.warning("Failed to sync uploaded skills to active sandboxes.")

            return SkillsOperationResult(
                data={"name": skill_name},
                message="Skill uploaded successfully.",
            )
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    logger.warning(f"Failed to remove temp skill file: {temp_path}")

    async def batch_upload_skills(self, file_list: list[Any]) -> SkillsOperationResult:
        self._ensure_mutation_allowed()

        if not file_list:
            raise SkillsServiceError("No files provided")

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
                await self._save_upload(file, temp_path)

                try:
                    skill_name = skill_mgr.install_skill_from_zip(
                        temp_path,
                        overwrite=False,
                        skill_name_hint=Path(filename).stem,
                    )
                except TypeError:
                    try:
                        skill_name = skill_mgr.install_skill_from_zip(
                            temp_path,
                            overwrite=False,
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

            except Exception as exc:
                failed.append({"filename": filename, "error": str(exc)})
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
                logger.warning("Failed to sync uploaded skills to active sandboxes.")

        total = len(file_list)
        success_count = len(succeeded)
        skipped_count = len(skipped)
        failed_count = len(failed)
        data = {
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
        }

        if failed_count == 0 and success_count == total:
            return SkillsOperationResult(
                data=data,
                message=f"All {total} skill(s) uploaded successfully.",
            )
        if failed_count == 0 and success_count == 0:
            return SkillsOperationResult(
                data=data,
                message=f"All {total} file(s) were skipped.",
            )
        if success_count == 0 and skipped_count == 0:
            return SkillsOperationResult(
                ok=False,
                data=data,
                message=f"Upload failed for all {total} file(s).",
            )

        return SkillsOperationResult(
            data=data,
            message=f"Partial success: {success_count}/{total} skill(s) uploaded.",
        )

    def prepare_skill_archive(self, name: str) -> SkillArchive:
        skill_name = str(name or "").strip()
        if not skill_name:
            raise SkillsServiceError("Missing skill name")
        if not _SKILL_NAME_RE.match(skill_name):
            raise SkillsServiceError("Invalid skill name")

        skill_mgr = SkillManager()
        if skill_mgr.is_sandbox_only_skill(skill_name):
            raise SkillsServiceError(
                "Sandbox preset skill cannot be downloaded from local skill files."
            )
        if skill_mgr.is_plugin_skill(skill_name):
            raise SkillsServiceError(
                "Plugin-provided skill cannot be downloaded from local skill files."
            )

        skill_dir = Path(skill_mgr.skills_root) / skill_name
        skill_md = skill_dir / "SKILL.md"
        if not skill_dir.is_dir() or not skill_md.exists():
            raise SkillsServiceError("Local skill not found")

        export_dir = Path(get_astrbot_temp_path()) / "skill_exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        zip_base = export_dir / skill_name
        zip_path = zip_base.with_suffix(".zip")
        if zip_path.exists():
            zip_path.unlink()

        shutil.make_archive(
            str(zip_base),
            "zip",
            root_dir=str(skill_mgr.skills_root),
            base_dir=skill_name,
        )
        return SkillArchive(path=zip_path, filename=f"{skill_name}.zip")

    def prepare_skill_archive_from_dashboard_query(
        self, name: str | None
    ) -> SkillArchive:
        return self.prepare_skill_archive(name or "")

    def list_skill_files(self, name: str, relative_path: str | None = "") -> dict:
        skill_name = str(name or "").strip()
        readonly = SkillManager().is_plugin_skill(skill_name)
        skill_dir = self.resolve_local_skill_dir(skill_name)
        target_dir = self.resolve_skill_relative_path(
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
                self.serialize_skill_file_entry(
                    skill_dir,
                    resolved,
                    readonly=readonly,
                )
            )

        return {
            "name": skill_name,
            "path": self.skill_relative_path(skill_dir, target_dir),
            "entries": entries,
        }

    def list_skill_files_from_dashboard_query(
        self,
        *,
        name: str | None,
        relative_path: str | None,
    ) -> dict:
        return self.list_skill_files(name or "", relative_path or "")

    def get_skill_file(self, name: str, relative_path: str | None = "SKILL.md") -> dict:
        skill_name = str(name or "").strip()
        skill_dir = self.resolve_local_skill_dir(skill_name)
        target_file = self.resolve_skill_relative_path(
            skill_dir,
            relative_path,
            expect_file=True,
        )
        if not self.is_editable_skill_file(target_file):
            raise SkillsServiceError("Unsupported file type")

        size = target_file.stat().st_size
        if size > _SKILL_FILE_MAX_BYTES:
            raise SkillsServiceError("File is too large")

        try:
            content = target_file.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise SkillsServiceError("File is not valid UTF-8 text") from exc

        return {
            "name": skill_name,
            "path": self.skill_relative_path(skill_dir, target_file),
            "content": content,
            "size": size,
            "editable": not SkillManager().is_plugin_skill(skill_name),
        }

    def get_skill_file_from_dashboard_query(
        self,
        *,
        name: str | None,
        relative_path: str | None,
    ) -> dict:
        return self.get_skill_file(name or "", relative_path or "SKILL.md")

    async def update_skill_file(self, data: object) -> dict:
        self._ensure_mutation_allowed()
        payload = self._payload(data)
        skill_name = str(payload.get("name") or "").strip()
        relative_path = payload.get("path", "SKILL.md")
        content = payload.get("content")
        if not isinstance(content, str):
            raise SkillsServiceError("Missing file content")

        encoded = content.encode("utf-8")
        if len(encoded) > _SKILL_FILE_MAX_BYTES:
            raise SkillsServiceError("File content is too large")

        skill_dir = self.resolve_local_skill_dir(skill_name)
        if SkillManager().is_plugin_skill(skill_name):
            raise SkillsServiceError("Plugin-provided skill is read-only.")
        target_file = self.resolve_skill_relative_path(
            skill_dir,
            relative_path,
            expect_file=True,
        )
        if not self.is_editable_skill_file(target_file):
            raise SkillsServiceError("Unsupported file type")

        target_file.write_text(content, encoding="utf-8")

        try:
            await sync_skills_to_active_sandboxes()
        except Exception:
            logger.warning("Failed to sync edited skills to active sandboxes.")

        return {
            "name": skill_name,
            "path": self.skill_relative_path(skill_dir, target_file),
            "size": len(encoded),
        }

    def update_skill(self, data: object) -> dict:
        self._ensure_mutation_allowed()
        payload = self._payload(data)
        name = payload.get("name")
        active = payload.get("active", True)
        if not name:
            raise SkillsServiceError("Missing skill name")
        SkillManager().set_skill_active(name, bool(active))
        return {"name": name, "active": bool(active)}

    async def delete_skill(self, data: object) -> dict:
        self._ensure_mutation_allowed()
        payload = self._payload(data)
        name = payload.get("name")
        if not name:
            raise SkillsServiceError("Missing skill name")
        SkillManager().delete_skill(name)
        try:
            await sync_skills_to_active_sandboxes()
        except Exception:
            logger.warning("Failed to sync deleted skills to active sandboxes.")
        return {"name": name}

    async def get_neo_candidates(self, query: dict[str, Any]) -> SkillsOperationResult:
        logger.info("[Neo] GET /skills/neo/candidates requested.")
        status = query.get("status")
        skill_key = query.get("skill_key")
        limit = int(query.get("limit", 100))
        offset = int(query.get("offset", 0))

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
            return result

        return await self.with_neo_client(_do)

    async def get_neo_candidates_from_dashboard_query(
        self,
        *,
        status: str | None,
        skill_key: str | None,
        limit: str | None,
        offset: str | None,
    ) -> SkillsOperationResult:
        return await self.get_neo_candidates(
            self._dashboard_query(
                status=status,
                skill_key=skill_key,
                limit=limit,
                offset=offset,
            )
        )

    async def get_neo_releases(self, query: dict[str, Any]) -> SkillsOperationResult:
        logger.info("[Neo] GET /skills/neo/releases requested.")
        skill_key = query.get("skill_key")
        stage = query.get("stage")
        active_only = _to_bool(query.get("active_only"), False)
        limit = int(query.get("limit", 100))
        offset = int(query.get("offset", 0))

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
            return result

        return await self.with_neo_client(_do)

    async def get_neo_releases_from_dashboard_query(
        self,
        *,
        skill_key: str | None,
        stage: str | None,
        active_only: str | None,
        limit: str | None,
        offset: str | None,
    ) -> SkillsOperationResult:
        return await self.get_neo_releases(
            self._dashboard_query(
                skill_key=skill_key,
                stage=stage,
                active_only=active_only,
                limit=limit,
                offset=offset,
            )
        )

    async def get_neo_payload(self, query: dict[str, Any]) -> SkillsOperationResult:
        logger.info("[Neo] GET /skills/neo/payload requested.")
        payload_ref = query.get("payload_ref", "")
        if not payload_ref:
            return SkillsOperationResult(ok=False, message="Missing payload_ref")

        async def _do(client):
            payload = await client.skills.get_payload(payload_ref)
            logger.info(f"[Neo] Payload fetched: ref={payload_ref}")
            return payload

        return await self.with_neo_client(_do)

    async def get_neo_payload_from_dashboard_query(
        self,
        payload_ref: str | None,
    ) -> SkillsOperationResult:
        return await self.get_neo_payload(
            self._dashboard_query(payload_ref=payload_ref)
        )

    async def evaluate_neo_candidate(
        self,
        data: object,
    ) -> SkillsOperationResult:
        self._ensure_mutation_allowed()
        logger.info("[Neo] POST /skills/neo/evaluate requested.")
        payload = self._payload(data)
        candidate_id = payload.get("candidate_id")
        passed_value = payload.get("passed")
        if not candidate_id or passed_value is None:
            return SkillsOperationResult(
                ok=False,
                message="Missing candidate_id or passed",
            )
        passed = _to_bool(passed_value, False)

        async def _do(client):
            result = await client.skills.evaluate_candidate(
                candidate_id,
                passed=passed,
                score=payload.get("score"),
                benchmark_id=payload.get("benchmark_id"),
                report=payload.get("report"),
            )
            logger.info(
                f"[Neo] Candidate evaluated: id={candidate_id}, passed={passed}"
            )
            return result

        return await self.with_neo_client(_do)

    async def promote_neo_candidate(self, data: object) -> SkillsOperationResult:
        self._ensure_mutation_allowed()
        logger.info("[Neo] POST /skills/neo/promote requested.")
        payload = self._payload(data)
        candidate_id = payload.get("candidate_id")
        stage = payload.get("stage", "canary")
        sync_to_local = _to_bool(payload.get("sync_to_local"), True)
        if not candidate_id:
            return SkillsOperationResult(ok=False, message="Missing candidate_id")
        if stage not in {"canary", "stable"}:
            return SkillsOperationResult(
                ok=False,
                message="Invalid stage, must be canary/stable",
            )

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
                    "[Neo] Stable release synced to local: "
                    f"skill={sync_json.get('local_skill_name', '')}"
                )

            if result.get("sync_error"):
                return SkillsOperationResult(
                    ok=False,
                    message=(
                        "Stable promote synced failed and has been rolled back. "
                        f"sync_error={result['sync_error']}"
                    ),
                    data={
                        "release": release_json,
                        "rollback": result.get("rollback"),
                    },
                )

            if not did_sync_to_local:
                try:
                    await sync_skills_to_active_sandboxes()
                except Exception:
                    logger.warning("Failed to sync skills to active sandboxes.")

            return {"release": release_json, "sync": sync_json}

        return await self.with_neo_client(_do)

    async def rollback_neo_release(self, data: object) -> SkillsOperationResult:
        self._ensure_mutation_allowed()
        logger.info("[Neo] POST /skills/neo/rollback requested.")
        payload = self._payload(data)
        release_id = payload.get("release_id")
        if not release_id:
            return SkillsOperationResult(ok=False, message="Missing release_id")

        async def _do(client):
            result = await client.skills.rollback_release(release_id)
            logger.info(f"[Neo] Release rolled back: id={release_id}")
            return result

        return await self.with_neo_client(_do)

    async def sync_neo_release(self, data: object) -> SkillsOperationResult:
        self._ensure_mutation_allowed()
        logger.info("[Neo] POST /skills/neo/sync requested.")
        payload = self._payload(data)
        release_id = payload.get("release_id")
        skill_key = payload.get("skill_key")
        require_stable = _to_bool(payload.get("require_stable"), True)
        if not release_id and not skill_key:
            return SkillsOperationResult(
                ok=False,
                message="Missing release_id or skill_key",
            )

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
            return {
                "skill_key": result.skill_key,
                "local_skill_name": result.local_skill_name,
                "release_id": result.release_id,
                "candidate_id": result.candidate_id,
                "payload_ref": result.payload_ref,
                "map_path": result.map_path,
                "synced_at": result.synced_at,
            }

        return await self.with_neo_client(_do)

    async def delete_neo_candidate(self, data: object) -> SkillsOperationResult:
        self._ensure_mutation_allowed()
        logger.info("[Neo] POST /skills/neo/delete-candidate requested.")
        payload = self._payload(data)
        candidate_id = payload.get("candidate_id")
        reason = payload.get("reason")
        if not candidate_id:
            return SkillsOperationResult(ok=False, message="Missing candidate_id")

        async def _do(client):
            result = await client.skills.delete_candidate(candidate_id, reason=reason)
            logger.info(f"[Neo] Candidate deleted: id={candidate_id}")
            return result

        return await self.with_neo_client(_do)

    async def delete_neo_release(self, data: object) -> SkillsOperationResult:
        self._ensure_mutation_allowed()
        logger.info("[Neo] POST /skills/neo/delete-release requested.")
        payload = self._payload(data)
        release_id = payload.get("release_id")
        reason = payload.get("reason")
        if not release_id:
            return SkillsOperationResult(ok=False, message="Missing release_id")

        async def _do(client):
            result = await client.skills.delete_release(release_id, reason=reason)
            logger.info(f"[Neo] Release deleted: id={release_id}")
            return result

        return await self.with_neo_client(_do)

    @staticmethod
    def _dashboard_query(**values: Any) -> dict[str, Any]:
        return {
            key: value
            for key, value in values.items()
            if value is not None and value != ""
        }
