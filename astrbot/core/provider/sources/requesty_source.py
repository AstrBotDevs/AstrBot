from openai.pagination import AsyncPage
from openai.types import Model

from astrbot import logger

from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial
from .request_retry import retry_provider_request


@register_provider_adapter(
    "requesty_chat_completion", "Requesty Chat Completion Provider Adapter"
)
class ProviderRequesty(ProviderOpenAIOfficial):
    """Requesty provider using its OpenAI-compatible Chat Completions API."""

    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        if not provider_config.get("api_base"):
            provider_config["api_base"] = "https://router.requesty.ai/v1"
        super().__init__(provider_config, provider_settings)
        # Reference to: https://docs.requesty.ai
        self.client._custom_headers["HTTP-Referer"] = (  # type: ignore
            "https://github.com/AstrBotDevs/AstrBot"
        )
        self.client._custom_headers["X-Title"] = "AstrBot"  # type: ignore

    async def get_models(self) -> list[str]:
        """Return Requesty managed model IDs first, then the full model catalog.

        Managed IDs (for example ``claude-sonnet-5``) are Requesty maintained
        routing policies and are used as-is in the ``model`` field. Catalog IDs
        use the ``vendor/model`` format. Each list is fetched independently so
        one failing endpoint does not hide the other.

        Returns:
            Deduplicated model IDs, managed IDs first.

        Raises:
            Exception: If neither model list endpoint is available.
        """
        model_ids: list[str] = []
        last_error: Exception | None = None
        for path in ("/models/managed", "/models"):
            try:
                page = await retry_provider_request(
                    "Requesty",
                    lambda path=path: self.client.get_api_list(
                        path, page=AsyncPage[Model], model=Model
                    ),
                )
            except Exception as exc:
                logger.warning(f"Failed to fetch Requesty models from {path}: {exc}")
                last_error = exc
                continue
            # Model IDs are rendered in the WebUI, so skip any with control characters.
            model_ids.extend(
                sorted(m.id for m in page.data if m.id and m.id.isprintable())
            )
        if not model_ids and last_error is not None:
            raise Exception(
                f"Failed to fetch Requesty model list: {last_error}"
            ) from last_error
        return list(dict.fromkeys(model_ids))
