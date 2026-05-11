from astrbot import logger
from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic

from ..register import register_provider_adapter

MINIMAX_TOKEN_PLAN_MODELS = [
    "MiniMax-M2.7",
    "MiniMax-M2.7-highspeed",
    "MiniMax-M2.5",
    "MiniMax-M2.5-highspeed",
    "MiniMax-M2.1",
    "MiniMax-M2.1-highspeed",
    "MiniMax-M2",
]


@register_provider_adapter(
    "minimax_token_plan",
    "MiniMax Token Plan Provider Adapter",
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
            logger.warning(
                f"Configured model {configured_model!r} is not in the known "
                f"Token Plan model list "
                f"({', '.join(MINIMAX_TOKEN_PLAN_MODELS)}). "
                f"The model may still work if your plan supports it. "
                f"If you encounter errors, please check your plan's "
                f"model availability."
            )

        self.set_model(configured_model)

    async def get_models(self) -> list[str]:
        """Return the hard-coded known model list because Token Plan cannot fetch it dynamically."""
        return MINIMAX_TOKEN_PLAN_MODELS.copy()
