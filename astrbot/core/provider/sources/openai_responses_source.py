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
    def _get_field(obj: Any, name: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)

    @staticmethod
    def _arguments_to_json_string(arguments: Any) -> str:
        if arguments is None:
            return ""
        if isinstance(arguments, str):
            return arguments
        try:
            return json.dumps(arguments, ensure_ascii=False)
        except TypeError:
            return str(arguments)

    @classmethod
    def _message_content_to_response_content(cls, content: Any, role: str) -> Any:
        converted, _ = cls._message_content_to_response_content_and_reasoning_items(
            content,
            role,
        )
        return converted

    @staticmethod
    def _to_plain_data(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: ProviderOpenAIResponses._to_plain_data(item)
                for key, item in value.items()
                if item is not None
            }
        if isinstance(value, (list, tuple)):
            return [ProviderOpenAIResponses._to_plain_data(item) for item in value]
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            return model_dump(mode="json", exclude_none=True)
        return value

    @classmethod
    def _normalize_reasoning_item(cls, item: Any) -> dict[str, Any] | None:
        if cls._get_field(item, "type") != "reasoning":
            return None
        data = cls._to_plain_data(item)
        if not isinstance(data, dict) or not data.get("id"):
            return None
        data["type"] = "reasoning"
        if "summary" not in data:
            data["summary"] = []
        return data

    @classmethod
    def _think_part_to_response_reasoning_items(
        cls,
        part: dict[str, Any],
    ) -> list[dict[str, Any]]:
        encrypted = part.get("encrypted")
        if not isinstance(encrypted, str) or not encrypted.strip():
            return []
        try:
            stored = json.loads(encrypted)
        except json.JSONDecodeError:
            return []

        raw_items = stored if isinstance(stored, list) else [stored]
        reasoning_items: list[dict[str, Any]] = []
        for raw_item in raw_items:
            reasoning_item = cls._normalize_reasoning_item(raw_item)
            if reasoning_item is not None:
                reasoning_items.append(reasoning_item)
        return reasoning_items

    @classmethod
    def _message_content_to_response_content_and_reasoning_items(
        cls,
        content: Any,
        role: str,
    ) -> tuple[Any, list[dict[str, Any]]]:
        if isinstance(content, str) or content is None:
            return content or "", []
        if not isinstance(content, list):
            return content, []

        converted: list[dict[str, Any]] = []
        reasoning_items: list[dict[str, Any]] = []
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
            elif part_type in {"audio_url", "input_audio"}:
                converted.append({"type": text_type, "text": "[Audio]"})
            elif part_type == "think":
                if role == "assistant":
                    reasoning_items.extend(
                        cls._think_part_to_response_reasoning_items(part),
                    )
                continue
            else:
                converted.append(part)
        return converted, reasoning_items

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
        function = ProviderOpenAIResponses._get_field(tool_call, "function", {})
        call_id = (
            ProviderOpenAIResponses._get_field(tool_call, "id")
            or ProviderOpenAIResponses._get_field(tool_call, "call_id")
            or ""
        )
        name = ProviderOpenAIResponses._get_field(function, "name", "")
        arguments = ProviderOpenAIResponses._get_field(function, "arguments", "")

        return {
            "type": "function_call",
            "call_id": call_id,
            "name": name or "",
            "arguments": ProviderOpenAIResponses._arguments_to_json_string(arguments),
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

        content, reasoning_items = (
            cls._message_content_to_response_content_and_reasoning_items(
                message.get("content", ""),
                role,
            )
        )
        item = {
            "role": role,
            "content": content,
        }
        if role != "assistant":
            return [item]

        items = list(reasoning_items)
        if not cls._is_empty_response_content(content):
            items.append(item)
        if not message.get("tool_calls"):
            return items

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
            value = ProviderOpenAIResponses._get_field(usage, name, 0)
            return value if isinstance(value, int) else 0

        input_tokens = _get("input_tokens")
        output_tokens = _get("output_tokens")
        cached = 0
        details = ProviderOpenAIResponses._get_field(usage, "input_tokens_details")
        if details is not None:
            cached = ProviderOpenAIResponses._get_field(details, "cached_tokens", 0)
            cached = cached or 0
        cached = cached if isinstance(cached, int) else 0
        return TokenUsage(
            input_other=max(input_tokens - cached, 0),
            input_cached=cached,
            output=output_tokens,
        )

    @staticmethod
    def _extract_response_output_text(response: Any) -> str:
        output_text = ProviderOpenAIResponses._get_field(response, "output_text")
        if isinstance(output_text, str):
            return output_text.strip()

        output = ProviderOpenAIResponses._get_field(response, "output", [])
        parts: list[str] = []
        if isinstance(output, list):
            for item in output:
                content = ProviderOpenAIResponses._get_field(item, "content", [])
                if not isinstance(content, list):
                    continue
                for part in content:
                    part_type = ProviderOpenAIResponses._get_field(part, "type")
                    if part_type not in {"output_text", "text"}:
                        continue
                    text = ProviderOpenAIResponses._get_field(part, "text")
                    if isinstance(text, str):
                        parts.append(text)
        return "".join(parts).strip()

    @classmethod
    def _extract_response_reasoning(
        cls,
        response: Any,
    ) -> tuple[str | None, str | None]:
        reasoning_items: list[dict[str, Any]] = []
        text_parts: list[str] = []
        for item in cls._iter_response_output_items(response):
            reasoning_item = cls._normalize_reasoning_item(item)
            if reasoning_item is None:
                continue
            reasoning_items.append(reasoning_item)

            item_text_parts: list[str] = []
            content = reasoning_item.get("content")
            if isinstance(content, list):
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    if part.get("type") != "reasoning_text":
                        continue
                    text = part.get("text")
                    if isinstance(text, str) and text:
                        item_text_parts.append(text)

            if not item_text_parts:
                summary = reasoning_item.get("summary")
                if isinstance(summary, list):
                    for part in summary:
                        if not isinstance(part, dict):
                            continue
                        if part.get("type") != "summary_text":
                            continue
                        text = part.get("text")
                        if isinstance(text, str) and text:
                            item_text_parts.append(text)

            text_parts.extend(item_text_parts)

        if not reasoning_items:
            return None, None

        reasoning_text = "\n".join(text_parts).strip() or None
        signature_payload: dict[str, Any] | list[dict[str, Any]]
        if len(reasoning_items) == 1:
            signature_payload = reasoning_items[0]
        else:
            signature_payload = reasoning_items
        return reasoning_text, json.dumps(signature_payload, ensure_ascii=False)

    @staticmethod
    def _iter_response_output_items(response: Any) -> list[Any]:
        output = ProviderOpenAIResponses._get_field(response, "output", [])
        return output if isinstance(output, list) else []

    @classmethod
    def _iter_function_calls(cls, response: Any) -> list[dict[str, Any]]:
        calls: list[dict[str, Any]] = []
        for item in cls._iter_response_output_items(response):
            if cls._get_field(item, "type") != "function_call":
                continue
            calls.append(
                {
                    "name": cls._get_field(item, "name"),
                    "arguments": cls._get_field(item, "arguments"),
                    "call_id": cls._get_field(item, "call_id"),
                }
            )
        return calls

    @staticmethod
    def _parse_function_call_arguments(arguments: Any) -> dict:
        if isinstance(arguments, str):
            try:
                parsed_args = json.loads(arguments)
            except json.JSONDecodeError:
                return {}
            return parsed_args if isinstance(parsed_args, dict) else {}
        if isinstance(arguments, dict):
            return arguments
        return {}

    async def _parse_responses_completion(
        self,
        response: Any,
        tools: ToolSet | None,
    ) -> LLMResponse:
        llm_response = LLMResponse("assistant")
        response_id = self._get_field(response, "id")

        if tools is not None:
            args_ls: list[dict] = []
            func_name_ls: list[str] = []
            tool_call_ids: list[str] = []
            for call in self._iter_function_calls(response):
                name = call["name"]
                if not name:
                    continue
                args_ls.append(self._parse_function_call_arguments(call["arguments"]))
                func_name_ls.append(name)
                tool_call_ids.append(call["call_id"] or response_id or "")
            if args_ls:
                llm_response.role = "tool"
                llm_response.tools_call_args = args_ls
                llm_response.tools_call_name = func_name_ls
                llm_response.tools_call_ids = tool_call_ids

        completion_text = self._extract_response_output_text(response)
        if completion_text:
            llm_response.result_chain = MessageChain().message(completion_text)
        reasoning_content, reasoning_signature = self._extract_response_reasoning(
            response,
        )
        if reasoning_content is not None:
            llm_response.reasoning_content = reasoning_content
        if reasoning_signature is not None:
            llm_response.reasoning_signature = reasoning_signature
        llm_response.raw_completion = response
        llm_response.id = response_id
        usage = self._get_field(response, "usage")
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

    def _build_responses_request(
        self,
        payloads: dict,
        tools: ToolSet | None,
    ) -> tuple[dict, dict]:
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
        return self._split_responses_extra_body(response_payload)

    async def _query(
        self,
        payloads: dict,
        tools: ToolSet | None,
        *,
        request_max_retries: int | None = None,
    ) -> LLMResponse:
        request_payload, extra_body = self._build_responses_request(payloads, tools)
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
        return ProviderOpenAIResponses._get_field(event, name, default)

    @classmethod
    def _stream_function_call_key(
        cls,
        event: Any,
        function_calls: dict[str, dict[str, Any]],
    ) -> str:
        item = cls._event_value(event, "item")
        for value in (
            cls._event_value(event, "output_index"),
            cls._event_value(event, "item_id"),
            cls._get_field(item, "id"),
            cls._get_field(item, "call_id"),
        ):
            if value is not None:
                return str(value)
        return str(len(function_calls))

    @classmethod
    def _merge_stream_function_call_event(
        cls,
        event: Any,
        function_calls: dict[str, dict[str, Any]],
    ) -> None:
        event_type = cls._event_value(event, "type", "")
        item = cls._event_value(event, "item")
        call_key = cls._stream_function_call_key(event, function_calls)

        if event_type in {"response.output_item.added", "response.output_item.done"}:
            if cls._get_field(item, "type") != "function_call":
                return
            call = function_calls.setdefault(call_key, {})
            call["name"] = cls._get_field(item, "name", call.get("name"))
            call["call_id"] = cls._get_field(item, "call_id", call.get("call_id"))
            arguments = cls._get_field(item, "arguments")
            if arguments is not None:
                call["arguments"] = arguments
            return

        if event_type == "response.function_call_arguments.delta":
            delta = cls._event_value(event, "delta", "")
            if delta:
                call = function_calls.setdefault(call_key, {})
                call["arguments"] = f"{call.get('arguments', '')}{delta}"
            return

        if event_type == "response.function_call_arguments.done":
            arguments = cls._event_value(event, "arguments", "")
            function_calls.setdefault(call_key, {})["arguments"] = arguments

    async def _stream_function_calls_to_response(
        self,
        function_calls: dict[str, dict[str, Any]],
        tools: ToolSet | None,
    ) -> LLMResponse:
        output = []
        for call in function_calls.values():
            if not call.get("name"):
                continue
            output.append(
                {
                    "type": "function_call",
                    "name": call.get("name", ""),
                    "call_id": call.get("call_id", ""),
                    "arguments": call.get("arguments", ""),
                }
            )
        return await self._parse_responses_completion({"output": output}, tools)

    async def _query_stream(
        self,
        payloads: dict,
        tools: ToolSet | None,
        *,
        request_max_retries: int | None = None,
    ) -> AsyncGenerator[LLMResponse, None]:
        request_payload, extra_body = self._build_responses_request(payloads, tools)
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
        reasoning_text = ""
        final_response = None
        function_calls: dict[str, dict[str, Any]] = {}
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
            elif event_type == "response.reasoning_text.delta":
                delta = self._event_value(event, "delta", "")
                if not delta:
                    continue
                reasoning_text += str(delta)
                yield LLMResponse(
                    "assistant",
                    reasoning_content=str(delta),
                    is_chunk=True,
                )
            elif event_type == "response.reasoning_text.done":
                text = self._event_value(event, "text", "")
                if text:
                    reasoning_text = str(text)
            elif event_type == "response.completed":
                final_response = self._event_value(event, "response")
            else:
                self._merge_stream_function_call_event(event, function_calls)

        if final_response is not None:
            llm_response = await self._parse_responses_completion(final_response, tools)
            if not llm_response.completion_text and output_text:
                llm_response.result_chain = MessageChain().message(output_text)
        elif function_calls:
            llm_response = await self._stream_function_calls_to_response(
                function_calls,
                tools,
            )
        else:
            llm_response = LLMResponse(
                "assistant",
                result_chain=MessageChain().message(output_text),
            )
        if reasoning_text and not llm_response.reasoning_content:
            llm_response.reasoning_content = reasoning_text
        yield llm_response
