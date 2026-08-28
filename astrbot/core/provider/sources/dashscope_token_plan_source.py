"""DashScope (Aliyun Bailian) Token Plan chat completion provider.

Routes Token Plan subscriptions through DashScope's Anthropic-compatible
endpoint with a Claude Code User-Agent, mirroring how Kimi/MiniMax/Xiaomi
Token Plan adapters work.
"""

from ..register import register_provider_adapter
from .anthropic_source import ProviderAnthropic

DASHSCOPE_API_BASE = "https://token-plan.cn-beijing.maas.aliyuncs.com/apps/anthropic"
DASHSCOPE_DEFAULT_MODEL = "qwen3.8-max"
DASHSCOPE_USER_AGENT = "claude-code/0.1.0"


@register_provider_adapter(
    "dashscope_token_plan_chat_completion",
    "DashScope Token Plan Provider Adapter",
)
class ProviderDashScopeTokenPlan(ProviderAnthropic):
    """DashScope Token Plan provider via the Anthropic-compatible endpoint."""

    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        merged_provider_config = dict(provider_config)
        if not str(merged_provider_config.get("api_base", "")).strip():
            merged_provider_config["api_base"] = DASHSCOPE_API_BASE
        if not str(merged_provider_config.get("model", "")).strip():
            merged_provider_config["model"] = DASHSCOPE_DEFAULT_MODEL
        merged_provider_config["custom_headers"] = self._resolve_custom_headers(
            merged_provider_config,
            required_headers={"User-Agent": DASHSCOPE_USER_AGENT},
        )

        super().__init__(merged_provider_config, provider_settings)
