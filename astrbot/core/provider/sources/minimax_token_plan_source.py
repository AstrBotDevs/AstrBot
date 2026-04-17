from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic

from ..register import register_provider_adapter

MINIMAX_TOKEN_PLAN_MODELS = [
    "MiniMax-M2.7",
    "MiniMax-M2.5",
    "MiniMax-M2.1",
    "MiniMax-M2",
]


@register_provider_adapter(
    "minimax_token_plan",
    "MiniMax Token Plan Provider Adapter",
    default_config_tmpl={
        "key": "",
    },
    provider_display_name="MiniMax Token Plan",
)
class ProviderMiniMaxTokenPlan(ProviderAnthropic):
    """MiniMax Token Plan provider.

    The Token Plan API does not support the /models endpoint, so get_models()
    returns a hard-coded model list. This is a Token Plan API limitation.
    See https://github.com/AstrBotDevs/AstrBot/issues/7585 for details.
    """

    def __init__(
        self,
        provider_config,
        provider_settings,
    ) -> None:
        # Keep api_base fixed; Token Plan users do not need to configure it.
        provider_config["api_base"] = "https://api.minimaxi.com/anthropic"
        # MiniMax Token Plan requires the Authorization: Bearer <token> header.
        key = provider_config.get("key", "")
        actual_key = key[0] if isinstance(key, list) else key
        provider_config.setdefault("custom_headers", {})["Authorization"] = (
            f"Bearer {actual_key}"
        )

        super().__init__(
            provider_config,
            provider_settings,
        )

        configured_model = provider_config.get("model", "MiniMax-M2.7")
        if configured_model not in MINIMAX_TOKEN_PLAN_MODELS:
            raise ValueError(
                f"Unsupported model: {configured_model!r}. "
                f"Supported models: {', '.join(MINIMAX_TOKEN_PLAN_MODELS)}"
            )

        self.set_model(configured_model)

    async def get_models(self) -> list[str]:
        """Return the hard-coded known model list because Token Plan cannot fetch it dynamically."""
        return MINIMAX_TOKEN_PLAN_MODELS.copy()
