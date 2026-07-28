import httpx

from astrbot import logger
from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic

from ..register import register_provider_adapter

# Current MiniMax Token Plan model IDs. Returned as a fallback when the
# dynamic /v1/models fetch is unavailable (no API key configured yet or a
# transient network error) so the model picker can still surface the current
# models. The dynamic list remains authoritative whenever it succeeds.
_MINIMAX_TOKEN_PLAN_FALLBACK_MODELS = ["MiniMax-M3", "MiniMax-M2.7"]


@register_provider_adapter(
    "minimax_token_plan",
    "MiniMax Token Plan Provider Adapter",
)
class ProviderMiniMaxTokenPlan(ProviderAnthropic):
    """MiniMax Token Plan provider.

    The model list is fetched dynamically from the MiniMax API's /v1/models
    endpoint, so newly released models are automatically discovered without
    a code change. The default model is MiniMax-M3, the current flagship.
    When the dynamic fetch is unavailable, a small fallback list of current
    model IDs is returned so the dashboard is never empty.
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

        configured_model = provider_config.get("model", "MiniMax-M3")
        self.set_model(configured_model)

    async def get_models(self) -> list[str]:
        """Fetch available models from the MiniMax API.

        Returns the current fallback model IDs when the dynamic fetch is
        unavailable (no API key or a network/API error) so the model picker
        is never empty. The dynamic list is authoritative when it succeeds.
        """
        key = self.chosen_api_key
        if not key:
            logger.warning("No API key configured for MiniMax Token Plan.")
            return _MINIMAX_TOKEN_PLAN_FALLBACK_MODELS.copy()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.minimaxi.com/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                models = [m["id"] for m in data.get("data", [])]
                if models:
                    return models
                logger.warning("MiniMax /v1/models returned an empty list.")
                return _MINIMAX_TOKEN_PLAN_FALLBACK_MODELS.copy()
        except Exception as e:
            logger.error(f"Failed to fetch MiniMax model list: {e}")
            return _MINIMAX_TOKEN_PLAN_FALLBACK_MODELS.copy()
