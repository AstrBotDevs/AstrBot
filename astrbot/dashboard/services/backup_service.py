from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import time
import traceback
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import jwt

from astrbot.core import logger
from astrbot.core.backup.constants import get_backup_directories
from astrbot.core.backup.exporter import AstrBotExporter
from astrbot.core.backup.importer import AstrBotImporter
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.utils.astrbot_path import (
    ASTRBOT_BACKUP_DIR_ENV,
    get_astrbot_data_path,
    get_default_astrbot_backups_path,
    validate_astrbot_backup_dir,
)
from astrbot.core.utils.upload import UploadTooLargeError
from astrbot.dashboard.services.chunked_upload_service import (
    ChunkedUploadError,
    ChunkedUploadService,
)

CHUNK_SIZE = 1024 * 1024
# Hard caps against disk exhaustion: a backup is never legitimately larger
# than this, and the whole-file endpoint is only for small backups (large
# ones must use the chunked flow).
MAX_BACKUP_TOTAL_BYTES = 8 * 1024 * 1024 * 1024
MAX_DIRECT_UPLOAD_BYTES = 128 * 1024 * 1024


class BackupServiceError(Exception):
    pass


@dataclass
class BackupDownload:
    path: str
    filename: str


def secure_filename(filename: str) -> str:
    filename = filename.replace("\\", "/")
    filename = os.path.basename(filename)
    filename = filename.replace("..", "_")
    filename = re.sub(r"[^\w\-.]", "_", filename)
    filename = filename.strip(".")
    if not filename or filename.replace("_", "") == "":
        filename = "backup"
    return filename


def generate_unique_filename(original_filename: str) -> str:
    name, ext = os.path.splitext(original_filename)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{name}_{timestamp}{ext}"


class BackupService:
    def __init__(
        self,
        db: BaseDatabase,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        self.db = db
        self.core_lifecycle = core_lifecycle
        self.config = core_lifecycle.astrbot_config
        self.data_dir = get_astrbot_data_path()
        self._backup_dir_override: str | None = None
        self._chunks_dir_override: str | None = None
        self._dir_lock = threading.RLock()
        self._active_direct_uploads = 0
        self.backup_tasks: dict[str, dict] = {}
        self.backup_progress: dict[str, dict] = {}
        self.chunked_uploads = ChunkedUploadService(self.chunks_dir)

    @property
    def backup_dir(self) -> str:
        """Return the effective backup directory (dynamic unless overridden)."""
        if self._backup_dir_override is not None:
            return self._backup_dir_override
        return self._resolve_backup_dir_state(check_writable=False)[
            "effective_backup_dir"
        ]

    @backup_dir.setter
    def backup_dir(self, value: str) -> None:
        self._backup_dir_override = value
        if self._chunks_dir_override is None and hasattr(self, "chunked_uploads"):
            self.chunked_uploads.chunks_root = Path(value) / ".chunks"

    @property
    def chunks_dir(self) -> str:
        """Return the effective temporary chunks directory."""
        if self._chunks_dir_override is not None:
            return self._chunks_dir_override
        return os.path.join(self.backup_dir, ".chunks")

    @chunks_dir.setter
    def chunks_dir(self, value: str) -> None:
        self._chunks_dir_override = value
        if hasattr(self, "chunked_uploads"):
            self.chunked_uploads.chunks_root = Path(value)

    def _sync_chunks_root(self, backup_dir: str) -> None:
        if self._chunks_dir_override is None:
            self.chunked_uploads.chunks_root = Path(backup_dir) / ".chunks"

    def _get_configured_backup_dir(self) -> str:
        if isinstance(self.config, dict):
            raw = self.config.get("backup_dir")
            if isinstance(raw, str):
                return raw.strip()
        return ""

    def _has_active_tasks(self) -> bool:
        if self._active_direct_uploads > 0:
            return True
        if any(
            task.get("status") in ("pending", "processing")
            for task in self.backup_tasks.values()
        ):
            return True
        now = time.time()
        return any(
            now - session.last_activity <= self.chunked_uploads.expire_seconds
            for session in self.chunked_uploads.sessions.values()
        )

    def _resolve_backup_dir_state(
        self, *, check_writable: bool = False
    ) -> dict[str, Any]:
        default_dir = get_default_astrbot_backups_path()
        if self._backup_dir_override is not None:
            override_path = self._backup_dir_override
            if check_writable:
                try:
                    Path(override_path).mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    return {
                        "backup_dir": override_path,
                        "effective_backup_dir": override_path,
                        "default_backup_dir": default_dir,
                        "is_custom": True,
                        "source": "override",
                        "env_override": False,
                        "is_valid": False,
                        "validation_error": f"Cannot create backup directory: {exc}",
                    }
            return {
                "backup_dir": override_path,
                "effective_backup_dir": override_path,
                "default_backup_dir": default_dir,
                "is_custom": os.path.normcase(os.path.realpath(override_path))
                != os.path.normcase(default_dir),
                "source": "override",
                "env_override": False,
                "is_valid": True,
                "validation_error": None,
            }

        env_raw = os.environ.get(ASTRBOT_BACKUP_DIR_ENV, "").strip()
        config_raw = self._get_configured_backup_dir()

        if env_raw:
            source = "env"
            raw_target: str | None = env_raw
        elif config_raw:
            source = "config"
            raw_target = config_raw
        else:
            source = "default"
            raw_target = None

        try:
            resolved = validate_astrbot_backup_dir(
                raw_target,
                extra_protected_dirs=get_backup_directories().values(),
                check_writable=check_writable,
            )
            return {
                "backup_dir": config_raw,
                "effective_backup_dir": resolved,
                "default_backup_dir": default_dir,
                "is_custom": source != "default",
                "source": source,
                "env_override": source == "env",
                "is_valid": True,
                "validation_error": None,
            }
        except ValueError as exc:
            return {
                "backup_dir": config_raw,
                "effective_backup_dir": default_dir,
                "default_backup_dir": default_dir,
                "is_custom": source != "default",
                "source": source,
                "env_override": source == "env",
                "is_valid": False,
                "validation_error": str(exc),
            }

    def _require_valid_backup_dir(self, *, check_writable: bool = False) -> str:
        state = self._resolve_backup_dir_state(check_writable=check_writable)
        if not state["is_valid"]:
            raise BackupServiceError(
                state["validation_error"] or "Invalid backup directory configuration."
            )
        effective_dir = state["effective_backup_dir"]
        self._sync_chunks_root(effective_dir)
        return effective_dir

    def get_backup_settings(self) -> dict[str, Any]:
        """Return the current backup directory settings and runtime state.

        Returns:
            Dictionary describing configured, effective, and default backup
            directories, source metadata, active-task state, and validation
            status.
        """
        with self._dir_lock:
            state = self._resolve_backup_dir_state(check_writable=False)
            if state["is_valid"]:
                self._sync_chunks_root(state["effective_backup_dir"])
            state["has_active_tasks"] = self._has_active_tasks()
            return state

    def update_backup_settings(self, data: object) -> dict[str, Any]:
        """Validate and persist a new backup directory setting.

        Existing backup files in the previous directory are never moved or
        deleted automatically.

        Args:
            data: Request payload dictionary containing optional ``backup_dir``.

        Returns:
            Updated backup directory settings dictionary.

        Raises:
            BackupServiceError: If overridden by environment variable, an active
                backup operation is running, or the target directory is invalid
                or not writable.
        """
        payload = self._payload(data)
        raw_backup_dir = payload.get("backup_dir")
        if raw_backup_dir is None:
            normalized_input = ""
        elif isinstance(raw_backup_dir, str):
            normalized_input = raw_backup_dir.strip()
        else:
            raise BackupServiceError("backup_dir must be a string.")

        with self._dir_lock:
            if os.environ.get(ASTRBOT_BACKUP_DIR_ENV, "").strip():
                raise BackupServiceError(
                    f"Backup directory is overridden by the {ASTRBOT_BACKUP_DIR_ENV} "
                    "environment variable and cannot be modified here."
                )

            if self._has_active_tasks():
                raise BackupServiceError(
                    "Cannot change backup directory while a backup export, import, "
                    "or upload is in progress."
                )

            try:
                resolved = validate_astrbot_backup_dir(
                    normalized_input or None,
                    extra_protected_dirs=get_backup_directories().values(),
                    check_writable=True,
                )
            except ValueError as exc:
                raise BackupServiceError(str(exc)) from exc

            default_dir = get_default_astrbot_backups_path()
            if not normalized_input or os.path.normcase(resolved) == os.path.normcase(
                default_dir
            ):
                value_to_store = ""
            else:
                value_to_store = os.path.normpath(normalized_input)

            prev_override = self._backup_dir_override
            has_config_dict = isinstance(self.config, dict)
            had_prev_key = has_config_dict and "backup_dir" in self.config
            prev_config_value = self.config.get("backup_dir") if had_prev_key else None

            self._backup_dir_override = None
            if has_config_dict:
                self.config["backup_dir"] = value_to_store
                if hasattr(self.config, "save_config"):
                    try:
                        self.config.save_config()
                    except Exception:
                        self._backup_dir_override = prev_override
                        if had_prev_key:
                            self.config["backup_dir"] = prev_config_value
                        else:
                            self.config.pop("backup_dir", None)
                        raise

            self._sync_chunks_root(resolved)
            logger.info(
                "Updated backup directory setting: configured=%r, effective=%s",
                value_to_store,
                resolved,
            )
            return self.get_backup_settings()

    @staticmethod
    def _payload(data: object) -> dict[str, Any]:
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _validate_backup_filename(filename: str | None, *, missing: str) -> str:
        if not filename:
            raise BackupServiceError(missing)
        if (
            "\x00" in filename
            or ".." in filename
            or "/" in filename
            or "\\" in filename
            or filename.startswith(".")
        ):
            raise BackupServiceError("无效的文件名")
        return filename

    @staticmethod
    def _is_within_backup_dir(candidate_real: str, base_real: str) -> bool:
        """Check whether canonical path ``candidate_real`` stays inside ``base_real``.

        Args:
            candidate_real: Canonicalized file path.
            base_real: Canonicalized backup directory path.

        Returns:
            True if ``candidate_real`` is a strict descendant of ``base_real``.
        """
        candidate_cmp = os.path.normcase(candidate_real)
        base_cmp = os.path.normcase(base_real)
        base_prefix = os.path.join(base_cmp, "")
        return candidate_cmp != base_cmp and candidate_cmp.startswith(base_prefix)

    def _find_existing_backup_file(
        self, filename: str, *, backup_dir: str
    ) -> tuple[str, str] | None:
        """Locate an existing backup file by matching server-enumerated entries.

        Matching against ``os.scandir`` entries avoids joining request input
        directly into filesystem paths for lookups while rejecting symlinks
        whose targets escape ``backup_dir``.

        Args:
            filename: Validated single-segment backup filename.
            backup_dir: Effective backup directory path.

        Returns:
            ``(canonical_path, matched_filename)`` when a regular file matches,
            or ``None`` if no matching regular file exists.

        Raises:
            BackupServiceError: If a matching entry resolves outside
                ``backup_dir``.
        """
        base_real = os.path.realpath(backup_dir)
        try:
            with os.scandir(base_real) as entries:
                for entry in entries:
                    if entry.name != filename:
                        continue
                    candidate_real = os.path.realpath(entry.path)
                    if not self._is_within_backup_dir(candidate_real, base_real):
                        raise BackupServiceError("无效的文件名")
                    if not os.path.isfile(candidate_real):
                        return None
                    return candidate_real, entry.name
        except OSError:
            return None
        return None

    def _resolve_new_backup_file_path(self, filename: str, *, backup_dir: str) -> str:
        """Resolve a safe destination path for a new backup file inside ``backup_dir``.

        Args:
            filename: Validated single-segment backup filename.
            backup_dir: Effective backup directory path.

        Returns:
            Canonical path guaranteed to reside inside ``backup_dir``.

        Raises:
            BackupServiceError: If the filename is invalid or resolves outside
                ``backup_dir``.
        """
        safe_name = self._validate_backup_filename(filename, missing="无效的文件名")
        base_real = os.path.realpath(backup_dir)
        base_prefix = os.path.join(base_real, "")
        candidate_real = os.path.realpath(os.path.join(base_real, safe_name))
        if not candidate_real.startswith(base_prefix):
            raise BackupServiceError("无效的文件名")
        if not self._is_within_backup_dir(candidate_real, base_real):
            raise BackupServiceError("无效的文件名")
        return candidate_real

    def _init_task(self, task_id: str, task_type: str, status: str = "pending") -> None:
        self.backup_tasks[task_id] = {
            "type": task_type,
            "status": status,
            "result": None,
            "error": None,
        }
        self.backup_progress[task_id] = {
            "status": status,
            "stage": "waiting",
            "current": 0,
            "total": 100,
            "message": "",
        }

    def _set_task_result(
        self,
        task_id: str,
        status: str,
        result: dict | None = None,
        error: str | None = None,
    ) -> None:
        if task_id in self.backup_tasks:
            self.backup_tasks[task_id]["status"] = status
            self.backup_tasks[task_id]["result"] = result
            self.backup_tasks[task_id]["error"] = error
        if task_id in self.backup_progress:
            self.backup_progress[task_id]["status"] = status

    def _update_progress(
        self,
        task_id: str,
        *,
        status: str | None = None,
        stage: str | None = None,
        current: int | None = None,
        total: int | None = None,
        message: str | None = None,
    ) -> None:
        if task_id not in self.backup_progress:
            return
        progress = self.backup_progress[task_id]
        if status is not None:
            progress["status"] = status
        if stage is not None:
            progress["stage"] = stage
        if current is not None:
            progress["current"] = current
        if total is not None:
            progress["total"] = total
        if message is not None:
            progress["message"] = message

    def _make_progress_callback(self, task_id: str):
        async def _callback(
            stage: str,
            current: int,
            total: int,
            message: str = "",
        ) -> None:
            self._update_progress(
                task_id,
                status="processing",
                stage=stage,
                current=current,
                total=total,
                message=message,
            )

        return _callback

    def ensure_cleanup_task_started(self) -> None:
        self.chunked_uploads.ensure_cleanup_task_started()

    async def cleanup_upload_session(self, upload_id: str) -> None:
        await self.chunked_uploads.cleanup_session(upload_id)

    def get_backup_manifest(self, zip_path: str) -> dict | None:
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                if "manifest.json" in zf.namelist():
                    manifest_data = zf.read("manifest.json")
                    return json.loads(manifest_data.decode("utf-8"))
                return None
        except Exception as exc:
            logger.debug(f"读取备份 manifest 失败: {exc}")
        return None

    def list_backups(self, *, page: int, page_size: int) -> dict:
        self.ensure_cleanup_task_started()
        backup_dir = self._require_valid_backup_dir(check_writable=False)
        base_real = os.path.realpath(backup_dir)
        try:
            Path(base_real).mkdir(parents=True, exist_ok=True)
            with os.scandir(base_real) as scan:
                entries = list(scan)
        except OSError as exc:
            raise BackupServiceError(f"Cannot access backup directory: {exc}") from exc

        backup_files = []
        for entry in entries:
            filename = entry.name
            if not filename.endswith(".zip") or filename.startswith("."):
                continue

            file_path = os.path.realpath(entry.path)
            if not self._is_within_backup_dir(file_path, base_real):
                logger.debug(f"跳过越界备份文件: {filename}")
                continue
            if not os.path.isfile(file_path):
                continue

            manifest = self.get_backup_manifest(file_path)
            if manifest is None:
                logger.debug(f"跳过无效备份文件: {filename}")
                continue

            stat = os.stat(file_path)
            backup_files.append(
                {
                    "filename": filename,
                    "size": stat.st_size,
                    "created_at": stat.st_mtime,
                    "type": manifest.get("origin", "exported"),
                    "astrbot_version": manifest.get("astrbot_version", "未知"),
                    "exported_at": manifest.get("exported_at"),
                }
            )

        backup_files.sort(key=lambda x: x["created_at"], reverse=True)
        start = (page - 1) * page_size
        end = start + page_size

        return {
            "items": backup_files[start:end],
            "total": len(backup_files),
            "page": page,
            "page_size": page_size,
            "backup_dir": backup_dir,
        }

    def export_backup(self) -> dict:
        with self._dir_lock:
            output_dir = self._require_valid_backup_dir(check_writable=True)
            task_id = str(uuid.uuid4())
            self._init_task(task_id, "export", "pending")
        asyncio.create_task(self.background_export_task(task_id, output_dir))
        return {
            "task_id": task_id,
            "backup_dir": output_dir,
            "message": "export task created, processing in background",
        }

    async def background_export_task(
        self, task_id: str, output_dir: str | None = None
    ) -> None:
        try:
            self._update_progress(task_id, status="processing", message="正在初始化...")
            target_dir = output_dir or self._require_valid_backup_dir(
                check_writable=True
            )
            kb_manager = getattr(self.core_lifecycle, "kb_manager", None)
            exporter = AstrBotExporter(
                main_db=self.db,
                kb_manager=kb_manager,
                config_path=os.path.join(self.data_dir, "cmd_config.json"),
            )
            zip_path = await exporter.export_all(
                output_dir=target_dir,
                progress_callback=self._make_progress_callback(task_id),
            )
            self._set_task_result(
                task_id,
                "completed",
                result={
                    "filename": os.path.basename(zip_path),
                    "path": zip_path,
                    "backup_dir": target_dir,
                    "size": os.path.getsize(zip_path),
                },
            )
        except Exception as exc:
            logger.error(f"后台导出任务 {task_id} 失败: {exc}")
            logger.error(traceback.format_exc())
            self._set_task_result(task_id, "failed", error=str(exc))

    async def upload_backup(self, file: Any | None) -> dict:
        if not file:
            raise BackupServiceError("缺少备份文件")
        if not file.filename or not file.filename.endswith(".zip"):
            raise BackupServiceError("请上传 ZIP 格式的备份文件")

        safe_filename = secure_filename(file.filename)
        unique_filename = generate_unique_filename(safe_filename)

        with self._dir_lock:
            backup_dir = self._require_valid_backup_dir(check_writable=True)
            zip_path = self._resolve_new_backup_file_path(
                unique_filename, backup_dir=backup_dir
            )
            self._active_direct_uploads += 1

        try:
            await file.save(zip_path, max_bytes=MAX_DIRECT_UPLOAD_BYTES)
        except UploadTooLargeError as exc:
            raise BackupServiceError(
                f"Backup file exceeds the size limit ({MAX_DIRECT_UPLOAD_BYTES // (1024**2)} MB); "
                "use chunked upload instead."
            ) from exc
        finally:
            with self._dir_lock:
                self._active_direct_uploads -= 1

        logger.info(
            f"上传的备份文件已保存: {unique_filename} (原始名称: {file.filename})"
        )
        return {
            "filename": unique_filename,
            "original_filename": file.filename,
            "path": zip_path,
            "backup_dir": backup_dir,
            "size": os.path.getsize(zip_path),
        }

    def upload_init(self, data: object, *, owner: str = "") -> dict:
        payload = self._payload(data)
        filename = payload.get("filename")
        total_size = payload.get("total_size", 0)

        if not filename:
            raise BackupServiceError("缺少 filename 参数")
        if not filename.endswith(".zip"):
            raise BackupServiceError("请上传 ZIP 格式的备份文件")
        if total_size <= 0:
            raise BackupServiceError("无效的文件大小")
        if total_size > MAX_BACKUP_TOTAL_BYTES:
            raise BackupServiceError(
                f"Backup file exceeds the size limit ({MAX_BACKUP_TOTAL_BYTES // (1024**3)} GB). "
                "You can copy it into the backups folder "
                "via FTP/SFTP and restore it from the backup list."
            )

        unique_filename = generate_unique_filename(secure_filename(filename))
        with self._dir_lock:
            self._require_valid_backup_dir(check_writable=True)
            self.chunked_uploads.ensure_cleanup_task_started()
            try:
                session = self.chunked_uploads.init_session(
                    owner=owner,
                    purpose="backup",
                    filename=unique_filename,
                    original_filename=filename,
                    total_size=total_size,
                )
            except ChunkedUploadError as exc:
                raise BackupServiceError(str(exc)) from exc

        return {
            "upload_id": session.id,
            "chunk_size": session.chunk_size,
            "total_chunks": session.total_chunks,
            "filename": unique_filename,
        }

    async def upload_chunk(
        self,
        *,
        upload_id: str | None,
        chunk_index_str: str | None,
        chunk_file: Any | None,
        owner: str = "",
    ) -> dict:
        if not upload_id or chunk_index_str is None:
            raise BackupServiceError("缺少必要参数")

        try:
            chunk_index = int(chunk_index_str)
        except ValueError as exc:
            raise BackupServiceError("无效的分片索引") from exc

        if not chunk_file:
            raise BackupServiceError("缺少分片数据")

        try:
            return await self.chunked_uploads.save_chunk(
                upload_id, chunk_index, chunk_file, owner=owner
            )
        except ChunkedUploadError as exc:
            raise BackupServiceError(str(exc)) from exc

    def mark_backup_as_uploaded(self, zip_path: str) -> None:
        try:
            manifest = {"origin": "uploaded", "uploaded_at": datetime.now().isoformat()}
            with zipfile.ZipFile(zip_path, "r") as zf:
                if "manifest.json" in zf.namelist():
                    manifest_data = zf.read("manifest.json")
                    manifest = json.loads(manifest_data.decode("utf-8"))
                    manifest["origin"] = "uploaded"
                    manifest["uploaded_at"] = datetime.now().isoformat()

            with zipfile.ZipFile(zip_path, "a") as zf:
                new_manifest = json.dumps(manifest, ensure_ascii=False, indent=2)
                zf.writestr("manifest.json", new_manifest)

            logger.debug(f"已标记备份为上传来源: {zip_path}")
        except Exception as exc:
            logger.warning(f"标记备份来源失败: {exc}")

    async def upload_complete(self, data: object, *, owner: str = "") -> dict:
        payload = self._payload(data)
        upload_id = payload.get("upload_id")

        if not upload_id:
            raise BackupServiceError("缺少 upload_id 参数")

        try:
            session = self.chunked_uploads.get_session(upload_id, owner=owner)
            backup_dir = self._require_valid_backup_dir(check_writable=True)
            output_path = self._resolve_new_backup_file_path(
                session.filename, backup_dir=backup_dir
            )
            file_size = await self.chunked_uploads.assemble(
                upload_id, output_path, owner=owner
            )
        except ChunkedUploadError as exc:
            raise BackupServiceError(str(exc)) from exc

        self.mark_backup_as_uploaded(output_path)
        logger.info(
            f"分片上传完成: {session.filename}, size={file_size}, "
            f"chunks={session.total_chunks}"
        )

        return {
            "filename": session.filename,
            "original_filename": session.original_filename,
            "path": output_path,
            "backup_dir": backup_dir,
            "size": file_size,
        }

    async def upload_abort(
        self, data: object, *, owner: str = ""
    ) -> tuple[dict | None, str | None]:
        payload = self._payload(data)
        upload_id = payload.get("upload_id")
        if not upload_id:
            raise BackupServiceError("缺少 upload_id 参数")

        try:
            if await self.chunked_uploads.abort(upload_id, owner=owner):
                logger.info(f"取消分片上传: {upload_id}")
        except ChunkedUploadError as exc:
            raise BackupServiceError(str(exc)) from exc

        return None, "上传已取消"

    def upload_status(self, data: object, *, owner: str = "") -> dict:
        payload = self._payload(data)
        upload_id = payload.get("upload_id")
        if not upload_id:
            raise BackupServiceError("缺少 upload_id 参数")

        try:
            return self.chunked_uploads.session_status(upload_id, owner=owner)
        except ChunkedUploadError as exc:
            raise BackupServiceError(str(exc)) from exc

    def check_backup(self, data: object) -> dict:
        payload = self._payload(data)
        filename = self._validate_backup_filename(
            payload.get("filename"),
            missing="缺少 filename 参数",
        )
        backup_dir = self._require_valid_backup_dir(check_writable=False)
        found = self._find_existing_backup_file(filename, backup_dir=backup_dir)
        if found is None:
            raise BackupServiceError(f"备份文件不存在: {filename}")
        zip_path, _ = found

        kb_manager = getattr(self.core_lifecycle, "kb_manager", None)
        importer = AstrBotImporter(
            main_db=self.db,
            kb_manager=kb_manager,
            config_path=os.path.join(self.data_dir, "cmd_config.json"),
        )
        return importer.pre_check(zip_path).to_dict()

    def import_backup(self, data: object) -> dict:
        payload = self._payload(data)
        filename = self._validate_backup_filename(
            payload.get("filename"),
            missing="缺少 filename 参数",
        )
        confirmed = payload.get("confirmed", False)
        if not confirmed:
            raise BackupServiceError(
                "请先确认导入。导入将会清空并覆盖现有数据，此操作不可撤销。"
            )

        with self._dir_lock:
            backup_dir = self._require_valid_backup_dir(check_writable=False)
            found = self._find_existing_backup_file(filename, backup_dir=backup_dir)
            if found is None:
                raise BackupServiceError(f"备份文件不存在: {filename}")
            zip_path, _ = found

            task_id = str(uuid.uuid4())
            self._init_task(task_id, "import", "pending")
        asyncio.create_task(self.background_import_task(task_id, zip_path))

        return {
            "task_id": task_id,
            "message": "import task created, processing in background",
        }

    async def background_import_task(self, task_id: str, zip_path: str) -> None:
        try:
            self._update_progress(task_id, status="processing", message="正在初始化...")
            kb_manager = getattr(self.core_lifecycle, "kb_manager", None)
            importer = AstrBotImporter(
                main_db=self.db,
                kb_manager=kb_manager,
                config_path=os.path.join(self.data_dir, "cmd_config.json"),
            )
            result = await importer.import_all(
                zip_path=zip_path,
                mode="replace",
                progress_callback=self._make_progress_callback(task_id),
            )

            if result.success:
                self._set_task_result(task_id, "completed", result=result.to_dict())
            else:
                self._set_task_result(
                    task_id,
                    "failed",
                    error="; ".join(result.errors),
                )
        except Exception as exc:
            logger.error(f"后台导入任务 {task_id} 失败: {exc}")
            logger.error(traceback.format_exc())
            self._set_task_result(task_id, "failed", error=str(exc))

    def get_progress(self, task_id: str | None) -> dict:
        if not task_id:
            raise BackupServiceError("缺少参数 task_id")
        if task_id not in self.backup_tasks:
            raise BackupServiceError("找不到该任务")

        task_info = self.backup_tasks[task_id]
        status = task_info["status"]
        response_data = {
            "task_id": task_id,
            "type": task_info["type"],
            "status": status,
        }

        if status == "processing" and task_id in self.backup_progress:
            response_data["progress"] = self.backup_progress[task_id]
        if status == "completed":
            response_data["result"] = task_info["result"]
        if status == "failed":
            response_data["error"] = task_info["error"]

        return response_data

    def prepare_download(
        self,
        *,
        filename: str | None,
        token: str | None,
        jwt_secret: str | None,
    ) -> BackupDownload:
        if not filename:
            raise BackupServiceError("缺少参数 filename")
        if not token:
            raise BackupServiceError("缺少参数 token")
        if not jwt_secret:
            raise BackupServiceError("服务器配置错误")

        try:
            jwt.decode(
                token,
                jwt_secret,
                algorithms=["HS256"],
                options={
                    "require": ["exp"],
                    "verify_signature": True,
                    "verify_exp": True,
                },
            )
        except jwt.ExpiredSignatureError as exc:
            raise BackupServiceError("Token 已过期，请刷新页面后重试") from exc
        except jwt.InvalidTokenError as exc:
            raise BackupServiceError("Token 无效") from exc

        filename = self._validate_backup_filename(filename, missing="缺少参数 filename")
        backup_dir = self._require_valid_backup_dir(check_writable=False)
        found = self._find_existing_backup_file(filename, backup_dir=backup_dir)
        if found is None:
            raise BackupServiceError("备份文件不存在")
        file_path, matched_name = found
        return BackupDownload(path=file_path, filename=matched_name)

    def delete_backup(self, data: object) -> tuple[dict | None, str | None]:
        payload = self._payload(data)
        filename = self._validate_backup_filename(
            payload.get("filename"),
            missing="缺少参数 filename",
        )
        backup_dir = self._require_valid_backup_dir(check_writable=False)
        found = self._find_existing_backup_file(filename, backup_dir=backup_dir)
        if found is None:
            raise BackupServiceError("备份文件不存在")
        file_path, _ = found

        os.remove(file_path)
        return None, "删除备份成功"

    def rename_backup(self, data: object) -> dict:
        payload = self._payload(data)
        filename = self._validate_backup_filename(
            payload.get("filename"),
            missing="缺少参数 filename",
        )
        new_name = payload.get("new_name")
        if not new_name:
            raise BackupServiceError("缺少参数 new_name")

        new_name = secure_filename(new_name)
        if new_name.endswith(".zip"):
            new_name = new_name[:-4]
        if not new_name or new_name.replace("_", "") == "":
            raise BackupServiceError("新文件名无效")

        new_filename = f"{new_name}.zip"
        backup_dir = self._require_valid_backup_dir(check_writable=False)
        found = self._find_existing_backup_file(filename, backup_dir=backup_dir)
        if found is None:
            raise BackupServiceError("备份文件不存在")
        old_path, _ = found

        new_path = self._resolve_new_backup_file_path(
            new_filename, backup_dir=backup_dir
        )
        if os.path.exists(new_path):
            raise BackupServiceError(f"文件名 '{new_filename}' 已存在")

        os.rename(old_path, new_path)
        logger.info(f"备份文件重命名: {filename} -> {new_filename}")
        return {
            "old_filename": filename,
            "new_filename": new_filename,
        }
