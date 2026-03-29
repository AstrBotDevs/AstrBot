from astrbot.core.provider.register import register_provider_adapter

from .openai_source import ProviderOpenAIOfficial


@register_provider_adapter(
    "groq_chat_completion", "Groq Chat Completion Provider Adapter"
)
class ProviderGroq(ProviderOpenAIOfficial):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.reasoning_key = "reasoning"

    def _finally_convert_payload(self, payloads: dict) -> None:
        """Groq rejects assistant history items that include reasoning_content."""
        super()._finally_convert_payload(payloads)
        for message in payloads.get("messages", []):
            if message.get("role") == "assistant":
                message.pop("reasoning_content", None)
                message.pop("reasoning", None)
