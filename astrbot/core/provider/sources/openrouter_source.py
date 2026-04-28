from astrbot.core.provider.register import register_provider_adapter

from .openai_source import ProviderOpenAIOfficial


@register_provider_adapter(
    "openrouter_chat_completion",
    "OpenRouter Chat Completion Provider Adapter",
)
class ProviderOpenRouter(ProviderOpenAIOfficial):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        # Inject OpenRouter-specific default headers so the parent passes them as
        # default_headers to the AsyncOpenAI client, avoiding direct access to
        # the private _custom_headers attribute.
        custom_headers = provider_config.get("custom_headers", {})
        if not isinstance(custom_headers, dict):
            custom_headers = {}
        custom_headers["HTTP-Referer"] = (
            "https://github.com/AstrBotDevs/AstrBot"
        )
        custom_headers["X-OpenRouter-Title"] = "AstrBot"
        custom_headers["X-OpenRouter-Categories"] = (
            "general-chat,personal-agent"
        )
        provider_config["custom_headers"] = custom_headers
        super().__init__(provider_config, provider_settings)
        self.reasoning_key = "reasoning"
