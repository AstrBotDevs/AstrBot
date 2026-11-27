from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic

from ..register import register_provider_adapter
from .minimax_models import MINIMAX_SUBSCRIPTION_MODELS, is_minimax_api


@register_provider_adapter(
    "minimax_token_plan",
    "MiniMax Token Plan Provider Adapter",
)
class ProviderMiniMaxTokenPlan(ProviderAnthropic):
    """MiniMax subscription provider with the documented M Plan text model.

    Subscription eligibility is separate from the general API model catalog.
    Explicit saved and custom model IDs remain available for requests.
    """

    def __init__(
        self,
        provider_config,
        provider_settings,
    ) -> None:
        # Keep configured regional and custom endpoints; default to China.
        provider_config["api_base"] = (
            provider_config.get("api_base") or "https://api.minimax.cn/anthropic"
        )
        # MiniMax Token Plan requires the Authorization: Bearer <token> header.
        key = provider_config.get("key", "")
        actual_key = (key[0] if key else "") if isinstance(key, list) else key
        provider_config.setdefault("custom_headers", {})["Authorization"] = (
            f"Bearer {actual_key}"
        )

        super().__init__(
            provider_config,
            provider_settings,
        )

        configured_model = provider_config.get("model", MINIMAX_SUBSCRIPTION_MODELS[0])
        self.set_model(configured_model)

    async def get_models(self) -> list[str]:
        """Offer documented subscription choices without requiring an API key."""
        if is_minimax_api(self.base_url):
            return list(MINIMAX_SUBSCRIPTION_MODELS)
        return await super().get_models()
