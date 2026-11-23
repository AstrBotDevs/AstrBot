from openai.types.chat import ChatCompletion, ChatCompletionChunk

from ..register import register_provider_adapter
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
        self.client._custom_headers["HTTP-Referer"] = (  # type: ignore
            "https://github.com/AstrBotDevs/AstrBot"
        )
        self.client._custom_headers["X-OpenRouter-Title"] = "AstrBot"  # type: ignore
        self.client._custom_headers["X-OpenRouter-Categories"] = (
            "general-chat,personal-agent"  # type: ignore
        )
        self.reasoning_key = "reasoning"

    def _extract_reasoning_content(
        self, completion: ChatCompletion | ChatCompletionChunk
    ) -> str | None:
        reasoning = super()._extract_reasoning_content(completion)
        if (
            reasoning
            or not isinstance(completion, ChatCompletion)
            or not completion.choices
        ):
            return reasoning

        details = getattr(completion.choices[0].message, "reasoning_details", None)
        if not isinstance(details, list):
            return reasoning

        parts: list[str] = []
        previous_type = None
        for detail in details:
            if not isinstance(detail, dict):
                continue
            detail_type = detail.get("type")
            if detail_type == "reasoning.summary":
                text = detail.get("summary")
            elif detail_type == "reasoning.text":
                text = detail.get("text")
            else:
                continue
            if isinstance(text, str) and text:
                if (
                    parts
                    and detail_type != previous_type
                    and not parts[-1][-1].isspace()
                    and not text[0].isspace()
                ):
                    parts.append("\n\n")
                parts.append(text)
                previous_type = detail_type
        return "".join(parts) if parts else reasoning
