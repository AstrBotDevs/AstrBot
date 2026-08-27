from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial


@register_provider_adapter(
    "synthorai_chat_completion", "Synthorai Chat Completion Provider Adapter"
)
class ProviderSynthorai(ProviderOpenAIOfficial):
    """Synthorai provider using its OpenAI-compatible Chat Completions API."""

    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        """Initialize the Synthorai client with provider defaults.

        Args:
            provider_config: AstrBot provider source configuration.
            provider_settings: Global provider settings.
        """
        if not provider_config.get("api_base"):
            provider_config["api_base"] = "https://synthorai.io/v1"
        super().__init__(provider_config, provider_settings)
        self.client._custom_headers["X-Title"] = "AstrBot"  # type: ignore
