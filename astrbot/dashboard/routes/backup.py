"""备份管理 API 路由"""

import asyncio
import json
import os
import re
import shutil
import time
import traceback
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

import jwt
from quart import request, send_file

from astrbot.core import logger
from astrbot.core.backup.exporter import AstrBotExporter
from astrbot.core.backup.importer import AstrBotImporter
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.utils.astrbot_path import (
    get_astrbot_backups_path,
    get_astrbot_data_path,
)

from .route import Response, Route, RouteContext

# 分片上传常量
CHUNK_SIZE = 1024 * 1024  # 1MB
UPLOAD_EXPIRE_SECONDS = 3600  # 上传会话过期时间（1小时）


def secure_filename(filename: str) -> str:
    """清洗文件名，移除路径遍历字符和危险字符

    Args:
        filename: 原始文件名

    Returns:
        安全的文件名
    """
    # 跨平台处理：先将反斜杠替换为正斜杠，再取文件名
    filename = filename.replace("\\", "/")
    # 仅保留文件名部分，移除路径
    filename = os.path.basename(filename)

    # 替换路径遍历字符
    filename = filename.replace("..", "_")

    # 仅保留字母、数字、下划线、连字符、点
    filename = re.sub(r"[^\w\-.]", "_", filename)

    # 移除前导点（隐藏文件）和尾部点
    filename = filename.strip(".")

    # 如果文件名为空或只包含下划线，生成一个默认名称
    if not filename or filename.replace("_", "") == "":
        filename = "backup"

    return filename


def generate_unique_filename(original_filename: str) -> str:
    """生成唯一的文件名，在原文件名后添加时间戳后缀避免重名

    Args:
        original_filename: 原始文件名（已清洗）

    Returns:
        添加了时间戳后缀的唯一文件名，格式为 {原文件名}_{YYYYMMDD_HHMMSS}.{扩展名}
    """
    name, ext = os.path.splitext(original_filename)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{name}_{timestamp}{ext}"


class BackupRoute(Route):
    """备份管理路由

    提供备份导出、导入、列表等 API 接口
    """

    def __init__(
        self,
        context: RouteContext,
        db: BaseDatabase,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.db = db
        self.core_lifecycle = core_lifecycle
        self.backup_dir = get_astrbot_backups_path()
        self.data_dir = get_astrbot_data_path()
        self.chunks_dir = os.path.join(self.backup_dir, ".chunks")

        # 任务状态跟踪
        self.backup_tasks: dict[str, dict] = {}
        self.backup_progress: dict[str, dict] = {}

        # 分片上传会话跟踪
        # upload_id -> {filename, total_chunks, received_chunks, last_activity, chunk_dir}
        self.upload_sessions: dict[str, dict] = {}

        # 后台清理任务句柄
        self._cleanup_task: asyncio.Task | None = None

        # 注册路由
        self.routes = {
            "/backup/list": ("GET", self.list_backups),
            "/backup/export": ("POST", self.export_backup),
            "/backup/upload": ("POST", self.upload_backup),  # 上传文件（兼容小文件）
            "/backup/upload/init": ("POST", self.upload_init),  # 分片上传初始化
            "/backup/upload/chunk": ("POST", self.upload_chunk),  # 上传分片
            "/backup/upload/complete": ("POST", self.upload_complete),  # 完成分片上传
            "/backup/upload/abort": ("POST", self.upload_abort),  # 取消上传
            "/backup/check": ("POST", self.check_backup),  # 预检查
            "/backup/import": ("POST", self.import_backup),  # 确认导入
            "/backup/progress": ("GET", self.get_progress),
            "/backup/download": ("GET", self.download_backup),
            "/backup/delete": ("POST", self.delete_backup),
            "/backup/rename": ("POST", self.rename_backup),  # 重命名备份
        }
        self.register_routes()

    def _init_task(self, task_id: str, task_type: str, status: str = "pending") -> None:
        """初始化任务状态"""
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
        """设置任务结果"""
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
        """更新任务进度"""
        if task_id not in self.backup_progress:
            return
        p = self.backup_progress[task_id]
        if status is not None:
            p["status"] = status
        if stage is not None:
            p["stage"] = stage
        if current is not None:
            p["current"] = current
        if total is not None:
            p["total"] = total
        if message is not None:
            p["message"] = message

    def _make_progress_callback(self, task_id: str):
        """创建进度回调函数"""

        async def _callback(stage: str, current: int, total: int, message: str = ""):
            self._update_progress(
                task_id,
                status="processing",
                stage=stage,
                current=current,
                total=total,
                message=message,
            )

        return _callback

    def _ensure_cleanup_task_started(self):
        """确保后台清理任务已启动（在异步上下文中延迟启动）"""
        if self._cleanup_task is None or self._cleanup_task.done():
            try:
                self._cleanup_task = asyncio.create_task(
                    self._cleanup_expired_uploads()
                )
            except RuntimeError:
                # 如果没有运行中的事件循环，跳过（等待下次异步调用时启动）
                pass

    async def _cleanup_expired_uploads(self):
        """定期清理过期的上传会话

        基于 last_activity 字段判断过期，避免清理活跃的上传会话。
        """
        while True:
            try:
                await asyncio.sleep(300)  # 每5分钟检查一次
                current_time = time.time()
                expired_sessions = []

                for upload_id, session in self.upload_sessions.items():
                    # 使用 last_activity 判断过期，而非 created_at
                    last_activity = session.get("last_activity", session["created_at"])
                    if current_time - last_activity > UPLOAD_EXPIRE_SECONDS:
                        expired_sessions.append(upload_id)

                for upload_id in expired_sessions:
                    await self._cleanup_upload_session(upload_id)
                    logger.info(f"清理过期的上传会话: {upload_id}")

            except asyncio.CancelledError:
                # 任务被取消，正常退出
                break
            except Exception as e:
                logger.error(f"清理过期上传会话失败: {e}")

    async def _cleanup_upload_session(self, upload_id: str):
        """清理上传会话"""
        if upload_id in self.upload_sessions:
            session = self.upload_sessions[upload_id]
            chunk_dir = session.get("chunk_dir")
            if chunk_dir and os.path.exists(chunk_dir):
                try:
                    shutil.rmtree(chunk_dir)
                except Exception as e:
                    logger.warning(f"清理分片目录失败: {e}")
            del self.upload_sessions[upload_id]

    def _get_backup_manifest(self, zip_path: str) -> dict | None:
        """从备份文件读取 manifest.json

        Args:
            zip_path: ZIP 文件路径

        Returns:
            dict | None: manifest 内容，如果不是有效备份则返回 None
        """
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                if "manifest.json" in zf.namelist():
                    manifest_data = zf.read("manifest.json")
                    return json.loads(manifest_data.decode("utf-8"))
                else:
                    # 没有 manifest.json，不是有效的 AstrBot 备份
                    return None
        except Exception as e:
            logger.debug(f"读取备份 manifest 失败: {e}")
        return None  # 无法读取，不是有效备份

    async def list_backups(self):
        # 确保后台清理任务已启动
        self._ensure_cleanup_task_started()

        """获取备份列表

        Query 参数:
        - page: 页码 (默认 1)
        - page_size: 每页数量 (默认 20)
        """
        try:
            page = request.args.get("page", 1, type=int)
            page_size = request.args.get("page_size", 20, type=int)

            # 确保备份目录存在
            Path(self.backup_dir).mkdir(parents=True, exist_ok=True)

            # 获取所有备份文件
            backup_files = []
            for filename in os.listdir(self.backup_dir):
                # 只处理 .zip 文件，排除隐藏文件和目录
                if not filename.endswith(".zip") or filename.startswith("."):
                    continue

                file_path = os.path.join(self.backup_dir, filename)
                if not os.path.isfile(file_path):
                    continue

                # 读取 manifest.json 获取备份信息
                # 如果返回 None，说明不是有效的 AstrBot 备份，跳过
                manifest = self._get_backup_manifest(file_path)
                if manifest is None:
                    logger.debug(f"跳过无效备份文件: {filename}")
                    continue

                stat = os.stat(file_path)
                backup_files.append(
                    {
                        "filename": filename,
                        "size": stat.st_size,
                        "created_at": stat.st_mtime,
                        "type": manifest.get(
                            "origin", "exported"
                        ),  # 老版本没有 origin 默认为 exported
                        "astrbot_version": manifest.get("astrbot_version", "未知"),
                        "exported_at": manifest.get("exported_at"),
                    }
                )

            # 按创建时间倒序排序
            backup_files.sort(key=lambda x: x["created_at"], reverse=True)

            # 分页
            start = (page - 1) * page_size
            end = start + page_size
            items = backup_files[start:end]

            return (
                Response()
                .ok(
                    {
                        "items": items,
                        "total": len(backup_files),
                        "page": page,
                        "page_size": page_size,
                    }
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"获取备份列表失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"获取备份列表失败: {e!s}").__dict__

    async def export_backup(self):
        """创建备份

        返回:
        - task_id: 任务ID，用于查询导出进度
        """
        try:
            # 生成任务ID
            task_id = str(uuid.uuid4())

            # 初始化任务状态
            self._init_task(task_id, "export", "pending")

            # 启动后台导出任务
            asyncio.create_task(self._background_export_task(task_id))

            return (
                Response()
                .ok(
                    {
                        "task_id": task_id,
                        "message": "export task created, processing in background",
                    }
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"创建备份失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"创建备份失败: {e!s}").__dict__

    async def _background_export_task(self, task_id: str):
        """后台导出任务"""
        try:
            self._update_progress(task_id, status="processing", message="正在初始化...")

            # 获取知识库管理器
            kb_manager = getattr(self.core_lifecycle, "kb_manager", None)

            exporter = AstrBotExporter(
                main_db=self.db,
                kb_manager=kb_manager,
                config_path=os.path.join(self.data_dir, "cmd_config.json"),
            )

            # 创建进度回调
            progress_callback = self._make_progress_callback(task_id)

            # 执行导出
            zip_path = await exporter.export_all(
                output_dir=self.backup_dir,
                progress_callback=progress_callback,
            )

            # 设置成功结果
            self._set_task_result(
                task_id,
                "completed",
                result={
                    "filename": os.path.basename(zip_path),
                    "path": zip_path,
                    "size": os.path.getsize(zip_path),
                },
            )
        except Exception as e:
            logger.error(f"后台导出任务 {task_id} 失败: {e}")
            logger.error(traceback.format_exc())
            self._set_task_result(task_id, "failed", error=str(e))

    async def upload_backup(self):
        """上传备份文件

        将备份文件上传到服务器，返回保存的文件名。
        上传后应调用 check_backup 进行预检查。

        Form Data:
        - file: 备份文件 (.zip)

        返回:
        - filename: 保存的文件名
        """
        try:
            files = await request.files
            if "file" not in files:
                return Response().error("缺少备份文件").__dict__

            file = files["file"]
            if not file.filename or not file.filename.endswith(".zip"):
                return Response().error("请上传 ZIP 格式的备份文件").__dict__

            # 清洗文件名并生成唯一名称，防止路径遍历和覆盖
            safe_filename = secure_filename(file.filename)
            unique_filename = generate_unique_filename(safe_filename)

            # 保存上传的文件
            Path(self.backup_dir).mkdir(parents=True, exist_ok=True)
            zip_path = os.path.join(self.backup_dir, unique_filename)
            await file.save(zip_path)

            logger.info(
                f"上传的备份文件已保存: {unique_filename} (原始名称: {file.filename})"
            )

            return (
                Response()
                .ok(
                    {
                        "filename": unique_filename,
                        "original_filename": file.filename,
                        "size": os.path.getsize(zip_path),
                    }
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"上传备份文件失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"上传备份文件失败: {e!s}").__dict__

    async def upload_init(self):
        """初始化分片上传

        创建一个上传会话，返回 upload_id 供后续分片上传使用。

        JSON Body:
        - filename: 原始文件名
        - total_size: 文件总大小（字节）

        返回:
        - upload_id: 上传会话 ID
        - chunk_size: 分片大小（由后端决定）
        - total_chunks: 分片总数（由后端根据 total_size 和 chunk_size 计算）
        """
        try:
            data = await request.json
            filename = data.get("filename")
            total_size = data.get("total_size", 0)

            if not filename:
                return Response().error("缺少 filename 参数").__dict__

            if not filename.endswith(".zip"):
                return Response().error("请上传 ZIP 格式的备份文件").__dict__

            if total_size <= 0:
                return Response().error("无效的文件大小").__dict__

            # 由后端计算分片总数，确保前后端一致
            import math

            total_chunks = math.ceil(total_size / CHUNK_SIZE)

            # 生成上传 ID
            upload_id = str(uuid.uuid4())

            # 创建分片存储目录
            chunk_dir = os.path.join(self.chunks_dir, upload_id)
            Path(chunk_dir).mkdir(parents=True, exist_ok=True)

            # 清洗文件名
            safe_filename = secure_filename(filename)
            unique_filename = generate_unique_filename(safe_filename)

            # 创建上传会话
            current_time = time.time()
            self.upload_sessions[upload_id] = {
                "filename": unique_filename,
                "original_filename": filename,
                "total_size": total_size,
                "total_chunks": total_chunks,
                "received_chunks": set(),
                "created_at": current_time,
                "last_activity": current_time,  # 用于判断会话是否活跃
                "chunk_dir": chunk_dir,
            }

            logger.info(
                f"初始化分片上传: upload_id={upload_id}, "
                f"filename={unique_filename}, total_chunks={total_chunks}"
            )

            return (
                Response()
                .ok(
                    {
                        "upload_id": upload_id,
                        "chunk_size": CHUNK_SIZE,
                        "total_chunks": total_chunks,
                        "filename": unique_filename,
                    }
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"初始化分片上传失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"初始化分片上传失败: {e!s}").__dict__

    async def upload_chunk(self):
        """上传分片

        上传单个分片数据。

        Form Data:
        - upload_id: 上传会话 ID
        - chunk_index: 分片索引（从 0 开始）
        - chunk: 分片数据

        返回:
        - received: 已接收的分片数量
        - total: 分片总数
        """
        try:
            form = await request.form
            files = await request.files

            upload_id = form.get("upload_id")
            chunk_index_str = form.get("chunk_index")

            if not upload_id or chunk_index_str is None:
                return Response().error("缺少必要参数").__dict__

            try:
                chunk_index = int(chunk_index_str)
            except ValueError:
                return Response().error("无效的分片索引").__dict__

            if "chunk" not in files:
                return Response().error("缺少分片数据").__dict__

            # 验证上传会话
            if upload_id not in self.upload_sessions:
                return Response().error("上传会话不存在或已过期").__dict__

            session = self.upload_sessions[upload_id]

            # 验证分片索引
            if chunk_index < 0 or chunk_index >= session["total_chunks"]:
                return Response().error("分片索引超出范围").__dict__

            # 保存分片
            chunk_file = files["chunk"]
            chunk_path = os.path.join(session["chunk_dir"], f"{chunk_index}.part")
            await chunk_file.save(chunk_path)

            # 记录已接收的分片，并更新最后活动时间
            session["received_chunks"].add(chunk_index)
            session["last_activity"] = time.time()  # 刷新活动时间，防止活跃上传被清理

            received_count = len(session["received_chunks"])
            total_chunks = session["total_chunks"]

            logger.debug(
                f"接收分片: upload_id={upload_id}, "
                f"chunk={chunk_index + 1}/{total_chunks}"
            )

            return (
                Response()
                .ok(
                    {
                        "received": received_count,
                        "total": total_chunks,
                        "chunk_index": chunk_index,
                    }
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"上传分片失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"上传分片失败: {e!s}").__dict__

    def _mark_backup_as_uploaded(self, zip_path: str) -> None:
        """修改备份文件的 manifest.json，将 origin 设置为 uploaded

        使用 zipfile 的 append 模式添加新的 manifest.json，
        ZIP 规范中后添加的同名文件会覆盖先前的文件。

        Args:
            zip_path: ZIP 文件路径
        """
        try:
            # 读取原有 manifest
            manifest = {"origin": "uploaded", "uploaded_at": datetime.now().isoformat()}
            with zipfile.ZipFile(zip_path, "r") as zf:
                if "manifest.json" in zf.namelist():
                    manifest_data = zf.read("manifest.json")
                    manifest = json.loads(manifest_data.decode("utf-8"))
                    manifest["origin"] = "uploaded"
                    manifest["uploaded_at"] = datetime.now().isoformat()

            # 使用 append 模式添加新的 manifest.json
            # ZIP 规范中，后添加的同名文件会覆盖先前的
            with zipfile.ZipFile(zip_path, "a") as zf:
                new_manifest = json.dumps(manifest, ensure_ascii=False, indent=2)
                zf.writestr("manifest.json", new_manifest)

            logger.debug(f"已标记备份为上传来源: {zip_path}")
        except Exception as e:
            logger.warning(f"标记备份来源失败: {e}")

    async def upload_complete(self):
        """完成分片上传

        合并所有分片为完整文件。

        JSON Body:
        - upload_id: 上传会话 ID

        返回:
        - filename: 合并后的文件名
        - size: 文件大小
        """
        try:
            data = await request.json
            upload_id = data.get("upload_id")

            if not upload_id:
                return Response().error("缺少 upload_id 参数").__dict__

            # 验证上传会话
            if upload_id not in self.upload_sessions:
                return Response().error("上传会话不存在或已过期").__dict__

            session = self.upload_sessions[upload_id]

            # 检查是否所有分片都已接收
            received = session["received_chunks"]
            total = session["total_chunks"]

            if len(received) != total:
                missing = set(range(total)) - received
                return (
                    Response()
                    .error(f"分片不完整，缺少: {sorted(missing)[:10]}...")
                    .__dict__
                )

            # 合并分片
            chunk_dir = session["chunk_dir"]
            filename = session["filename"]

            Path(self.backup_dir).mkdir(parents=True, exist_ok=True)
            output_path = os.path.join(self.backup_dir, filename)

            try:
                with open(output_path, "wb") as outfile:
                    for i in range(total):
                        chunk_path = os.path.join(chunk_dir, f"{i}.part")
                        with open(chunk_path, "rb") as chunk_file:
                            # 分块读取，避免内存溢出
                            while True:
                                data_block = chunk_file.read(8192)
                                if not data_block:
                                    break
                                outfile.write(data_block)

                file_size = os.path.getsize(output_path)

                # 标记备份为上传来源（修改 manifest.json 中的 origin 字段）
                self._mark_backup_as_uploaded(output_path)

                logger.info(
                    f"分片上传完成: {filename}, size={file_size}, chunks={total}"
                )

                # 清理分片目录
                await self._cleanup_upload_session(upload_id)

                return (
                    Response()
                    .ok(
                        {
                            "filename": filename,
                            "original_filename": session["original_filename"],
                            "size": file_size,
                        }
                    )
                    .__dict__
                )
            except Exception as e:
                # 如果合并失败，删除不完整的文件
                if os.path.exists(output_path):
                    os.remove(output_path)
                raise e

        except Exception as e:
            logger.error(f"完成分片上传失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"完成分片上传失败: {e!s}").__dict__

    async def upload_abort(self):
        """取消分片上传

        取消上传并清理已上传的分片。

        JSON Body:
        - upload_id: 上传会话 ID
        """
        try:
            data = await request.json
            upload_id = data.get("upload_id")

            if not upload_id:
                return Response().error("缺少 upload_id 参数").__dict__

            if upload_id not in self.upload_sessions:
                # 会话已不存在，可能已过期或已完成
                return Response().ok(message="上传已取消").__dict__

            # 清理会话
            await self._cleanup_upload_session(upload_id)

            logger.info(f"取消分片上传: {upload_id}")

            return Response().ok(message="上传已取消").__dict__
        except Exception as e:
            logger.error(f"取消上传失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"取消上传失败: {e!s}").__dict__

    async def check_backup(self):
        """预检查备份文件

        检查备份文件的版本兼容性，返回确认信息。
        用户确认后调用 import_backup 执行导入。

        JSON Body:
        - filename: 已上传的备份文件名

        返回:
        - ImportPreCheckResult: 预检查结果
        """
        try:
            data = await request.json
            filename = data.get("filename")
            if not filename:
                return Response().error("缺少 filename 参数").__dict__

            # 安全检查 - 防止路径遍历
            if ".." in filename or "/" in filename or "\\" in filename:
                return Response().error("无效的文件名").__dict__

            zip_path = os.path.join(self.backup_dir, filename)
            if not os.path.exists(zip_path):
                return Response().error(f"备份文件不存在: {filename}").__dict__

            # 获取知识库管理器（用于构造 importer）
            kb_manager = getattr(self.core_lifecycle, "kb_manager", None)

            importer = AstrBotImporter(
                main_db=self.db,
                kb_manager=kb_manager,
                config_path=os.path.join(self.data_dir, "cmd_config.json"),
            )

            # 执行预检查
            check_result = importer.pre_check(zip_path)

            return Response().ok(check_result.to_dict()).__dict__
        except Exception as e:
            logger.error(f"预检查备份文件失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"预检查备份文件失败: {e!s}").__dict__

    async def import_backup(self):
        """执行备份导入

        在用户确认后执行实际的导入操作。
        需要先调用 upload_backup 上传文件，再调用 check_backup 预检查。

        JSON Body:
        - filename: 已上传的备份文件名（必填）
        - confirmed: 用户已确认（必填，必须为 true）

        返回:
        - task_id: 任务ID，用于查询导入进度
        """
        try:
            data = await request.json
            filename = data.get("filename")
            confirmed = data.get("confirmed", False)

            if not filename:
                return Response().error("缺少 filename 参数").__dict__

            if not confirmed:
                return (
                    Response()
                    .error("请先确认导入。导入将会清空并覆盖现有数据，此操作不可撤销。")
                    .__dict__
                )

            # 安全检查 - 防止路径遍历
            if ".." in filename or "/" in filename or "\\" in filename:
                return Response().error("无效的文件名").__dict__

            zip_path = os.path.join(self.backup_dir, filename)
            if not os.path.exists(zip_path):
                return Response().error(f"备份文件不存在: {filename}").__dict__

            # 生成任务ID
            task_id = str(uuid.uuid4())

            # 初始化任务状态
            self._init_task(task_id, "import", "pending")

            # 启动后台导入任务
            asyncio.create_task(self._background_import_task(task_id, zip_path))

            return (
                Response()
                .ok(
                    {
                        "task_id": task_id,
                        "message": "import task created, processing in background",
                    }
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"导入备份失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"导入备份失败: {e!s}").__dict__

    async def _background_import_task(self, task_id: str, zip_path: str):
        """后台导入任务"""
        try:
            self._update_progress(task_id, status="processing", message="正在初始化...")

            # 获取知识库管理器
            kb_manager = getattr(self.core_lifecycle, "kb_manager", None)

            importer = AstrBotImporter(
                main_db=self.db,
                kb_manager=kb_manager,
                config_path=os.path.join(self.data_dir, "cmd_config.json"),
            )

            # 创建进度回调
            progress_callback = self._make_progress_callback(task_id)

            # 执行导入
            result = await importer.import_all(
                zip_path=zip_path,
                mode="replace",
                progress_callback=progress_callback,
            )

            # 设置结果
            if result.success:
                self._set_task_result(
                    task_id,
                    "completed",
                    result=result.to_dict(),
                )
            else:
                self._set_task_result(
                    task_id,
                    "failed",
                    error="; ".join(result.errors),
                )
        except Exception as e:
            logger.error(f"后台导入任务 {task_id} 失败: {e}")
            logger.error(traceback.format_exc())
            self._set_task_result(task_id, "failed", error=str(e))

    async def get_progress(self):
        """获取任务进度

        Query 参数:
        - task_id: 任务 ID (必填)
        """
        try:
            task_id = request.args.get("task_id")
            if not task_id:
                return Response().error("缺少参数 task_id").__dict__

            if task_id not in self.backup_tasks:
                return Response().error("找不到该任务").__dict__

            task_info = self.backup_tasks[task_id]
            status = task_info["status"]

            response_data = {
                "task_id": task_id,
                "type": task_info["type"],
                "status": status,
            }

            # 如果任务正在处理，返回进度信息
            if status == "processing" and task_id in self.backup_progress:
                response_data["progress"] = self.backup_progress[task_id]

            # 如果任务完成，返回结果
            if status == "completed":
                response_data["result"] = task_info["result"]

            # 如果任务失败，返回错误信息
            if status == "failed":
                response_data["error"] = task_info["error"]

            return Response().ok(response_data).__dict__
        except Exception as e:
            logger.error(f"获取任务进度失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"获取任务进度失败: {e!s}").__dict__

    async def download_backup(self):
        """下载备份文件

        Query 参数:
        - filename: 备份文件名 (必填)
        - token: JWT token (必填，用于浏览器原生下载鉴权)

        注意: 此路由已被添加到 auth_middleware 白名单中，
              使用 URL 参数中的 token 进行鉴权，以支持浏览器原生下载。
        """
        try:
            filename = request.args.get("filename")
            token = request.args.get("token")

            if not filename:
                return Response().error("缺少参数 filename").__dict__

            if not token:
                return Response().error("缺少参数 token").__dict__

            # 验证 JWT token
            try:
                jwt_secret = self.config.get("dashboard", {}).get("jwt_secret")
                if not jwt_secret:
                    return Response().error("服务器配置错误").__dict__

                jwt.decode(token, jwt_secret, algorithms=["HS256"])
            except jwt.ExpiredSignatureError:
                return Response().error("Token 已过期，请刷新页面后重试").__dict__
            except jwt.InvalidTokenError:
                return Response().error("Token 无效").__dict__

            # 安全检查 - 防止路径遍历
            if ".." in filename or "/" in filename or "\\" in filename:
                return Response().error("无效的文件名").__dict__

            file_path = os.path.join(self.backup_dir, filename)
            if not os.path.exists(file_path):
                return Response().error("备份文件不存在").__dict__

            return await send_file(
                file_path,
                as_attachment=True,
                attachment_filename=filename,
                conditional=True,  # 启用 Range 请求支持（断点续传）
            )
        except Exception as e:
            logger.error(f"下载备份失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"下载备份失败: {e!s}").__dict__

    async def delete_backup(self):
        """删除备份文件

        Body:
        - filename: 备份文件名 (必填)
        """
        try:
            data = await request.json
            filename = data.get("filename")
            if not filename:
                return Response().error("缺少参数 filename").__dict__

            # 安全检查 - 防止路径遍历
            if ".." in filename or "/" in filename or "\\" in filename:
                return Response().error("无效的文件名").__dict__

            file_path = os.path.join(self.backup_dir, filename)
            if not os.path.exists(file_path):
                return Response().error("备份文件不存在").__dict__

            os.remove(file_path)
            return Response().ok(message="删除备份成功").__dict__
        except Exception as e:
            logger.error(f"删除备份失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"删除备份失败: {e!s}").__dict__

    async def rename_backup(self):
        """重命名备份文件

        Body:
        - filename: 当前文件名 (必填)
        - new_name: 新文件名 (必填，不含扩展名)
        """
        try:
            data = await request.json
            filename = data.get("filename")
            new_name = data.get("new_name")

            if not filename:
                return Response().error("缺少参数 filename").__dict__

            if not new_name:
                return Response().error("缺少参数 new_name").__dict__

            # 安全检查 - 防止路径遍历
            if ".." in filename or "/" in filename or "\\" in filename:
                return Response().error("无效的文件名").__dict__

            # 清洗新文件名（移除路径和危险字符）
            new_name = secure_filename(new_name)

            # 移除新文件名中的扩展名（如果有的话）
            if new_name.endswith(".zip"):
                new_name = new_name[:-4]

            # 验证新文件名不为空
            if not new_name or new_name.replace("_", "") == "":
                return Response().error("新文件名无效").__dict__

            # 强制使用 .zip 扩展名
            new_filename = f"{new_name}.zip"

            # 检查原文件是否存在
            old_path = os.path.join(self.backup_dir, filename)
            if not os.path.exists(old_path):
                return Response().error("备份文件不存在").__dict__

            # 检查新文件名是否已存在
            new_path = os.path.join(self.backup_dir, new_filename)
            if os.path.exists(new_path):
                return Response().error(f"文件名 '{new_filename}' 已存在").__dict__

            # 执行重命名
            os.rename(old_path, new_path)

            logger.info(f"备份文件重命名: {filename} -> {new_filename}")

            return (
                Response()
                .ok(
                    {
                        "old_filename": filename,
                        "new_filename": new_filename,
                    }
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"重命名备份失败: {e}")
            logger.error(traceback.format_exc())
            return Response().error(f"重命名备份失败: {e!s}").__dict__
