import traceback
from inspect import isawaitable

from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.dashboard.fastapi_compat import jsonify, make_response, request
from astrbot.dashboard.services.config_service import (
    BotConfigService,
    ConfigDisplayService,
    ConfigFileService,
    ConfigProfileService,
    ConfigRoutingService,
    ProviderConfigService,
)
from astrbot.dashboard.v1.responses import ApiError

from .route import Response, Route, RouteContext

TWO_FACTOR_CODE_HEADER = "X-2FA-Code"


class ConfigRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.config_profile_service = ConfigProfileService(
            core_lifecycle,
            core_lifecycle.db,
        )
        self.config_display_service = ConfigDisplayService(core_lifecycle)
        self.config_file_service = ConfigFileService(core_lifecycle)
        self.config_routing_service = ConfigRoutingService(core_lifecycle)
        self.bot_config_service = BotConfigService(core_lifecycle)
        self.provider_config_service = ProviderConfigService(core_lifecycle)
        self.routes = {
            "/config/abconf/new": ("POST", self.create_abconf),
            "/config/abconf": ("GET", self.get_abconf),
            "/config/abconfs": ("GET", self.get_abconf_list),
            "/config/abconf/delete": ("POST", self.delete_abconf),
            "/config/abconf/update": ("POST", self.update_abconf),
            "/config/umo_abconf_routes": ("GET", self.get_uc_table),
            "/config/umo_abconf_route/update_all": ("POST", self.update_ucr_all),
            "/config/umo_abconf_route/update": ("POST", self.update_ucr),
            "/config/umo_abconf_route/delete": ("POST", self.delete_ucr),
            "/config/get": ("GET", self.get_configs),
            "/config/default": ("GET", self.get_default_config),
            "/config/astrbot/update": ("POST", self.post_astrbot_configs),
            "/config/plugin/update": ("POST", self.post_plugin_configs),
            "/config/file/upload": ("POST", self.upload_config_file),
            "/config/file/delete": ("POST", self.delete_config_file),
            "/config/file/get": ("GET", self.get_config_file_list),
            "/config/platform/new": ("POST", self.post_new_platform),
            "/config/platform/update": ("POST", self.post_update_platform),
            "/config/platform/delete": ("POST", self.post_delete_platform),
            "/config/platform/list": ("GET", self.get_platform_list),
            "/config/provider/new": ("POST", self.post_new_provider),
            "/config/provider/update": ("POST", self.post_update_provider),
            "/config/provider/delete": ("POST", self.post_delete_provider),
            "/config/provider/template": ("GET", self.get_provider_template),
            "/config/provider/check_one": ("GET", self.check_one_provider_status),
            "/config/provider/list": ("GET", self.get_provider_config_list),
            "/config/provider/model_list": ("GET", self.get_provider_model_list),
            "/config/provider/get_embedding_dim": ("POST", self.get_embedding_dim),
            "/config/provider_sources/models": (
                "GET",
                self.get_provider_source_models,
            ),
            "/config/provider_sources/update": (
                "POST",
                self.update_provider_source,
            ),
            "/config/provider_sources/delete": (
                "POST",
                self.delete_provider_source,
            ),
        }
        self.register_routes()

    @staticmethod
    def _ok(data=None, message: str | None = None):
        return Response().ok(data, message).__dict__

    @staticmethod
    def _error(message: str):
        return Response().error(message).__dict__

    async def _json_body(self):
        return await request.json

    async def _run(
        self,
        operation,
        *,
        message: str | None = None,
        result_as_message: bool = False,
        error_prefix: str | None = None,
        trace: bool = True,
    ):
        try:
            result = operation()
            if isawaitable(result):
                result = await result
            if result_as_message:
                return self._ok(message=str(result) if result is not None else message)
            return self._ok(result, message)
        except ValueError as e:
            return self._error(str(e))
        except Exception as e:
            if trace:
                logger.error(traceback.format_exc())
            error_message = f"{error_prefix}: {e!s}" if error_prefix else str(e)
            return self._error(error_message)

    async def _run_json(self, operation, **kwargs):
        payload = await self._json_body()
        return await self._run(lambda: operation(payload), **kwargs)

    async def delete_provider_source(self):
        """删除 provider_source，并更新关联的 providers"""
        return await self._run_json(
            self.provider_config_service.delete_provider_source_from_legacy_payload,
            result_as_message=True,
        )

    async def update_provider_source(self):
        """更新或新增 provider_source，并重载关联的 providers"""
        return await self._run_json(
            self.provider_config_service.upsert_provider_source_from_legacy_payload,
            result_as_message=True,
        )

    async def get_provider_template(self):
        return self._ok(data=self.provider_config_service.get_provider_schema())

    async def get_uc_table(self):
        """获取 UMOP 配置路由表"""
        return self._ok(self.config_routing_service.list_routes())

    async def update_ucr_all(self):
        """更新 UMOP 配置路由表的全部内容"""
        return await self._run_json(
            self.config_routing_service.replace_routes_from_legacy_payload,
            result_as_message=True,
            error_prefix="更新路由表失败",
        )

    async def update_ucr(self):
        """更新 UMOP 配置路由表"""
        return await self._run_json(
            self.config_routing_service.upsert_route_from_legacy_payload,
            result_as_message=True,
            error_prefix="更新路由表失败",
        )

    async def delete_ucr(self):
        """删除 UMOP 配置路由表中的一项"""
        return await self._run_json(
            self.config_routing_service.delete_route_from_legacy_payload,
            result_as_message=True,
            error_prefix="删除路由表项失败",
        )

    async def get_default_config(self):
        """获取默认配置文件"""
        return self._ok(self.config_profile_service.get_profile_schema())

    async def get_abconf_list(self):
        """获取所有 AstrBot 配置文件的列表"""
        return self._ok(self.config_profile_service.list_profiles())

    async def create_abconf(self):
        """创建新的 AstrBot 配置文件"""
        return await self._run_json(
            self.config_profile_service.create_profile_from_legacy_payload,
            message="创建成功",
        )

    async def get_abconf(self):
        """获取指定 AstrBot 配置文件"""
        return await self._run(
            lambda: self.config_profile_service.get_profile_from_legacy_args(
                request.args
            )
        )

    async def delete_abconf(self):
        """删除指定 AstrBot 配置文件"""
        return await self._run_json(
            self.config_profile_service.delete_profile_from_legacy_payload,
            result_as_message=True,
            error_prefix="删除配置文件失败",
        )

    async def update_abconf(self):
        """更新指定 AstrBot 配置文件信息"""
        return await self._run_json(
            self.config_profile_service.rename_profile_from_legacy_payload,
            result_as_message=True,
            error_prefix="更新配置文件失败",
        )

    async def check_one_provider_status(self):
        """API: check a single LLM Provider's status by id"""
        return await self._run(
            lambda: self.provider_config_service.test_provider_from_legacy_args(
                request.args
            ),
            error_prefix="Critical error checking provider",
        )

    async def get_configs(self):
        return await self._run(
            lambda: self.config_display_service.get_configs_from_legacy_args(
                request.args
            )
        )

    async def get_provider_config_list(self):
        return await self._run(
            lambda: self.provider_config_service.list_providers_from_legacy_args(
                request.args
            )
        )

    async def get_provider_model_list(self):
        """获取指定提供商的模型列表"""
        return await self._run(
            lambda: self.provider_config_service.list_provider_models_from_legacy_args(
                request.args
            )
        )

    async def get_embedding_dim(self):
        """获取嵌入模型的维度"""
        return await self._run_json(
            self.provider_config_service.get_embedding_dimension_from_legacy_payload,
            error_prefix="获取嵌入维度失败",
        )

    async def get_provider_source_models(self):
        """获取指定 provider_source 支持的模型列表

        本质上会临时初始化一个 Provider 实例，调用 get_models() 获取模型列表，然后销毁实例
        """
        return await self._run(
            lambda: self.provider_config_service.list_provider_source_models_for_legacy(
                request.args.get("source_id")
            ),
            error_prefix="获取模型列表失败",
        )

    async def get_platform_list(self):
        """获取所有平台的列表"""
        return self._ok(self.bot_config_service.list_platforms_for_legacy())

    async def post_astrbot_configs(self):
        data = await request.json

        try:
            message = (
                await self.config_profile_service.update_profile_from_legacy_payload(
                    data,
                    two_factor_code=request.headers.get(TWO_FACTOR_CODE_HEADER),
                )
            )
            return Response().ok(None, message or "保存成功~").__dict__
        except ApiError as e:
            if e.status_code == 401 and e.data == {"totp_required": True}:
                return await self._config_2fa_required_response()
            return Response().error(e.message).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__

    async def _config_2fa_required_response(self):
        response = await make_response(
            jsonify(
                {
                    "status": "error",
                    "data": {
                        "totp_required": True,
                    },
                }
            )
        )
        response.status_code = 401
        return response

    async def post_plugin_configs(self):
        return await self._run_json(
            lambda payload: (
                self.config_file_service.save_plugin_configs_from_legacy_payload(
                    payload,
                    plugin_name=request.args.get("plugin_name", "unknown"),
                )
            ),
            result_as_message=True,
            trace=False,
        )

    async def upload_config_file(self):
        """上传文件到插件数据目录（用于某个 file 类型配置项）。"""
        files = await request.files
        return await self._run(
            lambda: self.config_file_service.upload_config_file_from_legacy_request(
                request.args,
                files,
            )
        )

    async def delete_config_file(self):
        """删除插件数据目录中的文件。"""
        payload = await request.get_json()
        return await self._run(
            lambda: self.config_file_service.delete_config_file_from_legacy_request(
                request.args,
                payload,
            ),
            result_as_message=True,
            trace=False,
        )

    async def get_config_file_list(self):
        """获取配置项对应目录下的文件列表。"""
        return await self._run(
            lambda: self.config_file_service.list_config_files_from_legacy_args(
                request.args
            ),
            trace=False,
        )

    async def post_new_platform(self):
        return await self._run_json(
            self.bot_config_service.create_bot_from_legacy_payload,
            result_as_message=True,
            trace=False,
        )

    async def post_new_provider(self):
        return await self._run_json(
            self.provider_config_service.create_provider_from_legacy_payload,
            result_as_message=True,
            trace=False,
        )

    async def post_update_platform(self):
        return await self._run_json(
            self.bot_config_service.update_bot_from_legacy_payload,
            result_as_message=True,
            trace=False,
        )

    async def post_update_provider(self):
        return await self._run_json(
            self.provider_config_service.update_provider_from_legacy_payload,
            result_as_message=True,
            trace=False,
        )

    async def post_delete_platform(self):
        return await self._run_json(
            self.bot_config_service.delete_bot_from_legacy_payload,
            result_as_message=True,
            trace=False,
        )

    async def post_delete_provider(self):
        return await self._run_json(
            self.provider_config_service.delete_provider_from_legacy_payload,
            result_as_message=True,
            trace=False,
        )
