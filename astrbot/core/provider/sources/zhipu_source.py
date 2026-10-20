# This file was originally created to adapt to glm-4v-flash, which only supports one image in the context.
# It is no longer specifically adapted to Zhipu's models. To ensure compatibility, this


from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial


@register_provider_adapter("zhipu_chat_completion", "智谱 Chat Completion 提供商适配器")
class ProviderZhipu(ProviderOpenAIOfficial):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
