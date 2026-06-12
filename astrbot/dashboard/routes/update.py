"""Dashboard 更新 / 公告代理路由.

提供 AstrBot Core 与自建更新服务器之间的桥接：
  - /api/update/*         已有：版本检查 / 下载更新
  - /api/system/announcement 新增：代理更新服务器的 /announcement

设计要点：
  - 公告源 = 内网/官方更新服务器，无需 dashboard 直连。
  - 通过 update_config.json 中 core_update.release_api_url 复用 base URL，
    自动剥掉末级路径再拼 "/announcement"。
  - 默认配置连官方 API（无 /announcement）时返回 404，前端静默隐藏公告条。
"""
import asyncio
import traceback
import uuid
from urllib.parse import urlparse

import aiohttp
from quart import request

from astrbot.core import DEMO_MODE, logger, pip_installer
from astrbot.core.config.default import VERSION
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db.migration.helper import check_migration_needed_v4, do_migration_v4
from astrbot.core.updator import AstrBotUpdator
from astrbot.core.utils.io import download_dashboard, get_dashboard_version

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
            "/system/announcement": ("GET", self.get_announcement),
        }
        self.astrbot_updator = astrbot_updator
        self.core_lifecycle = core_lifecycle
        self.update_progress: dict[str, dict] = {}
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

    @staticmethod
    def _resolve_announcement_upstream_url() -> str | None:
        """从 update_config 复用 base URL 拼接出公告上游地址.

        复用策略: 取 core_update.release_api_url (例如 "http://server:8080/releases"),
        剥掉末级路径只保留 scheme://netloc, 然后拼接 "/announcement".
        复用而非新加配置, 避免 update_config.json 字段膨胀.

        Returns:
            拼接后的上游完整 URL；若 URL 不合法返回 None.
        """
        try:
            from astrbot.core.config.update_config import UpdateConfig

            base_full = UpdateConfig().get_core_release_api_url()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"读取 update_config 失败，无法解析公告上游: {e!s}")
            return None

        parsed = urlparse(base_full)
        if not parsed.scheme or not parsed.netloc:
            return None
        return f"{parsed.scheme}://{parsed.netloc}/announcement"

    async def get_announcement(self):
        """代理更新服务器的 /announcement 接口.

        行为:
          - 上游 200 → 原样返回 JSON.
          - 上游 404 → 返回 404 + {"detail": "no_announcement"} (无公告/已禁用).
          - 上游 5xx 或网络错误 → 返回 502 (后端作为代理出错).
          - base URL 解析失败 → 返回 503 (未配置/配置错误).
        """
        upstream_url = self._resolve_announcement_upstream_url()
        if not upstream_url:
            return (
                Response()
                .error("更新服务器 base URL 未配置或格式不合法，无法获取公告。")
                .__dict__
            ), 503

        try:
            async with (
                aiohttp.ClientSession() as session,
                session.get(
                    upstream_url,
                    timeout=aiohttp.ClientTimeout(total=5.0),
                    headers={"Accept": "application/json"},
                ) as response,
            ):
                # 透传状态码语义: 404 表示"无公告", 前端据此隐藏公告条.
                if response.status == 404:
                    return (
                        Response()
                        .error("当前没有公告")
                        .__dict__
                    ), 404
                if response.status >= 400:
                    detail = await response.text()
                    logger.warning(
                        f"更新服务器公告接口异常: {response.status} {detail[:200]}"
                    )
                    return (
                        Response()
                        .error(f"更新服务器返回错误: HTTP {response.status}")
                        .__dict__
                    ), 502
                payload = await response.json(content_type=None)
        except aiohttp.ClientError as e:
            logger.warning(f"连接更新服务器失败 ({upstream_url}): {e!s}")
            return (
                Response()
                .error(f"无法连接更新服务器: {e!s}")
                .__dict__
            ), 502
        except (ValueError, asyncio.TimeoutError) as e:
            logger.warning(f"获取公告响应解析失败: {e!s}")
            return (
                Response()
                .error(f"获取公告失败: {e!s}")
                .__dict__
            ), 502

        return Response().ok(payload).__dict__

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

        self._init_update_progress(progress_id, version)
        try:
            self._set_update_stage(
                progress_id,
                "dashboard",
                "running",
                "正在下载 WebUI...",
                0,
            )
            await download_dashboard(
                latest=latest,
                version=version,
                proxy=proxy,
                progress_callback=self._make_progress_callback(
                    progress_id,
                    "dashboard",
                    0,
                    45,
                ),
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
            await self.astrbot_updator.update(
                latest=latest,
                version=version,
                proxy=proxy,
                progress_callback=self._make_progress_callback(
                    progress_id,
                    "core",
                    45,
                    45,
                ),
            )
            self._set_update_stage(
                progress_id,
                "core",
                "done",
                "项目代码下载完成。",
                90,
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
                ret = (
                    Response()
                    .ok(None, "更新成功，AstrBot 将在 2 秒内全量重启以应用新的代码。")
                    .__dict__
                )
                return ret, 200, CLEAR_SITE_DATA_HEADERS
            self.update_progress[progress_id].update(
                {
                    "status": "success",
                    "stage": "done",
                    "message": "更新成功，AstrBot 将在下次启动时应用新的代码。",
                    "overall_percent": 100,
                },
            )
            ret = (
                Response()
                .ok(None, "更新成功，AstrBot 将在下次启动时应用新的代码。")
                .__dict__
            )
            return ret, 200, CLEAR_SITE_DATA_HEADERS
        except Exception as e:
            self.update_progress[progress_id].update(
                {
                    "status": "error",
                    "message": e.__str__(),
                },
            )
            logger.error(f"/api/update_project: {traceback.format_exc()}")
            return Response().error(e.__str__()).__dict__

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
