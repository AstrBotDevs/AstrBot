import httpx
from openai import AsyncOpenAI

from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial


@register_provider_adapter(
    "daoxe_chat_completion", "DaoXE Chat Completion Provider Adapter"
)
class ProviderDaoXE(ProviderOpenAIOfficial):
    """DaoXE provider using its OpenAI-compatible Chat Completions API."""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        """Initialize the DaoXE client with provider defaults.

        Args:
            provider_config: AstrBot provider source configuration.
            provider_settings: Global provider settings.
        """
        if not provider_config.get("api_base"):
            provider_config["api_base"] = "https://api.daoxe.com/v1"
        super().__init__(provider_config, provider_settings)

    async def get_models(self) -> list[str]:
        """Return the account-scoped model catalog.

        The live catalog changes as upstream vendors add or retire models, so
        the list is read from the gateway's own ``/v1/models`` endpoint rather
        than pinned here.

        Returns:
            Sorted model IDs visible to the configured API key.

        Raises:
            Exception: If the DaoXE model catalog endpoint is unavailable.
        """
        try:
            response = await self.client.models.list()
            return sorted(model.id for model in response.data)
        except (httpx.HTTPError, Exception) as exc:
            raise Exception(f"Failed to fetch DaoXE model list: {exc}") from exc
