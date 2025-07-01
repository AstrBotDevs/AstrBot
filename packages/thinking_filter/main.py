import re
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.provider import LLMResponse
from openai.types.chat.chat_completion import ChatCompletion


@register(
    "thinking_filter",
    "Soulter",
    "可选择是否过滤推理模型的思考内容",
    "1.0.0",
    "https://astrbot.app",
)
class R1Filter(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.display_reasoning_text = (
            self.context.get_config()
            .get("provider_settings", {})
            .get("display_reasoning_text", False)
        )

    @filter.on_llm_response()
    async def resp(self, event: AstrMessageEvent, response: LLMResponse):
        if self.display_reasoning_text:
            if (
                response
                and response.raw_completion
                and isinstance(response.raw_completion, ChatCompletion)
            ):
                if (
                    len(response.raw_completion.choices)
                    and response.raw_completion.choices[0].message
                ):
                    message = response.raw_completion.choices[0].message
                    reasoning_content = ""  # 初始化 reasoning_content

                    # 检查 Groq deepseek-r1-distill-llama-70b模型的 'reasoning' 属性
                    if hasattr(message, "reasoning") and message.reasoning:
                        reasoning_content = message.reasoning
                    # 检查 DeepSeek deepseek-reasoner模型的 'reasoning_content'
                    elif (
                        hasattr(message, "reasoning_content")
                        and message.reasoning_content
                    ):
                        reasoning_content = message.reasoning_content

                    if reasoning_content:
                        response.completion_text = (
                            f"🤔思考：{reasoning_content}\n\n{message.content}"
                        )
                    else:
                        response.completion_text = message.content

        else:
            # DeepSeek 官方的模型的思考存在了 reason_content 字段因此不需要过滤
            completion_text = response.completion_text
            # 适配 ollama deepseek-r1 模型
            if r"<think>" in completion_text or r"</think>" in completion_text:
                completion_text = re.sub(
                    r"<think>.*?</think>", "", completion_text, flags=re.DOTALL
                ).strip()
                # 可能有单标签情况
                completion_text = (
                    completion_text.replace(r"<think>", "")
                    .replace(r"</think>", "")
                    .strip()
                )
            response.completion_text = completion_text
