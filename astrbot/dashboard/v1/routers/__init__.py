from fastapi import APIRouter

from .bots import router as bots_router
from .compat import compat_routers
from .config_profiles import router as config_profiles_router
from .extensions import router as extensions_router
from .open_api_compat import router as open_api_compat_router
from .plugins import router as plugins_router
from .providers import router as providers_router


def build_v1_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    router.include_router(config_profiles_router)
    router.include_router(bots_router)
    router.include_router(providers_router)
    router.include_router(plugins_router)
    router.include_router(extensions_router)
    router.include_router(open_api_compat_router)
    for compat_router in compat_routers:
        router.include_router(compat_router)
    return router
