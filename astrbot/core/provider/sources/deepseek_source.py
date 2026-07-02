from collections.abc import AsyncGenerator
from typing import Any

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
)
class ProviderDeepSeek(ProviderOpenAIOfficial):
    _FORCE_OMIT_TOOL_CHOICE_KEY = "_deepseek_force_omit_tool_choice"

    @staticmethod
    def _extract_thinking_type(source: Any) -> str | None:
        if not isinstance(source, dict):
            return None
        thinking = source.get("thinking")
        if not isinstance(thinking, dict):
            return None
        thinking_type = thinking.get("type")
        if not isinstance(thinking_type, str):
            return None
        normalized = thinking_type.strip().lower()
        return normalized or None

    def _is_thinking_enabled(
        self,
        payloads: dict,
        extra_body: dict[str, Any] | None = None,
    ) -> bool:
        for source in (
            payloads,
            extra_body,
            self.provider_config.get("custom_extra_body", {}),
        ):
            thinking_type = self._extract_thinking_type(source)
            if thinking_type == "enabled":
                return True
            if thinking_type == "disabled":
                return False
        # DeepSeek documents thinking mode as enabled by default.
        return True

    def _is_thinking_tool_choice_error(self, error: Exception) -> bool:
        for candidate in self._extract_error_text_candidates(error):
            lowered = candidate.lower()
            if "tool_choice" in lowered and (
                "thinking" in lowered or "reasoning" in lowered
            ):
                return True
        return False

    def _normalize_tool_choice(
        self,
        payloads: dict,
        extra_body: dict[str, Any],
        *,
        thinking_enabled: bool,
        force_omit: bool = False,
    ) -> None:
        if not thinking_enabled and not force_omit:
            return

        payload_tool_choice = payloads.pop("tool_choice", None)
        extra_tool_choice = extra_body.pop("tool_choice", None)
        removed_tool_choice = (
            payload_tool_choice
            if payload_tool_choice is not None
            else extra_tool_choice
        )
        if removed_tool_choice and removed_tool_choice != "auto":
            logger.warning(
                f"{self.get_model()} 思考模式不支持 tool_choice={removed_tool_choice!r}，"
                "已改为 DeepSeek 默认工具选择策略。"
            )

    def _prepare_request(
        self,
        payloads: dict,
        tools: ToolSet | None,
    ) -> tuple[dict, dict[str, Any], ToolSet | None]:
        if tools:
            tool_list = tools.get_func_desc_openai_style(
                omit_empty_parameter_field=False,
            )
            if tool_list:
                payloads["tools"] = tool_list

        extra_body: dict[str, Any] = {}
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

        force_omit = bool(payloads.pop(self._FORCE_OMIT_TOOL_CHOICE_KEY, False))
        thinking_enabled = self._is_thinking_enabled(payloads, extra_body)
        self._normalize_tool_choice(
            payloads,
            extra_body,
            thinking_enabled=thinking_enabled,
            force_omit=force_omit,
        )
        self._sanitize_assistant_messages(payloads)
        return payloads, extra_body, tools

    def _finally_convert_payload(self, payloads: dict) -> None:
        assistant_messages_without_reasoning = set()
        if not self._is_thinking_enabled(payloads):
            for idx, message in enumerate(payloads.get("messages", [])):
                if (
                    isinstance(message, dict)
                    and message.get("role") == "assistant"
                    and "reasoning_content" not in message
                ):
                    assistant_messages_without_reasoning.add(idx)

        super()._finally_convert_payload(payloads)

        if not assistant_messages_without_reasoning:
            return

        for idx in assistant_messages_without_reasoning:
            message = payloads["messages"][idx]
            if message.get("reasoning_content") == "":
                message.pop("reasoning_content", None)

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
        if self._is_thinking_tool_choice_error(e):
            logger.warning(
                f"{self.get_model()} 思考模式不支持当前 tool_choice，已移除该参数并重试。"
            )
            payloads.pop("tool_choice", None)
            payloads[self._FORCE_OMIT_TOOL_CHOICE_KEY] = True
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
        payloads, extra_body, tools = self._prepare_request(payloads, tools)

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
        payloads, extra_body, tools = self._prepare_request(payloads, tools)

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
