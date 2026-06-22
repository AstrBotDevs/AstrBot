import inspect
import json
from collections.abc import AsyncGenerator
from typing import Any

import astrbot.core.message.components as Comp
from astrbot.core.agent.tool import ToolSet
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import LLMResponse, TokenUsage

from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial
from .request_retry import retry_provider_request


@register_provider_adapter(
    "openai_responses",
    "OpenAI Responses API 提供商适配器",
)
class ProviderOpenAIResponses(ProviderOpenAIOfficial):
    """OpenAI-compatible provider that calls the Responses API."""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.default_params = inspect.signature(
            self.client.responses.create,
        ).parameters.keys()

    @staticmethod
    def _message_content_to_response_content(content: Any, role: str) -> Any:
        if isinstance(content, str) or content is None:
            return content or ""
        if not isinstance(content, list):
            return content

        converted: list[dict[str, Any]] = []
        text_type = "output_text" if role == "assistant" else "input_text"
        for part in content:
            if not isinstance(part, dict):
                converted.append({"type": text_type, "text": str(part)})
                continue
            part_type = part.get("type")
            if part_type == "text":
                converted.append({"type": text_type, "text": part.get("text", "")})
            elif part_type == "image_url":
                image_url = part.get("image_url", {})
                if isinstance(image_url, dict):
                    url = image_url.get("url")
                    detail = image_url.get("detail")
                else:
                    url = image_url
                    detail = None
                image_part = {"type": "input_image", "image_url": url}
                if detail:
                    image_part["detail"] = detail
                converted.append(image_part)
            elif part_type == "input_audio":
                converted.append(part)
            elif part_type == "think":
                continue
            else:
                converted.append(part)
        return converted

    @staticmethod
    def _is_empty_response_content(content: Any) -> bool:
        if content is None:
            return True
        if isinstance(content, str):
            return not content
        if isinstance(content, list):
            return not content
        return False

    @staticmethod
    def _chat_tool_call_to_response_function_call(tool_call: Any) -> dict:
        if isinstance(tool_call, dict):
            function = tool_call.get("function", {})
            call_id = tool_call.get("id") or tool_call.get("call_id") or ""
        else:
            function = getattr(tool_call, "function", {})
            call_id = (
                getattr(tool_call, "id", None)
                or getattr(tool_call, "call_id", None)
                or ""
            )

        if isinstance(function, dict):
            name = function.get("name", "")
            arguments = function.get("arguments", "")
        else:
            name = getattr(function, "name", "")
            arguments = getattr(function, "arguments", "")

        return {
            "type": "function_call",
            "call_id": call_id,
            "name": name or "",
            "arguments": arguments or "",
            "status": "completed",
        }

    @classmethod
    def _message_to_response_input_items(cls, message: dict) -> list[dict]:
        role = message.get("role", "user")
        if role == "tool":
            return [
                {
                    "type": "function_call_output",
                    "call_id": message.get("tool_call_id", ""),
                    "output": message.get("content", ""),
                },
            ]

        content = cls._message_content_to_response_content(
            message.get("content", ""),
            role,
        )
        item = {
            "role": role,
            "content": content,
        }
        if role != "assistant" or not message.get("tool_calls"):
            return [item]

        items = [] if cls._is_empty_response_content(content) else [item]
        items.extend(
            cls._chat_tool_call_to_response_function_call(tool_call)
            for tool_call in message["tool_calls"]
        )
        return items

    @classmethod
    def _messages_to_response_input(cls, messages: list[dict]) -> list[dict]:
        items: list[dict] = []
        for message in messages:
            items.extend(cls._message_to_response_input_items(message))
        return items

    @classmethod
    def _chat_payload_to_responses_payload(cls, payloads: dict) -> dict:
        response_payload = dict(payloads)
        messages = response_payload.pop("messages", [])
        if isinstance(messages, list):
            response_payload["input"] = cls._messages_to_response_input(messages)
        return response_payload

    @staticmethod
    def _responses_function_tools(tools: ToolSet | None) -> list[dict]:
        if not tools:
            return []
        converted: list[dict] = []
        for tool in tools.openai_schema():
            if tool.get("type") != "function":
                converted.append(tool)
                continue
            function = tool.get("function", {})
            item = {
                "type": "function",
                "name": function.get("name", ""),
                "strict": False,
            }
            if function.get("description"):
                item["description"] = function["description"]
            if "parameters" in function:
                item["parameters"] = function["parameters"]
            converted.append(item)
        return converted

    @staticmethod
    def _response_usage_to_token_usage(usage: Any) -> TokenUsage | None:
        if not usage:
            return None

        def _get(name: str) -> int:
            if isinstance(usage, dict):
                value = usage.get(name, 0)
            else:
                value = getattr(usage, name, 0)
            return value if isinstance(value, int) else 0

        input_tokens = _get("input_tokens")
        output_tokens = _get("output_tokens")
        cached = 0
        details = (
            usage.get("input_tokens_details")
            if isinstance(usage, dict)
            else getattr(usage, "input_tokens_details", None)
        )
        if isinstance(details, dict):
            cached = details.get("cached_tokens", 0) or 0
        elif details is not None:
            cached = getattr(details, "cached_tokens", 0) or 0
        cached = cached if isinstance(cached, int) else 0
        return TokenUsage(
            input_other=max(input_tokens - cached, 0),
            input_cached=cached,
            output=output_tokens,
        )

    @staticmethod
    def _extract_response_output_text(response: Any) -> str:
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str):
            return output_text.strip()
        if isinstance(response, dict) and isinstance(response.get("output_text"), str):
            return response["output_text"].strip()

        output = (
            response.get("output", [])
            if isinstance(response, dict)
            else getattr(response, "output", [])
        )
        parts: list[str] = []
        if isinstance(output, list):
            for item in output:
                content = (
                    item.get("content", [])
                    if isinstance(item, dict)
                    else getattr(item, "content", [])
                )
                if not isinstance(content, list):
                    continue
                for part in content:
                    part_type = (
                        part.get("type")
                        if isinstance(part, dict)
                        else getattr(part, "type", None)
                    )
                    if part_type not in {"output_text", "text"}:
                        continue
                    text = (
                        part.get("text")
                        if isinstance(part, dict)
                        else getattr(part, "text", None)
                    )
                    if isinstance(text, str):
                        parts.append(text)
        return "".join(parts).strip()

    @staticmethod
    def _iter_response_output_items(response: Any) -> list[Any]:
        if isinstance(response, dict):
            output = response.get("output", [])
        else:
            output = getattr(response, "output", [])
        return output if isinstance(output, list) else []

    async def _parse_responses_completion(
        self,
        response: Any,
        tools: ToolSet | None,
    ) -> LLMResponse:
        llm_response = LLMResponse("assistant")
        response_id = (
            response.get("id")
            if isinstance(response, dict)
            else getattr(response, "id", None)
        )

        if tools is not None:
            args_ls: list[dict] = []
            func_name_ls: list[str] = []
            tool_call_ids: list[str] = []
            for item in self._iter_response_output_items(response):
                item_type = (
                    item.get("type")
                    if isinstance(item, dict)
                    else getattr(item, "type", None)
                )
                if item_type != "function_call":
                    continue
                name = (
                    item.get("name")
                    if isinstance(item, dict)
                    else getattr(item, "name", None)
                )
                arguments = (
                    item.get("arguments")
                    if isinstance(item, dict)
                    else getattr(item, "arguments", None)
                )
                call_id = (
                    item.get("call_id")
                    if isinstance(item, dict)
                    else getattr(item, "call_id", None)
                )
                if not name:
                    continue
                if isinstance(arguments, str):
                    try:
                        parsed_args = json.loads(arguments)
                    except json.JSONDecodeError:
                        parsed_args = {}
                elif isinstance(arguments, dict):
                    parsed_args = arguments
                else:
                    parsed_args = {}
                args_ls.append(parsed_args)
                func_name_ls.append(name)
                tool_call_ids.append(call_id or response_id or "")
            if args_ls:
                llm_response.role = "tool"
                llm_response.tools_call_args = args_ls
                llm_response.tools_call_name = func_name_ls
                llm_response.tools_call_ids = tool_call_ids

        completion_text = self._extract_response_output_text(response)
        if completion_text:
            llm_response.result_chain = MessageChain().message(completion_text)
        llm_response.raw_completion = response
        llm_response.id = response_id
        usage = (
            response.get("usage")
            if isinstance(response, dict)
            else getattr(response, "usage", None)
        )
        llm_response.usage = self._response_usage_to_token_usage(usage)
        return llm_response

    def _split_responses_extra_body(self, payloads: dict) -> tuple[dict, dict]:
        request_payload = dict(payloads)
        extra_body = {}
        custom_extra_body = self.provider_config.get("custom_extra_body", {})
        if isinstance(custom_extra_body, dict):
            extra_body.update(custom_extra_body)

        for key in list(request_payload):
            if key not in self.default_params:
                extra_body[key] = request_payload.pop(key)
        self._apply_provider_specific_extra_body_overrides(extra_body)
        return request_payload, extra_body

    async def _query(
        self,
        payloads: dict,
        tools: ToolSet | None,
        *,
        request_max_retries: int | None = None,
    ) -> LLMResponse:
        self._sanitize_assistant_messages(payloads)
        response_payload = self._chat_payload_to_responses_payload(payloads)
        response_tools = self._responses_function_tools(tools)
        if response_tools:
            response_payload["tools"] = response_tools
            if tools and not tools.empty():
                response_payload["tool_choice"] = response_payload.get(
                    "tool_choice", "auto"
                )
        else:
            response_payload.pop("tool_choice", None)

        request_payload, extra_body = self._split_responses_extra_body(response_payload)
        response = await retry_provider_request(
            "OpenAI",
            lambda: self.client.responses.create(
                **request_payload,
                stream=False,
                extra_body=extra_body,
            ),
            max_attempts=request_max_retries,
        )
        return await self._parse_responses_completion(response, tools)

    @staticmethod
    def _event_value(event: Any, name: str, default: Any = None) -> Any:
        if isinstance(event, dict):
            return event.get(name, default)
        return getattr(event, name, default)

    async def _query_stream(
        self,
        payloads: dict,
        tools: ToolSet | None,
        *,
        request_max_retries: int | None = None,
    ) -> AsyncGenerator[LLMResponse, None]:
        self._sanitize_assistant_messages(payloads)
        response_payload = self._chat_payload_to_responses_payload(payloads)
        response_tools = self._responses_function_tools(tools)
        if response_tools:
            response_payload["tools"] = response_tools
            if tools and not tools.empty():
                response_payload["tool_choice"] = response_payload.get(
                    "tool_choice", "auto"
                )
        else:
            response_payload.pop("tool_choice", None)

        request_payload, extra_body = self._split_responses_extra_body(response_payload)
        stream = await retry_provider_request(
            "OpenAI",
            lambda: self.client.responses.create(
                **request_payload,
                stream=True,
                extra_body=extra_body,
            ),
            max_attempts=request_max_retries,
        )

        output_text = ""
        final_response = None
        async for event in stream:
            event_type = self._event_value(event, "type", "")
            if event_type == "response.output_text.delta":
                delta = self._event_value(event, "delta", "")
                if not delta:
                    continue
                output_text += str(delta)
                yield LLMResponse(
                    "assistant",
                    result_chain=MessageChain(chain=[Comp.Plain(str(delta))]),
                    is_chunk=True,
                )
            elif event_type == "response.output_text.done":
                text = self._event_value(event, "text", "")
                if text:
                    output_text = str(text)
            elif event_type == "response.completed":
                final_response = self._event_value(event, "response")

        if final_response is not None:
            llm_response = await self._parse_responses_completion(final_response, tools)
            if not llm_response.completion_text and output_text:
                llm_response.result_chain = MessageChain().message(output_text)
        else:
            llm_response = LLMResponse(
                "assistant",
                result_chain=MessageChain().message(output_text),
            )
        yield llm_response
