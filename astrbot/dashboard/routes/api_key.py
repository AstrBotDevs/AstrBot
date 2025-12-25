from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase

from ..services.api_key import ApiKeyService
from .route import Route, RouteContext


class ApiKeyRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        core_lifecycle: AstrBotCoreLifecycle,
        db: BaseDatabase,
    ):
        super().__init__(context)
        self.api_key_service = ApiKeyService(core_lifecycle, db)
        self.routes = {
            "/api-key": [
                ("POST", self.api_key_service.create_api_key),
                ("GET", self.api_key_service.list_api_keys),
            ],
            "/api-key/<key_id>": [("DELETE", self.api_key_service.delete_api_key)],
        }
        self.register_routes()
