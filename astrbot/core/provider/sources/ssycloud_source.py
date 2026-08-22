from openai._exceptions import NotFoundError

from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial
from .request_retry import retry_provider_request


@register_provider_adapter(
    "ssycloud_chat_completion",
    "SSYCloud Chat Completion Provider Adapter",
)
class ProviderSSYCloud(ProviderOpenAIOfficial):
    """SSYCloud provider using its OpenAI-compatible Chat Completions API."""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        """Initialize the SSYCloud client with provider defaults.

        Args:
            provider_config: AstrBot provider source configuration.
            provider_settings: Global provider settings.
        """
        if not provider_config.get("api_base"):
            provider_config["api_base"] = "https://router.shengsuanyun.com/api/v1"
        custom_headers = provider_config.get("custom_headers")
        if not isinstance(custom_headers, dict):
            custom_headers = {}
            provider_config["custom_headers"] = custom_headers
        custom_headers.setdefault("X-Title", "AstrBot")
        super().__init__(provider_config, provider_settings)

    async def get_models(self) -> list[str]:
        """Return models compatible with the Chat Completions API.

        Returns:
            Sorted model IDs. Models without ``support_apis`` metadata are kept
            for compatibility with older SSYCloud responses.

        Raises:
            Exception: If the SSYCloud model catalog endpoint is unavailable.
        """
        try:
            response = await retry_provider_request(
                "SSYCloud",
                lambda: self.client.models.list(),
            )
            model_ids: list[str] = []
            for model in response.data:
                support_apis = getattr(model, "support_apis", None)
                if support_apis is None:
                    model_extra = getattr(model, "model_extra", None)
                    if isinstance(model_extra, dict):
                        support_apis = model_extra.get("support_apis")
                if not isinstance(support_apis, list) or (
                    "/v1/chat/completions" in support_apis
                ):
                    model_ids.append(model.id)
            return sorted(model_ids)
        except NotFoundError as exc:
            raise Exception(f"Failed to fetch SSYCloud model list: {exc}") from exc
