from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial


@register_provider_adapter(
    "xai_chat_completion", "xAI Chat Completion Provider Adapter"
)
class ProviderXAI(ProviderOpenAIOfficial):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)

    def _maybe_inject_xai_search(self, payloads: dict):
        """当开启 xAI 原生搜索时，向请求体注入 Live Search 参数。

        - 仅在 provider_config.xai_native_search 为 True 时生效
        - 默认注入 {"mode": "auto"}
        """
        if not bool(self.provider_config.get("xai_native_search", False)):
            return
        # OpenAI SDK 不识别的字段会在 _query/_query_stream 中放入 extra_body
        payloads["search_parameters"] = {"mode": "auto"}

    def _finally_convert_payload(self, payloads: dict):
        self._maybe_inject_xai_search(payloads)
        super()._finally_convert_payload(payloads)
