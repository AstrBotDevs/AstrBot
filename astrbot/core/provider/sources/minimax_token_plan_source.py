import httpx

from astrbot import logger
from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic

from ..register import register_provider_adapter

_MINIMAX_TOKEN_PLAN_FALLBACK_MODELS = ("MiniMax-M3", "MiniMax-M2.7")


@register_provider_adapter(
    "minimax_token_plan",
    "MiniMax Token Plan Provider Adapter",
)
class ProviderMiniMaxTokenPlan(ProviderAnthropic):
    """MiniMax Token Plan provider.

    The model list is fetched dynamically from the MiniMax API's /v1/models
    endpoint, so newly released models are automatically discovered without
    a code change. The default model is MiniMax-M3, the current flagship.
    Current models remain available when dynamic discovery is unavailable.
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

        Returns:
            The dynamically discovered models, or the current fallback models
            when discovery is unavailable.
        """
        key = self.chosen_api_key
        if not key:
            logger.warning("No API key configured for MiniMax Token Plan.")
            return list(_MINIMAX_TOKEN_PLAN_FALLBACK_MODELS)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.minimaxi.com/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                items = data.get("data", []) if isinstance(data, dict) else []
                if not isinstance(items, list):
                    items = []
                models = [
                    model["id"]
                    for model in items
                    if isinstance(model, dict) and isinstance(model.get("id"), str)
                ]
                if models:
                    return models
                logger.warning("MiniMax model discovery returned no models.")
        except (httpx.HTTPError, ValueError) as e:
            logger.error(f"Failed to fetch MiniMax model list: {e}")
        return list(_MINIMAX_TOKEN_PLAN_FALLBACK_MODELS)
