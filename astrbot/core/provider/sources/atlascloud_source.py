from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial

ATLASCLOUD_DEFAULT_API_BASE = "https://api.atlascloud.ai/v1"
ATLASCLOUD_DEFAULT_MODEL = "qwen/qwen3.5-flash"
ATLASCLOUD_MODELS = [
    "qwen/qwen3.5-flash",
    "deepseek-ai/deepseek-v4-pro",
    "deepseek-ai/deepseek-v4-flash",
]


@register_provider_adapter(
    "atlascloud_chat_completion",
    "Atlas Cloud Chat Completion Provider Adapter",
)
class ProviderAtlasCloud(ProviderOpenAIOfficial):
    """Atlas Cloud provider using its OpenAI-compatible LLM endpoint."""

    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        if not provider_config.get("api_base"):
            provider_config["api_base"] = ATLASCLOUD_DEFAULT_API_BASE
        if not provider_config.get("model"):
            provider_config["model"] = ATLASCLOUD_DEFAULT_MODEL

        super().__init__(provider_config, provider_settings)

    async def get_models(self) -> list[str]:
        try:
            models = await super().get_models()
            if models:
                return models
        except Exception:
            pass

        return ATLASCLOUD_MODELS.copy()
