from astrbot.core.agent.tool import ToolSet
from astrbot.core.provider.entities import LLMResponse

from ..entities import ProviderType
from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial


@register_provider_adapter(
    "deepseek_chat_completion",
    "DeepSeek API Chat Completion 提供商适配器",
    ProviderType.CHAT_COMPLETION,
    default_config_tmpl={
        "id": "deepseek",
        "provider": "deepseek",
        "type": "deepseek_chat_completion",
        "provider_type": "chat_completion",
        "enable": True,
        "key": [],
        "api_base": "https://api.deepseek.com/v1",
        "timeout": 120,
        "custom_headers": {},
        "hint": "DeepSeek 官方 API，支持思考模式。",
    },
    provider_display_name="DeepSeek",
)
class ProviderDeepSeek(ProviderOpenAIOfficial):
    def _should_enable_thinking(self, payloads: dict) -> bool:
        """判断是否应该启用思考模式

        规则：
        1. deepseek-chat 模型无条件关闭思维链
        2. deepseek-reasoner 模型无条件开启思维链
        3. 其他模型根据 ds_thinking_tool_call 配置决定
        """
        model = payloads.get("model", "").lower()

        # deepseek-chat 强制关闭
        if "deepseek-chat" in model:
            return False

        # deepseek-reasoner 强制开启
        if "deepseek-reasoner" in model or "reasoner" in model:
            return True

        # 其他模型根据配置决定
        return self.provider_config.get("ds_thinking_tool_call", False)

    async def _query_stream(
        self,
        payloads: dict,
        tools: ToolSet | None,
    ):
        # 判断是否启用思考模式
        ds_thinking_enabled = self._should_enable_thinking(payloads)

        if ds_thinking_enabled:
            messages = payloads.get("messages", [])

            # DeepSeek API 要求:思考模式下每条助手消息必须有 reasoning_content
            # 先确保每条助手消息都有这个字段
            for msg in messages:
                if msg.get("role") == "assistant":
                    if "reasoning_content" not in msg:
                        # 工具调用消息等特殊消息初始化为空字符串
                        msg["reasoning_content"] = ""

            # 清理历史消息中的 reasoning_content
            # 只有最后一条是 user 时才清空（说明是新问题）
            if messages and messages[-1].get("role") == "user":
                for msg in messages:
                    if msg.get("role") == "assistant" and "reasoning_content" in msg:
                        msg["reasoning_content"] = ""

            # 添加 thinking 参数（父类会自动把它放到 extra_body）
            payloads["thinking"] = {"type": "enabled"}

        # 调用父类方法
        async for response in super()._query_stream(payloads, tools):
            yield response

    async def _query(
        self,
        payloads: dict,
        tools: ToolSet | None,
    ) -> LLMResponse:
        # 判断是否启用思考模式
        ds_thinking_enabled = self._should_enable_thinking(payloads)

        if ds_thinking_enabled:
            messages = payloads.get("messages", [])

            # DeepSeek API 要求：思考模式下每条助手消息必须有 reasoning_content
            # 先确保每条助手消息都有这个字段
            for msg in messages:
                if msg.get("role") == "assistant":
                    if "reasoning_content" not in msg:
                        # 工具调用消息等特殊消息初始化为空字符串
                        msg["reasoning_content"] = ""

            # 清理历史消息中的 reasoning_content
            # 只有最后一条是 user 时才清空（说明是新问题）
            if messages and messages[-1].get("role") == "user":
                for msg in messages:
                    if msg.get("role") == "assistant" and "reasoning_content" in msg:
                        msg["reasoning_content"] = ""

            # 添加 thinking 参数
            payloads["thinking"] = {"type": "enabled"}

        # 调用父类方法
        return await super()._query(payloads, tools)
