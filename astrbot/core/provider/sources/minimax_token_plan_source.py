import httpx

from astrbot import logger
from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic

from ..register import register_provider_adapter


@register_provider_adapter(
    "minimax_token_plan",
    "MiniMax Token Plan Provider Adapter",
)
class ProviderMiniMaxTokenPlan(ProviderAnthropic):
    """MiniMax Token Plan provider.

    The model list is fetched dynamically from the MiniMax API's /v1/models
    endpoint, so newly released models are automatically discovered without
    a code change. The default model is MiniMax-M3, the current flagship.
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
        """Dynamically fetch available models from the MiniMax API."""
        key = self.chosen_api_key
        if not key:
            logger.warning("No API key configured for MiniMax Token Plan.")
            return []
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.minimaxi.com/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                return [m["id"] for m in data.get("data", [])]
        except Exception as e:
            logger.error(f"Failed to fetch MiniMax model list: {e}")
            return []
