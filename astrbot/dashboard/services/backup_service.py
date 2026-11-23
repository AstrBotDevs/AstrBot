from __future__ import annotations

import asyncio
import json
import os
import re
import traceback
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import jwt

from astrbot.core import logger
from astrbot.core.backup.exporter import AstrBotExporter
from astrbot.core.backup.importer import AstrBotImporter
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.utils.astrbot_path import (
    get_astrbot_backups_path,
    get_astrbot_data_path,
)
from astrbot.core.utils.upload import UploadTooLargeError
from astrbot.dashboard.services.chunked_upload_service import (
    DEFAULT_EXPIRE_SECONDS,
    ChunkedUploadError,
    ChunkedUploadService,
)
from astrbot.dashboard.services.task_progress import (
    BackupProgressMixin,
    task_progress_response,
)
from astrbot.dashboard.validation import is_json_object

CHUNK_SIZE = 1024 * 1024
UPLOAD_EXPIRE_SECONDS = DEFAULT_EXPIRE_SECONDS
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


def validate_backup_filename(filename: object, *, missing: str) -> str:
    """Accept a backup basename without allowing traversal or path separators."""
    if not isinstance(filename, str) or not filename:
        raise BackupServiceError(missing)
    if ".." in filename or "/" in filename or "\\" in filename:
        raise BackupServiceError("无效的文件名")
    return filename


def read_backup_manifest(zip_path: str) -> dict | None:
    """Read the archive manifest, treating unreadable archives as invalid backups."""
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            if "manifest.json" in archive.namelist():
                return json.loads(archive.read("manifest.json").decode("utf-8"))
    except Exception as exc:
        logger.debug(f"读取备份 manifest 失败: {exc}")
    return None


def backup_archive_metadata(filename: str, file_path: str, manifest: dict) -> dict:
    """Build the shared list representation while preserving legacy defaults."""
    stat = Path(file_path).stat()
    return {
        "filename": filename,
        "size": stat.st_size,
        "created_at": stat.st_mtime,
        "type": manifest.get("origin", "exported"),
        "astrbot_version": manifest.get("astrbot_version", "未知"),
        "exported_at": manifest.get("exported_at"),
    }


def mark_backup_archive_uploaded(zip_path: str) -> None:
    """Mark an uploaded backup while preserving its existing manifest fields."""
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

        logger.debug("Marked backup as uploaded: %s", zip_path)
    except Exception as exc:
        logger.warning("Failed to mark backup origin: %s", exc)


class BackupService(BackupProgressMixin):
    def __init__(
        self,
        db: BaseDatabase,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        self.db = db
        self.core_lifecycle = core_lifecycle
        self.config = core_lifecycle.astrbot_config
        self.backup_dir = get_astrbot_backups_path()
        self.data_dir = get_astrbot_data_path()
        self.chunks_dir = os.path.join(self.backup_dir, ".chunks")
        self.backup_tasks: dict[str, dict] = {}
        self.backup_progress: dict[str, dict] = {}
        self.chunked_uploads = ChunkedUploadService(self.chunks_dir)

    @staticmethod
    def _payload(data: object) -> dict[str, object]:
        return data if is_json_object(data) else {}

    @staticmethod
    def _validate_backup_filename(filename: object, *, missing: str) -> str:
        return validate_backup_filename(filename, missing=missing)

    def ensure_cleanup_task_started(self) -> None:
        self.chunked_uploads.ensure_cleanup_task_started()

    async def cleanup_upload_session(self, upload_id: str) -> None:
        await self.chunked_uploads.cleanup_session(upload_id)

    def get_backup_manifest(self, zip_path: str) -> dict | None:
        return read_backup_manifest(zip_path)

    def list_backups(self, *, page: int, page_size: int) -> dict:
        self.ensure_cleanup_task_started()
        Path(self.backup_dir).mkdir(parents=True, exist_ok=True)

        backup_files = []
        for filename in os.listdir(self.backup_dir):
            if not filename.endswith(".zip") or filename.startswith("."):
                continue

            file_path = os.path.join(self.backup_dir, filename)
            if not os.path.isfile(file_path):
                continue

            manifest = self.get_backup_manifest(file_path)
            if manifest is None:
                logger.debug(f"跳过无效备份文件: {filename}")
                continue

            backup_files.append(backup_archive_metadata(filename, file_path, manifest))

        backup_files.sort(key=lambda x: x["created_at"], reverse=True)
        start = (page - 1) * page_size
        end = start + page_size

        return {
            "items": backup_files[start:end],
            "total": len(backup_files),
            "page": page,
            "page_size": page_size,
        }

    def export_backup(self) -> dict:
        task_id = str(uuid.uuid4())
        self._init_task(task_id, "export", "pending")
        asyncio.create_task(self.background_export_task(task_id))
        return {
            "task_id": task_id,
            "message": "export task created, processing in background",
        }

    async def background_export_task(self, task_id: str) -> None:
        try:
            self._update_progress(task_id, status="processing", message="正在初始化...")
            kb_manager = getattr(self.core_lifecycle, "kb_manager", None)
            exporter = AstrBotExporter(
                main_db=self.db,
                kb_manager=kb_manager,
                config_path=os.path.join(self.data_dir, "cmd_config.json"),
            )
            zip_path = await exporter.export_all(
                output_dir=self.backup_dir,
                progress_callback=self._make_progress_callback(task_id),
            )
            self._set_task_result(
                task_id,
                "completed",
                result={
                    "filename": os.path.basename(zip_path),
                    "path": zip_path,
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

        Path(self.backup_dir).mkdir(parents=True, exist_ok=True)
        zip_path = os.path.join(self.backup_dir, unique_filename)
        try:
            await file.save(zip_path, max_bytes=MAX_DIRECT_UPLOAD_BYTES)
        except UploadTooLargeError as exc:
            raise BackupServiceError(
                f"Backup file exceeds the size limit ({MAX_DIRECT_UPLOAD_BYTES // (1024**2)} MB); "
                "use chunked upload instead."
            ) from exc

        logger.info(
            f"上传的备份文件已保存: {unique_filename} (原始名称: {file.filename})"
        )
        return {
            "filename": unique_filename,
            "original_filename": file.filename,
            "size": os.path.getsize(zip_path),
        }

    def upload_init(self, data: object, *, owner: str = "") -> dict:
        payload = self._payload(data)
        filename = payload.get("filename")
        total_size = payload.get("total_size", 0)

        if not isinstance(filename, str) or not filename:
            raise BackupServiceError("缺少 filename 参数")
        if not filename.endswith(".zip"):
            raise BackupServiceError("请上传 ZIP 格式的备份文件")
        if not isinstance(total_size, (int, float)) or total_size <= 0:
            raise BackupServiceError("无效的文件大小")
        if total_size > MAX_BACKUP_TOTAL_BYTES:
            raise BackupServiceError(
                f"Backup file exceeds the size limit ({MAX_BACKUP_TOTAL_BYTES // (1024**3)} GB). "
                "You can copy it into the backups folder of the data directory "
                "via FTP/SFTP and restore it from the backup list."
            )

        unique_filename = generate_unique_filename(secure_filename(filename))
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
        mark_backup_archive_uploaded(zip_path)

    async def upload_complete(self, data: object, *, owner: str = "") -> dict:
        payload = self._payload(data)
        upload_id = payload.get("upload_id")

        if not isinstance(upload_id, str) or not upload_id:
            raise BackupServiceError("缺少 upload_id 参数")

        try:
            session = self.chunked_uploads.get_session(upload_id, owner=owner)
            Path(self.backup_dir).mkdir(parents=True, exist_ok=True)
            output_path = os.path.join(self.backup_dir, session.filename)
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
            "size": file_size,
        }

    async def upload_abort(
        self, data: object, *, owner: str = ""
    ) -> tuple[dict | None, str | None]:
        payload = self._payload(data)
        upload_id = payload.get("upload_id")
        if not isinstance(upload_id, str) or not upload_id:
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
        if not isinstance(upload_id, str) or not upload_id:
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
        zip_path = os.path.join(self.backup_dir, filename)
        if not os.path.exists(zip_path):
            raise BackupServiceError(f"备份文件不存在: {filename}")

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

        zip_path = os.path.join(self.backup_dir, filename)
        if not os.path.exists(zip_path):
            raise BackupServiceError(f"备份文件不存在: {filename}")

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

        response_data = task_progress_response(
            task_id, self.backup_tasks[task_id], self.backup_progress, include_type=True
        )

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
        file_path = os.path.join(self.backup_dir, filename)
        if not os.path.exists(file_path):
            raise BackupServiceError("备份文件不存在")
        return BackupDownload(path=file_path, filename=filename)

    def delete_backup(self, data: object) -> tuple[dict | None, str | None]:
        payload = self._payload(data)
        filename = self._validate_backup_filename(
            payload.get("filename"),
            missing="缺少参数 filename",
        )
        file_path = os.path.join(self.backup_dir, filename)
        if not os.path.exists(file_path):
            raise BackupServiceError("备份文件不存在")

        os.remove(file_path)
        return None, "删除备份成功"

    def rename_backup(self, data: object) -> dict:
        payload = self._payload(data)
        filename = self._validate_backup_filename(
            payload.get("filename"),
            missing="缺少参数 filename",
        )
        new_name = payload.get("new_name")
        if not isinstance(new_name, str) or not new_name:
            raise BackupServiceError("缺少参数 new_name")

        new_name = secure_filename(new_name)
        if new_name.endswith(".zip"):
            new_name = new_name[:-4]
        if not new_name or new_name.replace("_", "") == "":
            raise BackupServiceError("新文件名无效")

        new_filename = f"{new_name}.zip"
        old_path = os.path.join(self.backup_dir, filename)
        if not os.path.exists(old_path):
            raise BackupServiceError("备份文件不存在")

        new_path = os.path.join(self.backup_dir, new_filename)
        if os.path.exists(new_path):
            raise BackupServiceError(f"文件名 '{new_filename}' 已存在")

        os.rename(old_path, new_path)
        logger.info(f"备份文件重命名: {filename} -> {new_filename}")
        return {
            "old_filename": filename,
            "new_filename": new_filename,
        }
