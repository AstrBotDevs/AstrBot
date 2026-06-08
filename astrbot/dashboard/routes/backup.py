"""备份管理 API 路由"""

from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.dashboard.fastapi_compat import request, send_file
from astrbot.dashboard.services.backup_service import (
    BackupService,
    BackupServiceError,
)

from .route import Response, Route, RouteContext


class BackupRoute(Route):
    """备份管理路由"""

    def __init__(
        self,
        context: RouteContext,
        db: BaseDatabase,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.service = BackupService(db, core_lifecycle)
        self.routes = {
            "/backup/list": ("GET", self.list_backups),
            "/backup/export": ("POST", self.export_backup),
            "/backup/upload": ("POST", self.upload_backup),
            "/backup/upload/init": ("POST", self.upload_init),
            "/backup/upload/chunk": ("POST", self.upload_chunk),
            "/backup/upload/complete": ("POST", self.upload_complete),
            "/backup/upload/abort": ("POST", self.upload_abort),
            "/backup/check": ("POST", self.check_backup),
            "/backup/import": ("POST", self.import_backup),
            "/backup/progress": ("GET", self.get_progress),
            "/backup/download": ("GET", self.download_backup),
            "/backup/delete": ("POST", self.delete_backup),
            "/backup/rename": ("POST", self.rename_backup),
        }
        self.register_routes()

    @staticmethod
    def _ok(data: dict | list | None = None, message: str | None = None) -> dict:
        return Response().ok(data, message).__dict__

    @staticmethod
    def _error(message: str) -> dict:
        return Response().error(message).__dict__

    @staticmethod
    async def _json_body() -> dict:
        data = await request.get_json()
        return data if isinstance(data, dict) else {}

    async def _run(self, operation, *, prefix: str):
        try:
            result = operation() if callable(operation) else operation
            while hasattr(result, "__await__"):
                result = await result
            if isinstance(result, tuple):
                data, message = result
                return self._ok(data, message)
            return self._ok(result)
        except BackupServiceError as exc:
            return self._error(str(exc))
        except Exception as exc:
            logger.error("%s: %s", prefix, exc, exc_info=True)
            return self._error(f"{prefix}: {exc!s}")

    async def _run_json(self, operation, *, prefix: str):
        async def invoke():
            data = await self._json_body()
            return operation(data)

        return await self._run(invoke, prefix=prefix)

    async def list_backups(self):
        return await self._run(
            lambda: self.service.list_backups_from_legacy_query(
                page=request.args.get("page", 1),
                page_size=request.args.get("page_size", 20),
            ),
            prefix="获取备份列表失败",
        )

    async def export_backup(self):
        return await self._run(self.service.export_backup, prefix="创建备份失败")

    async def upload_backup(self):
        async def _operation():
            files = await request.files
            return await self.service.upload_backup(files.get("file"))

        return await self._run(_operation, prefix="上传备份文件失败")

    async def upload_init(self):
        return await self._run_json(
            self.service.upload_init,
            prefix="初始化分片上传失败",
        )

    async def upload_chunk(self):
        async def _operation():
            form = await request.form
            files = await request.files
            return await self.service.upload_chunk(
                upload_id=form.get("upload_id"),
                chunk_index_str=form.get("chunk_index"),
                chunk_file=files.get("chunk"),
            )

        return await self._run(_operation, prefix="上传分片失败")

    async def upload_complete(self):
        return await self._run_json(
            self.service.upload_complete,
            prefix="完成分片上传失败",
        )

    async def upload_abort(self):
        return await self._run_json(
            self.service.upload_abort,
            prefix="取消上传失败",
        )

    async def check_backup(self):
        return await self._run_json(
            self.service.check_backup,
            prefix="预检查备份文件失败",
        )

    async def import_backup(self):
        return await self._run_json(
            self.service.import_backup,
            prefix="导入备份失败",
        )

    async def get_progress(self):
        return await self._run(
            lambda: self.service.get_progress_from_legacy_query(
                request.args.get("task_id")
            ),
            prefix="获取任务进度失败",
        )

    async def download_backup(self):
        try:
            download = self.service.prepare_download_from_legacy_query(
                filename=request.args.get("filename"),
                token=request.args.get("token"),
            )
            return await send_file(
                download.path,
                as_attachment=True,
                attachment_filename=download.filename,
                conditional=True,
            )
        except BackupServiceError as exc:
            return self._error(str(exc))
        except Exception as exc:
            logger.error("下载备份失败: %s", exc, exc_info=True)
            return self._error(f"下载备份失败: {exc!s}")

    async def delete_backup(self):
        return await self._run_json(
            self.service.delete_backup,
            prefix="删除备份失败",
        )

    async def rename_backup(self):
        return await self._run_json(
            self.service.rename_backup,
            prefix="重命名备份失败",
        )


__all__ = ["BackupRoute"]
