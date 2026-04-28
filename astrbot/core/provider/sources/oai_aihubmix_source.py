from astrbot.core.provider.register import register_provider_adapter

from .openai_source import ProviderOpenAIOfficial


@register_provider_adapter(
    "aihubmix_chat_completion",
    "AIHubMix Chat Completion Provider Adapter",
)
class ProviderAIHubMix(ProviderOpenAIOfficial):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.client._custom_headers = {**self.client._custom_headers, "APP-Code": "KRLC5702"}
