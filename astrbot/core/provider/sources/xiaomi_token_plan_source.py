from astrbot import logger
from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic

from ..register import register_provider_adapter

XIAOMI_TOKEN_PLAN_MODELS = [
    "mimo-v2.5-pro",
    "mimo-v2.5",
    "mimo-v2-pro",
    "mimo-v2-omni",
    "mimo-v2-flash",
]


@register_provider_adapter(
    "xiaomi_token_plan",
    "Xiaomi Token Plan 提供商适配器",
    default_config_tmpl={
        "id": "xiaomi-token-plan",
        "provider": "xiaomi-token-plan",
        "type": "xiaomi_token_plan",
        "provider_type": "chat_completion",
        "enable": True,
        "key": [],
        "api_base": "https://token-plan-cn.xiaomimimo.com/anthropic",
        "timeout": 120,
        "proxy": "",
        "custom_headers": {"User-Agent": "claude-code/0.1.0"},
        "custom_extra_body": {"temperature": 1, "top_p": 0.95},
        "anth_thinking_config": {"type": "", "budget": 0, "effort": ""},
    },
)
class ProviderXiaomiTokenPlan(ProviderAnthropic):
    """Xiaomi Token Plan provider.

    The Token Plan API uses Anthropic-compatible endpoint with Bearer token auth.
    See https://platform.xiaomimimo.com/docs/tokenplan/quick-access
    """

    def __init__(
        self,
        provider_config,
        provider_settings,
    ) -> None:
        # Keep api_base fixed; Token Plan users do not need to configure it.
        provider_config["api_base"] = "https://token-plan-cn.xiaomimimo.com/anthropic"

        # Xiaomi Token Plan requires the Authorization: Bearer <token> header.
        key = provider_config.get("key", "")
        actual_key = key[0] if isinstance(key, list) else key
        provider_config.setdefault("custom_headers", {})["Authorization"] = (
            f"Bearer {actual_key}"
        )

        super().__init__(
            provider_config,
            provider_settings,
        )

        configured_model = provider_config.get("model", "mimo-v2.5")
        if configured_model not in XIAOMI_TOKEN_PLAN_MODELS:
            logger.warning(
                f"Configured model {configured_model!r} is not in the known "
                f"Token Plan model list "
                f"({', '.join(XIAOMI_TOKEN_PLAN_MODELS)}). "
                f"The model may still work if your plan supports it. "
                f"If you encounter errors, please check your plan's "
                f"model availability."
            )

        self.set_model(configured_model)

    async def get_models(self) -> list[str]:
        """Return the hard-coded known model list because Token Plan cannot fetch it dynamically."""
        return XIAOMI_TOKEN_PLAN_MODELS.copy()
