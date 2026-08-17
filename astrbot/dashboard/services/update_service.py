from __future__ import annotations

import asyncio
import traceback
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from astrbot.core import logger, pip_installer
from astrbot.core.config.default import VERSION
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.dashboard_assets import get_dashboard_version
from astrbot.core.desktop_runtime import (
    DESKTOP_MANAGED_RESTART_MESSAGE,
    is_desktop_managed_backend,
)
from astrbot.core.updater import AstrBotUpdater, UpdateProgress


async def call_get_dashboard_version(*args, **kwargs):
    return await get_dashboard_version(*args, **kwargs)


async def call_pip_install(*args, **kwargs):
    return await pip_installer.install(*args, **kwargs)


@dataclass
class UpdateServiceResult:
    data: Any = None
    message: str | None = None
    status: str = "ok"
    headers: dict | None = None


class UpdateServiceError(Exception):
    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class UpdateService:
    def __init__(
        self,
        astrbot_updater: AstrBotUpdater,
        core_lifecycle: AstrBotCoreLifecycle,
        *,
        get_dashboard_version_func: Callable[..., Awaitable[str | None]],
        pip_install_func: Callable[..., Awaitable[Any]],
        demo_mode: bool,
        clear_site_data_headers: dict,
    ) -> None:
        self._updater = astrbot_updater
        self.core_lifecycle = core_lifecycle
        self.get_dashboard_version = get_dashboard_version_func
        self.pip_install = pip_install_func
        self.demo_mode = demo_mode
        self.clear_site_data_headers = clear_site_data_headers
        self.update_progress: dict[str, dict] = {}
        self._update_tasks: dict[str, asyncio.Task] = {}

    def get_update_progress(self, progress_id: str) -> UpdateServiceResult:
        if not progress_id:
            raise UpdateServiceError("缺少参数 id。")
        progress = self.update_progress.get(progress_id)
        if not progress:
            return UpdateServiceResult(
                data={"id": progress_id, "status": "idle"},
                message="没有正在进行的更新。",
            )
        return UpdateServiceResult(data=progress)

    async def check_update(self, update_type: str | None) -> UpdateServiceResult:
        try:
            dashboard_version = await self.get_dashboard_version()
            if update_type == "dashboard":
                return UpdateServiceResult(
                    data={
                        "has_new_version": dashboard_version != f"v{VERSION}",
                        "current_version": dashboard_version,
                    }
                )
            update_result = await self._updater.check_update(False)
            return UpdateServiceResult(
                status="success",
                message=str(update_result)
                if update_result is not None
                else "已经是最新版本了。",
                data={
                    "version": f"v{VERSION}",
                    "has_new_version": update_result is not None,
                    "dashboard_version": dashboard_version,
                    "dashboard_has_new_version": bool(
                        dashboard_version and dashboard_version != f"v{VERSION}"
                    ),
                },
            )
        except Exception as exc:
            logger.warning(f"检查更新失败: {exc!s} (不影响除项目更新外的正常使用)")
            raise UpdateServiceError(exc.__str__()) from exc

    async def get_releases(self) -> UpdateServiceResult:
        try:
            releases = await self._updater.get_releases()
            return UpdateServiceResult(
                data=[
                    {
                        "tag_name": release.version,
                        "published_at": release.published_at,
                        "body": release.body,
                    }
                    for release in releases
                ]
            )
        except Exception as exc:
            logger.error(f"/api/update/releases: {traceback.format_exc()}")
            raise UpdateServiceError(exc.__str__()) from exc

    async def update_project(self, data: object) -> UpdateServiceResult:
        if is_desktop_managed_backend():
            raise UpdateServiceError(
                DESKTOP_MANAGED_RESTART_MESSAGE,
                code="desktop_managed",
            )

        payload = data if isinstance(data, dict) else {}
        version = payload.get("version", "")
        reboot = payload.get("reboot", True)
        progress_id = payload.get("progress_id") or uuid.uuid4().hex
        if version == "" or version == "latest":
            version = None

        proxy: str | None = payload.get("proxy", None)
        if proxy:
            proxy = proxy.removesuffix("/")

        existing_task = self._update_tasks.get(progress_id)
        if existing_task and not existing_task.done():
            return UpdateServiceResult(
                data={"id": progress_id, "status": "running"},
                message="更新任务正在进行中。",
                headers=self.clear_site_data_headers,
            )

        self._init_update_progress(progress_id, version)
        task = asyncio.create_task(
            self._run_update_project(progress_id, version, reboot, proxy)
        )
        self._update_tasks[progress_id] = task
        task.add_done_callback(lambda _task: self._update_tasks.pop(progress_id, None))
        return UpdateServiceResult(
            data={"id": progress_id, "status": "running"},
            message="更新任务已开始。",
            headers=self.clear_site_data_headers,
        )

    async def _run_update_project(
        self,
        progress_id: str,
        version: str | None,
        reboot: bool,
        proxy: str | None,
    ) -> None:
        """Run the long core update outside the request lifecycle.

        Args:
            progress_id: Progress record id reported to the frontend.
            version: Target version without the latest sentinel.
            reboot: Whether to restart AstrBot after applying files.
            proxy: Optional GitHub proxy URL.
        """
        try:

            async def observe_update(event: UpdateProgress) -> None:
                self._set_update_stage(
                    progress_id,
                    event.stage,
                    event.status,
                    event.message,
                    event.overall_percent,
                )
                if event.downloaded_bytes is not None:
                    stage_data = self.update_progress[progress_id]["stages"][
                        event.stage
                    ]
                    download_percent = (
                        int(event.downloaded_bytes / event.total_bytes * 100)
                        if event.total_bytes
                        else 0
                    )
                    stage_data.update(
                        {
                            "downloaded": event.downloaded_bytes,
                            "total": event.total_bytes or 0,
                            "percent": max(0, min(100, download_percent)),
                            "speed": event.speed_kib_per_second or 0,
                        }
                    )

            await self._updater.update(
                version=version,
                proxy=proxy or "",
                progress_callback=observe_update,
            )

            self._set_update_stage(
                progress_id,
                "dependencies",
                "running",
                "正在更新依赖...",
                92,
            )
            logger.info("Updating dependencies...")
            try:
                await self.pip_install(requirements_path="requirements.txt")
            except Exception as exc:
                logger.error(f"Failed to update dependencies: {exc}")
            self._set_update_stage(
                progress_id,
                "dependencies",
                "done",
                "依赖更新完成。",
                96,
            )

            if reboot:
                self._set_update_stage(
                    progress_id,
                    "restart",
                    "running",
                    "更新成功，正在准备重启...",
                    98,
                )
                await self.core_lifecycle.restart()
                message = "更新成功，AstrBot 将在 2 秒内全量重启以应用新的代码。"
            else:
                message = "更新成功，AstrBot 将在下次启动时应用新的代码。"

            self.update_progress[progress_id].update(
                {
                    "status": "success",
                    "stage": "done",
                    "message": message,
                    "overall_percent": 100,
                },
            )
            logger.info(message)
        except asyncio.CancelledError:
            self.update_progress[progress_id].update(
                {
                    "status": "error",
                    "message": "更新任务已取消。",
                },
            )
            logger.warning(f"Update task was cancelled: {progress_id}")
            raise
        except Exception as exc:
            self.update_progress[progress_id].update(
                {
                    "status": "error",
                    "message": "更新失败，请查看服务端日志。",
                },
            )
            logger.error(f"/api/update_project: {traceback.format_exc()}")
            logger.debug(f"Update task failed: {exc!s}")

    async def update_dashboard(self) -> UpdateServiceResult:
        try:
            try:
                await self._updater.ensure_dashboard()
            except Exception as exc:
                logger.error(f"Failed to ensure Dashboard assets: {exc}")
                raise UpdateServiceError(f"管理面板修复失败: {exc}") from exc
            return UpdateServiceResult(
                message="管理面板已与当前 AstrBot 版本同步。",
                headers=self.clear_site_data_headers,
            )
        except UpdateServiceError:
            raise
        except Exception as exc:
            logger.error(f"/api/update_dashboard: {traceback.format_exc()}")
            raise UpdateServiceError(exc.__str__()) from exc

    async def install_pip_package(self, data: object) -> UpdateServiceResult:
        if self.demo_mode:
            raise UpdateServiceError(
                "You are not permitted to do this operation in demo mode"
            )

        payload = data if isinstance(data, dict) else {}
        package = payload.get("package", "")
        mirror = payload.get("mirror", None)
        if not package:
            raise UpdateServiceError("缺少参数 package 或不合法。")
        try:
            await self.pip_install(package, mirror=mirror)
            return UpdateServiceResult(message="安装成功。")
        except Exception as exc:
            logger.error(f"/api/update_pip: {traceback.format_exc()}")
            raise UpdateServiceError(exc.__str__()) from exc

    def _init_update_progress(self, progress_id: str, version: str | None) -> None:
        self.update_progress[progress_id] = {
            "id": progress_id,
            "status": "running",
            "stage": "preparing",
            "version": version or "latest",
            "message": "正在准备更新...",
            "overall_percent": 0,
            "stages": {
                "dashboard": self._empty_stage("pending"),
                "core": self._empty_stage("pending"),
            },
        }

    @staticmethod
    def _empty_stage(status: str = "pending") -> dict:
        return {
            "status": status,
            "downloaded": 0,
            "total": 0,
            "percent": 0,
            "speed": 0,
        }

    def _set_update_stage(
        self,
        progress_id: str,
        stage: str,
        status: str,
        message: str,
        overall_percent: int | None = None,
    ) -> None:
        progress = self.update_progress.get(progress_id)
        if not progress:
            return
        progress["stage"] = stage
        progress["message"] = message
        progress["stages"].setdefault(stage, self._empty_stage())
        progress["stages"][stage]["status"] = status
        if overall_percent is not None:
            progress["overall_percent"] = overall_percent
