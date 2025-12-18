"""备份管理 API 路由"""

import asyncio
import os
import re
import traceback
import uuid
from datetime import datetime
from pathlib import Path

from quart import request, send_file

from astrbot.core import logger
from astrbot.core.backup.exporter import AstrBotExporter
from astrbot.core.backup.importer import AstrBotImporter
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase

from .route import Response, Route, RouteContext


def secure_filename(filename: str) -> str:
    """清洗文件名，移除路径遍历字符和危险字符

    Args:
        filename: 原始文件名

    Returns:
        安全的文件名
    """
    # 仅保留文件名部分，移除路径
    filename = os.path.basename(filename)

    # 替换路径分隔符和危险字符
    filename = filename.replace("..", "_")
    filename = filename.replace("/", "_")
    filename = filename.replace("\\", "_")

    # 仅保留字母、数字、下划线、连字符、点
    filename = re.sub(r"[^\w\-.]", "_", filename)

    # 移除前导点（隐藏文件）
    filename = filename.lstrip(".")

    # 如果文件名为空，生成一个默认名称
    if not filename:
        filename = "backup"

    return filename


def generate_unique_filename(original_filename: str) -> str:
    """生成唯一的文件名，添加时间戳前缀

    Args:
        original_filename: 原始文件名（已清洗）

    Returns:
        唯一的文件名
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name, ext = os.path.splitext(original_filename)
    return f"uploaded_{timestamp}_{name}{ext}"


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
        self.backup_dir = "data/backups"

        # 任务状态跟踪
        self.backup_tasks: dict[str, dict] = {}
        self.backup_progress: dict[str, dict] = {}

        # 注册路由
        self.routes = {
            "/backup/list": ("GET", self.list_backups),
            "/backup/export": ("POST", self.export_backup),
            "/backup/import": ("POST", self.import_backup),
            "/backup/progress": ("GET", self.get_progress),
            "/backup/download": ("GET", self.download_backup),
            "/backup/delete": ("POST", self.delete_backup),
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

    async def list_backups(self):
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
                if filename.endswith(".zip") and filename.startswith("astrbot_backup_"):
                    file_path = os.path.join(self.backup_dir, filename)
                    stat = os.stat(file_path)
                    backup_files.append(
                        {
                            "filename": filename,
                            "size": stat.st_size,
                            "created_at": stat.st_mtime,
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
                config_path="data/cmd_config.json",
                attachments_dir="data/attachments",
                data_root="data",
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

    async def import_backup(self):
        """导入备份

        支持两种方式:
        1. multipart/form-data 文件上传
        2. JSON 指定已存在的备份文件名

        Form Data:
        - file: 备份文件 (可选)

        JSON Body:
        - filename: 已存在的备份文件名 (可选)

        返回:
        - task_id: 任务ID，用于查询导入进度
        """
        try:
            zip_path = None
            content_type = request.content_type or ""

            if "multipart/form-data" in content_type:
                # 文件上传模式
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
            else:
                # JSON 模式 - 使用已存在的文件
                data = await request.json
                filename = data.get("filename")
                if not filename:
                    return Response().error("缺少 filename 参数").__dict__

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
                config_path="data/cmd_config.json",
                attachments_dir="data/attachments",
                data_root="data",
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
        """
        try:
            filename = request.args.get("filename")
            if not filename:
                return Response().error("缺少参数 filename").__dict__

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
