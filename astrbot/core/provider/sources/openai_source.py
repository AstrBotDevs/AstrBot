import asyncio
import base64
import inspect
import json
import random
import re
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from openai import AsyncAzureOpenAI, AsyncOpenAI
from openai._exceptions import NotFoundError
from openai.lib.streaming.chat._completions import ChatCompletionStreamState
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.completion_usage import CompletionUsage

import astrbot.core.message.components as Comp
from astrbot import logger
from astrbot.api.provider import Provider
from astrbot.core.agent.message import ContentPart, ImageURLPart, Message, TextPart
from astrbot.core.agent.tool import ToolSet
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import LLMResponse, TokenUsage, ToolCallsResult
from astrbot.core.utils.io import download_image_by_url
from astrbot.core.utils.network_utils import (
    create_proxy_client,
    is_connection_error,
    log_connection_failure,
)
from astrbot.core.utils.string_utils import normalize_and_dedupe_strings

from ..register import register_provider_adapter


@register_provider_adapter(
    "openai_chat_completion",
    "OpenAI API Chat Completion 提供商适配器",
)
class ProviderOpenAIOfficial(Provider):
    _ERROR_TEXT_CANDIDATE_MAX_CHARS = 4096

    @classmethod
    def _truncate_error_text_candidate(cls, text: str) -> str:
        if len(text) <= cls._ERROR_TEXT_CANDIDATE_MAX_CHARS:
            return text
        return text[: cls._ERROR_TEXT_CANDIDATE_MAX_CHARS]

    @staticmethod
    def _safe_json_dump(value: Any) -> str | None:
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            return None

    def _get_image_moderation_error_patterns(self) -> list[str]:
        """Return configured moderation patterns (case-insensitive substring match, not regex)."""
        configured = self.provider_config.get("image_moderation_error_patterns", [])
        patterns: list[str] = []
        if isinstance(configured, str):
            configured = [configured]
        if isinstance(configured, list):
            for pattern in configured:
                if not isinstance(pattern, str):
                    continue
                pattern = pattern.strip()
                if pattern:
                    patterns.append(pattern)
        return patterns

    @staticmethod
    def _extract_error_text_candidates(error: Exception) -> list[str]:
        candidates: list[str] = []

        def _append_candidate(candidate: Any):
            if candidate is None:
                return
            text = str(candidate).strip()
            if not text:
                return
            candidates.append(
                ProviderOpenAIOfficial._truncate_error_text_candidate(text)
            )

        _append_candidate(str(error))

        body = getattr(error, "body", None)
        if isinstance(body, dict):
            err_obj = body.get("error")
            body_text = ProviderOpenAIOfficial._safe_json_dump(
                {"error": err_obj} if isinstance(err_obj, dict) else body
            )
            _append_candidate(body_text)
            if isinstance(err_obj, dict):
                for field in ("message", "type", "code", "param"):
                    value = err_obj.get(field)
                    if value is not None:
                        _append_candidate(value)
        elif isinstance(body, str):
            _append_candidate(body)

        response = getattr(error, "response", None)
        if response is not None:
            response_text = getattr(response, "text", None)
            if isinstance(response_text, str):
                _append_candidate(response_text)

        return normalize_and_dedupe_strings(candidates)

    def _is_content_moderated_upload_error(self, error: Exception) -> bool:
        patterns = [
            pattern.lower() for pattern in self._get_image_moderation_error_patterns()
        ]
        if not patterns:
            return False
        candidates = [
            candidate.lower()
            for candidate in self._extract_error_text_candidates(error)
        ]
        for pattern in patterns:
            if any(pattern in candidate for candidate in candidates):
                return True
        return False

    @staticmethod
    def _context_contains_image(contexts: list[dict]) -> bool:
        for context in contexts:
            content = context.get("content")
            if not isinstance(content, list):
                continue
            for item in content:
                if isinstance(item, dict) and item.get("type") == "image_url":
                    return True
        return False

    async def _fallback_to_text_only_and_retry(
        self,
        payloads: dict,
        context_query: list,
        chosen_key: str,
        available_api_keys: list[str],
        func_tool: ToolSet | None,
        reason: str,
        *,
        image_fallback_used: bool = False,
    ) -> tuple:
        logger.warning(
            "检测到图片请求失败（%s），已移除图片并重试（保留文本内容）。",
            reason,
        )
        new_contexts = await self._remove_image_from_context(context_query)
        payloads["messages"] = new_contexts
        return (
            False,
            chosen_key,
            available_api_keys,
            payloads,
            new_contexts,
            func_tool,
            image_fallback_used,
        )

    def _create_http_client(self, provider_config: dict) -> httpx.AsyncClient | None:
        """创建带代理的 HTTP 客户端"""
        proxy = provider_config.get("proxy", "")
        return create_proxy_client("OpenAI", proxy)

    def __init__(self, provider_config, provider_settings) -> None:
        super().__init__(provider_config, provider_settings)
        self.chosen_api_key = None
        self.api_keys: list = super().get_keys()
        self.chosen_api_key = self.api_keys[0] if len(self.api_keys) > 0 else None
        self.timeout = provider_config.get("timeout", 120)
        self.custom_headers = provider_config.get("custom_headers", {})
        if isinstance(self.timeout, str):
            self.timeout = int(self.timeout)

        if not isinstance(self.custom_headers, dict) or not self.custom_headers:
            self.custom_headers = None
        else:
            for key in self.custom_headers:
                self.custom_headers[key] = str(self.custom_headers[key])

        if "api_version" in provider_config:
            # Using Azure OpenAI API
            self.client = AsyncAzureOpenAI(
                api_key=self.chosen_api_key,
                api_version=provider_config.get("api_version", None),
                default_headers=self.custom_headers,
                base_url=provider_config.get("api_base", ""),
                timeout=self.timeout,
                http_client=self._create_http_client(provider_config),
            )
        else:
            # Using OpenAI Official API
            self.client = AsyncOpenAI(
                api_key=self.chosen_api_key,
                base_url=provider_config.get("api_base", None),
                default_headers=self.custom_headers,
                timeout=self.timeout,
                http_client=self._create_http_client(provider_config),
            )

        self.default_params = inspect.signature(
            self.client.chat.completions.create,
        ).parameters.keys()

        model = provider_config.get("model", "unknown")
        self.set_model(model)

        self.reasoning_key = "reasoning_content"

    async def get_models(self):
        try:
            models_str = []
            models = await self.client.models.list()
            models = sorted(models.data, key=lambda x: x.id)
            for model in models:
                models_str.append(model.id)
            return models_str
        except NotFoundError as e:
            raise Exception(f"获取模型列表失败：{e}")

    async def _query(self, payloads: dict, tools: ToolSet | None) -> LLMResponse:
        if tools:
            model = payloads.get("model", "").lower()
            omit_empty_param_field = "gemini" in model
            tool_list = tools.get_func_desc_openai_style(
                omit_empty_parameter_field=omit_empty_param_field,
            )
            if tool_list:
                payloads["tools"] = tool_list

        # 不在默认参数中的参数放在 extra_body 中
        extra_body = {}
        to_del = []
        for key in payloads:
            if key not in self.default_params:
                extra_body[key] = payloads[key]
                to_del.append(key)
        for key in to_del:
            del payloads[key]

        # 读取并合并 custom_extra_body 配置
        custom_extra_body = self.provider_config.get("custom_extra_body", {})
        if isinstance(custom_extra_body, dict):
            extra_body.update(custom_extra_body)

        model = payloads.get("model", "").lower()

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

        llm_response = await self._parse_openai_completion(completion, tools)

        return llm_response

    async def _query_stream(
        self,
        payloads: dict,
        tools: ToolSet | None,
    ) -> AsyncGenerator[LLMResponse, None]:
        """流式查询API，逐步返回结果"""
        if tools:
            model = payloads.get("model", "").lower()
            omit_empty_param_field = "gemini" in model
            tool_list = tools.get_func_desc_openai_style(
                omit_empty_parameter_field=omit_empty_param_field,
            )
            if tool_list:
                payloads["tools"] = tool_list

        # 不在默认参数中的参数放在 extra_body 中
        extra_body = {}

        # 读取并合并 custom_extra_body 配置
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

        stream = await self.client.chat.completions.create(
            **payloads,
            stream=True,
            extra_body=extra_body,
        )

        llm_response = LLMResponse("assistant", is_chunk=True)

        state = ChatCompletionStreamState()

        async for chunk in stream:
            try:
                state.handle_chunk(chunk)
            except Exception as e:
                logger.warning("Saving chunk state error: " + str(e))
            if len(chunk.choices) == 0:
                continue
            delta = chunk.choices[0].delta
            # logger.debug(f"chunk delta: {delta}")
            # handle the content delta
            reasoning = self._extract_reasoning_content(chunk)
            _y = False
            llm_response.id = chunk.id
            if reasoning:
                llm_response.reasoning_content = reasoning
                _y = True
            if delta.content:
                # Don't strip streaming chunks to preserve spaces between words
                completion_text = self._normalize_content(delta.content, strip=False)
                llm_response.result_chain = MessageChain(
                    chain=[Comp.Plain(completion_text)],
                )
                _y = True
            if chunk.usage:
                llm_response.usage = self._extract_usage(chunk.usage)
            if _y:
                yield llm_response

        final_completion = state.get_final_completion()
        llm_response = await self._parse_openai_completion(final_completion, tools)

        yield llm_response

    def _extract_reasoning_content(
        self,
        completion: ChatCompletion | ChatCompletionChunk,
    ) -> str:
        """Extract reasoning content from OpenAI ChatCompletion if available."""
        reasoning_text = ""
        if len(completion.choices) == 0:
            return reasoning_text
        if isinstance(completion, ChatCompletion):
            choice = completion.choices[0]
            reasoning_attr = getattr(choice.message, self.reasoning_key, None)
            if reasoning_attr:
                reasoning_text = str(reasoning_attr)
        elif isinstance(completion, ChatCompletionChunk):
            delta = completion.choices[0].delta
            reasoning_attr = getattr(delta, self.reasoning_key, None)
            if reasoning_attr:
                reasoning_text = str(reasoning_attr)
        return reasoning_text

    def _extract_usage(self, usage: CompletionUsage) -> TokenUsage:
        ptd = usage.prompt_tokens_details
        cached = ptd.cached_tokens if ptd and ptd.cached_tokens else 0
        prompt_tokens = 0 if usage.prompt_tokens is None else usage.prompt_tokens
        completion_tokens = (
            0 if usage.completion_tokens is None else usage.completion_tokens
        )
        return TokenUsage(
            input_other=prompt_tokens - cached,
            input_cached=cached,
            output=completion_tokens,
        )

    @staticmethod
    def _normalize_content(raw_content: Any, strip: bool = True) -> str:
        """Normalize content from various formats to plain string.

        Some LLM providers return content as list[dict] format
        like [{'type': 'text', 'text': '...'}] instead of
        plain string. This method handles both formats.

        Args:
            raw_content: The raw content from LLM response, can be str, list, dict, or other.
            strip: Whether to strip whitespace from the result. Set to False for
                   streaming chunks to preserve spaces between words.

        Returns:
            Normalized plain text string.
        """
        # Handle dict format (e.g., {"type": "text", "text": "..."})
        if isinstance(raw_content, dict):
            if "text" in raw_content:
                text_val = raw_content.get("text", "")
                return str(text_val) if text_val is not None else ""
            # For other dict formats, return empty string and log
            logger.warning(f"Unexpected dict format content: {raw_content}")
            return ""

        if isinstance(raw_content, list):
            # Check if this looks like OpenAI content-part format
            # Only process if at least one item has {'type': 'text', 'text': ...} structure
            has_content_part = any(
                isinstance(part, dict) and part.get("type") == "text"
                for part in raw_content
            )
            if has_content_part:
                text_parts = []
                for part in raw_content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text_val = part.get("text", "")
                        # Coerce to str in case text is null or non-string
                        text_parts.append(str(text_val) if text_val is not None else "")
                return "".join(text_parts)
            # Not content-part format, return string representation
            return str(raw_content)

        if isinstance(raw_content, str):
            content = raw_content.strip() if strip else raw_content
            # Check if the string is a JSON-encoded list (e.g., "[{'type': 'text', ...}]")
            # This can happen when streaming concatenates content that was originally list format
            # Only check if it looks like a complete JSON array (requires strip for check)
            check_content = raw_content.strip()
            if (
                check_content.startswith("[")
                and check_content.endswith("]")
                and len(check_content) < 8192
            ):
                try:
                    # First try standard JSON parsing
                    parsed = json.loads(check_content)
                except json.JSONDecodeError:
                    # If that fails, try parsing as Python literal (handles single quotes)
                    # This is safer than blind replace("'", '"') which corrupts apostrophes
                    try:
                        import ast

                        parsed = ast.literal_eval(check_content)
                    except (ValueError, SyntaxError):
                        parsed = None

                if isinstance(parsed, list):
                    # Only convert if it matches OpenAI content-part schema
                    # i.e., at least one item has {'type': 'text', 'text': ...}
                    has_content_part = any(
                        isinstance(part, dict) and part.get("type") == "text"
                        for part in parsed
                    )
                    if has_content_part:
                        text_parts = []
                        for part in parsed:
                            if isinstance(part, dict) and part.get("type") == "text":
                                text_val = part.get("text", "")
                                # Coerce to str in case text is null or non-string
                                text_parts.append(
                                    str(text_val) if text_val is not None else ""
                                )
                        if text_parts:
                            return "".join(text_parts)
            return content

        # Fallback for other types (int, float, etc.)
        return str(raw_content) if raw_content is not None else ""

    async def _parse_openai_completion(
        self, completion: ChatCompletion, tools: ToolSet | None
    ) -> LLMResponse:
        """Parse OpenAI ChatCompletion into LLMResponse"""
        llm_response = LLMResponse("assistant")

        if len(completion.choices) == 0:
            raise Exception("API 返回的 completion 为空。")
        choice = completion.choices[0]

        # parse the text completion
        if choice.message.content is not None:
            completion_text = self._normalize_content(choice.message.content)
            # specially, some providers may set <think> tags around reasoning content in the completion text,
            # we use regex to remove them, and store then in reasoning_content field
            reasoning_pattern = re.compile(r"<think>(.*?)</think>", re.DOTALL)
            matches = reasoning_pattern.findall(completion_text)
            if matches:
                llm_response.reasoning_content = "\n".join(
                    [match.strip() for match in matches],
                )
                completion_text = reasoning_pattern.sub("", completion_text).strip()
            # Also clean up orphan </think> tags that may leak from some models
            completion_text = re.sub(r"</think>\s*$", "", completion_text).strip()
            llm_response.result_chain = MessageChain().message(completion_text)

        # parse the reasoning content if any
        # the priority is higher than the <think> tag extraction
        llm_response.reasoning_content = self._extract_reasoning_content(completion)

        # parse tool calls if any
        if choice.message.tool_calls and tools is not None:
            args_ls = []
            func_name_ls = []
            tool_call_ids = []
            tool_call_extra_content_dict = {}
            for tool_call in choice.message.tool_calls:
                if isinstance(tool_call, str):
                    # workaround for #1359
                    tool_call = json.loads(tool_call)
                if tools is None:
                    # 工具集未提供
                    # Should be unreachable
                    raise Exception("工具集未提供")
                for tool in tools.func_list:
                    if (
                        tool_call.type == "function"
                        and tool.name == tool_call.function.name
                    ):
                        # workaround for #1454
                        if isinstance(tool_call.function.arguments, str):
                            args = json.loads(tool_call.function.arguments)
                        else:
                            args = tool_call.function.arguments
                        args_ls.append(args)
                        func_name_ls.append(tool_call.function.name)
                        tool_call_ids.append(tool_call.id)

                        # gemini-2.5 / gemini-3 series extra_content handling
                        extra_content = getattr(tool_call, "extra_content", None)
                        if extra_content is not None:
                            tool_call_extra_content_dict[tool_call.id] = extra_content
            llm_response.role = "tool"
            llm_response.tools_call_args = args_ls
            llm_response.tools_call_name = func_name_ls
            llm_response.tools_call_ids = tool_call_ids
            llm_response.tools_call_extra_content = tool_call_extra_content_dict
        # specially handle finish reason
        if choice.finish_reason == "content_filter":
            raise Exception(
                "API 返回的 completion 由于内容安全过滤被拒绝(非 AstrBot)。",
            )
        if llm_response.completion_text is None and not llm_response.tools_call_args:
            logger.error(f"API 返回的 completion 无法解析：{completion}。")
            raise Exception(f"API 返回的 completion 无法解析：{completion}。")

        llm_response.raw_completion = completion
        llm_response.id = completion.id

        if completion.usage:
            llm_response.usage = self._extract_usage(completion.usage)

        return llm_response

    async def _prepare_chat_payload(
        self,
        prompt: str | None,
        image_urls: list[str] | None = None,
        contexts: list[dict] | list[Message] | None = None,
        system_prompt: str | None = None,
        tool_calls_result: ToolCallsResult | list[ToolCallsResult] | None = None,
        model: str | None = None,
        extra_user_content_parts: list[ContentPart] | None = None,
        **kwargs,
    ) -> tuple:
        """准备聊天所需的有效载荷和上下文"""
        if contexts is None:
            contexts = []
        new_record = None
        if prompt is not None:
            new_record = await self.assemble_context(
                prompt, image_urls, extra_user_content_parts
            )
        context_query = self._ensure_message_to_dicts(contexts)
        if new_record:
            context_query.append(new_record)
        if system_prompt:
            context_query.insert(0, {"role": "system", "content": system_prompt})

        for part in context_query:
            if "_no_save" in part:
                del part["_no_save"]

        # tool calls result
        if tool_calls_result:
            if isinstance(tool_calls_result, ToolCallsResult):
                context_query.extend(tool_calls_result.to_openai_messages())
            else:
                for tcr in tool_calls_result:
                    context_query.extend(tcr.to_openai_messages())

        model = model or self.get_model()

        payloads = {"messages": context_query, "model": model}

        self._finally_convert_payload(payloads)

        return payloads, context_query

    def _finally_convert_payload(self, payloads: dict) -> None:
        """Finally convert the payload. Such as think part conversion, tool inject."""
        for message in payloads.get("messages", []):
            if message.get("role") == "assistant" and isinstance(
                message.get("content"), list
            ):
                reasoning_content = ""
                new_content = []  # not including think part
                for part in message["content"]:
                    if part.get("type") == "think":
                        reasoning_content += str(part.get("think"))
                    else:
                        new_content.append(part)
                message["content"] = new_content
                # reasoning key is "reasoning_content"
                if reasoning_content:
                    message["reasoning_content"] = reasoning_content

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
        """处理API错误并尝试恢复"""
        if "429" in str(e):
            logger.warning(
                f"API 调用过于频繁，尝试使用其他 Key 重试。当前 Key: {chosen_key[:12]}",
            )
            # 最后一次不等待
            if retry_cnt < max_retries - 1:
                await asyncio.sleep(1)
            available_api_keys.remove(chosen_key)
            if len(available_api_keys) > 0:
                chosen_key = random.choice(available_api_keys)
                return (
                    False,
                    chosen_key,
                    available_api_keys,
                    payloads,
                    context_query,
                    func_tool,
                    image_fallback_used,
                )
            raise e
        if "maximum context length" in str(e):
            logger.warning(
                f"上下文长度超过限制。尝试弹出最早的记录然后重试。当前记录条数: {len(context_query)}",
            )
            await self.pop_record(context_query)
            payloads["messages"] = context_query
            return (
                False,
                chosen_key,
                available_api_keys,
                payloads,
                context_query,
                func_tool,
                image_fallback_used,
            )
        if "The model is not a VLM" in str(e):  # siliconcloud
            if image_fallback_used or not self._context_contains_image(context_query):
                raise e
            # 尝试删除所有 image
            return await self._fallback_to_text_only_and_retry(
                payloads,
                context_query,
                chosen_key,
                available_api_keys,
                func_tool,
                "model_not_vlm",
                image_fallback_used=True,
            )
        if self._is_content_moderated_upload_error(e):
            if image_fallback_used or not self._context_contains_image(context_query):
                raise e
            return await self._fallback_to_text_only_and_retry(
                payloads,
                context_query,
                chosen_key,
                available_api_keys,
                func_tool,
                "image_content_moderated",
                image_fallback_used=True,
            )

        if (
            "Function calling is not enabled" in str(e)
            or ("tool" in str(e).lower() and "support" in str(e).lower())
            or ("function" in str(e).lower() and "support" in str(e).lower())
        ):
            # openai, ollama, gemini openai, siliconcloud 的错误提示与 code 不统一，只能通过字符串匹配
            logger.info(
                f"{self.get_model()} 不支持函数工具调用，已自动去除，不影响使用。",
            )
            payloads.pop("tools", None)
            return (
                False,
                chosen_key,
                available_api_keys,
                payloads,
                context_query,
                None,
                image_fallback_used,
            )
        # logger.error(f"发生了错误。Provider 配置如下: {self.provider_config}")

        if "tool" in str(e).lower() and "support" in str(e).lower():
            logger.error("疑似该模型不支持函数调用工具调用。请输入 /tool off_all")

        if is_connection_error(e):
            proxy = self.provider_config.get("proxy", "")
            log_connection_failure("OpenAI", e, proxy)

        raise e

    async def text_chat(
        self,
        prompt=None,
        session_id=None,
        image_urls=None,
        func_tool=None,
        contexts=None,
        system_prompt=None,
        tool_calls_result=None,
        model=None,
        extra_user_content_parts=None,
        **kwargs,
    ) -> LLMResponse:
        payloads, context_query = await self._prepare_chat_payload(
            prompt,
            image_urls,
            contexts,
            system_prompt,
            tool_calls_result,
            model=model,
            extra_user_content_parts=extra_user_content_parts,
            **kwargs,
        )

        llm_response = None
        max_retries = 10
        available_api_keys = self.api_keys.copy()
        chosen_key = random.choice(available_api_keys)
        image_fallback_used = False

        last_exception = None
        retry_cnt = 0
        for retry_cnt in range(max_retries):
            try:
                self.client.api_key = chosen_key
                llm_response = await self._query(payloads, func_tool)
                break
            except Exception as e:
                last_exception = e
                (
                    success,
                    chosen_key,
                    available_api_keys,
                    payloads,
                    context_query,
                    func_tool,
                    image_fallback_used,
                ) = await self._handle_api_error(
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
                if success:
                    break

        if retry_cnt == max_retries - 1 or llm_response is None:
            logger.error(f"API 调用失败，重试 {max_retries} 次仍然失败。")
            if last_exception is None:
                raise Exception("未知错误")
            raise last_exception
        return llm_response

    async def text_chat_stream(
        self,
        prompt=None,
        session_id=None,
        image_urls=None,
        func_tool=None,
        contexts=None,
        system_prompt=None,
        tool_calls_result=None,
        model=None,
        **kwargs,
    ) -> AsyncGenerator[LLMResponse, None]:
        """流式对话，与服务商交互并逐步返回结果"""
        payloads, context_query = await self._prepare_chat_payload(
            prompt,
            image_urls,
            contexts,
            system_prompt,
            tool_calls_result,
            model=model,
            **kwargs,
        )

        max_retries = 10
        available_api_keys = self.api_keys.copy()
        chosen_key = random.choice(available_api_keys)
        image_fallback_used = False

        last_exception = None
        retry_cnt = 0
        for retry_cnt in range(max_retries):
            try:
                self.client.api_key = chosen_key
                async for response in self._query_stream(payloads, func_tool):
                    yield response
                break
            except Exception as e:
                last_exception = e
                (
                    success,
                    chosen_key,
                    available_api_keys,
                    payloads,
                    context_query,
                    func_tool,
                    image_fallback_used,
                ) = await self._handle_api_error(
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
                if success:
                    break

        if retry_cnt == max_retries - 1:
            logger.error(f"API 调用失败，重试 {max_retries} 次仍然失败。")
            if last_exception is None:
                raise Exception("未知错误")
            raise last_exception

    async def _remove_image_from_context(self, contexts: list):
        """从上下文中删除所有带有 image 的记录"""
        new_contexts = []

        for context in contexts:
            if "content" in context and isinstance(context["content"], list):
                # continue
                new_content = []
                for item in context["content"]:
                    if isinstance(item, dict) and "image_url" in item:
                        continue
                    new_content.append(item)
                if not new_content:
                    # 用户只发了图片
                    new_content = [{"type": "text", "text": "[图片]"}]
                context["content"] = new_content
            new_contexts.append(context)
        return new_contexts

    def get_current_key(self) -> str:
        return self.client.api_key

    def get_keys(self) -> list[str]:
        return self.api_keys

    def set_key(self, key) -> None:
        self.client.api_key = key

    async def assemble_context(
        self,
        text: str,
        image_urls: list[str] | None = None,
        extra_user_content_parts: list[ContentPart] | None = None,
    ) -> dict:
        """组装成符合 OpenAI 格式的 role 为 user 的消息段"""

        async def resolve_image_part(image_url: str) -> dict | None:
            if image_url.startswith("http"):
                image_path = await download_image_by_url(image_url)
                image_data = await self.encode_image_bs64(image_path)
            elif image_url.startswith("file:///"):
                image_path = image_url.replace("file:///", "")
                image_data = await self.encode_image_bs64(image_path)
            else:
                image_data = await self.encode_image_bs64(image_url)
            if not image_data:
                logger.warning(f"图片 {image_url} 得到的结果为空，将忽略。")
                return None
            return {
                "type": "image_url",
                "image_url": {"url": image_data},
            }

        # 构建内容块列表
        content_blocks = []

        # 1. 用户原始发言（OpenAI 建议：用户发言在前）
        if text:
            content_blocks.append({"type": "text", "text": text})
        elif image_urls:
            # 如果没有文本但有图片，添加占位文本
            content_blocks.append({"type": "text", "text": "[图片]"})
        elif extra_user_content_parts:
            # 如果只有额外内容块，也需要添加占位文本
            content_blocks.append({"type": "text", "text": " "})

        # 2. 额外的内容块（系统提醒、指令等）
        if extra_user_content_parts:
            for part in extra_user_content_parts:
                if isinstance(part, TextPart):
                    content_blocks.append({"type": "text", "text": part.text})
                elif isinstance(part, ImageURLPart):
                    image_part = await resolve_image_part(part.image_url.url)
                    if image_part:
                        content_blocks.append(image_part)
                else:
                    raise ValueError(f"不支持的额外内容块类型: {type(part)}")

        # 3. 图片内容
        if image_urls:
            for image_url in image_urls:
                image_part = await resolve_image_part(image_url)
                if image_part:
                    content_blocks.append(image_part)

        # 如果只有主文本且没有额外内容块和图片，返回简单格式以保持向后兼容
        if (
            text
            and not extra_user_content_parts
            and not image_urls
            and len(content_blocks) == 1
            and content_blocks[0]["type"] == "text"
        ):
            return {"role": "user", "content": content_blocks[0]["text"]}

        # 否则返回多模态格式
        return {"role": "user", "content": content_blocks}

    async def encode_image_bs64(self, image_url: str) -> str:
        """将图片转换为 base64"""
        if image_url.startswith("base64://"):
            return image_url.replace("base64://", "data:image/jpeg;base64,")
        with open(image_url, "rb") as f:
            image_bs64 = base64.b64encode(f.read()).decode("utf-8")
            return "data:image/jpeg;base64," + image_bs64

    async def terminate(self):
        if self.client:
            await self.client.close()
