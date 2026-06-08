from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from astrbot.core import LogBroker
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
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
    call_check_migration_needed_v4,
    call_do_migration_v4,
    call_download_dashboard,
    call_get_dashboard_version,
    call_pip_install,
)

from .api_keys import dashboard_router as dashboard_api_keys_router
from .auth import dashboard_router as dashboard_auth_router
from .backups import dashboard_router as dashboard_backups_router
from .bots import dashboard_router as dashboard_bots_router
from .chat import dashboard_router as dashboard_chat_router
from .chat_projects import dashboard_router as dashboard_chat_projects_router
from .config_profiles import dashboard_router as dashboard_config_profiles_router
from .conversations import dashboard_router as dashboard_conversations_router
from .cron import dashboard_router as dashboard_cron_router
from .extensions import dashboard_router as dashboard_extensions_router
from .files import dashboard_router as dashboard_files_router
from .knowledge_bases import dashboard_router as dashboard_knowledge_bases_router
from .live_chat import dashboard_router as dashboard_live_chat_router
from .logs import dashboard_router as dashboard_logs_router
from .personas import dashboard_router as dashboard_personas_router
from .platform import dashboard_router as dashboard_platform_router
from .plugins import dashboard_router as dashboard_plugins_router
from .providers import dashboard_router as dashboard_providers_router
from .responses import ApiError, error
from .router import build_api_router
from .sessions import dashboard_router as dashboard_sessions_router
from .skills import dashboard_router as dashboard_skills_router
from .static_files import router as static_files_router
from .stats import dashboard_router as dashboard_stats_router
from .subagents import dashboard_router as dashboard_subagents_router
from .t2i import dashboard_router as dashboard_t2i_router
from .tools import dashboard_router as dashboard_tools_router
from .updates import dashboard_router as dashboard_updates_router

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
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
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
            get_dashboard_version_func=call_get_dashboard_version,
            pip_install_func=call_pip_install,
            check_migration_needed_func=call_check_migration_needed_v4,
            do_migration_func=call_do_migration_v4,
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

    @app.exception_handler(HTTPException)
    async def http_error_handler(_request: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return JSONResponse(error(detail), status_code=exc.status_code)

    app.include_router(dashboard_api_keys_router)
    app.include_router(dashboard_auth_router)
    app.include_router(dashboard_backups_router)
    app.include_router(dashboard_config_profiles_router)
    app.include_router(dashboard_bots_router)
    app.include_router(dashboard_providers_router)
    app.include_router(dashboard_chat_router)
    app.include_router(dashboard_chat_projects_router)
    app.include_router(dashboard_conversations_router)
    app.include_router(dashboard_cron_router)
    app.include_router(dashboard_extensions_router)
    app.include_router(dashboard_files_router)
    app.include_router(dashboard_knowledge_bases_router)
    app.include_router(dashboard_live_chat_router)
    app.include_router(dashboard_logs_router)
    app.include_router(dashboard_sessions_router)
    app.include_router(dashboard_skills_router)
    app.include_router(dashboard_stats_router)
    app.include_router(dashboard_subagents_router)
    app.include_router(dashboard_tools_router)
    app.include_router(dashboard_platform_router)
    app.include_router(dashboard_plugins_router)
    app.include_router(dashboard_t2i_router)
    app.include_router(dashboard_personas_router)
    app.include_router(dashboard_updates_router)
    app.include_router(build_api_router())
    app.include_router(static_files_router)
    return app
