"""FastAPI HTTP API surface for the AstrBot dashboard."""

from fastapi import APIRouter
from fastapi.routing import APIRoute

from .api_keys import router as api_keys_router
from .auth import ScopeDependency
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
    router = APIRouter(prefix=API_V1_PREFIX)
    child_routers = (
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
    )
    for child_router in child_routers:
        for route in child_router.routes:
            if not isinstance(route, APIRoute) or not route.include_in_schema:
                continue
            required_scopes = {
                dependency.call.scope
                for dependency in route.dependant.dependencies
                if isinstance(dependency.call, ScopeDependency)
            }
            if len(required_scopes) != 1:
                continue
            required_scope = required_scopes.pop()
            route.openapi_extra = {
                **(route.openapi_extra or {}),
                "x-astrbot-scope": required_scope,
            }
            scope_description = f"**Required scope:** `{required_scope}`"
            sensitive_scopes = route.openapi_extra.get("x-astrbot-sensitive-scopes", [])
            if sensitive_scopes:
                formatted_scopes = ", ".join(f"`{scope}`" for scope in sensitive_scopes)
                scope_description += (
                    "\n\n**Conditional sensitive scope:** " + formatted_scopes
                )
            if scope_description not in route.description:
                route.description = "\n\n".join(
                    part
                    for part in (route.description.strip(), scope_description)
                    if part
                )
        router.include_router(child_router)
    return router
