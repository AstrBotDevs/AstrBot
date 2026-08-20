import copy
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from astrbot import logger
from astrbot.core.agent.mcp_client import validate_mcp_server_config
from astrbot.core.core_runtime import CoreControl, CoreRuntime
from astrbot.core.db.protocols import DashboardStore
from astrbot.core.skills.skill_manager import SkillManager
from astrbot.dashboard.responses import ApiError, DashboardValidationError, error
from astrbot.dashboard.services.api_key_service import ApiKeyService
from astrbot.dashboard.services.appearance_service import AppearanceService
from astrbot.dashboard.services.auth_service import (
    DASHBOARD_JWT_COOKIE_NAME,
    AuthService,
    DashboardTokenValidator,
)
from astrbot.dashboard.services.backup_service import BackupService
from astrbot.dashboard.services.chat_service import ChatService
from astrbot.dashboard.services.chatui_project_service import ChatUIProjectService
from astrbot.dashboard.services.command_service import CommandService
from astrbot.dashboard.services.config_service import (
    BotConfigService,
    ConfigDisplayService,
    ConfigFileService,
    ConfigProfileService,
    ConfigRoutingService,
    ProviderConfigService,
    save_config_async,
)
from astrbot.dashboard.services.conversation_service import ConversationService
from astrbot.dashboard.services.cron_service import CronService
from astrbot.dashboard.services.data_file_service import DataFileService
from astrbot.dashboard.services.file_service import FileService
from astrbot.dashboard.services.knowledge_base_service import KnowledgeBaseService
from astrbot.dashboard.services.live_chat_service import LiveChatService
from astrbot.dashboard.services.log_service import LogService
from astrbot.dashboard.services.memory_service import MemoryService
from astrbot.dashboard.services.open_api_service import OpenApiService
from astrbot.dashboard.services.persona_service import PersonaService
from astrbot.dashboard.services.platform_service import PlatformService
from astrbot.dashboard.services.plugin_dashboard_service import PluginDashboardService
from astrbot.dashboard.services.plugin_file_ticket_service import (
    PluginFileTicketService,
)
from astrbot.dashboard.services.plugin_log_level_service import PluginLogLevelService
from astrbot.dashboard.services.plugin_page_session_service import (
    PluginPageSessionService,
)
from astrbot.dashboard.services.plugin_service import PluginService
from astrbot.dashboard.services.session_management_service import (
    SessionManagementService,
)
from astrbot.dashboard.services.skills_service import SkillsService
from astrbot.dashboard.services.stat_service import StatService
from astrbot.dashboard.services.subagent_service import SubAgentService
from astrbot.dashboard.services.t2i_service import T2iService
from astrbot.dashboard.services.tools_service import ToolsService
from astrbot.dashboard.services.update_service import (
    UpdateService,
    call_pip_install,
)

from .error_handling import internal_error_response
from .plugin_files import router as plugin_files_router
from .plugin_page_assets import router as plugin_page_assets_router
from .router import API_V1_PREFIX, build_api_router
from .static_files import router as static_files_router

CLEAR_SITE_DATA_HEADERS = {"Clear-Site-Data": '"cache"'}


def create_dashboard_asgi_app(
    *,
    runtime: CoreRuntime,
    core_control: CoreControl,
    db: DashboardStore,
    jwt_secret: str,
    static_folder: str | None = None,
) -> FastAPI:
    app = FastAPI(
        title="AstrBot OpenAPI",
        version="1.0.0",
        openapi_url=f"{API_V1_PREFIX}/openapi.json",
        docs_url=f"{API_V1_PREFIX}/docs",
        redoc_url=f"{API_V1_PREFIX}/redoc",
    )
    app.state.astrbot_config = runtime.astrbot_config
    app.state.runtime = runtime
    app.state.db = db
    app.state.jwt_secret = jwt_secret
    dashboard_token_validator = DashboardTokenValidator(jwt_secret)
    app.state.dashboard_token_validator = dashboard_token_validator
    app.state.dashboard_static_folder = static_folder
    app.state.dashboard_config = {}
    app.state.dashboard_testing = False
    extension_registry = runtime.plugin_manager.extensions.registry
    plugin_page_sessions = PluginPageSessionService(extension_registry, jwt_secret)
    plugin_file_tickets = PluginFileTicketService(extension_registry, jwt_secret)
    plugin_dashboard = PluginDashboardService(
        extension_registry,
        plugin_page_sessions,
        plugin_file_tickets,
    )
    auth_service = AuthService(
        db,
        runtime.astrbot_config,
        demo_mode=runtime.services.demo_mode,
        totp_runtime_state=runtime.services.totp_runtime_state,
        token_validator=dashboard_token_validator,
    )

    config_files_service = ConfigFileService(
        runtime.catalogs.plugins,
        runtime.plugin_manager.lifecycle,
    )

    async def save_managed_core_config(relative_path: str, next_config: dict) -> None:
        if relative_path.casefold().startswith("config/"):
            filename = Path(relative_path).name
            profile_id = next(
                (
                    config_id
                    for config_id, config in runtime.astrbot_config_mgr.confs.items()
                    if Path(config.config_path).name == filename
                ),
                None,
            )
            if profile_id is not None:
                profile_config = runtime.astrbot_config_mgr.confs[profile_id]
                previous = copy.deepcopy(dict(profile_config))
                committed = await save_config_async(
                    next_config,
                    profile_config,
                    is_core=True,
                )
                if not committed:
                    raise RuntimeError("Configuration save was superseded")
                try:
                    await core_control.reload_pipeline_scheduler(profile_id)
                except Exception as exc:
                    try:
                        await save_config_async(
                            previous,
                            profile_config,
                            is_core=True,
                        )
                        await core_control.reload_pipeline_scheduler(profile_id)
                    except Exception:
                        logger.error(
                            "Failed to restore config profile after reload failure"
                        )
                    raise RuntimeError("Configuration reload failed") from exc
                return
            await config_files_service.save_plugin_configs(
                next_config,
                Path(relative_path).stem,
            )
            return
        if relative_path != "cmd_config.json":
            if relative_path != "mcp_server.json":
                raise ValueError("Managed configuration is unavailable")
            servers = next_config.get("mcpServers")
            if not isinstance(servers, dict):
                raise ValueError("MCP configuration must contain an object mcpServers")
            for server_config in servers.values():
                if not isinstance(server_config, dict):
                    raise ValueError("MCP server configuration is invalid")
                try:
                    validate_mcp_server_config(server_config)
                except ValueError as exc:
                    raise ValueError("MCP server configuration is invalid") from exc
            tool_manager = runtime.catalogs.tools
            previous = tool_manager.load_mcp_config()
            if not tool_manager.save_mcp_config(next_config):
                raise ValueError("MCP configuration was not saved")
            try:
                await tool_manager.disable_mcp_server()
                for name, server_config in servers.items():
                    if server_config.get("active", True) and not server_config.get(
                        "auth_ref"
                    ):
                        await tool_manager.enable_mcp_server(
                            name, server_config, timeout_seconds=30
                        )
            except Exception as exc:
                # Restore both persisted and live state before reporting failure.
                tool_manager.save_mcp_config(previous)
                try:
                    await tool_manager.disable_mcp_server()
                    old_servers = previous.get("mcpServers", {})
                    if isinstance(old_servers, dict):
                        for name, server_config in old_servers.items():
                            if (
                                isinstance(server_config, dict)
                                and server_config.get("active", True)
                                and not server_config.get("auth_ref")
                            ):
                                await tool_manager.enable_mcp_server(
                                    name, server_config, timeout_seconds=30
                                )
                except Exception:
                    logger.error(
                        "Failed to restore MCP runtime after configuration error"
                    )
                raise RuntimeError("MCP configuration reload failed") from exc
            return
        previous = copy.deepcopy(dict(runtime.astrbot_config))
        committed = await save_config_async(
            next_config, runtime.astrbot_config, is_core=True
        )
        if not committed:
            raise RuntimeError("Configuration save was superseded")
        try:
            await core_control.reload_pipeline_scheduler("default")
        except Exception:
            try:
                await save_config_async(previous, runtime.astrbot_config, is_core=True)
                await core_control.reload_pipeline_scheduler("default")
            except Exception:
                logger.error("Failed to roll back managed Dashboard configuration")
            raise

    app.state.services = SimpleNamespace(
        appearance=AppearanceService(),
        config_profiles=ConfigProfileService(
            runtime.astrbot_config_mgr,
            runtime.umop_config_router,
            core_control,
            runtime.services.totp_runtime_state,
            db,
        ),
        config_display=ConfigDisplayService(
            runtime.astrbot_config,
            runtime.catalogs.platforms,
            runtime.catalogs.providers,
            runtime.catalogs.plugins,
            runtime.services.file_token_service,
        ),
        config_files=config_files_service,
        config_routes=ConfigRoutingService(runtime.umop_config_router),
        api_keys=ApiKeyService(db),
        auth=auth_service,
        backups=BackupService(
            db,
            runtime.astrbot_config,
            runtime.knowledge_base_manager,
        ),
        chat=ChatService(
            db,
            preferences=runtime.services.preferences,
            conversation_manager=runtime.conversation_manager,
            platform_message_history_manager=runtime.platform_message_history_manager,
            umop_config_router=runtime.umop_config_router,
            webchat_run_coordinator=runtime.webchat_run_coordinator,
            authorization=getattr(runtime.services, "authorization", None),
            active_event_control=runtime.execution_context.active_event_registry,
        ),
        chat_projects=ChatUIProjectService(db),
        commands=CommandService(
            runtime.astrbot_config,
            db,
            runtime.services.preferences,
            runtime.catalogs.handlers,
            runtime.plugin_manager.catalog,
            runtime.platform_manager,
            runtime.astrbot_config_mgr,
        ),
        conversations=ConversationService(db, runtime.conversation_manager),
        cron=CronService(runtime.cron_manager, runtime.astrbot_config_mgr),
        files=FileService(runtime.services.file_token_service),
        knowledge_bases=KnowledgeBaseService(runtime.knowledge_base_manager),
        memory=MemoryService(db, runtime.memory_manager),
        live_chat=LiveChatService(
            db,
            preferences=runtime.services.preferences,
            config=runtime.astrbot_config,
            provider_manager=runtime.provider_manager,
            platform_message_history_manager=runtime.platform_message_history_manager,
            webchat_run_coordinator=runtime.webchat_run_coordinator,
            mcp_interaction_coordinator=getattr(
                runtime.catalogs.tools, "mcp_interaction_coordinator", None
            ),
            token_validator=dashboard_token_validator,
            auth_service=auth_service,
        ),
        logs=LogService(runtime.log_broker, runtime.astrbot_config),
        bots=BotConfigService(
            runtime.astrbot_config,
            runtime.catalogs.platforms,
            runtime.platform_manager,
        ),
        platforms=PlatformService(runtime.platform_manager, runtime.catalogs.platforms),
        providers=ProviderConfigService(
            runtime.astrbot_config,
            runtime.provider_manager,
            runtime.catalogs.providers,
            runtime.services.llm_metadata_catalog,
        ),
        personas=PersonaService(runtime.persona_mgr),
        plugin_dashboard=plugin_dashboard,
        plugin_page_sessions=plugin_page_sessions,
        plugin_file_tickets=plugin_file_tickets,
        plugin_log_levels=PluginLogLevelService(runtime.plugin_manager.catalog),
        plugins=PluginService(
            runtime.plugin_manager.lifecycle,
            runtime.plugin_manager.loader,
            runtime.plugin_manager.packages,
            runtime.plugin_manager.extensions,
            runtime.catalogs.plugins,
            runtime.catalogs.handlers,
            runtime.services.preferences,
            runtime.services.file_token_service,
            runtime.services.computer_runtime,
            demo_mode=runtime.services.demo_mode,
        ),
        open_api=OpenApiService(
            db,
            platform_manager=runtime.platform_manager,
            astrbot_config_mgr=runtime.astrbot_config_mgr,
            umop_config_router=runtime.umop_config_router,
            astrbot_config=runtime.astrbot_config,
            platform_message_history_manager=runtime.platform_message_history_manager,
            webchat_run_coordinator=runtime.webchat_run_coordinator,
            authorization=getattr(runtime.services, "authorization", None),
        ),
        sessions=SessionManagementService(
            db,
            runtime.services.preferences,
            runtime.provider_manager,
            runtime.persona_mgr,
            runtime.catalogs.plugins,
            runtime.knowledge_base_manager,
            runtime.umop_config_router,
        ),
        skills=SkillsService(
            runtime.astrbot_config,
            runtime.services.computer_runtime,
            SkillManager(builtin_skill_catalog=runtime.catalogs.builtin_skills),
            demo_mode=runtime.services.demo_mode,
            plugins=runtime.catalogs.plugins,
        ),
        data_files=DataFileService(
            demo_mode=runtime.services.demo_mode,
            managed_config_saver=save_managed_core_config,
        ),
        stats=StatService(
            db,
            core_control,
            runtime.astrbot_config,
            demo_mode=runtime.services.demo_mode,
            start_time=runtime.start_time,
            html_renderer=runtime.services.html_renderer,
            plugin_catalog=runtime.catalogs.plugins,
            platform_manager=runtime.platform_manager,
        ),
        subagents=SubAgentService(
            runtime.astrbot_config,
            runtime.subagent_orchestrator,
            runtime.catalogs.tools,
        ),
        t2i=T2iService(
            runtime.astrbot_config,
            runtime.astrbot_config_mgr,
            core_control,
        ),
        tools=ToolsService(
            runtime.catalogs.tools,
            runtime.services.preferences,
            runtime.astrbot_config_mgr,
            runtime.catalogs.plugins,
        ),
        updates=UpdateService(
            runtime.updater,
            core_control,
            pip_install_func=lambda *args, **kwargs: call_pip_install(
                runtime.services.pip_installer, *args, **kwargs
            ),
            demo_mode=runtime.services.demo_mode,
            clear_site_data_headers=CLEAR_SITE_DATA_HEADERS,
        ),
    )

    @app.exception_handler(ApiError)
    async def api_error_handler(_request: Request, exc: ApiError):
        return JSONResponse(
            error(exc.message, exc.data),
            status_code=exc.status_code,
        )

    @app.exception_handler(DashboardValidationError)
    async def dashboard_validation_error_handler(
        _request: Request,
        exc: DashboardValidationError,
    ):
        return JSONResponse(error(str(exc)), status_code=400)

    @app.exception_handler(ValueError)
    async def value_error_handler(_request: Request, exc: ValueError):
        return internal_error_response(
            logger,
            "Unhandled dashboard API value error",
            exc,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_request: Request, exc: StarletteHTTPException):
        if isinstance(exc.detail, str):
            return JSONResponse(
                error(exc.detail),
                status_code=exc.status_code,
                headers=exc.headers,
            )
        return JSONResponse(
            error("Request failed"),
            status_code=exc.status_code,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(
        _request: Request,
        _exc: RequestValidationError,
    ):
        return JSONResponse(error("Invalid request payload"), status_code=422)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_request: Request, exc: Exception):
        return internal_error_response(
            logger,
            "Unhandled dashboard API exception",
            exc,
        )

    app.include_router(build_api_router())
    app.include_router(plugin_page_assets_router)
    app.include_router(plugin_files_router)
    app.include_router(static_files_router)

    def dashboard_openapi():
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            routes=app.routes,
        )
        security_schemes = schema.setdefault("components", {}).setdefault(
            "securitySchemes",
            {},
        )
        security_schemes["DashboardBearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "Dashboard session JWT",
        }
        security_schemes["DashboardCookieAuth"] = {
            "type": "apiKey",
            "in": "cookie",
            "name": DASHBOARD_JWT_COOKIE_NAME,
        }
        app.openapi_schema = schema
        return schema

    app.openapi = dashboard_openapi

    async def shutdown_plugin_dashboard_services() -> None:
        await app.state.services.updates.shutdown()
        await plugin_page_sessions.shutdown()
        await plugin_file_tickets.shutdown()

    app.router.add_event_handler("shutdown", shutdown_plugin_dashboard_services)
    return app
