from ..register import register_provider_adapter
from .openai_chat_completions_source import ProviderOpenAIChatCompletions


@register_provider_adapter(
    "mirarouter_chat_completion",
    "MiraRouter Chat Completion Provider Adapter",
)
class ProviderMiraRouter(ProviderOpenAIChatCompletions):
    """MiraRouter provider using its OpenAI-compatible API."""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        """Initialize the MiraRouter client with AstrBot attribution.

        Args:
            provider_config: AstrBot provider source configuration.
            provider_settings: Global provider settings.
        """
        super().__init__(provider_config, provider_settings)
        custom_headers = dict(getattr(self.client, "_custom_headers", {}))
        custom_headers["X-APP-CODE"] = "astrbot"
        self.client._custom_headers = custom_headers
