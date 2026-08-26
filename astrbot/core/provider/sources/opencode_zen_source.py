from ..register import register_provider_adapter
from .opencode_go_source import ProviderOpenCodeGo

OPENCODE_ZEN_API_BASE = "https://opencode.ai/zen/v1"
OPENCODE_ZEN_MODEL_PREFIX = "opencode/"
OPENCODE_ZEN_DEFAULT_MODEL = "kimi-k2.6"


@register_provider_adapter(
    "opencode_zen_chat_completion",
    "OpenCode Zen Provider Adapter",
)
class ProviderOpenCodeZen(ProviderOpenCodeGo):
    API_BASE = OPENCODE_ZEN_API_BASE
    MODEL_PREFIX = OPENCODE_ZEN_MODEL_PREFIX
    DEFAULT_MODEL = OPENCODE_ZEN_DEFAULT_MODEL
    PROVIDER_NAME = "OpenCode Zen"
    UNSUPPORTED_MODEL_ENDPOINTS = {}
    UNSUPPORTED_MODEL_PREFIX_ENDPOINTS = (
        ("claude-", "/v1/messages"),
        ("qwen", "/v1/messages"),
        ("gemini-", "/v1/models/{model}"),
        ("gpt-", "/v1/responses"),
        ("grok-", "/v1/responses"),
    )
