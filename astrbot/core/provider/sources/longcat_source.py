from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial


@register_provider_adapter(
    "longcat_chat_completion", "LongCat Chat Completion Provider Adapter"
)
class ProviderLongCat(ProviderOpenAIOfficial):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        api_base = (provider_config.get("api_base", "") or "").strip()
        if not api_base:
            provider_config["api_base"] = "https://api.longcat.chat/openai/v1"
        else:
            normalized_api_base = api_base.rstrip("/")
            if normalized_api_base.endswith("/openai"):
                normalized_api_base = f"{normalized_api_base}/v1"
            provider_config["api_base"] = normalized_api_base

        super().__init__(provider_config, provider_settings)
