from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from astrbot.core import LogBroker
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.log import LogManager
from astrbot.dashboard.responses import ApiError, error
from astrbot.dashboard.services.api_key_service import ApiKeyService
from astrbot.dashboard.services.auth_service import AuthService
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
)
from astrbot.dashboard.services.conversation_service import ConversationService
from astrbot.dashboard.services.cron_service import CronService
from astrbot.dashboard.services.file_service import FileService
from astrbot.dashboard.services.knowledge_base_service import KnowledgeBaseService
from astrbot.dashboard.services.live_chat_service import LiveChatService
from astrbot.dashboard.services.log_service import LogService
from astrbot.dashboard.services.open_api_service import OpenApiService
from astrbot.dashboard.services.persona_service import PersonaService
from astrbot.dashboard.services.platform_service import PlatformService
from astrbot.dashboard.services.plugin_page_service import PluginPageService
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
    DEMO_MODE,
    UpdateService,
    call_download_dashboard,
    call_extract_dashboard,
    call_get_dashboard_version,
    call_pip_install,
)

from .api_keys import legacy_router as legacy_api_keys_router
from .auth import legacy_router as legacy_auth_router
from .backups import legacy_router as legacy_backups_router
from .bots import legacy_router as legacy_bots_router
from .chat import legacy_router as legacy_chat_router
from .chat_projects import legacy_router as legacy_chat_projects_router
from .config_profiles import legacy_router as legacy_config_profiles_router
from .conversations import legacy_router as legacy_conversations_router
from .cron import legacy_router as legacy_cron_router
from .extensions import legacy_router as legacy_extensions_router
from .files import legacy_router as legacy_files_router
from .knowledge_bases import legacy_router as legacy_knowledge_bases_router
from .live_chat import legacy_router as legacy_live_chat_router
from .logs import legacy_router as legacy_logs_router
from .personas import legacy_router as legacy_personas_router
from .platform import legacy_router as legacy_platform_router
from .plugins import legacy_router as legacy_plugins_router
from .providers import legacy_router as legacy_providers_router
from .router import API_V1_PREFIX, build_api_router
from .sessions import legacy_router as legacy_sessions_router
from .skills import legacy_router as legacy_skills_router
from .static_files import router as static_files_router
from .stats import legacy_router as legacy_stats_router
from .subagents import legacy_router as legacy_subagents_router
from .t2i import legacy_router as legacy_t2i_router
from .tools import legacy_router as legacy_tools_router
from .updates import legacy_router as legacy_updates_router

CLEAR_SITE_DATA_HEADERS = {"Clear-Site-Data": '"cache"'}


def create_dashboard_asgi_app(
    *,
    core_lifecycle: AstrBotCoreLifecycle,
    db: BaseDatabase,
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
    app.state.core_lifecycle = core_lifecycle
    app.state.db = db
    app.state.jwt_secret = jwt_secret
    app.state.dashboard_static_folder = static_folder
    log_broker = getattr(core_lifecycle, "log_broker", None) or LogBroker()
    app.state.services = SimpleNamespace(
        config_profiles=ConfigProfileService(core_lifecycle, db),
        config_display=ConfigDisplayService(core_lifecycle),
        config_files=ConfigFileService(core_lifecycle),
        config_routes=ConfigRoutingService(core_lifecycle),
        api_keys=ApiKeyService(db),
        auth=AuthService(db, core_lifecycle.astrbot_config),
        backups=BackupService(db, core_lifecycle),
        chat=ChatService(db, core_lifecycle),
        chat_projects=ChatUIProjectService(db),
        commands=CommandService(core_lifecycle.astrbot_config, core_lifecycle),
        conversations=ConversationService(db, core_lifecycle),
        cron=CronService(core_lifecycle),
        files=FileService(),
        knowledge_bases=KnowledgeBaseService(core_lifecycle),
        live_chat=LiveChatService(db, core_lifecycle),
        logs=LogService(log_broker, core_lifecycle.astrbot_config),
        bots=BotConfigService(core_lifecycle),
        platforms=PlatformService(core_lifecycle),
        providers=ProviderConfigService(core_lifecycle),
        personas=PersonaService(core_lifecycle),
        plugins=PluginService(core_lifecycle, core_lifecycle.plugin_manager),
        plugin_pages=PluginPageService(
            core_lifecycle.plugin_manager,
            core_lifecycle=core_lifecycle,
        ),
        open_api=OpenApiService(db, core_lifecycle),
        sessions=SessionManagementService(core_lifecycle, db),
        skills=SkillsService(core_lifecycle),
        stats=StatService(db, core_lifecycle, core_lifecycle.astrbot_config),
        subagents=SubAgentService(core_lifecycle),
        t2i=T2iService(core_lifecycle),
        tools=ToolsService(core_lifecycle),
        updates=UpdateService(
            core_lifecycle.astrbot_updator,
            core_lifecycle,
            download_dashboard_func=call_download_dashboard,
            extract_dashboard_func=call_extract_dashboard,
            get_dashboard_version_func=call_get_dashboard_version,
            pip_install_func=call_pip_install,
            demo_mode=DEMO_MODE,
            clear_site_data_headers=CLEAR_SITE_DATA_HEADERS,
        ),
    )

    @app.exception_handler(ApiError)
    async def api_error_handler(_request: Request, exc: ApiError):
        return JSONResponse(
            error(exc.message, exc.data),
            status_code=exc.status_code,
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(_request: Request, exc: ValueError):
        return JSONResponse(error(str(exc)), status_code=400)

    @app.exception_handler(StarletteHTTPException)
    async def starlette_http_error_handler(
        _request: Request, exc: StarletteHTTPException
    ):
        if isinstance(exc.detail, str):
            return JSONResponse(
                error(exc.detail), status_code=exc.status_code, headers=exc.headers
            )
        return JSONResponse(
            error("Request failed", exc.detail),
            status_code=exc.status_code,
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def catch_all_handler(_request: Request, exc: Exception):
        LogManager.GetLogger("astrbot.dashboard").error(
            "Unhandled exception in dashboard API",
            exc_info=exc,
        )
        return JSONResponse(
            error("Internal server error"),
            status_code=500,
        )

    # Legacy dashboard routes keep old /api/* callers working without entering OpenAPI.
    app.include_router(legacy_api_keys_router)
    app.include_router(legacy_auth_router)
    app.include_router(legacy_backups_router)
    app.include_router(legacy_config_profiles_router)
    app.include_router(legacy_bots_router)
    app.include_router(legacy_providers_router)
    app.include_router(legacy_chat_router)
    app.include_router(legacy_chat_projects_router)
    app.include_router(legacy_conversations_router)
    app.include_router(legacy_cron_router)
    app.include_router(legacy_extensions_router)
    app.include_router(legacy_files_router)
    app.include_router(legacy_knowledge_bases_router)
    app.include_router(legacy_live_chat_router)
    app.include_router(legacy_logs_router)
    app.include_router(legacy_sessions_router)
    app.include_router(legacy_skills_router)
    app.include_router(legacy_stats_router)
    app.include_router(legacy_subagents_router)
    app.include_router(legacy_tools_router)
    app.include_router(legacy_platform_router)
    app.include_router(legacy_plugins_router)
    app.include_router(legacy_t2i_router)
    app.include_router(legacy_personas_router)
    app.include_router(legacy_updates_router)
    app.include_router(build_api_router())
    app.include_router(static_files_router)
    return app
