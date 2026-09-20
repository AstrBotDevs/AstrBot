import httpx

from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial


@register_provider_adapter(
    "dots_chat_completion", "Dots Chat Completion Provider Adapter"
)
class ProviderDots(ProviderOpenAIOfficial):
    """Use the Dots OpenAI-compatible API."""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        """Initialize the provider with Dots defaults.

        Args:
            provider_config: Provider source and model configuration.
            provider_settings: Global provider settings.
        """
        provider_config = provider_config.copy()
        if not provider_config.get("api_base"):
            provider_config["api_base"] = "https://note3-prev-api.askdiandian.com/v1"
        provider_config.setdefault("model", "dots3-note-prev")
        super().__init__(provider_config, provider_settings)

    def _create_http_client(self, provider_config: dict) -> httpx.AsyncClient:
        """Translate the SDK's per-request key to Dots authentication.

        Args:
            provider_config: Provider configuration, including proxy settings.

        Returns:
            HTTP client with a request hook that follows SDK key rotation.
        """
        client = super()._create_http_client(provider_config)

        async def add_api_key(request: httpx.Request) -> None:
            """Set the API key from the already-built request.

            Args:
                request: Outgoing SDK request with its selected bearer key.
            """
            # Read the request rather than mutable client state during concurrent calls.
            authorization = request.headers.get("Authorization", "")
            if authorization.startswith("Bearer "):
                request.headers["api-key"] = authorization.removeprefix("Bearer ")
                del request.headers["Authorization"]

        client.event_hooks["request"].append(add_api_key)
        return client
