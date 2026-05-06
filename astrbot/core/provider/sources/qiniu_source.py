from astrbot import logger

from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial


@register_provider_adapter(
    "qiniu_chat_completion",
    "Qiniu Chat Completion Provider Adapter",
)
class ProviderQiniu(ProviderOpenAIOfficial):
    async def get_models(self):
        try:
            models = await super().get_models()
            if models:
                return models
        except Exception as e:
            logger.debug(
                "Qiniu 列举模型不可用，退回占位列表: %s",
                e,
                exc_info=True,
            )
        return ["deepseek-v3"]
