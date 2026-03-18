from ..register import register_provider_adapter
from .anthropic_source import ProviderAnthropic

KIMI_CODE_API_BASE = "https://api.kimi.com/coding/"
KIMI_CODE_DEFAULT_MODEL = "kimi-code"
KIMI_CODE_USER_AGENT = "claude-code/0.1.0"


@register_provider_adapter(
    "kimi_code_chat_completion",
    "Kimi Code Chat Completion 提供商适配器",
)
class ProviderKimiCode(ProviderAnthropic):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        merged_provider_config = dict(provider_config)
        merged_provider_config.setdefault("api_base", KIMI_CODE_API_BASE)
        merged_provider_config.setdefault("model", KIMI_CODE_DEFAULT_MODEL)

        custom_headers = merged_provider_config.get("custom_headers", {})
        if not isinstance(custom_headers, dict):
            custom_headers = {}
        merged_headers = {str(key): str(value) for key, value in custom_headers.items()}
        if not merged_headers.get("User-Agent", "").strip():
            merged_headers["User-Agent"] = KIMI_CODE_USER_AGENT
        merged_provider_config["custom_headers"] = merged_headers

        super().__init__(merged_provider_config, provider_settings)
