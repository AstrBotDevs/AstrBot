from astrbot import logger
from astrbot.core.provider.func_tool_manager import FuncCall
from typing import List
from ..register import register_provider_adapter
from astrbot.core.provider.entities import LLMResponse
from .openai_source import ProviderOpenAIOfficial


@register_provider_adapter("zhipu_chat_completion", "智浦 Chat Completion 提供商适配器")
class ProviderZhipu(ProviderOpenAIOfficial):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
        default_persona=None,
    ) -> None:
        super().__init__(
            provider_config,
            provider_settings,
            default_persona,
        )

    async def text_chat(
        self,
        prompt: str,
        session_id: str = None,
        image_urls: List[str] = None,
        func_tool: FuncCall = None,
        contexts=None,
        system_prompt=None,
        model=None,
        **kwargs,
    ) -> LLMResponse:
        if contexts is None:
            contexts = []
        new_record = await self.assemble_context(prompt, image_urls)
        context_query = []

        context_query = [*contexts, new_record]

        model_cfgs: dict = self.provider_config.get("model_config", {})
        model = model or self.get_model()
        # glm-4v-flash 只支持一张图片
        if model.lower() == "glm-4v-flash" and image_urls and len(context_query) > 1:
            logger.debug("glm-4v-flash 只支持一张图片，将只保留最后一张图片")
            logger.debug(context_query)
            new_context_query_ = []
            for i in range(0, len(context_query) - 1, 2):
                if isinstance(context_query[i].get("content", ""), list):
                    continue
                new_context_query_.append(context_query[i])
                new_context_query_.append(context_query[i + 1])
            new_context_query_.append(context_query[-1])  # 保留最后一条记录
            context_query = new_context_query_
            logger.debug(context_query)

        if system_prompt:
            context_query.insert(0, {"role": "system", "content": system_prompt})

        payloads = {"messages": context_query, **model_cfgs}
        try:
            llm_response = await self._query(payloads, func_tool)
            return llm_response
        except Exception as e:
            if "maximum context length" in str(e):
                retry_cnt = 10
                while retry_cnt > 0:
                    logger.warning(
                        f"请求失败：{e}。上下文长度超过限制。尝试弹出最早的记录然后重试。"
                    )
                    try:
                        self.pop_record(session_id)
                        llm_response = await self._query(payloads, func_tool)
                        break
                    except Exception as e:
                        if "maximum context length" in str(e):
                            retry_cnt -= 1
                        else:
                            raise e
            else:
                raise e
