from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial

MINIMAX_MODELS = [
    "MiniMax-M2.5",
    "MiniMax-M2.5-highspeed",
]

DEFAULT_BASE_URL = "https://api.minimax.io/v1"


@register_provider_adapter(
    "minimax_chat_completion",
    "MiniMax Chat Completion Provider Adapter",
    provider_display_name="MiniMax",
)
class ProviderMiniMax(ProviderOpenAIOfficial):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        if not provider_config.get("api_base"):
            provider_config["api_base"] = DEFAULT_BASE_URL
        super().__init__(provider_config, provider_settings)

    async def get_models(self) -> list[str]:
        return list(MINIMAX_MODELS)

    def _finally_convert_payload(self, payloads: dict) -> None:
        super()._finally_convert_payload(payloads)
        # MiniMax requires temperature in (0.0, 1.0]; zero is rejected.
        temp = payloads.get("temperature")
        if temp is not None and temp <= 0:
            payloads["temperature"] = 1.0
        # MiniMax does not support response_format.
        payloads.pop("response_format", None)
