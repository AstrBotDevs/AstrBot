from astrbot.core.agent.tool import ToolSet

from ..register import register_provider_adapter
from .openai_responses_source import ProviderOpenAIResponses
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

    def _maybe_inject_xai_search(self, payloads: dict) -> None:
        """当开启 xAI 原生搜索时，向请求体注入 Live Search 参数。

        - 仅在 provider_config.xai_native_search 为 True 时生效
        - 默认注入 {"mode": "auto"}
        """
        if not bool(self.provider_config.get("xai_native_search", False)):
            return
        # OpenAI SDK 不识别的字段会在 _query/_query_stream 中放入 extra_body
        payloads["search_parameters"] = {"mode": "auto"}

    def _finally_convert_payload(self, payloads: dict) -> None:
        self._maybe_inject_xai_search(payloads)
        super()._finally_convert_payload(payloads)


@register_provider_adapter("xai_responses", "xAI Responses API Provider Adapter")
class ProviderXAIResponses(ProviderOpenAIResponses):
    def _get_grouped_config(self, key: str) -> dict:
        config = self.provider_config.get(key)
        if isinstance(config, dict):
            return config
        return {}

    @staticmethod
    def _as_non_empty_str_list(value) -> list[str]:
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []
        return [
            item.strip() for item in value if isinstance(item, str) and item.strip()
        ]

    def _build_xai_web_search_tool(self) -> dict | None:
        config = self._get_grouped_config("xai_web_search_config")
        if not bool(config.get("enabled", False)):
            return None

        allowed_domains = self._as_non_empty_str_list(config.get("allowed_domains"))
        excluded_domains = self._as_non_empty_str_list(config.get("excluded_domains"))
        if allowed_domains and excluded_domains:
            raise ValueError(
                "xAI Responses web search cannot set both allowed_domains and "
                "excluded_domains."
            )

        tool = {"type": "web_search"}
        if allowed_domains:
            tool["filters"] = {"allowed_domains": allowed_domains}
        elif excluded_domains:
            tool["filters"] = {"excluded_domains": excluded_domains}
        if "enable_image_understanding" in config:
            tool["enable_image_understanding"] = bool(
                config.get("enable_image_understanding")
            )
        return tool

    def _build_xai_x_search_tool(self) -> dict | None:
        config = self._get_grouped_config("xai_x_search_config")
        if not bool(config.get("enabled", False)):
            return None
        allowed_x_handles = self._as_non_empty_str_list(config.get("allowed_x_handles"))
        excluded_x_handles = self._as_non_empty_str_list(
            config.get("excluded_x_handles")
        )
        tool = {"type": "x_search"}
        if allowed_x_handles:
            tool["allowed_x_handles"] = allowed_x_handles
        if excluded_x_handles:
            tool["excluded_x_handles"] = excluded_x_handles
        if "enable_image_understanding" in config:
            tool["enable_image_understanding"] = bool(
                config.get("enable_image_understanding")
            )
        if "enable_video_understanding" in config:
            tool["enable_video_understanding"] = bool(
                config.get("enable_video_understanding")
            )

        return tool

    def _build_response_tools(self, tools: ToolSet | None) -> list[dict]:
        response_tools: list[dict] = []
        xai_web_search = self._build_xai_web_search_tool()
        if xai_web_search:
            response_tools.append(xai_web_search)
        xai_x_search = self._build_xai_x_search_tool()
        if xai_x_search:
            response_tools.append(xai_x_search)
        response_tools.extend(self._responses_function_tools(tools))
        return response_tools
