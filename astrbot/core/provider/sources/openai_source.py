import asyncio
import copy
import inspect
import json
import random
import re
from collections.abc import AsyncGenerator
from typing import Any, Literal

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
from astrbot.core.agent.message import (
    AudioURLPart,
    ContentPart,
    ImageURLPart,
    Message,
    TextPart,
)
from astrbot.core.agent.tool import ToolSet
from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import LLMResponse, TokenUsage, ToolCallsResult
from astrbot.core.utils.media_utils import (
    describe_media_ref,
    resolve_media_ref_to_base64_data,
)
from astrbot.core.utils.network_utils import (
    create_proxy_client,
    is_connection_error,
    log_connection_failure,
)
from astrbot.core.utils.string_utils import normalize_and_dedupe_strings

from ..register import register_provider_adapter
from .request_retry import retry_provider_request


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
                if isinstance(item, dict) and item.get("type") in {
                    "image_url",
                    "audio_url",
                }:
                    return True
        return False

    def _is_invalid_attachment_error(self, error: Exception) -> bool:
        body = getattr(error, "body", None)
        code: str | None = None
        message: str | None = None
        if isinstance(body, dict):
            err_obj = body.get("error")
            if isinstance(err_obj, dict):
                raw_code = err_obj.get("code")
                raw_message = err_obj.get("message")
                code = raw_code.lower() if isinstance(raw_code, str) else None
                message = raw_message.lower() if isinstance(raw_message, str) else None

        if code == "invalid_attachment":
            return True

        text_sources: list[str] = []
        if message:
            text_sources.append(message)
        if code:
            text_sources.append(code)
        text_sources.extend(map(str, self._extract_error_text_candidates(error)))

        error_text = " ".join(text.lower() for text in text_sources if text)
        if "invalid_attachment" in error_text:
            return True
        if "download attachment" in error_text and "404" in error_text:
            return True
        return False

    async def _image_ref_to_data_url(
        self,
        image_ref: str,
        *,
        mode: Literal["safe", "strict"] = "safe",
    ) -> str | None:
        image_data = await resolve_media_ref_to_base64_data(
            image_ref,
            media_type="image",
            strict=mode == "strict",
        )
        return image_data.to_data_url() if image_data else None

    async def _resolve_image_part(
        self,
        image_url: str,
        *,
        image_detail: str | None = None,
    ) -> dict | None:
        image_data = await self._image_ref_to_data_url(image_url, mode="safe")
        if not image_data:
            logger.warning("图片预处理结果为空，将忽略。")
            return None
        image_payload = {"url": image_data}

        if image_detail:
            image_payload["detail"] = image_detail
        return {
            "type": "image_url",
            "image_url": image_payload,
        }

    def _extract_image_part_info(self, part: dict) -> tuple[str | None, str | None]:
        if not isinstance(part, dict) or part.get("type") != "image_url":
            return None, None

        image_url_data = part.get("image_url")
        if not isinstance(image_url_data, dict):
            logger.warning("图片内容块格式无效，将保留原始内容。")
            return None, None

        url = image_url_data.get("url")
        if not isinstance(url, str) or not url:
            logger.warning("图片内容块缺少有效 URL，将保留原始内容。")
            return None, None

        image_detail = image_url_data.get("detail")
        if not isinstance(image_detail, str):
            image_detail = None
        return url, image_detail

    def _extract_audio_part_info(self, part: dict) -> str | None:
        if not isinstance(part, dict) or part.get("type") != "audio_url":
            return None

        audio_url_data = part.get("audio_url")
        if not isinstance(audio_url_data, dict):
            logger.warning("音频内容块格式无效，将保留原始内容。")
            return None

        url = audio_url_data.get("url")
        if not isinstance(url, str) or not url:
            logger.warning("音频内容块缺少有效路径，将保留原始内容。")
            return None

        return url

    async def _resolve_audio_part(self, audio_ref: str) -> dict | None:
        try:
            audio_data = await resolve_media_ref_to_base64_data(
                audio_ref,
                media_type="audio",
                strict=True,
            )
        except Exception as exc:
            logger.warning("音频预处理失败，将忽略。错误: %s", exc)
            return None

        if not audio_data or not audio_data.format:
            logger.warning("音频预处理结果为空，将忽略。")
            return None

        return {
            "type": "input_audio",
            "input_audio": {
                "data": audio_data.base64_data,
                "format": audio_data.format,
            },
        }

    async def _transform_content_part(self, part: dict) -> dict:
        if not isinstance(part, dict):
            return part

        if part.get("type") == "image_url":
            url, image_detail = self._extract_image_part_info(part)
            if not url:
                return part

            try:
                resolved_part = await self._resolve_image_part(
                    url, image_detail=image_detail
                )
            except Exception as exc:
                logger.warning(
                    "图片 %s 预处理失败，将保留原始内容。错误: %s",
                    url,
                    exc,
                )
                return part

            return resolved_part or part

        if part.get("type") == "audio_url":
            audio_ref = self._extract_audio_part_info(part)
            if not audio_ref:
                return part
            resolved_part = await self._resolve_audio_part(audio_ref)
            return resolved_part or part

        return part

    async def _materialize_message_image_parts(self, message: dict) -> dict:
        content = message.get("content")
        if not isinstance(content, list):
            return {**message}

        new_content = [await self._transform_content_part(part) for part in content]
        return {**message, "content": new_content}

    async def _materialize_context_image_parts(
        self, context_query: list[dict]
    ) -> list[dict]:
        return [
            await self._materialize_message_image_parts(message)
            for message in context_query
        ]

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

    def _create_http_client(self, provider_config: dict) -> httpx.AsyncClient:
        """创建带代理的 HTTP 客户端"""
        proxy = provider_config.get("proxy", "")
        httpx_module: Any = httpx
        try:
            from openai import _base_client as openai_base_client

            httpx_module = getattr(openai_base_client, "httpx", httpx)
        except ImportError:
            pass
        return create_proxy_client("OpenAI", proxy, httpx_module=httpx_module)

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

    def _ollama_disable_thinking_enabled(self) -> bool:
        value = self.provider_config.get("ollama_disable_thinking", False)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _apply_provider_specific_extra_body_overrides(
        self, extra_body: dict[str, Any]
    ) -> None:
        if self.provider_config.get("provider") != "ollama":
            return
        if not self._ollama_disable_thinking_enabled():
            return

        # Ollama's OpenAI-compatible endpoint reliably maps reasoning_effort=none
        # to think=false, while direct think=false passthrough is not stable.
        extra_body.pop("reasoning", None)
        extra_body.pop("think", None)
        extra_body["reasoning_effort"] = "none"

    async def get_models(self):
        try:
            models_str = []
            models = await retry_provider_request(
                "OpenAI",
                lambda: self.client.models.list(),
            )
            models = sorted(models.data, key=lambda x: x.id)
            for model in models:
                models_str.append(model.id)
            return models_str
        except NotFoundError as e:
            raise Exception(f"获取模型列表失败：{e}")

    @staticmethod
    def _sanitize_assistant_messages(payloads: dict) -> None:
        """在请求发送前过滤/规范化空的 assistant 消息。

        严格 API（Moonshot、DeepSeek Reasoner 等）会在 assistant 消息同时缺少
        ``content`` 和 ``tool_calls`` 时返回 400。把 ``""`` / ``None`` / ``[]``
        都视作空内容：无 tool_calls 时整条过滤掉；有 tool_calls 时将 content
        设为 ``None`` 以符合 OpenAI 规范。就地修改 ``payloads["messages"]``。
        """
        messages = payloads.get("messages")
        if not isinstance(messages, list):
            return

        def _is_empty(content: Any) -> bool:
            return content is None or content == "" or content == []

        cleaned: list[Any] = []
        for idx, msg in enumerate(messages):
            if not isinstance(msg, dict) or msg.get("role") != "assistant":
                cleaned.append(msg)
                continue

            content = msg.get("content")
            tool_calls = msg.get("tool_calls")
            reasoning_content = msg.get("reasoning_content")

            if _is_empty(content) and not tool_calls and not reasoning_content:
                logger.warning(f"过滤第 {idx} 条空 assistant 消息 (无工具调用)")
                continue

            if _is_empty(content) and tool_calls:
                msg["content"] = None

            cleaned.append(msg)

        payloads["messages"] = cleaned

    async def _query(
        self,
        payloads: dict,
        tools: ToolSet | None,
        *,
        request_max_retries: int | None = None,
    ) -> LLMResponse:
        if tools:
            model = payloads.get("model", "").lower()
            omit_empty_param_field = "gemini" in model
            tool_list = tools.get_func_desc_openai_style(
                omit_empty_parameter_field=omit_empty_param_field,
            )
            if tool_list:
                payloads["tools"] = tool_list
                payloads["tool_choice"] = payloads.get("tool_choice", "auto")

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
        self._apply_provider_specific_extra_body_overrides(extra_body)

        model = payloads.get("model", "").lower()

        self._sanitize_assistant_messages(payloads)

        completion = await retry_provider_request(
            "OpenAI",
            lambda: self.client.chat.completions.create(
                **payloads,
                stream=False,
                extra_body=extra_body,
            ),
            max_attempts=request_max_retries,
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
        *,
        request_max_retries: int | None = None,
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
                payloads["tool_choice"] = payloads.get("tool_choice", "auto")

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
        self._apply_provider_specific_extra_body_overrides(extra_body)

        self._sanitize_assistant_messages(payloads)

        stream = await retry_provider_request(
            "OpenAI",
            lambda: self.client.chat.completions.create(
                **payloads,
                stream=True,
                extra_body=extra_body,
                stream_options={"include_usage": True},
            ),
            max_attempts=request_max_retries,
        )

        llm_response = LLMResponse("assistant", is_chunk=True)

        state = ChatCompletionStreamState()

        async for chunk in stream:
            choice = chunk.choices[0] if chunk.choices else None
            delta = choice.delta if choice else None

            if delta and (dtcs := delta.tool_calls):
                for idx, tc in enumerate(dtcs):
                    # siliconflow workaround
                    if tc.function and tc.function.arguments:
                        tc.type = "function"
                    # Fix for #6661: Add missing 'index' field to tool_call deltas
                    # Gemini and some OpenAI-compatible proxies omit this field
                    if not hasattr(tc, "index") or tc.index is None:
                        tc.index = idx
            # 跳过 delta=None 的 chunk，避免 SDK 内部 _convert_initial_chunk_into_snapshot
            # 第 747 行 choice.delta.to_dict() 抛出 NoneType 错误。
            # refs: AstrBot#6689 / openai-python#5069 / #5047
            # 例外：流末尾的 usage chunk（choices=[]，delta=None 但有 usage 数据）
            # 需要传给 state，否则最终 completion 会丢失 usage 信息
            if delta is not None or chunk.usage:
                try:
                    state.handle_chunk(chunk)
                except Exception as e:
                    logger.error("Saving chunk state error: " + str(e))
            # logger.debug(f"chunk delta: {delta}")
            # handle the content delta
            reasoning = self._extract_reasoning_content(chunk)
            _y = False
            llm_response.id = chunk.id
            llm_response.reasoning_content = None
            llm_response.completion_text = ""
            if reasoning is not None:
                llm_response.reasoning_content = reasoning
                _y = True
            if delta and delta.content:
                # Don't strip streaming chunks to preserve spaces between words
                completion_text = self._normalize_content(delta.content, strip=False)
                llm_response.result_chain = MessageChain(
                    chain=[Comp.Plain(completion_text)],
                )
                _y = True
            if chunk.usage:
                llm_response.usage = self._extract_usage(chunk.usage)
            elif choice and (choice_usage := getattr(choice, "usage", None)):
                # Workaround for some providers that only return usage in choices[].usage, e.g. MoonshotAI
                # See https://github.com/AstrBotDevs/AstrBot/issues/6614
                llm_response.usage = self._extract_usage(choice_usage)
                state.current_completion_snapshot.usage = choice_usage
            if _y:
                yield llm_response

        try:
            final_completion = state.get_final_completion()
            llm_response = await self._parse_openai_completion(final_completion, tools)
            yield llm_response
        except Exception as e:
            logger.error("get_final_completion error: " + str(e))
            # 流式内容已通过 yield 发出，记录错误后正常结束即可
            return

    def _extract_reasoning_content(
        self,
        completion: ChatCompletion | ChatCompletionChunk,
    ) -> str | None:
        """Extract reasoning content from OpenAI ChatCompletion if available."""

        def _get_reasoning_attr(obj: Any) -> str | None:
            fields_set = getattr(obj, "model_fields_set", None)
            if isinstance(fields_set, set) and self.reasoning_key in fields_set:
                attr = getattr(obj, self.reasoning_key, "")
                return "" if attr is None else str(attr)
            attr = getattr(obj, self.reasoning_key, None)
            return None if attr is None else str(attr)

        if not completion.choices:
            return None
        if isinstance(completion, ChatCompletion):
            choice = completion.choices[0]
            reasoning_attr = _get_reasoning_attr(choice.message)
        elif isinstance(completion, ChatCompletionChunk):
            delta = completion.choices[0].delta
            reasoning_attr = _get_reasoning_attr(delta)
        else:
            return None
        return reasoning_attr

    def _extract_usage(self, usage: CompletionUsage | dict) -> TokenUsage:
        ptd = getattr(usage, "prompt_tokens_details", None)
        cached = getattr(ptd, "cached_tokens", 0) if ptd else 0
        cached = (
            cached if isinstance(cached, int) else 0
        )  # ptd.cached_tokens 可能为None
        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0  # 安全
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0
        cached = cached or 0
        prompt_tokens = prompt_tokens or 0
        completion_tokens = completion_tokens or 0
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

        if not completion.choices:
            raise EmptyModelOutputError(
                f"OpenAI completion has no choices. response_id={completion.id}"
            )
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
        elif refusal := getattr(choice.message, "refusal", None):
            refusal_text = self._normalize_content(refusal)
            if refusal_text:
                llm_response.result_chain = MessageChain().message(refusal_text)

        # parse the reasoning content if any
        # the priority is higher than the <think> tag extraction
        reasoning_content = self._extract_reasoning_content(completion)
        if reasoning_content is not None:
            llm_response.reasoning_content = reasoning_content

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

                if tool_call.type == "function":
                    # workaround for #1454
                    if isinstance(tool_call.function.arguments, str):
                        try:
                            args = json.loads(tool_call.function.arguments)
                        except json.JSONDecodeError as e:
                            logger.error(f"解析参数失败: {e}")
                            args = {}
                    else:
                        args = tool_call.function.arguments
                    # Some API may return None for tools with no parameters
                    if args is None:
                        args = {}
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
        has_text_output = bool((llm_response.completion_text or "").strip())
        has_reasoning_output = bool((llm_response.reasoning_content or "").strip())
        if (
            not has_text_output
            and not has_reasoning_output
            and not llm_response.tools_call_args
        ):
            logger.error(f"OpenAI completion has no usable output: {completion}.")
            raise EmptyModelOutputError(
                "OpenAI completion has no usable output. "
                f"response_id={completion.id}, finish_reason={choice.finish_reason}"
            )

        llm_response.raw_completion = completion
        llm_response.id = completion.id

        if completion.usage:
            llm_response.usage = self._extract_usage(completion.usage)

        return llm_response

    async def _prepare_chat_payload(
        self,
        prompt: str | None,
        image_urls: list[str] | None = None,
        audio_urls: list[str] | None = None,
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
                prompt or "",
                image_urls,
                audio_urls,
                extra_user_content_parts,
            )
        context_query = copy.deepcopy(self._ensure_message_to_dicts(contexts))
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

        if self._context_contains_image(context_query):
            context_query = await self._materialize_context_image_parts(context_query)

        model = model or self.get_model()

        payloads = {"messages": context_query, "model": model}

        self._finally_convert_payload(payloads)

        return payloads, context_query

    def _finally_convert_payload(self, payloads: dict) -> None:
        """Finally convert the payload. Such as think part conversion, tool inject."""
        model = payloads.get("model", "").lower()
        is_gemini = "gemini" in model
        deepseek_reasoning_models = {"deepseek-v4-pro", "deepseek-v4-flash"}
        is_deepseek_v4_reasoning = (
            model in deepseek_reasoning_models
            or "api.deepseek.com" in self.client.base_url.host
        )
        # MiMo 推理模型（MiMo-V2.5-Pro / MiMo-V2.5 / MiMo-V2-Pro / MiMo-V2-Omni / MiMo-V2-Flash）
        # 要求 assistant 历史消息必须回传 reasoning_content，否则返回 400
        mimo_reasoning_models = {
            "mimo-v2.5-pro",
            "mimo-v2.5",
            "mimo-v2-pro",
            "mimo-v2-omni",
            "mimo-v2-flash",
        }
        is_mimo_reasoning = model in mimo_reasoning_models
        for message in payloads.get("messages", []):
            if message.get("role") == "assistant" and isinstance(
                message.get("content"), list
            ):
                reasoning_content = ""
                reasoning_content_present = False
                new_content = []  # not including think part
                for part in message["content"]:
                    if part.get("type") == "think":
                        reasoning_content_present = True
                        reasoning_content += str(part.get("think"))
                    else:
                        new_content.append(part)
                # Some providers (Grok, etc.) reject empty content lists.
                # When all parts were think blocks, fall back to None.
                message["content"] = new_content or None
                if reasoning_content_present:
                    message["reasoning_content"] = reasoning_content

            if (
                message.get("role") == "assistant"
                and is_deepseek_v4_reasoning
                and "reasoning_content" not in message
            ):
                # DeepSeek v4 reasoning models require the field on assistant
                # history messages, even when the reasoning content is empty.
                message["reasoning_content"] = ""

            if (
                message.get("role") == "assistant"
                and is_mimo_reasoning
                and "reasoning_content" not in message
            ):
                # MiMo 推理模型要求 assistant 历史消息回传 reasoning_content，
                # 缺失时 API 返回 400。参见 MiMo 官方文档。
                message["reasoning_content"] = ""

            # Gemini 的 function_response 要求 google.protobuf.Struct（即 JSON 对象），
            # 纯文本会触发 400 Invalid argument，需要包一层 JSON。
            if is_gemini and message.get("role") == "tool":
                content = message.get("content", "")
                if isinstance(content, str):
                    try:
                        json.loads(content)
                    except (json.JSONDecodeError, ValueError):
                        message["content"] = json.dumps(
                            {"result": content}, ensure_ascii=False
                        )

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
            if chosen_key in available_api_keys:
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
        if "maximum context length" in str(e) or "context length" in str(e).lower():
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
        if self._is_invalid_attachment_error(e):
            if image_fallback_used or not self._context_contains_image(context_query):
                raise e
            return await self._fallback_to_text_only_and_retry(
                payloads,
                context_query,
                chosen_key,
                available_api_keys,
                func_tool,
                "invalid_attachment",
                image_fallback_used=True,
            )

        if (
            "Function calling is not enabled" in str(e)
            or ("tool" in str(e).lower() and "support" in str(e).lower())
            or ("function" in str(e).lower() and "support" in str(e).lower())
        ):
            # openai, ollama, gemini openai, siliconcloud 的错误提示与 code 不统一，只能通过字符串匹配
            logger.warning(
                f"{self.get_model()} 不支持函数工具调用，已自动去除，不影响使用。如需永久关闭，可前往 WebUI 中关闭工具调用。",
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

        if is_connection_error(e):
            proxy = self.provider_config.get("proxy", "")
            log_connection_failure("OpenAI", e, proxy)

        raise e

    async def text_chat(
        self,
        prompt=None,
        session_id=None,
        image_urls=None,
        audio_urls=None,
        func_tool=None,
        contexts=None,
        system_prompt=None,
        tool_calls_result=None,
        model=None,
        extra_user_content_parts=None,
        tool_choice: Literal["auto", "required"] = "auto",
        request_max_retries: int | None = None,
        **kwargs,
    ) -> LLMResponse:
        payloads, context_query = await self._prepare_chat_payload(
            prompt,
            image_urls,
            audio_urls,
            contexts,
            system_prompt,
            tool_calls_result,
            model=model,
            extra_user_content_parts=extra_user_content_parts,
            **kwargs,
        )
        if func_tool and not func_tool.empty():
            payloads["tool_choice"] = tool_choice

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
                llm_response = await self._query(
                    payloads,
                    func_tool,
                    request_max_retries=request_max_retries,
                )
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
        audio_urls=None,
        func_tool=None,
        contexts=None,
        system_prompt=None,
        tool_calls_result=None,
        model=None,
        tool_choice: Literal["auto", "required"] = "auto",
        request_max_retries: int | None = None,
        **kwargs,
    ) -> AsyncGenerator[LLMResponse, None]:
        """流式对话，与服务商交互并逐步返回结果"""
        payloads, context_query = await self._prepare_chat_payload(
            prompt,
            image_urls,
            audio_urls,
            contexts,
            system_prompt,
            tool_calls_result,
            model=model,
            **kwargs,
        )
        if func_tool and not func_tool.empty():
            payloads["tool_choice"] = tool_choice

        max_retries = 10
        available_api_keys = self.api_keys.copy()
        chosen_key = random.choice(available_api_keys)
        image_fallback_used = False

        last_exception = None
        retry_cnt = 0
        for retry_cnt in range(max_retries):
            try:
                self.client.api_key = chosen_key
                async for response in self._query_stream(
                    payloads,
                    func_tool,
                    request_max_retries=request_max_retries,
                ):
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
        audio_urls: list[str] | None = None,
        extra_user_content_parts: list[ContentPart] | None = None,
    ) -> dict:
        """组装成符合 OpenAI 格式的 role 为 user 的消息段"""

        # 构建内容块列表
        content_blocks = []

        # 1. 用户原始发言（OpenAI 建议：用户发言在前）
        if text:
            content_blocks.append({"type": "text", "text": text})
        elif image_urls:
            # 如果没有文本但有图片，添加占位文本
            content_blocks.append({"type": "text", "text": "[Image]"})
        elif audio_urls:
            content_blocks.append({"type": "text", "text": "[Audio]"})
        elif extra_user_content_parts:
            # 如果只有额外内容块，也需要添加占位文本
            content_blocks.append({"type": "text", "text": " "})

        # 2. 额外的内容块（系统提醒、指令等）
        if extra_user_content_parts:
            for part in extra_user_content_parts:
                if isinstance(part, TextPart):
                    content_blocks.append({"type": "text", "text": part.text})
                elif isinstance(part, ImageURLPart):
                    image_part = await self._resolve_image_part(
                        part.image_url.url,
                    )
                    if image_part:
                        content_blocks.append(image_part)
                elif isinstance(part, AudioURLPart):
                    audio_part = await self._resolve_audio_part(part.audio_url.url)
                    if audio_part:
                        content_blocks.append(audio_part)
                else:
                    raise ValueError(f"不支持的额外内容块类型: {type(part)}")

        # 3. 图片内容
        if image_urls:
            for image_url in image_urls:
                image_part = await self._resolve_image_part(image_url)
                if image_part:
                    content_blocks.append(image_part)

        if audio_urls:
            for audio_path in audio_urls:
                audio_part = await self._resolve_audio_part(audio_path)
                if audio_part:
                    content_blocks.append(audio_part)

        # 如果只有主文本且没有额外内容块和图片，返回简单格式以保持向后兼容
        if (
            text
            and not extra_user_content_parts
            and not image_urls
            and not audio_urls
            and len(content_blocks) == 1
            and content_blocks[0]["type"] == "text"
        ):
            return {"role": "user", "content": content_blocks[0]["text"]}

        # 否则返回多模态格式
        return {"role": "user", "content": content_blocks}

    async def encode_image_bs64(self, image_url: str) -> str:
        """将图片转换为 base64"""
        image_data = await self._image_ref_to_data_url(image_url, mode="strict")
        if image_data is None:
            raise RuntimeError(
                f"Failed to encode image data: {describe_media_ref(image_url)}"
            )
        return image_data

    async def terminate(self):
        if self.client:
            await self.client.close()
