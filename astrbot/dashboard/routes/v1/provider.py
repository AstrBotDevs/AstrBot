from astrbot.core.core_lifecycle import AstrBotCoreLifecycle

from ...services.provider import ProviderService
from ..route import Route, RouteContext


class V1ProviderRoute(Route):
    def __init__(self, context: RouteContext, core_lifecycle: AstrBotCoreLifecycle):
        super().__init__(context)
        self.provider_service = ProviderService(core_lifecycle)
        self.routes = {
            # provider source
            "/v1/provider-source": [
                (
                    "PUT",
                    self.provider_service.update_provider_source,
                    "v1_provider_source_update",
                ),
                (
                    "DELETE",
                    self.provider_service.delete_provider_source,
                    "v1_provider_source_delete",
                ),
                (
                    "GET",
                    self.provider_service.list_provider_sources,
                    "v1_provider_source_list",
                ),
                (
                    "GET",
                    self.provider_service.get_provider_source_models,
                    "v1_provider_source_models",
                ),
            ],
            # provider
            "/v1/provider": [
                (
                    "POST",
                    self.provider_service.post_new_provider,
                    "v1_provider_post_new_provider",
                ),
                (
                    "PUT",
                    self.provider_service.post_update_provider,
                    "v1_provider_post_update_provider",
                ),
                (
                    "DELETE",
                    self.provider_service.post_delete_provider,
                    "v1_provider_post_delete_provider",
                ),
                (
                    "GET",
                    self.provider_service.get_provider_config_list,
                    "v1_provider_get_provider_config_list",
                ),
            ],
        }
        self.register_routes()
