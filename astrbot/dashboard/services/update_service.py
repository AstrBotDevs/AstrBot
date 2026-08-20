import asyncio
import inspect
import tempfile
import traceback
import uuid
import zipfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from astrbot import logger
from astrbot.core.core_runtime import CoreControl
from astrbot.core.desktop_runtime import (
    DESKTOP_MANAGED_RESTART_MESSAGE,
    is_desktop_managed_backend,
)
from astrbot.core.updator import AstrBotUpdator, NoPublishedCoreReleaseError
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.error_redaction import redact_sensitive_text, safe_error
from astrbot.core.utils.pip_installer import PipInstaller

DEFAULT_MAX_PROGRESS_RECORDS = 100


async def call_pip_install(pip_installer: PipInstaller, *args, **kwargs):
    result = pip_installer.install(*args, **kwargs)
    if inspect.isawaitable(result):
        return await cast(Awaitable[Any], result)
    return result


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
        core_control: CoreControl,
        *,
        pip_install_func: Callable[..., Awaitable[Any]],
        demo_mode: bool,
        clear_site_data_headers: dict,
        max_progress_records: int = DEFAULT_MAX_PROGRESS_RECORDS,
    ) -> None:
        if max_progress_records < 1:
            raise ValueError("max_progress_records must be >= 1")
        self.astrbot_updator = astrbot_updator
        self.core_control = core_control
        self.pip_install = pip_install_func
        self.demo_mode = demo_mode
        self.clear_site_data_headers = clear_site_data_headers
        self.update_progress: dict[str, dict] = {}
        self._update_tasks: dict[str, asyncio.Task] = {}
        self._max_progress_records = max_progress_records
        self._closed = False
        self._shutdown_lock = asyncio.Lock()

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

    async def check_update(self) -> UpdateServiceResult:
        try:
            update_result = await self.astrbot_updator.check_update(None, None, False)
        except NoPublishedCoreReleaseError as exc:
            return UpdateServiceResult(
                status="success",
                message=str(exc),
                data={"has_new_version": False},
            )
        except Exception as exc:
            logger.warning(
                "检查更新失败: %s (不影响除项目更新外的正常使用)",
                safe_error("", exc),
            )
            raise UpdateServiceError("检查更新失败。") from exc
        return UpdateServiceResult(
            status="success",
            message=str(update_result)
            if update_result is not None
            else "已经是最新版本了。",
            data={
                "has_new_version": update_result is not None,
            },
        )

    async def get_releases(self) -> UpdateServiceResult:
        try:
            releases = await self.astrbot_updator.get_releases()
            return UpdateServiceResult(data=releases)
        except Exception as exc:
            logger.error(
                "/api/update/releases: %s",
                redact_sensitive_text(traceback.format_exc()),
            )
            raise UpdateServiceError("获取更新版本失败。") from exc

    async def update_project(self, data: object) -> UpdateServiceResult:
        if is_desktop_managed_backend():
            raise UpdateServiceError(
                DESKTOP_MANAGED_RESTART_MESSAGE,
                code="desktop_managed",
            )
        if self._closed:
            raise UpdateServiceError("更新服务已关闭。")

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
            self._run_update_project(progress_id, version, latest, reboot, proxy),
            name=f"dashboard-update:{progress_id}",
        )
        self._update_tasks[progress_id] = task
        task.add_done_callback(
            lambda completed_task: self._discard_update_task(
                progress_id,
                completed_task,
            )
        )
        return UpdateServiceResult(
            data={"id": progress_id, "status": "running"},
            message="更新任务已开始。",
            headers=self.clear_site_data_headers,
        )

    def _discard_update_task(self, progress_id: str, task: asyncio.Task) -> None:
        """Drop a completed task only when it is still the current task for its ID."""

        if self._update_tasks.get(progress_id) is task:
            self._update_tasks.pop(progress_id, None)

    async def shutdown(self) -> None:
        """Cancel and await update work owned by this Dashboard service."""

        async with self._shutdown_lock:
            self._closed = True
            owned_tasks = list(self._update_tasks.items())
            cancelled_progress_ids: list[str] = []
            for progress_id, task in owned_tasks:
                if not task.done() and task.cancel():
                    cancelled_progress_ids.append(progress_id)
            if owned_tasks:
                await asyncio.gather(
                    *(task for _, task in owned_tasks),
                    return_exceptions=True,
                )
            for progress_id in cancelled_progress_ids:
                progress = self.update_progress.get(progress_id)
                if progress and progress.get("status") == "running":
                    self._mark_update_cancelled(progress_id)
            self._update_tasks.clear()

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
        update_temp_parent = Path(get_astrbot_temp_path()) / "updates"
        try:
            if update_temp_parent.is_symlink():
                update_temp_parent.unlink()
            update_temp_parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            update_temp_parent.chmod(0o700)
            with tempfile.TemporaryDirectory(
                prefix="project-update-",
                dir=update_temp_parent,
            ) as update_temp_dir_name:
                update_temp_dir = Path(update_temp_dir_name)
                update_token = uuid.uuid4().hex
                core_zip_path = update_temp_dir / f"{update_token}-core.zip"
                self._set_update_stage(
                    progress_id,
                    "core",
                    "running",
                    "正在下载 AstrBot 项目代码...",
                    0,
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
                            0,
                            90,
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
                    with zipfile.ZipFile(core_zip_path, "r") as archive:
                        corrupt_member = archive.testzip()
                    if corrupt_member:
                        raise UpdateServiceError(f"更新包校验失败: {corrupt_member}")

                await self._run_threaded(_verify_update_packages)
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
                await self._run_threaded(
                    self.astrbot_updator.apply_update_package,
                    core_zip_path,
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
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error("更新依赖失败: %s", safe_error("", exc))
                    self._mark_update_error(
                        progress_id,
                        "依赖更新失败，未执行重启。",
                    )
                    return
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
                    await self.core_control.restart()
                    self._set_update_stage(
                        progress_id,
                        "restart",
                        "done",
                        "重启请求已提交。",
                        99,
                    )
                    message = "更新成功，AstrBot 将在 2 秒内全量重启以应用新的代码。"
                else:
                    message = "更新成功，AstrBot 将在下次启动时应用新的代码。"

                progress = self.update_progress.get(progress_id)
                if progress:
                    progress.update(
                        {
                            "status": "success",
                            "stage": "done",
                            "message": message,
                            "overall_percent": 100,
                        },
                    )
                logger.info(message)
        except asyncio.CancelledError:
            self._mark_update_cancelled(progress_id)
            logger.warning(
                "Update task was cancelled: %s",
                redact_sensitive_text(progress_id),
            )
            raise
        except Exception as exc:
            self._mark_update_error(progress_id, "更新失败，请查看服务端日志。")
            logger.error(
                "/api/update_project: %s",
                redact_sensitive_text(traceback.format_exc()),
            )
            logger.debug("Update task failed: %s", safe_error("", exc))

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
            logger.error(
                "/api/update_pip: %s",
                redact_sensitive_text(traceback.format_exc()),
            )
            raise UpdateServiceError("安装依赖失败。") from exc

    def _init_update_progress(self, progress_id: str, version: str) -> None:
        self._prune_update_progress(progress_id)
        self.update_progress.pop(progress_id, None)
        self.update_progress[progress_id] = {
            "id": progress_id,
            "status": "running",
            "stage": "preparing",
            "version": version or "latest",
            "message": "正在准备更新...",
            "overall_percent": 0,
            "stages": {
                "core": self._empty_stage("pending"),
            },
        }

    def _prune_update_progress(self, incoming_progress_id: str) -> None:
        """Keep terminal progress records bounded without dropping running updates."""

        if incoming_progress_id in self.update_progress:
            return
        while len(self.update_progress) >= self._max_progress_records:
            terminal_progress_id = next(
                (
                    progress_id
                    for progress_id, progress in self.update_progress.items()
                    if progress.get("status") != "running"
                ),
                None,
            )
            if terminal_progress_id is None:
                raise UpdateServiceError("更新任务过多，请稍后重试。")
            self.update_progress.pop(terminal_progress_id, None)

    async def _run_threaded(self, func: Callable[..., Any], *args: Any) -> Any:
        """Await executor work through cancellation so it cannot outlive its update task."""

        thread_task = asyncio.create_task(asyncio.to_thread(func, *args))
        try:
            return await asyncio.shield(thread_task)
        except asyncio.CancelledError:
            current_task = asyncio.current_task()
            while not thread_task.done():
                try:
                    await asyncio.shield(thread_task)
                except asyncio.CancelledError:
                    # Keep the executor work owned even when shutdown itself is
                    # cancelled again. Preserve the original cancellation below.
                    if current_task is not None:
                        current_task.uncancel()
            try:
                thread_task.result()
            except Exception as exc:
                logger.debug(
                    "Update thread failed during cancellation: %s", safe_error("", exc)
                )
            raise

    def _mark_update_stage_error(self, progress_id: str) -> None:
        progress = self.update_progress.get(progress_id)
        if not progress:
            return
        stage = str(progress.get("stage") or "preparing")
        stages = progress.setdefault("stages", {})
        stages.setdefault(stage, self._empty_stage())
        stages[stage]["status"] = "error"

    def _mark_update_error(self, progress_id: str, message: str) -> None:
        progress = self.update_progress.get(progress_id)
        if not progress:
            return
        self._mark_update_stage_error(progress_id)
        progress.update({"status": "error", "message": message})

    def _mark_update_cancelled(self, progress_id: str) -> None:
        self._mark_update_error(progress_id, "更新任务已取消。")

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
        except TypeError, ValueError:
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
