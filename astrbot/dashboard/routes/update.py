import asyncio
import traceback
import uuid
import zipfile
from pathlib import Path

from quart import request

from astrbot.core import DEMO_MODE, logger, pip_installer
from astrbot.core.config.default import VERSION
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db.migration.helper import check_migration_needed_v4, do_migration_v4
from astrbot.core.updator import AstrBotUpdator
from astrbot.core.utils.astrbot_path import (
    get_astrbot_data_path,
    get_astrbot_system_tmp_path,
)
from astrbot.core.utils.io import (
    download_dashboard,
    extract_dashboard,
    get_dashboard_version,
)

from .route import Response, Route, RouteContext

CLEAR_SITE_DATA_HEADERS = {"Clear-Site-Data": '"cache"'}


class UpdateRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        astrbot_updator: AstrBotUpdator,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.routes = {
            "/update/check": ("GET", self.check_update),
            "/update/progress": ("GET", self.get_update_progress),
            "/update/releases": ("GET", self.get_releases),
            "/update/do": ("POST", self.update_project),
            "/update/dashboard": ("POST", self.update_dashboard),
            "/update/pip-install": ("POST", self.install_pip_package),
            "/update/migration": ("POST", self.do_migration),
        }
        self.astrbot_updator = astrbot_updator
        self.core_lifecycle = core_lifecycle
        self.update_progress: dict[str, dict] = {}
        self._update_tasks: dict[str, asyncio.Task] = {}
        self.register_routes()

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

    async def get_update_progress(self):
        progress_id = request.args.get("id", "")
        if not progress_id:
            return Response().error("缺少参数 id。").__dict__
        progress = self.update_progress.get(progress_id)
        if not progress:
            return (
                Response()
                .ok(
                    {"id": progress_id, "status": "idle"},
                    "没有正在进行的更新。",
                )
                .__dict__
            )
        return Response().ok(progress).__dict__

    async def do_migration(self):
        need_migration = await check_migration_needed_v4(self.core_lifecycle.db)
        if not need_migration:
            return Response().ok(None, "不需要进行迁移。").__dict__
        try:
            data = await request.json
            pim = data.get("platform_id_map", {})
            await do_migration_v4(
                self.core_lifecycle.db,
                pim,
                self.core_lifecycle.astrbot_config,
            )
            return Response().ok(None, "迁移成功。").__dict__
        except Exception as e:
            logger.error(f"迁移失败: {traceback.format_exc()}")
            return Response().error(f"迁移失败: {e!s}").__dict__

    async def check_update(self):
        type_ = request.args.get("type", None)

        try:
            dv = await get_dashboard_version()
            if type_ == "dashboard":
                return (
                    Response()
                    .ok({"has_new_version": dv != f"v{VERSION}", "current_version": dv})
                    .__dict__
                )
            ret = await self.astrbot_updator.check_update(None, None, False)
            return Response(
                status="success",
                message=str(ret) if ret is not None else "已经是最新版本了。",
                data={
                    "version": f"v{VERSION}",
                    "has_new_version": ret is not None,
                    "dashboard_version": dv,
                    "dashboard_has_new_version": bool(dv and dv != f"v{VERSION}"),
                },
            ).__dict__
        except Exception as e:
            logger.warning(f"检查更新失败: {e!s} (不影响除项目更新外的正常使用)")
            return Response().error(e.__str__()).__dict__

    async def get_releases(self):
        try:
            ret = await self.astrbot_updator.get_releases()
            return Response().ok(ret).__dict__
        except Exception as e:
            logger.error(f"/api/update/releases: {traceback.format_exc()}")
            return Response().error(e.__str__()).__dict__

    async def update_project(self):
        data = await request.json
        version = data.get("version", "")
        reboot = data.get("reboot", True)
        progress_id = data.get("progress_id") or uuid.uuid4().hex
        if version == "" or version == "latest":
            latest = True
            version = ""
        else:
            latest = False

        proxy: str = data.get("proxy", None)
        if proxy:
            proxy = proxy.removesuffix("/")

        existing_task = self._update_tasks.get(progress_id)
        if existing_task and not existing_task.done():
            return (
                Response()
                .ok(
                    {"id": progress_id, "status": "running"},
                    "更新任务正在进行中。",
                )
                .__dict__,
                200,
                CLEAR_SITE_DATA_HEADERS,
            )

        self._init_update_progress(progress_id, version)
        task = asyncio.create_task(
            self._run_update_project(progress_id, version, latest, reboot, proxy),
        )
        self._update_tasks[progress_id] = task
        task.add_done_callback(lambda _task: self._update_tasks.pop(progress_id, None))
        return (
            Response()
            .ok(
                {"id": progress_id, "status": "running"},
                "更新任务已开始。",
            )
            .__dict__,
            200,
            CLEAR_SITE_DATA_HEADERS,
        )

    async def _run_update_project(
        self,
        progress_id: str,
        version: str,
        latest: bool,
        reboot: bool,
        proxy: str | None,
    ) -> None:
        """Run an update task outside the request lifecycle.

        Args:
            progress_id: Progress record id reported to the frontend.
            version: Target version without the latest sentinel.
            latest: Whether to install the latest release.
            reboot: Whether to restart AstrBot after applying files.
            proxy: Optional GitHub proxy URL.

        Returns:
            None.
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
            await download_dashboard(
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
            for zip_path in (dashboard_zip_path, core_zip_path):
                with zipfile.ZipFile(zip_path, "r") as archive:
                    corrupt_member = archive.testzip()
                if corrupt_member:
                    raise RuntimeError(f"更新包校验失败: {corrupt_member}")
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
            await asyncio.to_thread(
                extract_dashboard,
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

            # pip 更新依赖
            self._set_update_stage(
                progress_id,
                "dependencies",
                "running",
                "正在更新依赖...",
                92,
            )
            logger.info("更新依赖中...")
            try:
                await pip_installer.install(requirements_path="requirements.txt")
            except Exception as e:
                logger.error(f"更新依赖失败: {e}")
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
                self.update_progress[progress_id].update(
                    {
                        "status": "success",
                        "stage": "done",
                        "message": "更新成功，AstrBot 将在 2 秒内全量重启以应用新的代码。",
                        "overall_percent": 100,
                    },
                )
                return
            self.update_progress[progress_id].update(
                {
                    "status": "success",
                    "stage": "done",
                    "message": "更新成功，AstrBot 将在下次启动时应用新的代码。",
                    "overall_percent": 100,
                },
            )
        except asyncio.CancelledError:
            self.update_progress[progress_id].update(
                {
                    "status": "error",
                    "message": "更新任务已取消。",
                },
            )
            logger.warning(f"Update task was cancelled: {progress_id}")
        except Exception as e:
            self.update_progress[progress_id].update(
                {
                    "status": "error",
                    "message": e.__str__(),
                },
            )
            logger.error(f"/api/update_project: {traceback.format_exc()}")
        finally:
            for zip_path in (dashboard_zip_path, core_zip_path):
                try:
                    if zip_path.exists():
                        zip_path.unlink()
                except Exception as cleanup_exc:
                    logger.warning(f"清理更新临时文件失败: {zip_path}, {cleanup_exc}")

    async def update_dashboard(self):
        try:
            try:
                await download_dashboard(version=f"v{VERSION}", latest=False)
            except Exception as e:
                logger.error(f"下载管理面板文件失败: {e}。")
                return Response().error(f"下载管理面板文件失败: {e}").__dict__
            ret = Response().ok(None, "更新成功。刷新页面即可应用新版本面板。").__dict__
            return ret, 200, CLEAR_SITE_DATA_HEADERS
        except Exception as e:
            logger.error(f"/api/update_dashboard: {traceback.format_exc()}")
            return Response().error(e.__str__()).__dict__

    async def install_pip_package(self):
        if DEMO_MODE:
            return (
                Response()
                .error("You are not permitted to do this operation in demo mode")
                .__dict__
            )

        data = await request.json
        package = data.get("package", "")
        mirror = data.get("mirror", None)
        if not package:
            return Response().error("缺少参数 package 或不合法。").__dict__
        try:
            await pip_installer.install(package, mirror=mirror)
            return Response().ok(None, "安装成功。").__dict__
        except Exception as e:
            logger.error(f"/api/update_pip: {traceback.format_exc()}")
            return Response().error(e.__str__()).__dict__
