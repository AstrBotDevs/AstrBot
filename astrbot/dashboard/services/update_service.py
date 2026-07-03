from __future__ import annotations

import asyncio
import inspect
import traceback
import uuid
import zipfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from astrbot.core import DEMO_MODE as _DEMO_MODE
from astrbot.core import logger
from astrbot.core import pip_installer as _pip_installer
from astrbot.core.config.default import VERSION
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.desktop_runtime import (
    DESKTOP_MANAGED_RESTART_MESSAGE,
    is_desktop_managed_backend,
)
from astrbot.core.updator import AstrBotUpdator
from astrbot.core.utils.astrbot_path import (
    get_astrbot_data_path,
    get_astrbot_system_tmp_path,
)
from astrbot.core.utils.io import (
    download_dashboard as _download_dashboard,
)
from astrbot.core.utils.io import (
    extract_dashboard as _extract_dashboard,
)
from astrbot.core.utils.io import (
    get_dashboard_version as _get_dashboard_version,
)

DEMO_MODE = _DEMO_MODE
pip_installer = _pip_installer
download_dashboard = _download_dashboard
extract_dashboard = _extract_dashboard
get_dashboard_version = _get_dashboard_version


async def call_download_dashboard(*args, **kwargs):
    return await download_dashboard(*args, **kwargs)


async def call_extract_dashboard(*args, **kwargs):
    if inspect.iscoroutinefunction(extract_dashboard):
        return await extract_dashboard(*args, **kwargs)
    result = await asyncio.to_thread(extract_dashboard, *args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


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
        astrbot_updator: AstrBotUpdator,
        core_lifecycle: AstrBotCoreLifecycle,
        *,
        download_dashboard_func: Callable[..., Awaitable[Any]],
        extract_dashboard_func: Callable[..., Any],
        get_dashboard_version_func: Callable[..., Awaitable[str | None]],
        pip_install_func: Callable[..., Awaitable[Any]],
        demo_mode: bool,
        clear_site_data_headers: dict,
    ) -> None:
        self.astrbot_updator = astrbot_updator
        self.core_lifecycle = core_lifecycle
        self.download_dashboard = download_dashboard_func
        self.extract_dashboard = extract_dashboard_func
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
            update_result = await self.astrbot_updator.check_update(None, None, False)
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
            releases = await self.astrbot_updator.get_releases()
            return UpdateServiceResult(data=releases)
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
            latest = True
            version = ""
        else:
            latest = False

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
            self._run_update_project(progress_id, version, latest, reboot, proxy)
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
        version: str,
        latest: bool,
        reboot: bool,
        proxy: str | None,
    ) -> None:
        """Run the long core update outside the request lifecycle.

        Args:
            progress_id: Progress record id reported to the frontend.
            version: Target version without the latest sentinel.
            latest: Whether to install the latest release.
            reboot: Whether to restart AstrBot after applying files.
            proxy: Optional GitHub proxy URL.
        """
        update_temp_dir = Path(get_astrbot_system_tmp_path()) / "updates"
        update_temp_dir.mkdir(parents=True, exist_ok=True)
        update_token = uuid.uuid4().hex
        dashboard_zip_path = update_temp_dir / f"{update_token}-dashboard.zip"
        core_zip_path = update_temp_dir / f"{update_token}-core.zip"
        try:
            self._set_update_stage(
                progress_id,
                "dashboard",
                "running",
                "正在下载 WebUI...",
                0,
            )
            await self.download_dashboard(
                path=str(dashboard_zip_path),
                latest=latest,
                version=version,
                proxy=proxy or "",
                progress_callback=self._make_progress_callback(
                    progress_id,
                    "dashboard",
                    0,
                    45,
                ),
                extract=False,
            )
            self._set_update_stage(
                progress_id,
                "dashboard",
                "done",
                "WebUI 下载完成。",
                45,
            )

            self._set_update_stage(
                progress_id,
                "core",
                "running",
                "正在下载 AstrBot 项目代码...",
                45,
            )
            core_zip_path = Path(
                await self.astrbot_updator.download_update_package(
                    latest=latest,
                    version=version,
                    proxy=proxy or "",
                    path=core_zip_path,
                    progress_callback=self._make_progress_callback(
                        progress_id,
                        "core",
                        45,
                        45,
                    ),
                )
            )
            self._set_update_stage(
                progress_id,
                "core",
                "done",
                "项目代码下载完成。",
                90,
            )

            self._set_update_stage(
                progress_id,
                "verify",
                "running",
                "下载完成，正在校验更新包...",
                90,
            )

            def _verify_update_packages() -> None:
                for zip_path in (dashboard_zip_path, core_zip_path):
                    with zipfile.ZipFile(zip_path, "r") as archive:
                        corrupt_member = archive.testzip()
                    if corrupt_member:
                        raise UpdateServiceError(f"更新包校验失败: {corrupt_member}")

            await asyncio.to_thread(_verify_update_packages)
            self._set_update_stage(
                progress_id,
                "verify",
                "done",
                "更新包校验完成。",
                91,
            )

            self._set_update_stage(
                progress_id,
                "apply",
                "running",
                "下载完成，正在应用更新...",
                91,
            )
            await asyncio.to_thread(
                self.astrbot_updator.apply_update_package,
                core_zip_path,
            )
            await self.extract_dashboard(
                dashboard_zip_path,
                Path(get_astrbot_data_path()),
            )
            self._set_update_stage(
                progress_id,
                "apply",
                "done",
                "更新文件应用完成。",
                92,
            )

            self._set_update_stage(
                progress_id,
                "dependencies",
                "running",
                "正在更新依赖...",
                92,
            )
            logger.info("更新依赖中...")
            try:
                await self.pip_install(requirements_path="requirements.txt")
            except Exception as exc:
                logger.error(f"更新依赖失败: {exc}")
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
        finally:
            for zip_path in (dashboard_zip_path, core_zip_path):
                try:
                    if zip_path.exists():
                        zip_path.unlink()
                except Exception as cleanup_exc:
                    logger.warning(f"清理更新临时文件失败: {zip_path}, {cleanup_exc}")

    async def update_dashboard(self) -> UpdateServiceResult:
        try:
            try:
                await self.download_dashboard(version=f"v{VERSION}", latest=False)
            except Exception as exc:
                logger.error(f"下载管理面板文件失败: {exc}。")
                raise UpdateServiceError(f"下载管理面板文件失败: {exc}") from exc
            return UpdateServiceResult(
                message="更新成功。刷新页面即可应用新版本面板。",
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

    def _init_update_progress(self, progress_id: str, version: str) -> None:
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

    @staticmethod
    def _normalize_percent(value) -> int:
        try:
            percent = float(value or 0)
        except (TypeError, ValueError):
            return 0
        if percent <= 1:
            percent *= 100
        return max(0, min(100, int(percent)))

    def _make_progress_callback(
        self,
        progress_id: str,
        stage: str,
        stage_start: int,
        stage_weight: int,
    ):
        def _callback(payload: dict) -> None:
            progress = self.update_progress.get(progress_id)
            if not progress:
                return
            stage_percent = self._normalize_percent(payload.get("percent"))
            progress["stage"] = stage
            progress["stages"][stage] = {
                "status": "running" if stage_percent < 100 else "done",
                "downloaded": payload.get("downloaded", 0),
                "total": payload.get("total", 0),
                "percent": stage_percent,
                "speed": payload.get("speed", 0),
            }
            progress["overall_percent"] = min(
                99,
                stage_start + int(stage_percent * stage_weight / 100),
            )

        return _callback
