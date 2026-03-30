from collections.abc import MutableMapping
from typing import cast

from astrbot.core.provider.register import register_provider_adapter

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
        custom_headers = cast(
            MutableMapping[str, str], getattr(self.client, "_custom_headers")
        )
        custom_headers["HTTP-Referer"] = "https://github.com/AstrBotDevs/AstrBot"
        custom_headers["X-OpenRouter-Title"] = "AstrBot"
        custom_headers["X-OpenRouter-Categories"] = "general-chat,personal-agent"
