from __future__ import annotations

import asyncio
import json
import math
import os
import re
import shutil
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
from astrbot.core.backup.exporter import AstrBotExporter
from astrbot.core.backup.importer import AstrBotImporter
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.utils.astrbot_path import (
    get_astrbot_backups_path,
    get_astrbot_data_path,
)

CHUNK_SIZE = 1024 * 1024
UPLOAD_EXPIRE_SECONDS = 3600


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
        self.backup_dir = get_astrbot_backups_path()
        self.data_dir = get_astrbot_data_path()
        self.chunks_dir = os.path.join(self.backup_dir, ".chunks")
        self.backup_tasks: dict[str, dict] = {}
        self.backup_progress: dict[str, dict] = {}
        self.upload_sessions: dict[str, dict] = {}
        self._cleanup_task: asyncio.Task | None = None

    @staticmethod
    def _payload(data: object) -> dict[str, Any]:
        return data if isinstance(data, dict) else {}

    @staticmethod
    async def _save_upload(file: Any, target_path: str) -> None:
        if hasattr(file, "save"):
            result = file.save(target_path)
            if hasattr(result, "__await__"):
                await result
            return

        if hasattr(file, "read"):
            data = file.read()
            if hasattr(data, "__await__"):
                data = await data
            Path(target_path).write_bytes(data)
            return

        raise BackupServiceError("无效的上传文件")

    @staticmethod
    def _validate_backup_filename(filename: str | None, *, missing: str) -> str:
        if not filename:
            raise BackupServiceError(missing)
        if ".." in filename or "/" in filename or "\\" in filename:
            raise BackupServiceError("无效的文件名")
        return filename

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
        if self._cleanup_task is None or self._cleanup_task.done():
            try:
                self._cleanup_task = asyncio.create_task(
                    self._cleanup_expired_uploads()
                )
            except RuntimeError:
                pass

    async def _cleanup_expired_uploads(self) -> None:
        while True:
            try:
                await asyncio.sleep(300)
                current_time = time.time()
                expired_sessions = []

                for upload_id, session in self.upload_sessions.items():
                    last_activity = session.get("last_activity", session["created_at"])
                    if current_time - last_activity > UPLOAD_EXPIRE_SECONDS:
                        expired_sessions.append(upload_id)

                for upload_id in expired_sessions:
                    await self.cleanup_upload_session(upload_id)
                    logger.info(f"清理过期的上传会话: {upload_id}")

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"清理过期上传会话失败: {exc}")

    async def cleanup_upload_session(self, upload_id: str) -> None:
        if upload_id in self.upload_sessions:
            session = self.upload_sessions[upload_id]
            chunk_dir = session.get("chunk_dir")
            if chunk_dir and os.path.exists(chunk_dir):
                try:
                    shutil.rmtree(chunk_dir)
                except Exception as exc:
                    logger.warning(f"清理分片目录失败: {exc}")
            del self.upload_sessions[upload_id]

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
        await self._save_upload(file, zip_path)

        logger.info(
            f"上传的备份文件已保存: {unique_filename} (原始名称: {file.filename})"
        )
        return {
            "filename": unique_filename,
            "original_filename": file.filename,
            "size": os.path.getsize(zip_path),
        }

    def upload_init(self, data: object) -> dict:
        payload = self._payload(data)
        filename = payload.get("filename")
        total_size = payload.get("total_size", 0)

        if not filename:
            raise BackupServiceError("缺少 filename 参数")
        if not filename.endswith(".zip"):
            raise BackupServiceError("请上传 ZIP 格式的备份文件")
        if total_size <= 0:
            raise BackupServiceError("无效的文件大小")

        total_chunks = math.ceil(total_size / CHUNK_SIZE)
        upload_id = str(uuid.uuid4())
        chunk_dir = os.path.join(self.chunks_dir, upload_id)
        Path(chunk_dir).mkdir(parents=True, exist_ok=True)

        safe_filename = secure_filename(filename)
        unique_filename = generate_unique_filename(safe_filename)
        current_time = time.time()
        self.upload_sessions[upload_id] = {
            "filename": unique_filename,
            "original_filename": filename,
            "total_size": total_size,
            "total_chunks": total_chunks,
            "received_chunks": set(),
            "created_at": current_time,
            "last_activity": current_time,
            "chunk_dir": chunk_dir,
        }

        logger.info(
            f"初始化分片上传: upload_id={upload_id}, "
            f"filename={unique_filename}, total_chunks={total_chunks}"
        )

        return {
            "upload_id": upload_id,
            "chunk_size": CHUNK_SIZE,
            "total_chunks": total_chunks,
            "filename": unique_filename,
        }

    async def upload_chunk(
        self,
        *,
        upload_id: str | None,
        chunk_index_str: str | None,
        chunk_file: Any | None,
    ) -> dict:
        if not upload_id or chunk_index_str is None:
            raise BackupServiceError("缺少必要参数")

        try:
            chunk_index = int(chunk_index_str)
        except ValueError as exc:
            raise BackupServiceError("无效的分片索引") from exc

        if not chunk_file:
            raise BackupServiceError("缺少分片数据")
        if upload_id not in self.upload_sessions:
            raise BackupServiceError("上传会话不存在或已过期")

        session = self.upload_sessions[upload_id]
        if chunk_index < 0 or chunk_index >= session["total_chunks"]:
            raise BackupServiceError("分片索引超出范围")

        chunk_path = os.path.join(session["chunk_dir"], f"{chunk_index}.part")
        await self._save_upload(chunk_file, chunk_path)
        session["received_chunks"].add(chunk_index)
        session["last_activity"] = time.time()

        received_count = len(session["received_chunks"])
        total_chunks = session["total_chunks"]
        logger.debug(
            f"接收分片: upload_id={upload_id}, chunk={chunk_index + 1}/{total_chunks}"
        )

        return {
            "received": received_count,
            "total": total_chunks,
            "chunk_index": chunk_index,
        }

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

    async def upload_complete(self, data: object) -> dict:
        payload = self._payload(data)
        upload_id = payload.get("upload_id")

        if not upload_id:
            raise BackupServiceError("缺少 upload_id 参数")
        if upload_id not in self.upload_sessions:
            raise BackupServiceError("上传会话不存在或已过期")

        session = self.upload_sessions[upload_id]
        received = session["received_chunks"]
        total = session["total_chunks"]

        if len(received) != total:
            missing = set(range(total)) - received
            raise BackupServiceError(f"分片不完整，缺少: {sorted(missing)[:10]}...")

        chunk_dir = session["chunk_dir"]
        filename = session["filename"]

        Path(self.backup_dir).mkdir(parents=True, exist_ok=True)
        output_path = os.path.join(self.backup_dir, filename)

        try:
            with open(output_path, "wb") as outfile:
                for i in range(total):
                    chunk_path = os.path.join(chunk_dir, f"{i}.part")
                    with open(chunk_path, "rb") as chunk_file:
                        while True:
                            data_block = chunk_file.read(8192)
                            if not data_block:
                                break
                            outfile.write(data_block)

            file_size = os.path.getsize(output_path)
            self.mark_backup_as_uploaded(output_path)
            logger.info(f"分片上传完成: {filename}, size={file_size}, chunks={total}")
            await self.cleanup_upload_session(upload_id)

            return {
                "filename": filename,
                "original_filename": session["original_filename"],
                "size": file_size,
            }
        except Exception:
            if os.path.exists(output_path):
                os.remove(output_path)
            raise

    async def upload_abort(self, data: object) -> tuple[dict | None, str | None]:
        payload = self._payload(data)
        upload_id = payload.get("upload_id")
        if not upload_id:
            raise BackupServiceError("缺少 upload_id 参数")

        if upload_id in self.upload_sessions:
            await self.cleanup_upload_session(upload_id)
            logger.info(f"取消分片上传: {upload_id}")

        return None, "上传已取消"

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
        if not new_name:
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
