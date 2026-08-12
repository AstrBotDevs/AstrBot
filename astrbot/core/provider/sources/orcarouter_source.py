from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial


@register_provider_adapter(
    "orcarouter_chat_completion", "OrcaRouter Chat Completion Provider Adapter"
)
class ProviderOrcaRouter(ProviderOpenAIOfficial):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        # Reference to: https://www.orcarouter.ai
        self.client._custom_headers["HTTP-Referer"] = (  # type: ignore
            "https://github.com/AstrBotDevs/AstrBot"
        )
        self.reasoning_key = "reasoning"
