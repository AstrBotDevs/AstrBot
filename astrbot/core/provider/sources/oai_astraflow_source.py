from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial

# Astraflow (UCloud / 优刻得 优模方舟 / UModelverse) is an OpenAI-compatible AI
# model aggregation platform that supports 200+ models.
#
# Endpoints:
#   - Global: https://api-us-ca.umodelverse.ai/v1   (env var: ASTRAFLOW_API_KEY)
#   - China:  https://api.modelverse.cn/v1          (env var: ASTRAFLOW_CN_API_KEY)
#
# Because the API is OpenAI-compatible, this adapter only needs to set a
# default ``api_base``. Users may still override it via provider config
# (e.g. switching to the China endpoint).
ASTRAFLOW_DEFAULT_API_BASE = "https://api-us-ca.umodelverse.ai/v1"


@register_provider_adapter(
    "astraflow_chat_completion",
    "Astraflow (UModelverse) Chat Completion Provider Adapter",
)
class ProviderAstraflow(ProviderOpenAIOfficial):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        # Apply the default Astraflow base URL when the user has not
        # explicitly configured one. This makes the adapter work out of
        # the box for the global endpoint while still allowing users to
        # override ``api_base`` (e.g. to point at the China endpoint
        # https://api.modelverse.cn/v1).
        if not provider_config.get("api_base"):
            provider_config["api_base"] = ASTRAFLOW_DEFAULT_API_BASE
        super().__init__(provider_config, provider_settings)
