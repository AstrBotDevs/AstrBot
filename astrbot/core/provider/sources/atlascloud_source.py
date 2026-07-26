from astrbot import logger

from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial

ATLASCLOUD_DEFAULT_API_BASE = "https://api.atlascloud.ai/v1"
ATLASCLOUD_DEFAULT_MODEL = "qwen/qwen3.5-flash"
ATLASCLOUD_MODELS = [
    ATLASCLOUD_DEFAULT_MODEL,
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
        merged_provider_config = dict(provider_config)
        if not merged_provider_config.get("api_base"):
            merged_provider_config["api_base"] = ATLASCLOUD_DEFAULT_API_BASE
        if not merged_provider_config.get("model"):
            merged_provider_config["model"] = ATLASCLOUD_DEFAULT_MODEL

        super().__init__(merged_provider_config, provider_settings)

    async def get_models(self) -> list[str]:
        try:
            models = await super().get_models()
            if models:
                return models
        except Exception as exc:
            logger.warning(
                "Failed to fetch Atlas Cloud models; using the static model list.",
                exc_info=exc,
            )

        return ATLASCLOUD_MODELS.copy()
