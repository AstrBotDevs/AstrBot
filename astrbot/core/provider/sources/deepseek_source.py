from collections.abc import AsyncGenerator

from openai.lib.streaming.chat._completions import ChatCompletionStreamState
from openai.types.chat.chat_completion import ChatCompletion

import astrbot.core.message.components as Comp
from astrbot import logger
from astrbot.core.agent.tool import ToolSet
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import LLMResponse

from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial


@register_provider_adapter(
    "deepseek_chat_completion",
    "DeepSeek Chat Completion 提供商适配器",
    prompt_renderer_family="openai",
)
class ProviderDeepSeek(ProviderOpenAIOfficial):
    def _deepseek_omits_tool_choice(self, payloads: dict) -> bool:
        model = payloads.get("model", "").lower()
        base_url = getattr(self.client, "base_url", None)
        host = getattr(base_url, "host", "") or ""
        return (
            model.startswith("deepseek-reasoner")
            or model.startswith("deepseek-v4")
            or "api.deepseek.com" in host
        )

    def _normalize_deepseek_tool_choice(self, payloads: dict) -> None:
        if not self._deepseek_omits_tool_choice(payloads):
            return
        tool_choice = payloads.pop("tool_choice", None)
        if tool_choice and tool_choice != "auto":
            logger.warning(
                f"{self.get_model()} 思考模式不支持 tool_choice={tool_choice!r}，"
                "已改为 DeepSeek 默认工具选择策略。"
            )

    def _apply_provider_specific_extra_body_overrides(self, extra_body: dict) -> None:
        super()._apply_provider_specific_extra_body_overrides(extra_body)
        extra_body.pop("tool_choice", None)

    async def _handle_api_error(
        self,
        e: Exception,
        payloads: dict,
        context_query: list,
        func_tool: ToolSet | None,
        chosen_key: str,
        available_api_keys: list[str],
        retry_cnt: int,
        max_retries: int,
        image_fallback_used: bool = False,
    ) -> tuple:
        if "thinking mode does not support this tool_choice" in str(e).lower():
            logger.warning(
                f"{self.get_model()} 思考模式不支持当前 tool_choice，已移除该参数并重试。"
            )
            payloads.pop("tool_choice", None)
            return (
                False,
                chosen_key,
                available_api_keys,
                payloads,
                context_query,
                func_tool,
                image_fallback_used,
            )
        return await super()._handle_api_error(
            e,
            payloads,
            context_query,
            func_tool,
            chosen_key,
            available_api_keys,
            retry_cnt,
            max_retries,
            image_fallback_used=image_fallback_used,
        )

    async def _query(self, payloads: dict, tools: ToolSet | None) -> LLMResponse:
        if tools:
            tool_list = tools.get_func_desc_openai_style(
                omit_empty_parameter_field=False,
            )
            if tool_list:
                payloads["tools"] = tool_list

        self._normalize_deepseek_tool_choice(payloads)

        extra_body = {}
        to_del = []
        for key in payloads:
            if key not in self.default_params:
                extra_body[key] = payloads[key]
                to_del.append(key)
        for key in to_del:
            del payloads[key]

        custom_extra_body = self.provider_config.get("custom_extra_body", {})
        if isinstance(custom_extra_body, dict):
            extra_body.update(custom_extra_body)
        self._apply_provider_specific_extra_body_overrides(extra_body)

        self._sanitize_assistant_messages(payloads)

        completion = await self.client.chat.completions.create(
            **payloads,
            stream=False,
            extra_body=extra_body,
        )

        if not isinstance(completion, ChatCompletion):
            raise Exception(
                f"API 返回的 completion 类型错误：{type(completion)}: {completion}。",
            )

        logger.debug(f"completion: {completion}")

        return await self._parse_openai_completion(completion, tools)

    async def _query_stream(
        self,
        payloads: dict,
        tools: ToolSet | None,
    ) -> AsyncGenerator[LLMResponse, None]:
        if tools:
            tool_list = tools.get_func_desc_openai_style(
                omit_empty_parameter_field=False,
            )
            if tool_list:
                payloads["tools"] = tool_list

        self._normalize_deepseek_tool_choice(payloads)

        extra_body = {}

        custom_extra_body = self.provider_config.get("custom_extra_body", {})
        if isinstance(custom_extra_body, dict):
            extra_body.update(custom_extra_body)

        to_del = []
        for key in payloads:
            if key not in self.default_params:
                extra_body[key] = payloads[key]
                to_del.append(key)
        for key in to_del:
            del payloads[key]
        self._apply_provider_specific_extra_body_overrides(extra_body)
        self._sanitize_assistant_messages(payloads)

        stream = await self.client.chat.completions.create(
            **payloads,
            stream=True,
            extra_body=extra_body,
            stream_options={"include_usage": True},
        )

        llm_response = LLMResponse("assistant", is_chunk=True)
        state = ChatCompletionStreamState()

        async for chunk in stream:
            choice = chunk.choices[0] if chunk.choices else None
            delta = choice.delta if choice else None

            if delta and (dtcs := delta.tool_calls):
                for idx, tc in enumerate(dtcs):
                    if tc.function and tc.function.arguments:
                        tc.type = "function"
                    if not hasattr(tc, "index") or tc.index is None:
                        tc.index = idx

            if delta is not None or chunk.usage:
                try:
                    state.handle_chunk(chunk)
                except Exception as e:
                    logger.error("Saving chunk state error: " + str(e))

            reasoning = self._extract_reasoning_content(chunk)
            has_delta = False
            llm_response.id = chunk.id
            llm_response.reasoning_content = None
            llm_response.completion_text = ""
            if reasoning is not None:
                llm_response.reasoning_content = reasoning
                has_delta = True
            if delta and delta.content:
                completion_text = self._normalize_content(delta.content, strip=False)
                llm_response.result_chain = MessageChain(
                    chain=[Comp.Plain(completion_text)],
                )
                has_delta = True
            if chunk.usage:
                llm_response.usage = self._extract_usage(chunk.usage)
            elif choice and (choice_usage := getattr(choice, "usage", None)):
                llm_response.usage = self._extract_usage(choice_usage)
                state.current_completion_snapshot.usage = choice_usage
            if has_delta:
                yield llm_response

        try:
            final_completion = state.get_final_completion()
            llm_response = await self._parse_openai_completion(final_completion, tools)
            yield llm_response
        except Exception as e:
            logger.error("get_final_completion error: " + str(e))
            return
