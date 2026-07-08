"""FastAPI HTTP API surface for the AstrBot dashboard."""

from fastapi import APIRouter

from .api_keys import router as api_keys_router
from .auth import router as auth_router
from .backups import router as backups_router
from .bots import router as bots_router
from .chat import router as chat_router
from .chat_projects import router as chat_projects_router
from .config_profiles import router as config_profiles_router
from .conversations import router as conversations_router
from .cron import router as cron_router
from .extensions import router as extensions_router
from .files import router as files_router
from .knowledge_bases import router as knowledge_bases_router
from .live_chat import router as live_chat_router
from .logs import router as logs_router
from .open_api import router as open_api_router
from .personas import router as personas_router
from .platform import router as platform_router
from .plugins import router as plugins_router
from .providers import router as providers_router
from .sessions import router as sessions_router
from .skills import router as skills_router
from .stats import router as stats_router
from .subagents import router as subagents_router
from .t2i import router as t2i_router
from .tools import router as tools_router
from .updates import router as updates_router

API_V1_PREFIX = "/api/v1"


def build_api_router() -> APIRouter:
    """Build the versioned dashboard API router.

    Returns:
        APIRouter containing all `/api/v1` dashboard routes.
    """
    router = APIRouter()
    for api_router in (
        auth_router,
        backups_router,
        config_profiles_router,
        api_keys_router,
        bots_router,
        providers_router,
        plugins_router,
        chat_router,
        chat_projects_router,
        conversations_router,
        cron_router,
        files_router,
        knowledge_bases_router,
        extensions_router,
        skills_router,
        sessions_router,
        subagents_router,
        logs_router,
        stats_router,
        tools_router,
        platform_router,
        t2i_router,
        personas_router,
        updates_router,
        open_api_router,
        live_chat_router,
    ):
        router.include_router(api_router, prefix=API_V1_PREFIX)
    return router
