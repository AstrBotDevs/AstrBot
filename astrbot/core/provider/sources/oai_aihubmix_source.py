from collections.abc import MutableMapping
from typing import cast

from astrbot.core.provider.register import register_provider_adapter

from .openai_source import ProviderOpenAIOfficial


@register_provider_adapter(
    "aihubmix_chat_completion", "AIHubMix Chat Completion Provider Adapter"
)
class ProviderAIHubMix(ProviderOpenAIOfficial):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        # Reference to: https://aihubmix.com/appstore
        # Use this code can enjoy 10% off prices for AIHubMix API calls.
        custom_headers = cast(
            MutableMapping[str, str], getattr(self.client, "_custom_headers")
        )
        custom_headers["APP-Code"] = "KRLC5702"
