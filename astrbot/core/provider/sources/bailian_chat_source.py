from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial


@register_provider_adapter(
    "bailian_chat_completion",
    "阿里云百炼 Chat Completion 提供商适配器",
    provider_display_name="百炼",
)
class ProviderBailianChat(ProviderOpenAIOfficial):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        # 根据 Coding Plan 模式自动切换 API Base URL
        is_coding_plan = provider_config.get("bl_coding_plan", False)
        is_thinking = provider_config.get("bl_thinking", False)

        if is_coding_plan:
            provider_config["api_base"] = "https://coding.dashscope.aliyuncs.com/v1"
        else:
            provider_config["api_base"] = (
                "https://dashscope.aliyuncs.com/compatible-mode/v1"
            )

        if is_thinking and not provider_config.get("model"):
            if is_coding_plan:
                provider_config["model"] = "qwen3.5-plus"
            else:
                provider_config["model"] = "qwen-plus"

        super().__init__(provider_config, provider_settings)
        self.is_thinking = is_thinking

    def _finally_convert_payload(self, payloads: dict) -> None:
        """添加百炼特定参数"""
        super()._finally_convert_payload(payloads)

        if self.is_thinking:
            payloads["enable_thinking"] = True

    def _extract_reasoning_content(self, completion) -> str:
        """提取推理内容"""
        return super()._extract_reasoning_content(completion)
