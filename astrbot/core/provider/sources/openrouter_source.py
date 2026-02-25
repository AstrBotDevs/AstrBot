from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial


@register_provider_adapter(
    "openrouter_chat_completion", "OpenRouter Chat Completion Provider Adapter"
)
class ProviderOpenRouter(ProviderOpenAIOfficial):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        # Reference to: https://openrouter.ai/docs/api/reference/overview#headers
        self.client._custom_headers["HTTP-Referer"] = (  # type: ignore
            "https://github.com/AstrBotDevs/AstrBot"
        )
        self.client._custom_headers["X-TITLE"] = "AstrBot"  # type: ignore
