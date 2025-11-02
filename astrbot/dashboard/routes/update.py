import traceback
from typing import Any

from fastapi import Query
from pydantic import BaseModel

from astrbot.core import DEMO_MODE, logger, pip_installer
from astrbot.core.config.default import VERSION
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db.migration.helper import check_migration_needed_v4, do_migration_v4
from astrbot.core.updator import AstrBotUpdator
from astrbot.core.utils.io import download_dashboard, get_dashboard_version

from .route import Response, Route, RouteContext

CLEAR_SITE_DATA_HEADERS = {"Clear-Site-Data": '"cache"'}


class MigrationRequest(BaseModel):
    platform_id_map: dict = {}


class UpdateProjectRequest(BaseModel):
    version: str = ""
    reboot: bool = True


class DashboardUpdateRequest(BaseModel):
    version: str = ""


class PipInstallRequest(BaseModel):
    package: str
    mirror: str | None = None


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
            "/update/releases": ("GET", self.get_releases),
            "/update/do": ("POST", self.update_project),
            "/update/dashboard": ("POST", self.update_dashboard),
            "/update/pip-install": ("POST", self.install_pip_package),
            "/update/migration": ("POST", self.do_migration),
        }
        self.astrbot_updator = astrbot_updator
        self.core_lifecycle = core_lifecycle
        self.register_routes()

    async def do_migration(self, migration_data: MigrationRequest):
        need_migration = await check_migration_needed_v4(self.core_lifecycle.db)
        if not need_migration:
            return Response.ok(None, "不需要进行迁移。")
        try:
            pim = migration_data.platform_id_map
            await do_migration_v4(
                self.core_lifecycle.db,
                pim,
                self.core_lifecycle.astrbot_config,
            )
            return Response.ok(None, "迁移成功。")
        except Exception as e:
            logger.error(f"迁移失败: {traceback.format_exc()}")
            return Response.error(f"迁移失败: {e!s}")

    async def check_update(
        self, type_: str | None = Query(default=None, alias="type")
    ):
        try:
            dv = await get_dashboard_version()
            if type_ == "dashboard":
                return Response.ok({"has_new_version": dv != f"v{VERSION}", "current_version": dv})
            ret = await self.astrbot_updator.check_update(None, None, False)
            return Response(
                status="ok",
                message=str(ret) if ret is not None else "已经是最新版本了。",
                data={
                    "version": f"v{VERSION}",
                    "has_new_version": ret is not None,
                    "dashboard_version": dv,
                    "dashboard_has_new_version": bool(dv and dv != f"v{VERSION}"),
                },
            )
        except Exception as e:
            logger.warning(f"检查更新失败: {e!s} (不影响除项目更新外的正常使用)")
            return Response.error(e.__str__())

    async def get_releases(self):
        try:
            ret = await self.astrbot_updator.get_releases()
            return Response.ok(ret)
        except Exception as e:
            logger.error(f"/api/update/releases: {traceback.format_exc()}")
            return Response.error(e.__str__())

    async def update_project(self, update_data: UpdateProjectRequest):
        version = update_data.version
        reboot = update_data.reboot
        if version == "" or version == "latest":
            latest = True
            version = ""
        else:
            latest = False

        proxy_value: Any = self.config.get("http_proxy", "")
        proxy: str = ""
        if proxy_value and isinstance(proxy_value, str):
            proxy = proxy_value.removesuffix("/")

        try:
            await self.astrbot_updator.update(
                latest=latest,
                version=version,
                proxy=proxy,
            )

            try:
                await download_dashboard(latest=latest, version=version, proxy=proxy)
            except Exception as e:
                logger.error(f"下载管理面板文件失败: {e}。")

            # pip 更新依赖
            logger.info("更新依赖中...")
            try:
                await pip_installer.install(requirements_path="requirements.txt")
            except Exception as e:
                logger.error(f"更新依赖失败: {e}")

            if reboot:
                await self.core_lifecycle.restart()
                ret = Response.ok(None, "更新成功，AstrBot 将在 2 秒内全量重启以应用新的代码。"))
                return ret, 200, CLEAR_SITE_DATA_HEADERS
            ret = Response.ok(None, "更新成功，AstrBot 将在下次启动时应用新的代码。"))
            return ret, 200, CLEAR_SITE_DATA_HEADERS
        except Exception as e:
            logger.error(f"/api/update_project: {traceback.format_exc()}")
            return Response.error(e.__str__())

    async def update_dashboard(self):
        from fastapi.responses import JSONResponse

        try:
            try:
                await download_dashboard(version=f"v{VERSION}", latest=False)
            except Exception as e:
                logger.error(f"下载管理面板文件失败: {e}。")
                return Response.error(f"下载管理面板文件失败: {e}")
            return JSONResponse(
                content=Response()
                .ok(None, "更新成功。刷新页面即可应用新版本面板。")
                ,
                headers=CLEAR_SITE_DATA_HEADERS,
            )
        except Exception as e:
            logger.error(f"/api/update_dashboard: {traceback.format_exc()}")
            return Response.error(e.__str__())

    async def install_pip_package(self, pip_data: PipInstallRequest):
        if DEMO_MODE:
            return Response.error("You are not permitted to do this operation in demo mode")

        package = pip_data.package
        mirror = pip_data.mirror
        if not package:
            return Response.error("缺少参数 package 或不合法。")
        try:
            await pip_installer.install(package, mirror=mirror)
            return Response.ok(None, "安装成功。")
        except Exception as e:
            logger.error(f"/api/update_pip: {traceback.format_exc()}")
            return Response.error(e.__str__())
