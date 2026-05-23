import asyncio
import base64
import inspect
import json
import random
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from openai import AsyncOpenAI
from openai._exceptions import NotFoundError

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
    "openai_responses",
    "OpenAI API Responses 提供商适配器",
)
class ProviderOpenAIResponses(Provider):
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
                ProviderOpenAIResponses._truncate_error_text_candidate(text)
            )

        _append_candidate(str(error))

        body = getattr(error, "body", None)
        if isinstance(body, dict):
            err_obj = body.get("error")
            body_text = ProviderOpenAIResponses._safe_json_dump(
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

    def _get_image_moderation_error_patterns(self) -> list[str]:
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

    def _create_http_client(self, provider_config: dict) -> httpx.AsyncClient | None:
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

        self.client = AsyncOpenAI(
            api_key=self.chosen_api_key,
            base_url=provider_config.get("api_base", None),
            default_headers=self.custom_headers,
            timeout=self.timeout,
            http_client=self._create_http_client(provider_config),
        )

        self.default_params = inspect.signature(
            self.client.responses.create,
        ).parameters.keys()

        model = provider_config.get("model", "unknown")
        self.set_model(model)

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

    async def test(self, timeout: float = 45.0) -> None:
        """Respect streaming_response when checking provider availability."""
        use_stream = bool(self.provider_settings.get("streaming_response", False))
        logger.info(
            "[openai_responses.test] streaming_response=%s timeout=%s",
            use_stream,
            timeout,
        )
        if use_stream:

            async def _consume() -> None:
                logger.info("[openai_responses.test] using text_chat_stream")
                async for _ in self.text_chat_stream(
                    prompt="REPLY `PONG` ONLY",
                ):
                    break

            await asyncio.wait_for(_consume(), timeout=timeout)
        else:
            logger.info("[openai_responses.test] using text_chat")
            await asyncio.wait_for(
                self.text_chat(prompt="REPLY `PONG` ONLY"),
                timeout=timeout,
            )

    def _normalize_content(self, raw_content: Any, strip: bool = True) -> str:
        if isinstance(raw_content, dict):
            if "text" in raw_content:
                text_val = raw_content.get("text", "")
                return str(text_val) if text_val is not None else ""
            return ""

        if isinstance(raw_content, list):
            text_parts = []
            for part in raw_content:
                if isinstance(part, dict) and "text" in part:
                    text_val = part.get("text", "")
                    text_parts.append(str(text_val) if text_val is not None else "")
            if text_parts:
                return "".join(text_parts)
            return str(raw_content)

        if isinstance(raw_content, str):
            return raw_content.strip() if strip else raw_content

        return str(raw_content) if raw_content is not None else ""

    def _content_to_plain_text(self, content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        text_parts.append(str(part.get("text", "")))
                    elif "text" in part:
                        text_parts.append(str(part.get("text", "")))
                elif isinstance(part, str):
                    text_parts.append(part)
            return "".join(text_parts)
        if isinstance(content, dict):
            if "text" in content:
                return str(content.get("text", ""))
        return str(content)

    def _convert_content_to_input(self, content: Any) -> str | list[dict]:
        if content is None:
            return " "
        if isinstance(content, str):
            return content if content.strip() else " "
        if isinstance(content, list):
            items = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                part_type = part.get("type")
                if part_type == "text":
                    text = str(part.get("text", ""))
                    items.append({"type": "input_text", "text": text})
                elif part_type == "image_url":
                    image_url = part.get("image_url")
                    if isinstance(image_url, dict):
                        image_url = image_url.get("url")
                    if image_url:
                        items.append(
                            {"type": "input_image", "image_url": str(image_url)}
                        )
                elif part_type == "think":
                    # Skip internal thinking parts.
                    continue
            if not items:
                return " "
            return items
        if isinstance(content, dict):
            if content.get("type") == "text":
                return str(content.get("text", "")) or " "
        return self._content_to_plain_text(content) or " "

    def _convert_content_to_output(self, content: Any) -> list[dict] | None:
        if content is None:
            return None
        if isinstance(content, str):
            text = content
            if not text.strip():
                return None
            return [{"type": "output_text", "text": text}]
        if isinstance(content, list):
            items: list[dict] = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                part_type = part.get("type")
                if part_type in {"text", "output_text"}:
                    text = str(part.get("text", ""))
                    if text:
                        items.append({"type": "output_text", "text": text})
            return items or None
        if isinstance(content, dict):
            if content.get("type") in {"text", "output_text"}:
                text = str(content.get("text", ""))
                if text:
                    return [{"type": "output_text", "text": text}]
        text = self._content_to_plain_text(content)
        if text.strip():
            return [{"type": "output_text", "text": text}]
        return None

    def _convert_openai_messages_to_responses_input(
        self, messages: list[dict]
    ) -> list[dict]:
        items: list[dict] = []
        for message in messages:
            role = message.get("role")
            tool_calls = message.get("tool_calls")
            content = message.get("content")

            if role == "assistant" and tool_calls:
                converted = self._convert_content_to_output(content)
                if converted:
                    items.append({"role": "assistant", "content": converted})
                for tool_call in tool_calls:
                    if hasattr(tool_call, "model_dump"):
                        tool_call = tool_call.model_dump()
                    if isinstance(tool_call, str):
                        try:
                            tool_call = json.loads(tool_call)
                        except Exception:
                            tool_call = {}
                    func = (
                        tool_call.get("function", {})
                        if isinstance(tool_call, dict)
                        else {}
                    )
                    items.append(
                        {
                            "type": "function_call",
                            "call_id": tool_call.get("id")
                            or tool_call.get("call_id")
                            or "",
                            "name": func.get("name", ""),
                            "arguments": func.get("arguments") or "",
                        }
                    )
                continue

            if role == "tool":
                call_id = message.get("tool_call_id") or ""
                output_text = self._content_to_plain_text(content)
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": output_text,
                    }
                )
                continue

            if role == "assistant":
                converted = self._convert_content_to_output(content)
                if converted:
                    items.append({"role": "assistant", "content": converted})
                continue

            items.append(
                {"role": role, "content": self._convert_content_to_input(content)}
            )
        return items

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

        if tool_calls_result:
            if isinstance(tool_calls_result, ToolCallsResult):
                context_query.extend(tool_calls_result.to_openai_messages())
            else:
                for tcr in tool_calls_result:
                    context_query.extend(tcr.to_openai_messages())

        model = model or self.get_model()

        input_items = self._convert_openai_messages_to_responses_input(context_query)
        payloads = {"input": input_items, "model": model}
        payloads.update(kwargs)
        return payloads, context_query

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
        payloads["input"] = self._convert_openai_messages_to_responses_input(
            new_contexts
        )
        return (
            False,
            chosen_key,
            available_api_keys,
            payloads,
            new_contexts,
            func_tool,
            image_fallback_used,
        )

    def _extract_usage(self, usage: Any) -> TokenUsage:
        input_tokens = 0
        output_tokens = 0
        cached = 0
        if isinstance(usage, dict):
            input_tokens = int(usage.get("input_tokens", 0) or 0)
            output_tokens = int(usage.get("output_tokens", 0) or 0)
            details = usage.get("input_tokens_details") or {}
            cached = int(details.get("cached_tokens", 0) or 0)
        else:
            input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
            details = getattr(usage, "input_tokens_details", None)
            if details is not None:
                cached = int(getattr(details, "cached_tokens", 0) or 0)
        return TokenUsage(
            input_other=input_tokens - cached,
            input_cached=cached,
            output=output_tokens,
        )

    def _extract_output_text_from_items(self, output_items: list) -> str:
        texts: list[str] = []
        for item in output_items:
            item_type = getattr(item, "type", None)
            if isinstance(item, dict):
                item_type = item.get("type")
            if item_type != "message":
                continue
            content = getattr(item, "content", None)
            if isinstance(item, dict):
                content = item.get("content")
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") in {"output_text", "text", "input_text"}:
                            texts.append(str(part.get("text", "")))
        return "".join(texts)

    async def _parse_openai_response(
        self, response: Any, tools: ToolSet | None
    ) -> LLMResponse:
        llm_response = LLMResponse("assistant")
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, list):
            output_text = "".join(str(x) for x in output_text)
        if isinstance(output_text, str) and output_text.strip():
            llm_response.result_chain = MessageChain().message(
                self._normalize_content(output_text)
            )

        output_items = getattr(response, "output", None) or []
        if not llm_response.result_chain:
            extracted = self._extract_output_text_from_items(output_items)
            if extracted:
                llm_response.result_chain = MessageChain().message(
                    self._normalize_content(extracted)
                )

        if output_items:
            for item in output_items:
                item_type = getattr(item, "type", None)
                if isinstance(item, dict):
                    item_type = item.get("type")
                if item_type == "function_call":
                    name = getattr(item, "name", None)
                    arguments = getattr(item, "arguments", None)
                    call_id = getattr(item, "call_id", None)
                    if isinstance(item, dict):
                        name = item.get("name")
                        arguments = item.get("arguments")
                        call_id = item.get("call_id") or item.get("id")
                    if isinstance(arguments, str):
                        try:
                            args = json.loads(arguments)
                        except Exception:
                            args = {}
                    elif isinstance(arguments, dict):
                        args = arguments
                    else:
                        args = {}
                    if name:
                        llm_response.tools_call_name.append(name)
                        llm_response.tools_call_args.append(args)
                        llm_response.tools_call_ids.append(call_id or "")

        if llm_response.tools_call_name:
            llm_response.role = "tool"

        if getattr(response, "usage", None):
            llm_response.usage = self._extract_usage(response.usage)

        llm_response.raw_completion = response
        llm_response.id = getattr(response, "id", None)

        if llm_response.completion_text is None and not llm_response.tools_call_args:
            logger.error(f"API 返回的 response 无法解析：{response}。")
            raise Exception(f"API 返回的 response 无法解析：{response}。")

        return llm_response

    async def _query(self, payloads: dict, tools: ToolSet | None) -> LLMResponse:
        if tools:
            tool_list = tools.openai_responses_schema()
            if tool_list:
                payloads["tools"] = tool_list

        extra_body = self._prepare_request_payload(payloads)

        response = await self.client.responses.create(
            **payloads,
            stream=False,
            extra_body=extra_body,
        )

        logger.debug(f"response: {response}")
        llm_response = await self._parse_openai_response(response, tools)
        return llm_response

    async def _query_stream(
        self,
        payloads: dict,
        tools: ToolSet | None,
    ) -> AsyncGenerator[LLMResponse, None]:
        if tools:
            tool_list = tools.openai_responses_schema()
            if tool_list:
                payloads["tools"] = tool_list

        extra_body = self._prepare_request_payload(payloads)

        stream = await self.client.responses.create(
            **payloads,
            stream=True,
            extra_body=extra_body,
        )

        def _get_event_attr(event: Any, key: str, default: Any = None) -> Any:
            if hasattr(event, key):
                return getattr(event, key)
            if isinstance(event, dict):
                return event.get(key, default)
            if hasattr(event, "model_dump"):
                return event.model_dump().get(key, default)
            return default

        full_text = ""
        reasoning_text = ""
        had_text_delta = False
        tool_call_args: dict[str, str] = {}
        tool_call_names: dict[str, str] = {}
        tool_call_order: list[str] = []
        last_response = None

        async for event in stream:
            event_type = _get_event_attr(event, "type")

            if event_type == "response.output_text.delta":
                delta = _get_event_attr(event, "delta", "")
                if delta:
                    had_text_delta = True
                    full_text += str(delta)
                    yield LLMResponse(
                        "assistant",
                        is_chunk=True,
                        result_chain=MessageChain(chain=[Comp.Plain(str(delta))]),
                    )
                continue

            if event_type == "response.reasoning_text.delta":
                delta = _get_event_attr(event, "delta", "")
                if delta:
                    reasoning_text += str(delta)
                    yield LLMResponse(
                        "assistant",
                        is_chunk=True,
                        reasoning_content=str(delta),
                    )
                continue

            if event_type == "response.content_part.done":
                part = _get_event_attr(event, "part")
                if isinstance(part, dict):
                    if (
                        part.get("type") in {"output_text", "text"}
                        and not had_text_delta
                    ):
                        text = part.get("text", "")
                        if text:
                            full_text += str(text)
                continue

            if event_type == "response.function_call_arguments.delta":
                call_id = _get_event_attr(event, "item_id") or _get_event_attr(
                    event, "call_id", ""
                )
                delta = _get_event_attr(event, "delta", "")
                name = _get_event_attr(event, "name", "")
                if call_id:
                    if call_id not in tool_call_order:
                        tool_call_order.append(call_id)
                    if name:
                        tool_call_names[call_id] = str(name)
                    if delta:
                        tool_call_args[call_id] = tool_call_args.get(call_id, "") + str(
                            delta
                        )
                continue

            if event_type == "response.function_call_arguments.done":
                call_id = _get_event_attr(event, "item_id") or _get_event_attr(
                    event, "call_id", ""
                )
                args = _get_event_attr(event, "arguments", "")
                name = _get_event_attr(event, "name", "")
                if call_id:
                    if call_id not in tool_call_order:
                        tool_call_order.append(call_id)
                    if name:
                        tool_call_names[call_id] = str(name)
                    if args is not None:
                        tool_call_args[call_id] = str(args)
                continue

            # Some events include a response object
            response_obj = _get_event_attr(event, "response")
            if response_obj is not None:
                last_response = response_obj

        if last_response is not None:
            yield await self._parse_openai_response(last_response, tools)
            return

        llm_response = LLMResponse("assistant")
        if full_text:
            llm_response.result_chain = MessageChain().message(full_text)
        if reasoning_text:
            llm_response.reasoning_content = reasoning_text

        for call_id in tool_call_order:
            name = tool_call_names.get(call_id, "")
            args_str = tool_call_args.get(call_id, "")
            if not name:
                continue
            try:
                args = json.loads(args_str) if args_str else {}
            except Exception:
                args = {}
            llm_response.tools_call_name.append(name)
            llm_response.tools_call_args.append(args)
            llm_response.tools_call_ids.append(call_id)

        if llm_response.tools_call_name:
            llm_response.role = "tool"

        if llm_response.completion_text is None and not llm_response.tools_call_args:
            logger.error("API 返回的 response 无法解析（stream 模式）。")
            raise Exception("API 返回的 response 无法解析（stream 模式）。")

        yield llm_response

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
        if "429" in str(e):
            logger.warning(
                f"API 调用过于频繁，尝试使用其他 Key 重试。当前 Key: {chosen_key[:12]}",
            )
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
            payloads["input"] = self._convert_openai_messages_to_responses_input(
                context_query
            )
            return (
                False,
                chosen_key,
                available_api_keys,
                payloads,
                context_query,
                func_tool,
                image_fallback_used,
            )
        if "The model is not a VLM" in str(e):
            if image_fallback_used or not self._context_contains_image(context_query):
                raise e
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

        if is_connection_error(e):
            proxy = self.provider_config.get("proxy", "")
            log_connection_failure("OpenAI", e, proxy)

        raise e

    def _prepare_request_payload(self, payloads: dict) -> dict:
        payloads.pop("abort_signal", None)

        if payloads.get("store") is not False:
            logger.warning(
                "OpenAI Responses API requires store=false; overriding request store.",
            )
        payloads["store"] = False

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
        if extra_body.get("store") is not False:
            if "store" in extra_body:
                logger.warning(
                    "OpenAI Responses API requires store=false; overriding extra_body store.",
                )
            extra_body.pop("store", None)
        return extra_body

    async def _retry_request(
        self,
        payloads: dict,
        context_query: list,
        func_tool: ToolSet | None,
        *,
        stream: bool,
    ) -> AsyncGenerator[LLMResponse, None]:
        max_retries = 10
        available_api_keys = self.api_keys.copy()
        chosen_key = random.choice(available_api_keys)
        image_fallback_used = False

        last_exception = None
        retry_cnt = 0
        for retry_cnt in range(max_retries):
            try:
                self.client.api_key = chosen_key
                if stream:
                    async for response in self._query_stream(payloads, func_tool):
                        yield response
                else:
                    yield await self._query(payloads, func_tool)
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
        async for response in self._retry_request(
            payloads, context_query, func_tool, stream=False
        ):
            return response
        raise Exception("未知错误")

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
        payloads, context_query = await self._prepare_chat_payload(
            prompt,
            image_urls,
            contexts,
            system_prompt,
            tool_calls_result,
            model=model,
            **kwargs,
        )
        async for response in self._retry_request(
            payloads, context_query, func_tool, stream=True
        ):
            yield response

    async def _remove_image_from_context(self, contexts: list):
        new_contexts = []

        for context in contexts:
            new_context = dict(context)
            if "content" in new_context and isinstance(new_context["content"], list):
                new_content = []
                for item in new_context["content"]:
                    if isinstance(item, dict) and "image_url" in item:
                        continue
                    new_content.append(item)
                if not new_content:
                    new_content = [{"type": "text", "text": "[图片]"}]
                new_context["content"] = new_content
            new_contexts.append(new_context)
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

        content_blocks = []

        if text:
            content_blocks.append({"type": "text", "text": text})
        elif image_urls:
            content_blocks.append({"type": "text", "text": "[图片]"})
        elif extra_user_content_parts:
            content_blocks.append({"type": "text", "text": " "})

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

        if image_urls:
            for image_url in image_urls:
                image_part = await resolve_image_part(image_url)
                if image_part:
                    content_blocks.append(image_part)

        if (
            text
            and not extra_user_content_parts
            and not image_urls
            and len(content_blocks) == 1
            and content_blocks[0]["type"] == "text"
        ):
            return {"role": "user", "content": content_blocks[0]["text"]}

        return {"role": "user", "content": content_blocks}

    async def encode_image_bs64(self, image_url: str) -> str:
        if image_url.startswith("base64://"):
            return image_url.replace("base64://", "data:image/jpeg;base64,")
        with open(image_url, "rb") as f:
            image_bs64 = base64.b64encode(f.read()).decode("utf-8")
            return "data:image/jpeg;base64," + image_bs64

    async def terminate(self):
        if self.client:
            await self.client.close()
