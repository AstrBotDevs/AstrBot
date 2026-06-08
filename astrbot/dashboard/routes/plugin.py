from __future__ import annotations

from typing import TYPE_CHECKING, cast

from astrbot.core import logger
from astrbot.dashboard.fastapi_compat import Response as CompatResponse
from astrbot.dashboard.fastapi_compat import g, make_response, request
from astrbot.dashboard.services.plugin_page_service import (
    PluginPageContentPayload,
    PluginPageService,
    PluginPageServiceError,
)
from astrbot.dashboard.services.plugin_service import (
    PluginService,
    PluginServiceError,
    PluginServiceWarning,
)

from .route import Response, Route, RouteContext

if TYPE_CHECKING:
    from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
    from astrbot.core.star.star_manager import PluginManager


class PluginRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        core_lifecycle: AstrBotCoreLifecycle,
        plugin_manager: PluginManager,
    ) -> None:
        super().__init__(context)
        self.routes = {
            "/plugin/get": ("GET", self.get_plugins),
            "/plugin/detail": ("GET", self.get_plugin_detail),
            "/plugin/check-compat": ("POST", self.check_plugin_compatibility),
            "/plugin/page/entry": ("GET", self.get_plugin_page_entry_config),
            "/plugin/install": ("POST", self.install_plugin),
            "/plugin/install-upload": ("POST", self.install_plugin_upload),
            "/plugin/update": ("POST", self.update_plugin),
            "/plugin/update-all": ("POST", self.update_all_plugins),
            "/plugin/uninstall": ("POST", self.uninstall_plugin),
            "/plugin/uninstall-failed": ("POST", self.uninstall_failed_plugin),
            "/plugin/market_list": ("GET", self.get_online_plugins),
            "/plugin/off": ("POST", self.off_plugin),
            "/plugin/on": ("POST", self.on_plugin),
            "/plugin/reload-failed": ("POST", self.reload_failed_plugins),
            "/plugin/reload": ("POST", self.reload_plugins),
            "/plugin/readme": ("GET", self.get_plugin_readme),
            "/plugin/changelog": ("GET", self.get_plugin_changelog),
            "/plugin/source/get": ("GET", self.get_custom_source),
            "/plugin/source/save": ("POST", self.save_custom_source),
            "/plugin/source/get-failed-plugins": ("GET", self.get_failed_plugins),
        }
        self.service = PluginService(core_lifecycle, plugin_manager)
        self.page_service = PluginPageService(
            plugin_manager,
            core_lifecycle=core_lifecycle,
        )
        self.register_routes()
        self.app.add_url_rule(
            "/api/plugin/page/content/<plugin_name>/<page_name>/",
            endpoint="plugin_page_content_entry",
            view_func=self.get_plugin_page_entry,
            methods=["GET"],
        )
        self.app.add_url_rule(
            "/api/plugin/page/content/<plugin_name>/<page_name>/<path:asset_path>",
            endpoint="plugin_page_content_asset",
            view_func=self.get_plugin_page_asset,
            methods=["GET"],
        )
        self.app.add_url_rule(
            "/api/plugin/page/bridge-sdk.js",
            endpoint="plugin_page_bridge_sdk",
            view_func=self.get_plugin_page_bridge_sdk,
            methods=["GET"],
        )

    @staticmethod
    def _service_ok(result):
        if isinstance(result, tuple):
            data, message = result
            return Response().ok(data, message).__dict__
        return Response().ok(result).__dict__

    async def _run_service(self, operation, *, log_label: str | None = None):
        try:
            result = operation() if callable(operation) else operation
            while hasattr(result, "__await__"):
                result = await result
            return self._service_ok(result)
        except PluginServiceWarning as exc:
            return {
                "status": "warning",
                "message": str(exc),
                "data": exc.data,
            }
        except PluginServiceError as exc:
            return Response().error(str(exc)).__dict__
        except Exception as exc:
            if log_label:
                logger.error("%s: %s", log_label, exc, exc_info=True)
            else:
                logger.error(str(exc), exc_info=True)
            return Response().error(str(exc)).__dict__

    @staticmethod
    async def _json_body() -> dict:
        data = await request.get_json()
        return data if isinstance(data, dict) else {}

    async def _run_json(self, operation, *, log_label: str | None = None):
        async def invoke():
            data = await self._json_body()
            return operation(data)

        return await self._run_service(invoke, log_label=log_label)

    async def get_plugin_page_entry(self, plugin_name: str, page_name: str):
        return await self._serve_plugin_page_content(plugin_name, page_name, "")

    async def get_plugin_page_asset(
        self,
        plugin_name: str,
        page_name: str,
        asset_path: str,
    ):
        return await self._serve_plugin_page_content(
            plugin_name,
            page_name,
            asset_path,
        )

    async def get_plugin_page_bridge_sdk(self):
        try:
            payload = await self.page_service.serve_bridge_sdk(
                asset_token=request.args.get("asset_token", "").strip(),
                locale=self._get_request_locale(),
                theme=self._get_request_theme(),
            )
        except PluginPageServiceError as exc:
            return await self._plugin_page_error_response(
                exc.status_code,
                str(exc),
            )
        return await self._plugin_page_payload_response(payload)

    @staticmethod
    def _get_request_locale(default: str = "zh-CN") -> str:
        raw_locale = request.headers.get("Accept-Language", "").strip()
        locale = raw_locale.split(",", 1)[0].split(";", 1)[0].strip()
        if not locale or len(locale) > 32:
            return default
        return locale

    @staticmethod
    def _get_request_theme() -> str | None:
        theme = request.args.get("theme", "").strip()
        return theme if theme in ("dark", "light") else None

    @staticmethod
    async def _plugin_page_error_response(status_code: int, message: str):
        response = await make_response(message, status_code)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Type"] = "text/plain; charset=utf-8"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @staticmethod
    def _apply_plugin_page_security_headers(response: CompatResponse) -> CompatResponse:
        for name, value in PluginPageService.build_security_headers().items():
            response.headers[name] = value
        return response

    async def _plugin_page_payload_response(
        self,
        payload: PluginPageContentPayload,
    ):
        response = cast(
            CompatResponse,
            await make_response(
                payload.content,
                {"Content-Type": payload.content_type},
            ),
        )
        return self._apply_plugin_page_security_headers(response)

    async def _serve_plugin_page_content(
        self,
        plugin_name: str,
        page_name: str,
        asset_path: str,
    ):
        try:
            payload = await self.page_service.serve_page_content(
                plugin_name=plugin_name,
                page_name=page_name,
                asset_path=asset_path,
                asset_token=request.args.get("asset_token", "").strip(),
                username=getattr(g, "username", None),
                locale=self._get_request_locale(),
                theme=self._get_request_theme(),
            )
        except PluginPageServiceError as exc:
            return await self._plugin_page_error_response(
                exc.status_code,
                str(exc),
            )
        return await self._plugin_page_payload_response(payload)

    async def check_plugin_compatibility(self):
        return await self._run_json(
            self.service.check_plugin_compatibility,
            log_label="/api/plugin/check-compat",
        )

    async def get_plugin_page_entry_config(self):
        try:
            return (
                Response()
                .ok(
                    await self.page_service.get_plugin_page_entry_config(
                        plugin_name=request.args.get("name"),
                        page_name=request.args.get("page"),
                        username=getattr(g, "username", None),
                        locale=self._get_request_locale(),
                    )
                )
                .__dict__
            )
        except PluginPageServiceError as exc:
            return Response().error(str(exc)).__dict__

    async def reload_failed_plugins(self):
        return await self._run_json(
            self.service.reload_failed_plugin,
            log_label="/api/plugin/reload-failed",
        )

    async def reload_plugins(self):
        return await self._run_json(
            self.service.reload_plugin,
            log_label="/api/plugin/reload",
        )

    async def get_online_plugins(self):
        return await self._run_service(
            self.service.get_online_plugins_from_legacy_query(
                custom_registry=request.args.get("custom_registry"),
                force_refresh=request.args.get("force_refresh", "false"),
            ),
            log_label="/api/plugin/market_list",
        )

    async def get_plugins(self):
        return await self._run_service(
            self.service.list_plugins_from_legacy_query(
                plugin_name=request.args.get("name"),
                logo_token_resolver=self.service.get_plugin_logo_token,
                installed_at_resolver=self.service.get_plugin_installed_at,
                discover_pages=self.page_service.discover_plugin_pages,
            ),
            log_label="/api/plugin/get",
        )

    async def get_plugin_detail(self):
        return await self._run_service(
            self.service.get_plugin_detail_from_legacy_query(
                plugin_name=request.args.get("name"),
                logo_token_resolver=self.service.get_plugin_logo_token,
                installed_at_resolver=self.service.get_plugin_installed_at,
                serialize_pages=self.page_service.serialize_plugin_pages,
            ),
            log_label="/api/plugin/detail",
        )

    async def get_failed_plugins(self):
        return await self._run_service(self.service.get_failed_plugins)

    async def install_plugin(self):
        return await self._run_json(
            self.service.install_plugin,
            log_label="/api/plugin/install",
        )

    async def install_plugin_upload(self):
        async def _operation():
            files = await request.files
            file = files["file"]
            form_data = await request.form
            return await self.service.install_plugin_upload_from_legacy_form(
                upload_file=file,
                ignore_version_check=form_data.get("ignore_version_check", "false"),
            )

        return await self._run_service(
            _operation,
            log_label="/api/plugin/install-upload",
        )

    async def uninstall_plugin(self):
        return await self._run_json(
            self.service.uninstall_plugin,
            log_label="/api/plugin/uninstall",
        )

    async def uninstall_failed_plugin(self):
        return await self._run_json(
            self.service.uninstall_failed_plugin,
            log_label="/api/plugin/uninstall-failed",
        )

    async def update_plugin(self):
        return await self._run_json(
            self.service.update_plugin,
            log_label="/api/plugin/update",
        )

    async def update_all_plugins(self):
        return await self._run_json(
            self.service.update_all_plugins,
            log_label="/api/plugin/update-all",
        )

    async def off_plugin(self):
        return await self._run_json(
            lambda data: self.service.set_plugin_enabled(data, enabled=False),
            log_label="/api/plugin/off",
        )

    async def on_plugin(self):
        return await self._run_json(
            lambda data: self.service.set_plugin_enabled(data, enabled=True),
            log_label="/api/plugin/on",
        )

    async def get_plugin_readme(self):
        return await self._run_service(
            lambda: self.service.get_plugin_readme_from_legacy_query(
                request.args.get("name")
            ),
            log_label="/api/plugin/readme",
        )

    async def get_plugin_changelog(self):
        """获取插件更新日志

        读取插件目录下的 CHANGELOG.md 文件内容。
        """
        return await self._run_service(
            lambda: self.service.get_plugin_changelog_from_legacy_query(
                request.args.get("name")
            ),
            log_label="/api/plugin/changelog",
        )

    async def get_custom_source(self):
        """获取自定义插件源"""
        return await self._run_service(self.service.get_custom_sources)

    async def save_custom_source(self):
        """保存自定义插件源"""
        return await self._run_json(
            self.service.save_custom_sources,
            log_label="/api/plugin/source/save",
        )
